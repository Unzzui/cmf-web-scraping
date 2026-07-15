import pytest

from scripts.ingest_banks import build_arg_parser, iter_months, main, parse_period


def test_pause_flag_default_y_override():
    args = build_arg_parser().parse_args(["--from", "01/2015", "--to", "05/2026"])
    assert args.pause == 0.3
    args = build_arg_parser().parse_args(
        ["--from", "01/2015", "--to", "05/2026", "--pause", "0.5"]
    )
    assert args.pause == 0.5


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


def test_main_rango_vacio_retorna_error():
    assert main(["--from", "05/2025", "--to", "01/2025"]) == 2


def test_main_periodo_malo_retorna_error():
    assert main(["--from", "xx", "--to", "01/2025"]) == 2
