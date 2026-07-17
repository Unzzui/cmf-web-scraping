from src.banks.taxonomy import adecuacion_disponible, classify_epoch, classify_unit


def test_epoch_antes_de_2022():
    assert classify_epoch(2021, 12) == "pre_2022"
    assert classify_epoch(2009, 12) == "pre_2022"


def test_epoch_desde_2022():
    assert classify_epoch(2022, 1) == "compendio_2022"
    assert classify_epoch(2025, 5) == "compendio_2022"


def test_unit_sigue_a_la_epoca():
    assert classify_unit(2021, 12) == "MMCLP"
    assert classify_unit(2022, 1) == "CLP"


def test_adecuacion_hasta_2020_11():
    assert adecuacion_disponible(2020, 11) is True
    assert adecuacion_disponible(2018, 5) is True


def test_adecuacion_no_publicada_desde_2020_12():
    """Quiebre Basilea III: el API deja de publicar adecuación en 2020-12."""
    assert adecuacion_disponible(2020, 12) is False
    assert adecuacion_disponible(2021, 1) is False
    assert adecuacion_disponible(2026, 5) is False


def test_adecuacion_corte_es_independiente_de_la_epoca_contable():
    """El corte de adecuación (2020-12) no coincide con el del Compendio (2022-01)."""
    assert classify_epoch(2021, 6) == "pre_2022"
    assert adecuacion_disponible(2021, 6) is False
