from src.banks.taxonomy import classify_epoch, classify_unit


def test_epoch_antes_de_2022():
    assert classify_epoch(2021, 12) == "pre_2022"
    assert classify_epoch(2009, 12) == "pre_2022"


def test_epoch_desde_2022():
    assert classify_epoch(2022, 1) == "compendio_2022"
    assert classify_epoch(2025, 5) == "compendio_2022"


def test_unit_sigue_a_la_epoca():
    assert classify_unit(2021, 12) == "MMCLP"
    assert classify_unit(2022, 1) == "CLP"
