from cmf_extract.analisis_bancos import concept_map as cm


def test_codes_for_concepto_simple():
    assert cm.codes_for("activos_total") == ["100000000"]
    assert cm.codes_for("resultado_ejercicio") == ["590000000"]


def test_codes_for_concepto_compuesto():
    assert cm.codes_for("depositos_clientes") == ["241000000", "242000000"]


def test_statement_for():
    assert cm.statement_for("activos_total") == "balance"
    assert cm.statement_for("resultado_ejercicio") == "resultado"


def test_concepto_desconocido_levanta():
    import pytest

    with pytest.raises(KeyError):
        cm.codes_for("no_existe")
    with pytest.raises(KeyError):
        cm.statement_for("no_existe")


def test_all_concepts_incluye_balance_y_resultado():
    todos = cm.all_concepts()
    assert "activos_total" in todos
    assert "ingreso_neto_intereses" in todos
    assert len(todos) == len(set(todos))  # sin duplicados
