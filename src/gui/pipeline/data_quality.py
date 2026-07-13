"""Gate de calidad previo a la subida a producción (Supabase/Vercel).

Motivación
----------
El pipeline puede producir un Excel/CSV que *parece* sano pero cuya serie está
congelada o cuyo estado de resultados quedó degenerado. Dos causas reales:

1. El emisor dejó de publicar estados consolidados y solo emite individuales
   (Bolsa de Comercio desde 2023Q1, Metrogas desde 2024Q4, …). Antes del
   fallback a ``*_I.xbrl`` esos períodos se descartaban en silencio y la serie
   quedaba detenida años atrás.
2. La plantilla de ``new_eeff_estructura.json`` declara para el RUT un rol de
   estado de resultados (310000) distinto del que la empresa realmente reporta
   (320000, "por naturaleza"). El filtro por RoleCode deja cero filas de ER y lo
   único que sobrevive es la fila "Ganancia (pérdida)" que inyecta la
   propagación: un ER con ganancias y sin ingresos.

Ambos casos pasaban el único chequeo previo a la escritura (``if not rows or not
periods``) y llegaban a producción. Peor: con el override automático, un CSV
empobrecido puede BORRAR histórico bueno.

Este módulo decide, sólo a partir del CSV a subir, si la empresa entra a
producción o queda en cuarentena.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import date

__all__ = [
    "QualityIssue",
    "QualityReport",
    "QualityThresholds",
    "check_company_csv",
]


# --- Umbrales -----------------------------------------------------------------

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class QualityThresholds:
    """Umbrales del gate. Configurables por entorno para no tocar código."""

    # Trimestres de atraso tolerados respecto del último período razonablemente
    # publicable. La CMF publica con rezago, así que primero se descuenta
    # `publication_lag_quarters` al trimestre actual y sobre eso se permite
    # `max_stale_quarters` de antigüedad adicional.
    publication_lag_quarters: int = 2
    max_stale_quarters: int = 4
    # Mínimo de filas CON al menos un valor numérico, por estado.
    min_income_statement_rows: int = 3
    min_balance_sheet_rows: int = 5
    # Mínimo de datapoints numéricos en todo el CSV.
    min_data_points: int = 50

    @classmethod
    def from_env(cls) -> "QualityThresholds":
        return cls(
            publication_lag_quarters=_env_int("CMF_QA_PUBLICATION_LAG_Q", 2),
            max_stale_quarters=_env_int("CMF_QA_MAX_STALE_Q", 4),
            min_income_statement_rows=_env_int("CMF_QA_MIN_IS_ROWS", 3),
            min_balance_sheet_rows=_env_int("CMF_QA_MIN_BS_ROWS", 5),
            min_data_points=_env_int("CMF_QA_MIN_DATAPOINTS", 50),
        )


# Etiquetas que representan la línea superior del estado de resultados. Un ER sin
# ninguna de estas, pero con filas de "Ganancia", es exactamente el caso roto.
# Se cubren ER por función (310000) y por naturaleza (320000), y emisores no-IFRS
# (bancos/seguros) que reportan ingresos por intereses o primas.
REVENUE_PATTERNS = (
    r"ingresos?\s+de\s+actividades\s+ordinarias",
    r"ingresos?\s+por\s+intereses",
    r"ingresos?\s+ordinarios",
    r"ingresos?\s+operacionales",
    r"ingresos?\s+por\s+ventas",
    r"primas?\s+(ganadas|netas|emitidas)",
    r"^ingresos$",
    r"^revenue",
)
_REVENUE_RE = re.compile("|".join(REVENUE_PATTERNS), re.IGNORECASE)


def looks_like_revenue(label: str) -> bool:
    """¿La etiqueta es una línea de ingresos (top line del ER)?"""
    return bool(_REVENUE_RE.search((label or "").strip()))


# --- Resultado ----------------------------------------------------------------

@dataclass
class QualityIssue:
    code: str
    message: str
    blocking: bool = True


@dataclass
class QualityReport:
    rut: str
    issues: list[QualityIssue] = field(default_factory=list)
    # Métricas observadas, útiles para el reporte de cuarentena.
    last_period: str | None = None
    income_statement_rows: int = 0
    balance_sheet_rows: int = 0
    data_points: int = 0

    @property
    def blocking_issues(self) -> list[QualityIssue]:
        return [i for i in self.issues if i.blocking]

    @property
    def warnings(self) -> list[QualityIssue]:
        return [i for i in self.issues if not i.blocking]

    @property
    def ok(self) -> bool:
        """True si la empresa puede subirse a producción."""
        return not self.blocking_issues

    def summary(self) -> str:
        if self.ok:
            return "ok" if not self.warnings else \
                "ok con avisos: " + "; ".join(i.message for i in self.warnings)
        return "; ".join(i.message for i in self.blocking_issues)


# --- Chequeo ------------------------------------------------------------------

def _quarter_index(year: int, quarter: int) -> int:
    """Índice absoluto de trimestre. quarter=0 (anual) cuenta como Q4."""
    return year * 4 + (quarter if quarter else 4)


def _expected_min_quarter(th: QualityThresholds, today: date) -> int:
    """Trimestre mínimo que la serie debe alcanzar para no considerarse obsoleta."""
    current = _quarter_index(today.year, (today.month - 1) // 3 + 1)
    return current - th.publication_lag_quarters - th.max_stale_quarters


def _fmt_period(year: int, quarter: int) -> str:
    return f"{year}" if not quarter else f"{year}Q{quarter}"


def check_company_csv(
    csv_data,
    thresholds: QualityThresholds | None = None,
    today: date | None = None,
    statement_types: dict | None = None,
) -> QualityReport:
    """Evalúa un ``CompanyCSV`` y decide si puede subirse a producción.

    ``statement_types`` es el contenido del sidecar ``statement_types.json`` que
    escribe la consolidación; si trae períodos individuales se emite un aviso
    (no bloqueante): la serie es válida pero no es homogénea.
    """
    from .supabase_uploader import category_from_role, parse_value

    th = thresholds or QualityThresholds.from_env()
    today = today or date.today()
    report = QualityReport(rut=getattr(csv_data, "rut", "?"))

    rows = list(getattr(csv_data, "rows", None) or [])
    periods = list(getattr(csv_data, "periods", None) or [])

    if not rows or not periods:
        report.issues.append(QualityIssue(
            "csv_vacio", "CSV sin filas o sin períodos válidos"))
        return report

    period_keys = [(_fmt_period(y, q), y, q) for y, q in periods]

    # --- Conteos por estado, contando sólo filas con algún valor numérico ---
    income_rows: list[str] = []
    balance_rows = 0
    data_points = 0
    has_revenue = False

    for row in rows:
        label = (row.get("Label") or "").strip()
        role = (row.get("RoleCode") or "").strip()
        if not label or not role:
            continue
        n_values = 0
        for key, _y, _q in period_keys:
            if parse_value(row.get(key)) is not None:
                n_values += 1
        data_points += n_values
        if n_values == 0:
            continue
        category = category_from_role(role, label)
        if category == "income_statement":
            income_rows.append(label)
            if looks_like_revenue(label):
                has_revenue = True
        elif category == "balance_sheet":
            balance_rows += 1

    report.income_statement_rows = len(income_rows)
    report.balance_sheet_rows = balance_rows
    report.data_points = data_points

    # --- Obsolescencia ---
    last_year, last_quarter = max(periods, key=lambda p: _quarter_index(*p))
    report.last_period = _fmt_period(last_year, last_quarter)
    min_expected = _expected_min_quarter(th, today)
    if _quarter_index(last_year, last_quarter) < min_expected:
        report.issues.append(QualityIssue(
            "datos_obsoletos",
            f"serie congelada en {report.last_period} "
            f"(se esperaba llegar al menos a {_fmt_period(min_expected // 4, min_expected % 4 or 4)})",
        ))

    # --- Estado de resultados degenerado ---
    if not income_rows:
        report.issues.append(QualityIssue(
            "sin_estado_resultados",
            "el estado de resultados no tiene ninguna fila con datos",
        ))
    else:
        if len(income_rows) < th.min_income_statement_rows:
            report.issues.append(QualityIssue(
                "estado_resultados_incompleto",
                f"estado de resultados con sólo {len(income_rows)} fila(s) con datos "
                f"(mínimo {th.min_income_statement_rows})",
            ))
        if not has_revenue:
            report.issues.append(QualityIssue(
                "estado_resultados_sin_ingresos",
                "el estado de resultados no tiene línea de ingresos "
                "(sólo resultado/ganancias): el rol del ER no coincide con la plantilla",
            ))

    # --- Balance ---
    if balance_rows < th.min_balance_sheet_rows:
        report.issues.append(QualityIssue(
            "balance_incompleto",
            f"balance con sólo {balance_rows} fila(s) con datos "
            f"(mínimo {th.min_balance_sheet_rows})",
        ))

    # --- Volumen total ---
    if data_points < th.min_data_points:
        report.issues.append(QualityIssue(
            "pocos_datos",
            f"sólo {data_points} datapoints numéricos (mínimo {th.min_data_points})",
        ))

    # --- Aviso: serie no homogénea (mezcla consolidado / individual) ---
    individual = list((statement_types or {}).get("individual_periods") or [])
    if individual and (statement_types or {}).get("mixed"):
        report.issues.append(QualityIssue(
            "serie_mixta_consolidado_individual",
            f"{len(individual)} período(s) provienen de estados Individuales "
            f"({individual[0]}–{individual[-1]}), no comparables con el consolidado",
            blocking=False,
        ))

    return report
