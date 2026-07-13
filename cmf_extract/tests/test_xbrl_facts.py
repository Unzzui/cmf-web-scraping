"""Pruebas del lector de hechos XBRL.

Cada una fija una trampa que YA nos mordió al escribir el módulo. No son pruebas
defensivas escritas por si acaso: son cicatrices.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cmf_extract import xbrl_facts as xf

RAIZ = Path(__file__).resolve().parents[2] / "data" / "XBRL" / "Total"
pytestmark = pytest.mark.skipif(not RAIZ.is_dir(), reason="no hay XBRL descargado")


def _empresas():
    return [d for d in sorted(RAIZ.iterdir()) if d.is_dir()]


def _ultimo_xbrl(empresa_dir: Path):
    periodos = list(xf.periodos_de(empresa_dir))
    return periodos[-1][2] if periodos else None


def test_codificacion_no_rompe_los_acentos():
    """Los XBRL vienen en DOS codificaciones: 22 en UTF-8 y 52 en ISO-8859-1.

    Forzar una sola convierte "Constitución" en "ConstituciÃ³n". Para las cifras da
    igual; para nombres y direcciones —que es lo que venimos a rescatar— destruye el dato.
    """
    arauco = next(RAIZ.glob("93458000-1_*"), None)
    if arauco is None:
        pytest.skip("Arauco no está descargado")

    doc = xf.leer(_ultimo_xbrl(arauco))
    nombres = [h.valor for h in doc.hechos if h.concepto == "NombreEntidadDeudora"]
    assert nombres, "sin hechos de NombreEntidadDeudora"
    assert any("Constitución" in n for n in nombres), nombres[:2]
    assert not any("Ã" in n for n in nombres), "mojibake: se decodificó con la codificación equivocada"


def test_la_unidad_se_resuelve_por_su_measure_no_por_su_id():
    """En LATAM 2019Q3: <xbrli:unit id="CLP"><measure>iso4217:USD</measure>.

    El id es una etiqueta arbitraria del emisor. Creerle habría dividido las cifras de
    LATAM por 900.
    """
    latam = next(RAIZ.glob("89862200-2_*"), None)
    if latam is None:
        pytest.skip("LATAM no está descargado")

    for anio, trimestre, ruta in xf.periodos_de(latam):
        if (anio, trimestre) != (2019, 3):
            continue
        doc = xf.leer(ruta)
        assert doc.moneda() == "USD", "se leyó el id de la unidad en vez de su measure"
        return
    pytest.skip("LATAM 2019Q3 no está en disco")


def test_el_hecho_consolidado_es_el_que_no_tiene_ejes():
    """En Arauco, 2.147 de 2.154 contextos tienen dimensión.

    "Tiene dimensión" NO es "es un segmento": la mayoría son desgloses de patrimonio,
    clases de activo fijo, tramos de morosidad. El consolidado es el hecho SIN ejes.
    """
    arauco = next(RAIZ.glob("93458000-1_*"), None)
    if arauco is None:
        pytest.skip("Arauco no está descargado")

    doc = xf.leer(_ultimo_xbrl(arauco))
    cons = [h for h in doc.consolidados("Revenue") if h.es_numerico]
    assert cons, "sin ingresos consolidados"
    assert all(h.contexto.es_consolidado for h in cons)
    assert all(not h.contexto.ejes for h in cons)


def test_las_hojas_de_un_eje_reconstruyen_su_raiz():
    """LA prueba del extractor de segmentos, sobre TODAS las empresas en disco.

    Un eje no es una lista plana, es un árbol:

        OperatingSegmentsMember          <- la raíz: vale el total
          ReportableSegmentsMember       <- subtotal
            CELULOSA, MADERAS            <- segmentos de verdad
          AllOtherSegmentsMember         <- subtotal del residual
            OTROS                        <- segmento de verdad

    Sumar el eje entero sin distinguir daba 4.448 millones donde Arauco tiene 1.482:
    TRES VECES la cifra. Si las hojas suman su raíz, la detección es correcta.

    OJO: la raíz NO es el consolidado. Los ingresos de un segmento incluyen las ventas
    a OTROS segmentos; el consolidado sólo cuenta las ventas a terceros. La diferencia
    son las eliminaciones, y es IFRS 8 funcionando bien. En ENAP:

        hojas 1.098.195.514.000  −  eliminaciones 344.869.872.000
              +  no asignado 1.411.434.000  =  754.737.076.000  = consolidado, al peso.

    Y "hoja del eje" tampoco basta: en SMU, `UnallocatedAmountsMember` ES una hoja, pero
    cuelga de las partidas de RECONCILIACIÓN, no de los segmentos. Un segmento es una
    hoja que DESCIENDE de `OperatingSegmentsMember`.
    """
    revisadas = 0
    for empresa in _empresas():
        ruta = _ultimo_xbrl(empresa)
        if ruta is None:
            continue
        doc = xf.leer(ruta)
        hijos = xf.arbol(ruta)
        segmentos = xf.hojas_bajo(hijos, "OperatingSegmentsMember")

        raices = [
            h for h in doc.hechos
            if h.concepto == "Revenue" and h.es_numerico
            and h.contexto.ejes == (("OperatingSegmentsAxis", "OperatingSegmentsMember"),)
        ]
        if not raices:
            continue
        raiz = max(raices, key=lambda h: h.contexto.fin or "")

        hojas = [
            h for h in xf.hojas_de_eje(doc, "OperatingSegmentsAxis", segmentos, "Revenue")
            if h.es_numerico
            and h.contexto.inicio == raiz.contexto.inicio
            and h.contexto.fin == raiz.contexto.fin
        ]
        if not hojas:
            continue

        suma = sum(h.numero for h in hojas)
        desvio = abs(suma - raiz.numero) / abs(raiz.numero)
        assert desvio < 0.005, (
            f"{empresa.name}: los segmentos suman {suma:,.0f} y su total vale {raiz.numero:,.0f}"
        )
        revisadas += 1

    assert revisadas >= 20, f"sólo se pudo validar {revisadas} empresas"


def test_los_segmentos_tienen_nombre_humano():
    """Los miembros propios de la empresa se llaman `Item804`, no "CELULOSA".

    El nombre vive en el linkbase de etiquetas, que es OTRO archivo. Sin leerlo, el
    segmento más grande de Arauco se llamaría "Item804" en la web.
    """
    arauco = next(RAIZ.glob("93458000-1_*"), None)
    if arauco is None:
        pytest.skip("Arauco no está descargado")

    ruta = _ultimo_xbrl(arauco)
    etiquetas = xf.etiquetas(ruta)
    assert etiquetas, "no se leyó el linkbase de etiquetas"
    assert "CELULOSA" in etiquetas.values()
    assert "MADERAS" in etiquetas.values()
