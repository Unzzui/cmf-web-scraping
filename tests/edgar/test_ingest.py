"""Tests del parser. Cada uno corresponde a un gotcha que mordió de verdad."""

from datetime import date

from src.edgar.ingest import (
    build_fiscal_calendar,
    build_line_values,
    coerce_value,
    dedupe_facts,
    group_by_period,
    parse_facts,
    resolve_concept_periods,
    select_period_values,
)
from src.edgar.models import Fact
from src.edgar.taxonomy import CONCEPTS_BY_KEY
from tests.edgar.conftest import FY24_END, FY24_Q1, FY24_Q2, FY24_Q3, FY24_START, fact, payload


# --------------------------------------------------------------------------- valores
def test_coerce_value_rechaza_lo_que_no_es_numero():
    assert coerce_value(1234.5) == 1234.5
    assert coerce_value("1234.5") == 1234.5
    assert coerce_value(0) == 0.0  # un cero declarado SÍ es un dato
    assert coerce_value(None) is None
    assert coerce_value("") is None
    assert coerce_value("n/a") is None
    assert coerce_value(float("nan")) is None
    assert coerce_value(float("inf")) is None


def test_coerce_value_rechaza_bool():
    """`float(True)` es 1.0 porque bool es subclase de int: el análogo exacto del
    `Number(null) === 0` que metió 149 precios corruptos (spec §7)."""
    assert coerce_value(True) is None
    assert coerce_value(False) is None


def test_parse_facts_descarta_hechos_sin_valor_usable():
    p = payload({"Assets": [
        fact(100.0, "2024-09-28"),
        {"end": "2024-09-28", "val": None, "accn": "x", "form": "10-K", "filed": "2024-11-01"},
        {"end": "2024-09-28", "val": 5.0, "accn": "x", "form": "10-K"},  # sin filed
    ]})
    facts = parse_facts(p, "Assets")
    assert len(facts) == 1
    assert facts[0].val == 100.0


# --------------------------------------------------------------------------- dedupe §6.1
def test_dedupe_gana_el_filed_mas_reciente():
    original = Fact("Assets", None, date(2013, 12, 31), 2_415_689.0, "a-14", "10-K",
                    date(2014, 2, 20))
    reexpresado = Fact("Assets", None, date(2013, 12, 31), 2_414_879.0, "a-16", "10-K",
                       date(2016, 2, 23))
    assert dedupe_facts([original, reexpresado])[0].val == 2_414_879.0
    assert dedupe_facts([reexpresado, original])[0].val == 2_414_879.0  # sin importar el orden


def test_dedupe_desempata_por_accn_para_ser_determinista():
    """Mismo `filed` (enmienda publicada el mismo día): sin desempate el ganador dependería
    del orden del JSON y dos corridas cargarían valores distintos."""
    a = Fact("Assets", None, date(2024, 9, 28), 1.0, "0000320193-24-000001", "10-K",
             date(2024, 11, 1))
    b = Fact("Assets", None, date(2024, 9, 28), 2.0, "0000320193-24-000002", "10-K/A",
             date(2024, 11, 1))
    assert dedupe_facts([a, b])[0].val == 2.0
    assert dedupe_facts([b, a])[0].val == 2.0


