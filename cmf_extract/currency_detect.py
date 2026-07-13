"""Moneda de reporte, leída del XBRL que la empresa le entrega a la CMF.

Por qué existe este módulo
--------------------------
El pipeline escribía ``currency = 'CLP'`` para TODO. En producción quedaron 837.905
filas etiquetadas como pesos, pero 17 empresas reportan en DÓLARES: SQM, COPEC, CMPC,
LATAM, COLBÚN, ENEL AMÉRICAS, ENGIE, CAP, VAPORES, BLUMAR, CINTAC, IANSA,
INVERSIONES CMPC, AGROSUPER, ENEL CHILE, ENEL GENERACIÓN y ELÉCTRICA PEHUENCHE.

Consecuencias que eso tuvo en la web:
  - Los múltiplos dividían un market cap en PESOS por una utilidad en DÓLARES. El P/U
    de SQM daba 30.987 y la guarda de cordura lo anulaba, así que SQM, COPEC y CMPC
    simplemente NO mostraban múltiplos y nadie sabía por qué.
  - El screener ordenado por flujo de caja libre ponía a COPEC ÚLTIMO, cuando genera
    2,6 veces más caja que Falabella, que aparecía primera.
  - El Excel que el cliente paga dice "Moneda: CLP" en la portada. Para SQM, eso es
    lisa y llanamente falso.

Y lo más incómodo: el dato SIEMPRE estuvo en el archivo. El XBRL lo declara explícito.

LA MONEDA ES UN ATRIBUTO DEL PERÍODO, NO DE LA EMPRESA
------------------------------------------------------
Hay empresas que cambian a mitad de su serie histórica:
    ENEL CHILE          CLP → USD  en 2025
    ENEL GENERACIÓN     CLP → USD  en 2025
    ELÉCTRICA PEHUENCHE CLP → USD  en 2025
    AGROSUPER           CLP → USD  en 2021
    ENEL AMÉRICAS       CLP → USD  en 2017
Guardar una sola moneda por empresa deja media serie mal etiquetada. Por eso este
módulo devuelve un mapa año → moneda.

CUIDADO: EL ID DE LA UNIDAD MIENTE
----------------------------------
En el XBRL de LATAM 2019Q3::

    <xbrli:unit id="CLP"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>

Todos los hechos apuntan a ``unitRef="CLP"``, pero la moneda REAL es el dólar. El
``id`` es una etiqueta arbitraria que elige el emisor; la única fuente de verdad es el
``<measure>``, que es ISO 4217. Leer el id habría dividido las cifras de LATAM por 700.

Por eso siempre se resuelve: unitRef → id de la unidad → measure.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

# Monedas que la CMF acepta como moneda de presentación.
MONEDAS_VALIDAS = {"CLP", "USD", "EUR"}

_UNIT_RE = re.compile(
    r'<xbrli:unit[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:unit>', re.DOTALL | re.IGNORECASE
)
_ISO_RE = re.compile(r"iso4217:([A-Z]{3})", re.IGNORECASE)
_UNITREF_RE = re.compile(r'unitRef="([^"]+)"', re.IGNORECASE)
# ..._202512_extracted  →  año 2025, mes 12
_PERIODO_RE = re.compile(r"_(\d{4})(\d{2})_extracted$")

_MES_A_TRIMESTRE = {3: 1, 6: 2, 9: 3, 12: 4}


def moneda_de_xbrl(xbrl_path: Path | str) -> str | None:
    """Moneda de reporte de UN estado financiero.

    Se cuenta qué unidad usan los HECHOS, no sólo cuáles están declaradas: un estado
    puede declarar dos monedas y usar una sola. Gana la que más hechos monetarios tiene.

    El archivo viene en iso-8859-1 (lo genera DBNeT), no en UTF-8.
    """
    try:
        raw = Path(xbrl_path).read_bytes().decode("iso-8859-1", errors="replace")
    except OSError:
        return None

    # id de la unidad → moneda ISO real. NUNCA confiar en el id a secas.
    unidad_a_moneda: dict[str, str] = {}
    for uid, cuerpo in _UNIT_RE.findall(raw):
        iso = _ISO_RE.search(cuerpo)
        if iso:
            moneda = iso.group(1).upper()
            if moneda in MONEDAS_VALIDAS:
                unidad_a_moneda[uid] = moneda

    if not unidad_a_moneda:
        return None

    conteo: Counter[str] = Counter()
    for uid in _UNITREF_RE.findall(raw):
        moneda = unidad_a_moneda.get(uid)
        if moneda:
            conteo[moneda] += 1

    if not conteo:
        return None
    return conteo.most_common(1)[0][0]


def monedas_por_periodo(empresa_dir: Path | str) -> dict[tuple[int, int], str]:
    """Mapa (año, trimestre) → moneda, leyendo un XBRL por período.

    `empresa_dir` es la carpeta de la empresa en data/XBRL/Total/, que contiene un
    subdirectorio ``*_YYYYMM_extracted`` por estado financiero.
    """
    empresa_dir = Path(empresa_dir)
    resultado: dict[tuple[int, int], str] = {}
    if not empresa_dir.is_dir():
        return resultado

    for sub in sorted(empresa_dir.iterdir()):
        if not sub.is_dir():
            continue
        m = _PERIODO_RE.search(sub.name)
        if not m:
            continue
        anio, mes = int(m.group(1)), int(m.group(2))
        trimestre = _MES_A_TRIMESTRE.get(mes)
        if trimestre is None:
            continue

        xbrl = next(sub.glob("*.xbrl"), None)
        if xbrl is None:
            continue

        moneda = moneda_de_xbrl(xbrl)
        if moneda:
            resultado[(anio, trimestre)] = moneda

    return resultado


def monedas_por_anio(empresa_dir: Path | str) -> dict[int, str]:
    """Mapa año → moneda del CIERRE de ese año (Q4).

    Es lo que necesita la portada del Excel y cualquier serie anual. Si un año no tiene
    Q4, se usa el trimestre más reciente que sí exista.
    """
    por_periodo = monedas_por_periodo(empresa_dir)
    por_anio: dict[int, str] = {}
    for (anio, trimestre), moneda in sorted(por_periodo.items()):
        # El más alto (Q4 si existe) gana, porque es el cierre.
        por_anio[anio] = moneda
    return por_anio


def resumen_moneda(empresa_dir: Path | str) -> tuple[str, list[str]]:
    """Etiqueta para la portada del Excel y la lista de cambios de moneda.

    Devuelve, por ejemplo::

        ("USD", ["CLP hasta 2024", "USD desde 2025"])

    El analista TIENE que ver esto. Un Excel con cifras en dólares y una portada que
    dice "Moneda: CLP" no es un detalle de formato: es un error de un factor de 900 que
    el usuario sólo va a descubrir cuando ya tomó una decisión con esos números.
    """
    por_anio = monedas_por_anio(empresa_dir)
    if not por_anio:
        return "", []

    anios = sorted(por_anio)
    actual = por_anio[anios[-1]]

    # Tramos de moneda: [(moneda, año_inicio, año_fin), ...]
    tramos: list[tuple[str, int, int]] = []
    for anio in anios:
        moneda = por_anio[anio]
        if tramos and tramos[-1][0] == moneda:
            tramos[-1] = (moneda, tramos[-1][1], anio)
        else:
            tramos.append((moneda, anio, anio))

    if len(tramos) == 1:
        return actual, []

    # Hubo cambio de moneda: hay que decirlo, porque la serie NO es comparable consigo
    # misma sin convertir.
    detalle = []
    for i, (moneda, desde, hasta) in enumerate(tramos):
        if i == len(tramos) - 1:
            detalle.append(f"{moneda} desde {desde}")
        else:
            detalle.append(f"{moneda} hasta {hasta}")
    return actual, detalle
