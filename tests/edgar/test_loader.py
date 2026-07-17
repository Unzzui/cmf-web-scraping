"""Tests del loader. La escala es lo que más importa: se equivoca sin hacer ruido."""

from src.edgar.loader import CURRENCY_US, escalar_para_guardar
from src.edgar.taxonomy import CONCEPTS


def test_la_plata_se_guarda_en_miles():
    """EDGAR publica en unidades y `financial_data` guarda en miles. Los US$364.980
    millones de activos de Apple entran como 364.980.000."""
    assert escalar_para_guardar(364_980_000_000, "USD") == 364_980_000


def test_las_acciones_no_se_dividen():
    """Cencosud guarda 2.805.870.127 acciones, que son las reales. Y el motor de ratios
    hace `(Neta * 1000) / TotalAcciones`: si las acciones vinieran en miles, el EPS saldría
    1000x chico."""
    assert escalar_para_guardar(15_116_786_000, "shares") == 15_116_786_000


def test_el_eps_no_se_divide():
    """Ya es plata POR ACCIÓN: US$6,11 son 6,11, no 0,00611."""
    assert escalar_para_guardar(6.11, "USD/shares") == 6.11


def test_todas_las_unidades_del_catalogo_tienen_divisor():
    """Una unidad nueva sin divisor tiene que reventar acá y no cargar en la escala
    equivocada."""
    for concept in CONCEPTS:
        escalar_para_guardar(1.0, concept.unit)  # no lanza KeyError


def test_la_escala_no_altera_los_ratios_por_eso_hay_que_testearla_aparte():
    """Por qué esto necesita su propio test: un ratio es plata sobre plata, así que el
    factor 1000 se cancela y la validación de cuadratura y acumulación pasa igual de
    verde. El error sólo se ve en la UI y en el EPS."""
    activos, pasivos = 364_980_000_000, 308_030_000_000
    ratio_sin_escalar = activos / pasivos
    ratio_escalado = (escalar_para_guardar(activos, "USD")
                      / escalar_para_guardar(pasivos, "USD"))
    assert ratio_sin_escalar == ratio_escalado


def test_moneda_us():
    assert CURRENCY_US == "USD"