# ------------------------------------------------------------------ calendario fiscal §6.4
def test_calendario_sale_de_las_fechas_y_no_de_fy_fp(apple_revenue_payload):
    """Los hechos traen fy=2024/fp=Q2 cableado en la fixture; el Q1 igual tiene que salir
    Q1. `fy`/`fp` describen el filing, no el hecho (spec §6.4)."""
    facts = parse_facts(apple_revenue_payload,
                        "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts)
    assert cal[(2024, 1)].end == date(2023, 12, 30)
    assert cal[(2024, 4)].end == date(2024, 9, 28)


def test_el_q1_del_fy2024_cae_en_2024_aunque_termine_en_diciembre_de_2023(
    apple_revenue_payload,
):
    """`period_year` es el año FISCAL: el Q1 de Apple cierra el 2023-12-30 y pertenece al
    FY2024. Tomar el año calendario del cierre lo mandaría a 2023."""
    facts = parse_facts(apple_revenue_payload,
                        "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts)
    assert (2024, 1) in cal
    assert cal[(2024, 1)].end.year == 2023


# --------------------------------------------------------------- acumulación YTD §5
def test_toma_la_duracion_acumulada_y_no_el_trimestre_suelto(apple_revenue_payload):
    """EL test. La fixture trae ambas duraciones, como viene de verdad. Si se colara la de
    3 meses, Q2 daría 90.753 en vez de 210.328 y nada fallaría: los estados de EEUU
    quedarían discretos contra los chilenos acumulados y toda comparación entre mercados
    daría mal en silencio."""
    facts = parse_facts(apple_revenue_payload,
                        "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts)
    values = select_period_values(facts, cal)
    assert values[(2024, 1)] == 119_575_000_000
    assert values[(2024, 2)] == 210_328_000_000
    assert values[(2024, 3)] == 296_105_000_000
    assert values[(2024, 4)] == 391_035_000_000


def test_la_serie_ytd_es_creciente(apple_revenue_payload):
    facts = parse_facts(apple_revenue_payload,
                        "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts)
    v = select_period_values(facts, cal)
    serie = [v[(2024, q)] for q in (1, 2, 3, 4)]
    assert serie == sorted(serie)


def test_q4_es_el_ejercicio_completo_y_no_un_trimestre_suelto(apple_revenue_payload):
    """No hay que derivar el Q4: el 10-K da el año completo y eso ES period_quarter=4."""
    facts = parse_facts(apple_revenue_payload,
                        "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts)
    assert select_period_values(facts, cal)[(2024, 4)] == 391_035_000_000


# ------------------------------------------------------------------- balance (instant) §6.2
def test_el_balance_no_se_acumula_y_se_ubica_por_fecha_de_cierre():
    p = payload({
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            fact(100, FY24_Q1, FY24_START), fact(400, FY24_END, FY24_START, "10-K"),
        ],
        "Assets": [  # instants: sin `start`
            fact(352_583_000_000, FY24_Q1, None, "10-Q"),
            fact(364_980_000_000, FY24_END, None, "10-K"),
        ],
    })
    concept = CONCEPTS_BY_KEY["AT"]
    facts_rev = parse_facts(p, "RevenueFromContractWithCustomerExcludingAssessedTax")
    cal = build_fiscal_calendar(facts_rev)
    resolved = resolve_concept_periods(p, concept, cal)
    assert resolved[(2024, 1)][0] == 352_583_000_000  # foto al cierre del Q1, no una suma
    assert resolved[(2024, 4)][0] == 364_980_000_000


# --------------------------------------------------- cadena de tags: migración y convivencia
def test_migracion_de_tag_a_mitad_de_la_historia_no_parte_la_serie():
    """El caso XOM: `RevenueFromContract...` hasta 2021 y `Revenues` desde 2022. Resolver
    la cadena una vez por empresa dejaba a XOM sin ingresos desde 2022, sin aviso."""
    p = payload({
        "RevenueFromContractWithCustomerExcludingAssessedTax": [
            fact(276_692, "2021-12-31", "2021-01-01", "10-K", "2022-02-23"),
        ],
        "Revenues": [
            fact(413_680, "2022-12-31", "2022-01-01", "10-K", "2023-02-22"),
        ],
    })
    cal = build_fiscal_calendar(
        parse_facts(p, "RevenueFromContractWithCustomerExcludingAssessedTax")
        + parse_facts(p, "Revenues")
    )
    resolved = resolve_concept_periods(p, CONCEPTS_BY_KEY["Ventas"], cal)
    assert resolved[(2021, 4)] == (276_692, "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert resolved[(2022, 4)] == (413_680, "Revenues")


def test_un_solo_tag_por_ano_fiscal_cuando_dos_conviven_midiendo_distinto():
    """El caso Mastercard: `RevenueFromContract...` es BRUTO y `Revenues` es NETO, conviven
    y MA no publica el bruto del ejercicio. Resolviendo trimestre a trimestre la serie
    salía 8.025 / 16.729 / 25.896 / 22.237 — el Q4 "bajaba" porque cambiaba de magnitud.
    Con un tag por año gana `Revenues`, que es el que tiene el anual."""
    p = payload({
        "RevenueFromContractWithCustomerExcludingAssessedTax": [  # bruto, sin anual
            fact(8_025, "2022-03-31", "2022-01-01"),
            fact(16_729, "2022-06-30", "2022-01-01"),
            fact(25_896, "2022-09-30", "2022-01-01"),
        ],
        "Revenues": [  # neto, serie completa
            fact(5_167, "2022-03-31", "2022-01-01"),
            fact(10_664, "2022-06-30", "2022-01-01"),
            fact(16_420, "2022-09-30", "2022-01-01"),
            fact(22_237, "2022-12-31", "2022-01-01", "10-K", "2023-02-01"),
        ],
    })
    cal = build_fiscal_calendar(
        parse_facts(p, "RevenueFromContractWithCustomerExcludingAssessedTax")
        + parse_facts(p, "Revenues")
    )
    resolved = resolve_concept_periods(p, CONCEPTS_BY_KEY["Ventas"], cal)
    assert {tag for _, tag in resolved.values()} == {"Revenues"}
    serie = [resolved[(2022, q)][0] for q in (1, 2, 3, 4)]
    assert serie == [5_167, 10_664, 16_420, 22_237]
    assert serie == sorted(serie)


def test_concepto_que_la_empresa_no_publica_queda_hueco_no_cero():
    """JPM no tiene `AssetsCurrent` (un banco no presenta balance clasificado) y WMT no
    publica `Liabilities`. Un hueco es un hueco (spec §7)."""
    p = payload({"Assets": [fact(100, FY24_END, None, "10-K")],
                 "RevenueFromContractWithCustomerExcludingAssessedTax":
                     [fact(400, FY24_END, FY24_START, "10-K")]})
    values = build_line_values(p)
    assert "AC" not in {v.concept_key for v in values}
    assert not [v for v in values if v.value == 0 and v.concept_key == "AC"]


def test_build_line_values_marca_moneda_y_role_code_propios_de_eeuu(apple_revenue_payload):
    values = build_line_values(apple_revenue_payload)
    ventas = [v for v in values if v.concept_key == "Ventas"]
    assert ventas
    assert {v.role_code for v in ventas} == {"US-IS"}
    assert {v.category for v in ventas} == {"income_statement"}
    assert {v.label_es for v in ventas} == {"Ingresos de actividades ordinarias"}


def test_min_year_recorta_la_ventana():
    p = payload({"RevenueFromContractWithCustomerExcludingAssessedTax": [
        fact(1, "2010-12-31", "2010-01-01", "10-K", "2011-02-01"),
        fact(2, "2024-12-31", "2024-01-01", "10-K", "2025-02-01"),
    ]})
    years = {v.year for v in build_line_values(p, min_year=2011)}
    assert years == {2024}


def test_group_by_period(apple_revenue_payload):
    values = build_line_values(apple_revenue_payload)
    assert group_by_period(values)[(2024, 4)]["Ventas"] == 391_035_000_000
