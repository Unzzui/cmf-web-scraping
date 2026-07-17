"""Fixtures sintéticas con la forma real de companyfacts.

Los números y las fechas están calcados de Apple (año fiscal que cierra a fines de
septiembre, trimestres de 52/53 semanas) porque las reglas que se prueban —acumulación
YTD, dedupe, `fy`/`fp` mentiroso— sólo se manifiestan con esa forma.
"""

import pytest

FY24_START = "2023-10-01"
FY24_Q1 = "2023-12-30"
FY24_Q2 = "2024-03-30"
FY24_Q3 = "2024-06-29"
FY24_END = "2024-09-28"


def fact(val, end, start=None, form="10-Q", filed="2024-05-03", accn="0000320193-24-000001",
         fy=2024, fp="Q2"):
    d = {"end": end, "val": val, "accn": accn, "fy": fy, "fp": fp, "form": form,
         "filed": filed}
    if start is not None:
        d["start"] = start
    return d


def payload(facts_by_tag: dict, units_by_tag: dict | None = None) -> dict:
    units_by_tag = units_by_tag or {}
    return {
        "cik": 320193,
        "entityName": "Apple Inc.",
        "facts": {
            "us-gaap": {
                tag: {"label": tag, "units": {units_by_tag.get(tag, "USD"): items}}
                for tag, items in facts_by_tag.items()
            }
        },
    }


@pytest.fixture
def apple_revenue_payload():
    """Ingresos del FY2024 de Apple: las 4 duraciones acumuladas MÁS los trimestres
    sueltos, que es como viene de verdad y es la trampa del §5."""
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    return payload({
        tag: [
            # --- acumulados (YTD): lo que hay que tomar
            fact(119_575_000_000, FY24_Q1, FY24_START, "10-Q", "2024-02-02"),
            fact(210_328_000_000, FY24_Q2, FY24_START, "10-Q", "2024-05-03"),
            fact(296_105_000_000, FY24_Q3, FY24_START, "10-Q", "2024-08-02"),
            fact(391_035_000_000, FY24_END, FY24_START, "10-K", "2024-11-01"),
            # --- trimestres sueltos: NO se toman. En el dataset real le ganan 62 a 16.
            fact(90_753_000_000, FY24_Q2, "2023-12-31", "10-Q", "2024-05-03"),
            fact(85_777_000_000, FY24_Q3, "2023-03-31", "10-Q", "2024-08-02"),
            fact(94_930_000_000, FY24_END, "2024-06-30", "10-K", "2024-11-01"),
        ]
    })
