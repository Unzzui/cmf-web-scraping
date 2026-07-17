"""Tests del catálogo. El más importante es el que lo ata al motor de ratios."""

from src.edgar.taxonomy import CONCEPTS, CONCEPTS_BY_KEY, resolve_tag


def test_display_order_unico():
    """`financial_line_items` tiene UNIQUE (company_id, display_order): dos conceptos con
    el mismo orden se pisarían y sólo sobreviviría uno."""
    orders = [c.display_order for c in CONCEPTS]
    assert len(orders) == len(set(orders))


def test_keys_unicas():
    keys = [c.key for c in CONCEPTS]
    assert len(keys) == len(set(keys))


def test_categorias_son_las_cuatro_que_ramifica_la_web():
    validas = {"balance_sheet", "income_statement", "cash_flow", "miscellaneous"}
    assert {c.category for c in CONCEPTS} <= validas


def test_ningun_concepto_va_a_miscellaneous():
    """El motor de ratios descarta `miscellaneous` y role_code '000000' entero: una línea
    de estado financiero que caiga ahí es invisible para los ratios."""
    assert "miscellaneous" not in {c.category for c in CONCEPTS}
    assert "000000" not in {c.role_code for c in CONCEPTS}


def test_role_codes_no_reciclan_los_de_la_cmf():
    """210000/310000/510000 son roles de la taxonomía IFRS de la CMF y significan otra
    cosa. Reusarlos haría ilegible de dónde viene una fila (spec §4)."""
    cmf = {"210000", "310000", "320000", "510000", "000000"}
    assert not ({c.role_code for c in CONCEPTS} & cmf)
    assert all(c.role_code.startswith("US-") for c in CONCEPTS)


def test_cadenas_de_tags_sin_repetidos():
    for concept in CONCEPTS:
        assert len(concept.tags) == len(set(concept.tags)), concept.key


def test_resolve_tag_respeta_la_prioridad_de_la_cadena():
    ventas = CONCEPTS_BY_KEY["Ventas"]
    assert resolve_tag(ventas, {"Revenues"}) == "Revenues"
    # con los dos disponibles gana el primero de la cadena
    assert resolve_tag(
        ventas, {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"}
    ) == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert resolve_tag(ventas, {"OtraCosa"}) is None


def test_labels_es_son_los_strings_exactos_que_busca_el_motor_de_ratios():
    """El contrato con `ratio_calculator_postgresql.py`, que resuelve conceptos matcheando
    TEXTO DE LABEL EN ESPAÑOL contra su `concept_mappings`. Estos labels son los que usan
    las 543 chilenas; con ellos el motor toma las gringas sin que haya que tocarlo.

    Si alguien "arregla" un label acá, el ratio correspondiente deja de calcularse en
    silencio. Ya pasó en la primera versión de este catálogo: "Ganancia (pérdida) de
    actividades operacionales" en singular no matchea el "Ganancias (pérdidas) ..." que
    busca el motor, ni siquiera por 'contiene', y el EBIT de las 49 salía vacío.
    """
    esperados = {
        "AC": "Activos corrientes totales",
        "PC": "Pasivos corrientes totales",
        "Inv": "Inventarios corrientes",
        "Efec": "Efectivo y equivalentes al efectivo",
        "AT": "Total de activos",
        "PT": "Total de pasivos",
        "Patr": "Patrimonio atribuible a los propietarios de la controladora",
        "PatrTot": "Patrimonio total",
        "PPE": "Propiedades, planta y equipo",
        "Ventas": "Ingresos de actividades ordinarias",
        "COGS": "Costo de ventas",
        "GProfit": "Ganancia bruta",
        "OpInc": "Ganancias (pérdidas) de actividades operacionales",
        "NetInc": "Ganancia (pérdida)",
        "CostFin": "Costos financieros",
        "RE": "Ganancias (pérdidas) acumuladas",
        "Acciones": "Total número de acciones emitidas",
    }
    for key, label in esperados.items():
        assert CONCEPTS_BY_KEY[key].label_es == label, f"{key} desconectaría el motor de ratios"


def test_cxc_matchea_por_contiene_en_el_motor_de_ratios():
    """El motor busca 'deudores comerciales' con match por 'contiene' (en minúsculas)."""
    assert "deudores comerciales" in CONCEPTS_BY_KEY["CxC"].label_es.lower()
