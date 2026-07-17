"""Tests del calendario de resultados: parseo de submissions y estimación de próxima fecha."""

from datetime import date

from src.edgar.calendar import build_events, estimate_next


def _sub(filings: list[dict]) -> dict:
    """Arma un `submissions` mínimo desde una lista de filings (dicts sueltos)."""
    keys = ("form", "filingDate", "reportDate", "acceptanceDateTime", "items",
            "accessionNumber")
    recent = {k: [f.get(k, "") for f in filings] for k in keys}
    return {"filings": {"recent": recent}}


def _earn(fecha: str, hora_utc: str, accn: str) -> dict:
    return {"form": "8-K", "filingDate": fecha, "reportDate": fecha,
            "acceptanceDateTime": f"{fecha}T{hora_utc}.000Z", "items": "2.02,9.01",
            "accessionNumber": accn}


def _q(filing_date: str, report_date: str, accn: str, form="10-Q") -> dict:
    return {"form": form, "filingDate": filing_date, "reportDate": report_date,
            "accessionNumber": accn}


def test_earnings_timing_amc_vs_bmo():
    sub = _sub([
        _earn("2025-10-30", "20:30:00", "a1"),   # 20:30 UTC -> tras el cierre
        _earn("2025-07-31", "10:30:00", "a2"),   # 10:30 UTC -> antes de apertura
    ])
    events = {e.accession: e for e in build_events(sub) if e.event_type == "earnings"}
    assert events["a1"].timing == "amc"
    assert events["a1"].event_time == "20:30"
    assert events["a2"].timing == "bmo"


def test_ano_fiscal_desfasado_de_apple():
    # Apple cierra en septiembre. El 10-Q que reporta al 27-dic-2025 es el Q1 del FY2026,
    # no del 2025 — el año lo manda el ejercicio, no el calendario.
    sub = _sub([
        _q("2025-10-31", "2025-09-27", "k1", form="10-K"),   # FY2025 Q4 (cierre sept)
        _q("2026-01-30", "2025-12-27", "q1"),                # FY2026 Q1 (dic, sin 10-K aún)
        _q("2025-08-01", "2025-06-28", "q3prev"),            # FY2025 Q3
    ])
    fin = {e.accession: e for e in build_events(sub) if e.event_type == "financials"}
    assert (fin["k1"].period_year, fin["k1"].period_quarter) == (2025, 4)
    assert (fin["q1"].period_year, fin["q1"].period_quarter) == (2026, 1)


def test_ano_fiscal_calendario():
    # Empresa que cierra en diciembre: el Q1 que reporta al 31-mar-2026 es FY2026 Q1.
    sub = _sub([
        _q("2026-02-13", "2025-12-31", "k", form="10-K"),
        _q("2026-05-01", "2026-03-31", "q1"),
    ])
    fin = {e.accession: e for e in build_events(sub) if e.event_type == "financials"}
    assert (fin["k"].period_year, fin["k"].period_quarter) == (2025, 4)
    assert (fin["q1"].period_year, fin["q1"].period_quarter) == (2026, 1)


def test_estimate_next_avanza_hasta_pasar_hoy():
    # Cadencia trimestral limpia; la estimada debe caer ~91 días tras el último y en futuro.
    sub = _sub([
        _earn("2026-01-29", "20:30:00", "a1"),
        _earn("2025-10-30", "20:30:00", "a2"),
        _earn("2025-07-31", "20:30:00", "a3"),
        _earn("2025-05-01", "20:30:00", "a4"),
    ])
    est = estimate_next(build_events(sub), date(2026, 3, 1))
    assert est is not None
    assert est.status == "estimated"
    assert est.event_date > date(2026, 3, 1)
    assert est.timing == "amc"


def test_estimate_next_sin_cadencia_no_inventa():
    # Menos de 3 earnings: no hay con qué medir la cadencia, no se estima.
    sub = _sub([_earn("2026-01-29", "20:30:00", "a1"), _earn("2025-10-30", "20:30:00", "a2")])
    assert estimate_next(build_events(sub), date(2026, 3, 1)) is None
