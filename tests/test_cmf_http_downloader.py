"""Tests del descargador HTTP de la CMF.

El HTML está calcado de la página real de SONDA (RUT 83628100) en 2026-03 y 2026-06: el
caso con XBRL y el caso sin XBRL, que es donde el selector se equivocaba.
"""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from src.xbrl import cmf_xbrl_http_downloader as dl
from src.xbrl.cmf_xbrl_http_downloader import _declara_sin_xbrl, _find_xbrl_link


def _anchor(texto: str, auth: str) -> str:
    return (f'<a href="../inc/inf_financiera/ifrs/safec_ifrs_verarchivo.php'
            f'?auth={auth}&send=xxx">{texto}</a>')


# La CMF lista los documentos con el PDF primero y hrefs indistinguibles entre sí
# (todos `safec_ifrs_verarchivo.php?auth=…&send=…`): el texto es el único discriminante.
_PDF = _anchor("Estados financieros (PDF)", "aaa")
_DECL = _anchor("Declaración de responsabilidad", "bbb")
_HECHOS = _anchor("Hechos Relevantes", "ccc")
_XBRL = _anchor("Estados financieros (XBRL)", "ddd")
_ANALISIS = _anchor("Análisis Razonado", "eee")

# Enlace de navegación del portal: dice XBRL pero no es de descarga.
_NAV = '<a href="/portal/principal/605/w3-propertyvalue-18563.html">XBRL Mercado de Valores</a>'

CON_XBRL = f"<html><body>{_NAV}{_PDF}{_DECL}{_HECHOS}{_XBRL}{_ANALISIS}</body></html>"

SIN_XBRL = (f"<html><body>{_NAV}{_PDF}{_DECL}{_HECHOS}{_ANALISIS}"
            "<p>La entidad no registra envío de archivo XBRL para el periodo    2026-06;</p>"
            "</body></html>")


def test_toma_el_enlace_del_xbrl_y_no_el_primero_de_la_lista():
    href = _find_xbrl_link(CON_XBRL)
    assert href is not None
    assert "auth=ddd" in href  # el del XBRL, no el del PDF (auth=aaa)


def test_sin_anchor_de_xbrl_no_devuelve_el_pdf():
    """EL test. El fallback viejo aceptaba cualquier `verarchivo…ifrs` y se quedaba con
    "Estados financieros (PDF)", que encabeza la lista: en SONDA 2026-06 se bajaban 2,7 MB
    de PDF por ciclo para descartarlos por no ser ZIP, y el período quedaba rotulado como
    inconcluyente en vez de como la ausencia real que era."""
    assert _find_xbrl_link(SIN_XBRL) is None


def test_ignora_los_enlaces_informativos_del_sitio():
    """"XBRL Mercado de Valores" es navegación del portal, no un archivo."""
    assert _find_xbrl_link(f"<html><body>{_NAV}</body></html>") is None


def test_reconoce_el_aviso_explicito_de_la_cmf():
    """Distinguir "la empresa todavía no lo mandó" de "algo falló" es lo que evita tener
    que ir a mirar el sitio a mano cuando un período no aparece."""
    assert _declara_sin_xbrl(SIN_XBRL) is True
    assert _declara_sin_xbrl(CON_XBRL) is False


def test_el_aviso_tolera_acentos_y_mayusculas():
    variantes = [
        "La entidad no registra envio de archivo XBRL para el periodo 2026-06;",
        "LA ENTIDAD NO REGISTRA ENVÍO DE ARCHIVO XBRL PARA EL PERIODO 2026-06;",
    ]
    for html in variantes:
        assert _declara_sin_xbrl(html) is True


def test_el_aviso_se_detecta_con_entidades_html():
    """Como viene de verdad de la CMF: `env&iacute;o`, no `envío`. Buscar sobre el HTML
    crudo no matcheaba nunca, y el único síntoma era que el aviso no salía — una falla
    invisible en el detector que existe justamente para hacer visible una ausencia."""
    crudo = ("<p><h3>La entidad no registra env&iacute;o de archivo XBRL "
             "para el periodo    2026-06; </h3></p>")
    assert _declara_sin_xbrl(crudo) is True


# ------------------------------------------------- corto-circuito del borde reciente
RUT = "12345678"


class _Resp:
    def __init__(self, text):
        self.text = text
        self.content = b""
        self.status_code = 200
        self.headers = {}

    def raise_for_status(self):
        return None


@pytest.fixture
def repo_falso():
    """cwd temporal con un período viejo ya en disco.

    Hace falta para que 2020 quede en el "borde reciente": el borde son los períodos más
    nuevos que lo descargado, y sin nada en disco todo caería al histórico, que no tiene
    corto-circuito y no es lo que se quiere probar.
    """
    with TemporaryDirectory() as tmp:
        previo = os.getcwd()
        os.chdir(tmp)
        ext = (Path(tmp) / "data" / "XBRL" / "Total" / f"{RUT}-9_TEST"
               / f"Estados_financieros_(XBRL){RUT}_201912_extracted")
        ext.mkdir(parents=True)
        (ext / f"{RUT}_201912_C.xbrl").write_text("x")
        (ext / f"{RUT}_201912_C.xsd").write_text("x")
        try:
            yield
        finally:
            os.chdir(previo)


def _correr(monkeypatch, comportamiento):
    """Corre la descarga de 2020 con `comportamiento(yyyymm) -> 'ausente'|'error'`.

    Devuelve los períodos por los que se preguntó a la CMF.
    """
    consultados = []

    def _stub(session, method, url, **kw):
        if method == "GET":
            return _Resp("<html></html>")
        data = kw.get("data") or {}
        yyyymm = f"{data['aa']}{data['mm']}"
        consultados.append(yyyymm)
        if comportamiento(yyyymm) == "error":
            raise RuntimeError("bloqueo simulado de la CMF")
        return _Resp(SIN_XBRL)

    monkeypatch.setattr(dl, "_polite_request", _stub)
    dl.download_cmf_xbrl_http(RUT, start_year=2020, end_year=2020, max_workers=1)
    return consultados


def test_una_ausencia_concluyente_si_corta_el_resto_del_borde(repo_falso, monkeypatch):
    """El corto-circuito es deseado cuando la CMF responde limpio: si no publicó el
    trimestre viejo, los siguientes tampoco, y sondearlos son requests al pedo."""
    consultados = _correr(monkeypatch, lambda _: "ausente")
    assert "202003" in consultados
    assert "202006" not in consultados


def test_un_resultado_inconcluyente_no_da_por_no_publicado_el_resto(repo_falso, monkeypatch):
    """EL test. El corto-circuito se apoya en "este período no existe, así que los
    posteriores tampoco"; con un bloqueo de la CMF esa premisa no se sostiene. Antes el
    flag `definitive` se leía y se descartaba (`res, _def = _fetch(...)`), así que un 403
    transitorio escondía todos los trimestres siguientes y los rotulaba en el log como
    "aún no publicado" — una afirmación que no nos constaba."""
    consultados = _correr(monkeypatch,
                          lambda p: "error" if p == "202003" else "ausente")
    assert "202003" in consultados
    assert "202006" in consultados, "un inconcluyente no debe cortar el borde reciente"
