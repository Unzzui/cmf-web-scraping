"""Los supuestos del DCF salen de datos, no de constantes escritas a mano.

Cada uno de estos tests corresponde a un número que ESTABA hardcodeado en el modelo y que
se hacía pasar por un cálculo. No son hipótesis: son bugs que ya ocurrieron.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DCF = Path(__file__).resolve().parent.parent / "dcf_patch.py"
FUENTE = DCF.read_text(encoding="utf-8")


def test_el_tipo_de_cambio_no_es_una_constante():
    """El 950 convertía el valor por acción a pesos para compararlo contra la bolsa.

    Con el dólar real en 928,84 un 950 infla el valor intrínseco un 2,3%, y eso alimenta
    directo la "Prima/(Descuento)" y la "Recomendación". Cerca de los umbrales (COMPRA a
    +5%, MANTENER a ±5%) ese sesgo alcanza para dar vuelta el veredicto.

    Ahora sale del dólar observado del Banco Central. El 950 sobrevive SOLO como último
    recurso si la serie no está en disco, y en ese caso el pipeline lo avisa.
    """
    fila = re.search(r'\("Tipo de cambio[^\n]*\n[^\n]*', FUENTE)
    assert fila, "no encuentro la fila del tipo de cambio en el DCF"
    assert '"950"' not in fila.group(0), (
        "el tipo de cambio del DCF volvió a ser una constante. Tiene que salir de "
        "`_tipo_de_cambio_actual()`, que lee el dólar observado del Banco Central."
    )
    assert "_tipo_de_cambio_actual" in fila.group(0)


def test_el_beta_no_es_uno_para_todos():
    """Un beta fijo en 1,0 volvía el CAPM una identidad.

    Con Rf y ERP también fijos, Ke = 5,5% + 1 x 5,5% = 11% para las 232 empresas: una
    eléctrica muy apalancada y una empresa sin deuda salían con el mismo costo de
    patrimonio. Ahora se relevera con Hamada usando la deuda, el patrimonio y la tasa
    efectiva REALES de cada empresa.
    """
    assert "Beta apalancada (Hamada)" in FUENTE, "se perdió el beta relevereado"
    assert '("Beta (apalancada)", 1.0' not in FUENTE, "volvió el beta fijo en 1,0"


def test_los_escenarios_usan_el_wacc_real():
    """Los tres escenarios escribían los literales 0,12 / 0,10 / 0,08.

    O sea que NINGUNA de las tres valuaciones usaba el WACC calculado: una empresa con
    WACC 14% se valuaba igual que una con 7%, y el "rango de valuación" del resumen
    ejecutivo no decía nada sobre la empresa.
    """
    assert 'wacc_scenario = "0.12"' not in FUENTE
    assert 'wacc_scenario = "0.08"' not in FUENTE
    assert 'wacc_ref = find_cell_by_content' in FUENTE, (
        "los escenarios tienen que referenciar la celda del WACC de la hoja DCF"
    )


def test_el_multiplo_de_salida_se_deriva_del_modelo():
    """El 8,0x fijo no salía de la empresa, ni de comparables, ni del modelo.

    El "contraste de valor terminal" comparaba entonces la perpetuidad de Gordon contra un
    número arbitrario: no contrastaba nada. Ahora se muestra el múltiplo que la propia
    perpetuidad ya está aplicando, (1+g)/(WACC-g).
    """
    assert "Múltiplo implícito de Gordon (EV/EBITDA)" in FUENTE


def test_el_valor_por_accion_no_se_referencia_a_si_mismo():
    """La fila de conversión a pesos salía como `=IFERROR(B51*$B$26,"")`: circular.

    Cuando la empresa reporta en CLP, las etiquetas "Valor por Acción (DCF, {moneda})" y
    "Valor por Acción (DCF, CLP)" son la MISMA string, así que el dict de filas se quedaba
    con la última y la fórmula se apuntaba a sí misma. Excel la resolvía como vacío: la
    celda mostraba "$ -" junto a una fila duplicada con el mismo título.

    Ahora la fila de conversión sólo existe si los estados NO están en pesos.
    """
    assert "convierte = self.reporting_currency != \"CLP\"" in FUENTE
    assert 'r_dcf_clp = V["Valor por Acción (DCF, CLP)"] if convierte else r_dcf_moneda' in FUENTE


def test_el_rotulo_del_ano_base_no_se_sobrescribe_con_un_trimestre():
    """La celda decía "Año base: 2026Q1" mientras el modelo tomaba las ventas de 2025.

    `_find_base_annual_period()` elige a propósito el último año COMPLETO -- anualizar un
    trimestre suelto distorsiona a cualquier negocio estacional --, pero 300 líneas más
    abajo un bloque sobrescribía el rótulo con el último período disponible, que es un
    trimestre. El cálculo estaba bien; el rótulo mentía sobre el propio modelo.
    """
    assert 'cell_value and isinstance(cell_value, str) and "Año base" in cell_value' not in FUENTE, (
        "volvió el bloque que sobrescribe el rótulo del año base con un trimestre"
    )
