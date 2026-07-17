"""Tests de los criterios de aceptación del spec (§8)."""

from src.edgar.ingest import build_line_values
from src.edgar.validate import (
    check_accounting_identity,
    check_accumulation,
    check_restatement_drift,
)
from tests.edgar.conftest import FY24_END, FY24_Q1, FY24_START, fact, payload


def _balance(assets, total, end=FY24_END, accn="a-1", filed="2024-11-01"):
    return payload({
        "Assets": [fact(assets, end, None, "10-K", filed, accn)],
        "LiabilitiesAndStockholdersEquity": [fact(total, end, None, "10-K", filed, accn)],
    })


def test_identidad_contable_cuadra():
    assert check_accounting_identity(_balance(364_980, 364_980)) == []


def test_identidad_contable_detecta_mapeo_malo():
    problems = check_accounting_identity(_balance(364_980, 300_000))
    assert len(problems) == 1
    assert "!=" in problems[0]


def test_identidad_contable_compara_dentro_del_mismo_filing():
    """El caso JPM 2013: `Assets` reexpresado en el 10-K de 2016 (2.414.879) y
    `LiabilitiesAndStockholdersEquity` sin retaguear desde 2015 (2.415.689). Comparando la
    serie deduplicada da un descuadre falso; dentro de cada filing ambos cuadran y el
    chequeo responde lo que tiene que responder: el mapeo está bien."""
    p = payload({
        "Assets": [
            fact(2_415_689, "2013-12-31", None, "10-K", "2014-02-20", "a-14"),
            fact(2_414_879, "2013-12-31", None, "10-K", "2016-02-23", "a-16"),
        ],
        "LiabilitiesAndStockholdersEquity": [
            fact(2_415_689, "2013-12-31", None, "10-K", "2014-02-20", "a-14"),
        ],
    })
    assert check_accounting_identity(p) == []


def test_identidad_contable_respeta_min_year():
    """El único descuadre real de las 49 es JPM al 2009-12-31, fuera de la ventana que se
    carga: 2009 es el primer año del mandato XBRL y el tagueo era flojo."""
    p = _balance(2_119_673, 2_031_989, end="2009-12-31", filed="2010-02-24")
    assert len(check_accounting_identity(p)) == 1
    assert check_accounting_identity(p, min_year=2011) == []


def test_identidad_tolera_redondeo():
    assert check_accounting_identity(_balance(364_980_000_000, 364_980_000_001)) == []


def _revenue_series(q1, q2, q3, q4):
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    return build_line_values(payload({tag: [
        fact(q1, "2023-12-30", FY24_START, "10-Q", "2024-02-02"),
        fact(q2, "2024-03-30", FY24_START, "10-Q", "2024-05-03"),
        fact(q3, "2024-06-29", FY24_START, "10-Q", "2024-08-02"),
        fact(q4, FY24_END, FY24_START, "10-K", "2024-11-01"),
    ]}))


def test_acumulacion_ok():
    values = _revenue_series(119_575, 210_328, 296_105, 391_035)
    assert check_accumulation(values) == []


def test_acumulacion_detecta_que_se_tomo_la_duracion_de_3_meses():
    """Si Q2 ≈ Q1 en vez de ser ~el doble, se tomaron los 3 meses. Es el error del §5 y no
    lanza ninguna excepción por sí solo."""
    values = _revenue_series(119_575, 90_753, 85_777, 94_930)
    problems = check_accumulation(values)
    assert problems
    assert "3 meses" in problems[0]


def test_acumulacion_ignora_series_incompletas():
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    values = build_line_values(payload({tag: [
        fact(119_575, "2023-12-30", FY24_START, "10-Q", "2024-02-02"),
        fact(391_035, FY24_END, FY24_START, "10-K", "2024-11-01"),
    ]}))
    assert check_accumulation(values) == []


def _balance_cargado(assets, total):
    """Balance CON un hecho de duración: sin al menos un ejercicio de ~12 meses no hay de
    dónde derivar el calendario fiscal, y los instants no se pueden ubicar en ningún
    período. Es el comportamiento correcto — el período sale de las fechas de los hechos,
    no de `fy`/`fp` — pero hay que anclarlo en la fixture."""
    return build_line_values(payload({
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            fact(400, FY24_END, FY24_START, "10-K", "2024-11-01"),
        ],
        "Assets": [fact(assets, FY24_END, None, "10-K", "2024-11-01")],
        "LiabilitiesAndStockholdersEquity": [fact(total, FY24_END, None, "10-K", "2024-11-01")],
    }))


def test_drift_avisa_solo_cuando_es_demasiado_para_una_reexpresion():
    """Una reexpresión mueve el balance un poco (el peor de las 49 es GE con 1,7%); un
    mapeo malo lo mueve un orden de magnitud."""
    assert check_restatement_drift(_balance_cargado(1_000_000, 1_000_500)) == []  # 0,05%
    assert len(check_restatement_drift(_balance_cargado(1_000_000, 700_000))) == 1  # 30%
