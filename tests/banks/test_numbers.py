from src.banks.numbers import parse_spanish_number


def test_entero_con_decimales_cero():
    assert parse_spanish_number("59878091792,00") == 59878091792.0


def test_miles_y_decimales():
    assert parse_spanish_number("40.844,79") == 40844.79


def test_negativo():
    assert parse_spanish_number("-1.234,50") == -1234.5


def test_cero():
    assert parse_spanish_number("0,00") == 0.0


def test_vacio_es_none():
    assert parse_spanish_number("") is None
    assert parse_spanish_number("   ") is None


def test_none_es_none():
    assert parse_spanish_number(None) is None


def test_basura_es_none():
    assert parse_spanish_number("N/A") is None
