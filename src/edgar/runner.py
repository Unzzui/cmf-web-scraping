"""Orquestación: baja el companyfacts de una empresa, lo normaliza y lo carga."""

from dataclasses import dataclass

from src.edgar.api_client import NoDataError
from src.edgar.ingest import build_line_values, primary_tag_by_concept
from src.edgar.validate import (
    check_accounting_identity,
    check_accumulation,
    check_restatement_drift,
)

# XBRL es obligatorio por fases: los grandes emisores desde jun-2009, el resto desde
# jun-2011. Antes de eso no hay datos estructurados. Además los precios de la web llegan a
# 2016 (límite del plan de Marketstack), así que pelear por los años previos a 2011 no
# compra nada (spec §6.7).
DEFAULT_MIN_YEAR = 2011


@dataclass
class CompanyResult:
    cik: str
    ticker: str | None
    status: str  # completed | no_data | failed | skipped
    line_items: int = 0
    cells: int = 0
    years: tuple[int, int] | None = None
    identity_errors: int = 0
    accumulation_errors: int = 0
    drift_warnings: int = 0
    message: str | None = None


def ingest_company(
    client, loader, cik: str, min_year: int = DEFAULT_MIN_YEAR
) -> CompanyResult:
    """Ingesta una empresa de EEUU de punta a punta. No lanza: devuelve el estado."""
    company = loader.company_by_cik(cik)
    if company is None:
        return CompanyResult(cik, None, "skipped",
                             message=f"CIK {cik} no está en companies con market='US'")
    company_id, ticker = company

    try:
        payload = client.get_companyfacts(cik)
    except NoDataError as exc:
        loader.log_import(company_id, f"edgar:{cik}", 0, 0, "no_data", str(exc))
        return CompanyResult(cik, ticker, "no_data", message=str(exc))
    except Exception as exc:  # noqa: BLE001 - una empresa que falla no aborta el lote
        loader.log_import(company_id, f"edgar:{cik}", 0, 0, "failed", str(exc))
        return CompanyResult(cik, ticker, "failed", message=str(exc))

    try:
        values = build_line_values(payload, min_year=min_year)
        if not values:
            # Se reportan las taxonomías que SÍ trae en vez de adivinar el motivo: es lo
            # que distingue de un vistazo los dos casos reales. Un foreign private issuer
            # que presenta 20-F trae `ifrs-full` (§6.6). Una sociedad nueva que todavía no
            # publica estados —el holdco de una reorganización, por ejemplo— trae sólo
            # `dei` o `ffd` (tablas de fees de un S-8), y ahí el problema no es la
            # taxonomía sino que el CIK apunta a la entidad equivocada.
            taxonomias = sorted((payload.get("facts") or {}).keys())
            detalle = f"companyfacts sin conceptos us-gaap; taxonomías presentes: " \
                      f"{', '.join(taxonomias) or 'ninguna'}"
            loader.log_import(company_id, f"edgar:{cik}", 0, 0, "no_data", detalle)
            return CompanyResult(cik, ticker, "no_data", message=detalle)

        identity = check_accounting_identity(payload, min_year=min_year)
        accumulation = check_accumulation(values)
        drift = check_restatement_drift(values)

        tags = primary_tag_by_concept(values)
        ids_by_order = loader.upsert_line_items(company_id, values, tags)
        cells = loader.upsert_financial_data(company_id, values, ids_by_order)

        years = sorted({v.year for v in values})
        loader.log_import(company_id, f"edgar:{cik}", len(values), cells, "completed")
        return CompanyResult(
            cik, ticker, "completed",
            line_items=len(ids_by_order), cells=cells,
            years=(years[0], years[-1]) if years else None,
            identity_errors=len(identity),
            accumulation_errors=len(accumulation),
            drift_warnings=len(drift),
        )
    except Exception as exc:  # noqa: BLE001
        loader.log_import(company_id, f"edgar:{cik}", 0, 0, "failed", str(exc))
        return CompanyResult(cik, ticker, "failed", message=str(exc))
