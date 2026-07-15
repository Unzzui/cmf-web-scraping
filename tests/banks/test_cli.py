import pytest

from scripts.ingest_banks import iter_months, parse_period


def test_parse_period_ok():
    assert parse_period("05/2025") == (2025, 5)
    assert parse_period("12/2010") == (2010, 12)


def test_parse_period_invalido():
    with pytest.raises(ValueError):
        parse_period("2025-05")
    with pytest.raises(ValueError):
        parse_period("13/2025")


def test_iter_months_inclusivo_y_cruza_anho():
    assert iter_months((2024, 11), (2025, 2)) == [
        (2024, 11), (2024, 12), (2025, 1), (2025, 2),
    ]


def test_iter_months_un_solo_mes():
    assert iter_months((2025, 5), (2025, 5)) == [(2025, 5)]
