"""El arbol de presentacion no debe aportar cuentas sin nombre.

Regresion real (jul-2026, REDMEGACENTRO 76377075-3): su reporte de Arelle del periodo
2024-12 salio con 110 filas donde el arbol trae el QName crudo (`ifrs-full:Revenue`) en
vez de la etiqueta, porque ese XBRL no resolvio el linkbase de etiquetas. El periodo
2025-06 del mismo emisor trae 3.762 filas bien etiquetadas.

Como `_fusionar` inserta en el orden maestro toda cuenta que no reconoce, esas 38 filas
entraron como cuentas NUEVAS y el estado de resultados aparecio DUPLICADO en la ficha y
en el Excel que se vende: una vez en jerga inglesa y otra en español, con los mismos
valores. Verificado contra produccion: las 38 tenian su equivalente en español con la
misma cifra en el mismo periodo.
"""
import csv

import pytest

from cmf_extract import presentation_order as po


QNAMES = [
    "ifrs-full:Revenue",
    "ifrs-full:ProfitLossBeforeTax",
    "ifrs-full:BasicEarningsLossPerShare",
    "ifrs:CostOfSales",
    "cl-ci:OtrosIngresos",
]

ETIQUETAS_REALES = [
    "Ingresos de actividades ordinarias",
    "Costo de ventas",
    "Ganancia bruta",
    "Estado de resultados [sinopsis]",
    "Ganancia (pérdida) [sinopsis]",
    "Otras ganancias (pérdidas)",
    "Resultados por unidades de reajuste",
    "Ganancia (pérdida), atribuible a los propietarios de la controladora",
    # Lleva dos puntos y NO es un QName: el filtro no puede confundirla.
    "Deudores comerciales: neto",
]


@pytest.mark.parametrize("valor", QNAMES)
def test_detecta_qname_sin_resolver(valor):
    assert po.es_qname_sin_resolver(valor)


@pytest.mark.parametrize("valor", ETIQUETAS_REALES)
def test_no_confunde_una_etiqueta_de_verdad(valor):
    assert not po.es_qname_sin_resolver(valor)


def _escribir_presentacion(ruta, cuentas):
    """Reproduce el formato del reporte de presentacion de Arelle."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["Presentation Relationships", "", "Pref. Label", "Type", "References"])
        w.writerow(["[310000] Estado del resultado, por funcion de gasto", "", "", "", ""])
        for cuenta in cuentas:
            w.writerow(["", cuenta, "", "", ""])


def test_un_periodo_sin_etiquetas_no_aporta_cuentas(tmp_path):
    """El periodo mudo se ignora; el bien etiquetado manda."""
    ruta = tmp_path / "presentation_76377075_202412_es.csv"
    _escribir_presentacion(ruta, ["ifrs-full:Revenue", "ifrs-full:CostOfSales"])

    assert po.leer_presentacion(ruta).get("310000", []) == []


def test_el_periodo_bien_etiquetado_se_conserva_entero(tmp_path):
    ruta = tmp_path / "presentation_76377075_202506_es.csv"
    _escribir_presentacion(ruta, ["Ingresos de actividades ordinarias", "Costo de ventas"])

    assert po.leer_presentacion(ruta)["310000"] == [
        "Ingresos de actividades ordinarias",
        "Costo de ventas",
    ]


def test_periodo_mixto_conserva_solo_lo_que_tiene_nombre(tmp_path):
    """Ni se cae ni arrastra la cuenta muda: se queda con las que sabe nombrar."""
    ruta = tmp_path / "presentation_76377075_202412_es.csv"
    _escribir_presentacion(
        ruta,
        ["Ingresos de actividades ordinarias", "ifrs-full:CostOfSales", "Ganancia bruta"],
    )

    assert po.leer_presentacion(ruta)["310000"] == [
        "Ingresos de actividades ordinarias",
        "Ganancia bruta",
    ]
