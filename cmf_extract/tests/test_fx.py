"""La conversión de moneda, verificada contra lo que las propias empresas publicaron.

Estos números no salen de un manual: salen de las reexpresiones que ENEL CHILE, ENEL
GENERACIÓN, PEHUENCHE y AGROSUPER publicaron cuando cambiaron su moneda de presentación.
Dividiendo el valor viejo (CLP) por el nuevo (USD) del MISMO período se obtiene el tipo de
cambio que la empresa aplicó. Es la única fuente de verdad que existe para esto.

Si alguien cambia la regla del tipo de cambio, estos tests se caen -- que es exactamente lo
que tienen que hacer.
"""

from __future__ import annotations

import pytest

from cmf_extract import fx


# Tipo de cambio IMPLÍCITO en la reexpresión de cada empresa: CLP reportado / USD reexpresado.
#
#   (empresa, fecha de cierre, rol, tipo de cambio implícito)
#
# El rol decide qué tipo de cambio corresponde:
#   310000/510000 -> FLUJO  -> promedio del período
#   210000        -> STOCK  -> cierre
REEXPRESIONES = [
    # ENEL CHILE: ingresos 2024 = 3.904.732.890.000 CLP / 4.137.511.000 USD
    ("ENEL CHILE ingresos",   "2024-12-31", "310000", 3_904_732_890_000 / 4_137_511_000),
    # ENEL CHILE: activos 2024 = 12.719.897.584.000 CLP / 12.765.086.000 USD
    ("ENEL CHILE activos",    "2024-12-31", "210000", 12_719_897_584_000 / 12_765_086_000),
    ("ENEL CHILE patrimonio", "2024-12-31", "210000", 5_326_379_515_000 / 5_345_302_000),
]


@pytest.mark.skipif(not fx.disponible(),
                    reason="falta la serie del dólar observado en cmf_extract/public/")
@pytest.mark.parametrize("nombre,fecha,rol,implicito", REEXPRESIONES)
def test_el_tipo_de_cambio_coincide_con_la_reexpresion_de_la_empresa(
        nombre, fecha, rol, implicito):
    """El factor que usamos tiene que ser el que la empresa usó. Sin margen para inventar."""
    nuestro = fx.factor(fecha, rol)
    assert nuestro is not None, f"{nombre}: sin tipo de cambio para {fecha}"

    error = abs(nuestro - implicito) / implicito
    assert error < 0.005, (
        f"{nombre}: la empresa reexpresó a {implicito:.2f} CLP/USD y nosotros usamos "
        f"{nuestro:.2f} ({error:.2%} de error). O la regla de conversión está mal, o la "
        f"serie del Banco Central cambió."
    )


@pytest.mark.skipif(not fx.disponible() or not fx.es_diaria(),
                    reason="requiere la serie DIARIA del dólar observado")
def test_el_cierre_es_la_primera_observacion_posterior_no_la_anterior():
    """El cierre del 31-dic es el dólar publicado el siguiente día hábil, no el anterior.

    Suena al revés y no lo es: el dólar observado del día D refleja las operaciones del día
    hábil anterior, y el 31 de diciembre suele ser feriado bancario. Las cuatro empresas que
    cambiaron de moneda reexpresaron su balance 2024 a 996,46 -- el valor publicado el 2 de
    enero de 2025 -- y no a 992,12, el del 30 de diciembre.

    Tomar el anterior parece lo natural y mete 0,44% de error en TODO el balance.
    """
    assert fx.cierre("2024-12-31") == pytest.approx(996.46, rel=1e-4)


@pytest.mark.skipif(not fx.disponible(),
                    reason="falta la serie del dólar observado en cmf_extract/public/")
def test_los_flujos_usan_el_promedio_del_periodo_y_no_el_cierre():
    """Un flujo se acumula durante el año: le corresponde el promedio, no la foto final.

    En 2024 la diferencia entre ambos es de 5,6% -- todo el margen operacional de muchas
    empresas.
    """
    promedio = fx.factor("2024-12-31", "310000")   # estado de resultados
    cierre = fx.factor("2024-12-31", "210000")     # balance

    assert promedio is not None and cierre is not None
    assert promedio < cierre, (
        "en 2024 el dólar subió: el promedio del año tiene que ser MENOR que el cierre. "
        f"promedio={promedio:.2f}, cierre={cierre:.2f}"
    )
    assert promedio == pytest.approx(943.7, rel=0.01)
