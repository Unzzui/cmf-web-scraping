"""Orquestación: baja los recursos de un banco/período y los carga a la BD."""

from src.banks import endpoints, ingest
from src.banks.api_client import NoDataError
from src.banks.taxonomy import classify_epoch, classify_unit

REPORTS_DEFAULT = ("balance", "resultado", "adecuacion", "perfil", "accionistas",
                   "integrantes")

_AGGREGATE_CODES = {"999"}


def sync_institutions(client, loader, year: int, month: int) -> int:
    payload = client.get(endpoints.instituciones_path(year, month))
    insts = ingest.parse_instituciones(payload)
    for inst in insts:
        loader.upsert_institution(
            inst, is_aggregate=inst.codigo_institucion in _AGGREGATE_CODES
        )
    return len(insts)


def _ingest_accounts(client, loader, cod, year, month, statement, path) -> str:
    payload = client.get(path)
    rows = ingest.parse_accounts(payload, statement)
    epoch = classify_epoch(year, month)
    unit = classify_unit(year, month)
    ok = 0
    for row in rows:
        account_id = loader.upsert_account(
            statement, row.codigo_cuenta, row.descripcion_cuenta, epoch
        )
        loader.upsert_financial_row(cod, account_id, year, month, row, epoch, unit)
        ok += 1
    loader.log_import(cod, statement, year, month, "completed", rows_total=len(rows),
                      rows_ok=ok)
    return "completed"


def _ingest_adecuacion(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.adecuacion_componentes_path(year, month, cod))
    ca = ingest.parse_adecuacion_componentes(payload)
    for attr, indicador in (("indice_irs", "irs"), ("indice_ire", "ire")):
        try:
            ind_payload = client.get(
                endpoints.adecuacion_indicador_path(year, month, cod, indicador)
            )
            setattr(ca, attr, ingest.parse_adecuacion_indicador(ind_payload))
        except NoDataError:
            pass
    loader.upsert_capital_adequacy(cod, year, month, ca)
    loader.log_import(cod, "adecuacion", year, month, "completed", rows_total=1, rows_ok=1)
    return "completed"


def _ingest_perfil(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.perfil_path(cod, year, month))
    profile = ingest.parse_perfil(payload)
    if profile is None:
        raise NoDataError("perfil vacío")
    loader.upsert_profile(cod, year, month, profile)
    loader.log_import(cod, "perfil", year, month, "completed", rows_total=1, rows_ok=1)
    return "completed"


def _ingest_accionistas(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.accionistas_path(cod, year, month))
    rows = ingest.parse_accionistas(payload)
    loader.replace_shareholders(cod, year, month, rows)
    loader.log_import(cod, "accionistas", year, month, "completed", rows_total=len(rows),
                      rows_ok=len(rows))
    return "completed"


def _ingest_integrantes(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.integrantes_path(cod, year, month))
    rows = ingest.parse_integrantes(payload)
    loader.replace_executives(cod, year, month, rows)
    loader.log_import(cod, "integrantes", year, month, "completed", rows_total=len(rows),
                      rows_ok=len(rows))
    return "completed"


def ingest_period(client, loader, cod: str, year: int, month: int,
                  reports=REPORTS_DEFAULT) -> dict[str, str]:
    dispatch = {
        "balance": lambda: _ingest_accounts(
            client, loader, cod, year, month, "balance",
            endpoints.balance_path(year, month, cod)),
        "resultado": lambda: _ingest_accounts(
            client, loader, cod, year, month, "resultado",
            endpoints.resultado_path(year, month, cod)),
        "adecuacion": lambda: _ingest_adecuacion(client, loader, cod, year, month),
        "perfil": lambda: _ingest_perfil(client, loader, cod, year, month),
        "accionistas": lambda: _ingest_accionistas(client, loader, cod, year, month),
        "integrantes": lambda: _ingest_integrantes(client, loader, cod, year, month),
    }
    result: dict[str, str] = {}
    for report in reports:
        try:
            result[report] = dispatch[report]()
        except NoDataError:
            loader.log_import(cod, report, year, month, "no_data")
            result[report] = "no_data"
        except Exception as exc:  # noqa: BLE001 - un report que falla no aborta los demás
            loader.log_import(cod, report, year, month, "failed", message=str(exc))
            result[report] = "failed"
    return result
