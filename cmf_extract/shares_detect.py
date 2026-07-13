"""Número de acciones, leído del XBRL que la empresa le entrega a la CMF.

Por qué existe este módulo
--------------------------
El "Total de acciones" que llega a la base viene con la escala rota: a veces en
unidades, a veces en miles. Y el código de la web lo SABE y lo tapa:

    // Un market cap por debajo casi siempre significa "Total de acciones"
    // mal cargado (viene en miles o parcial) → mejor no mostrar nada.
    const marketCap = rawMarketCap >= 1e10 ? rawMarketCap : null

O sea que, en vez de arreglar el dato, se anula el market cap entero — y con él, TODOS
los múltiplos de esa empresa. El usuario ve un hueco y nadie sabe por qué. Es el mismo
patrón que escondía el P/U de SQM durante meses.

Y en el DCF es peor, porque ahí no hay guarda:

    price_per_share = (eq * 1000) / shares

Si `shares` viene en miles, el PRECIO OBJETIVO sale 1.000 veces más alto. Es el número
sobre el que un analista decide comprar o vender.

EL PROBLEMA DE LOS TICKERS
--------------------------
Sólo 42 de las 218 empresas tienen ticker, así que Yahoo no puede validar las otras 176
(Celulosa Arauco, por ejemplo, no cotiza: es filial de Copec).

Pero el XBRL sí. En XBRL la unidad `xbrli:shares` es un CONTEO por definición — no admite
"miles" ni ninguna otra escala. El número verdadero está en el documento fuente para las
218, con ticker o sin él:

    AGUAS ANDINAS      6.118.965.160    (~6,1 mil millones)   ✓
    SQM                  285.637.808    (~285,6 millones)     ✓
    CELULOSA ARAUCO      131.893.786    — y no tiene ticker   ✓

CÓMO SE ELIGE EL VALOR
----------------------
Un estado trae el período actual Y el comparativo del año anterior. NO se toma el
máximo: si la empresa recompró acciones, el máximo sería el dato viejo. Se resuelve el
`contextRef` de cada hecho contra la fecha de cierre del estado, que es la única forma
de saber a qué período pertenece cada número.
"""

from __future__ import annotations

import re
from pathlib import Path

# Conceptos IFRS que declaran el número de acciones, en orden de preferencia.
# `NumberOfSharesOutstanding` es el que corresponde al market cap (las que están en
# circulación). `Issued` puede incluir acciones en tesorería.
CONCEPTOS = (
    "NumberOfSharesOutstanding",
    "NumberOfSharesIssuedAndFullyPaid",
    "NumberOfSharesIssued",
    "NumberOfSharesAuthorised",
)

_UNIT_RE = re.compile(
    r'<xbrli:unit[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:unit>', re.DOTALL | re.IGNORECASE
)
_CONTEXT_RE = re.compile(
    r'<xbrli:context[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:context>', re.DOTALL | re.IGNORECASE
)
_INSTANT_RE = re.compile(r"<xbrli:instant>([\d\-]+)</xbrli:instant>", re.IGNORECASE)
_ENDDATE_RE = re.compile(r"<xbrli:endDate>([\d\-]+)</xbrli:endDate>", re.IGNORECASE)
_PERIODO_RE = re.compile(r"_(\d{4})(\d{2})_extracted$")

_ULTIMO_DIA = {3: 31, 6: 30, 9: 30, 12: 31}


def _fecha_cierre(yyyyymm: str) -> str | None:
    """'202512' -> '2025-12-31'."""
    try:
        anio, mes = int(str(yyyyymm)[:4]), int(str(yyyyymm)[4:6])
    except (TypeError, ValueError):
        return None
    dia = _ULTIMO_DIA.get(mes)
    return f"{anio:04d}-{mes:02d}-{dia:02d}" if dia else None


def acciones_de_xbrl(xbrl_path: Path | str, fecha_cierre: str | None = None) -> float | None:
    """Acciones en circulación al cierre del estado. En UNIDADES.

    `fecha_cierre` acota los hechos al período del estado. Sin ella, el comparativo del
    año anterior puede colarse — y si la empresa recompró acciones, el número quedaría
    inflado.
    """
    try:
        raw = Path(xbrl_path).read_bytes().decode("iso-8859-1", errors="replace")
    except OSError:
        return None

    # 1) Qué unidades son un CONTEO de acciones. Ojo: el `id` de la unidad es una
    #    etiqueta arbitraria del emisor (en LATAM una unidad llamada "CLP" medía USD),
    #    así que se mira el <measure>, nunca el nombre.
    unidades_shares = {
        uid for uid, cuerpo in _UNIT_RE.findall(raw) if "xbrli:shares" in cuerpo.lower()
    }
    if not unidades_shares:
        return None

    # 2) Cada contexto, a qué fecha corresponde.
    contexto_fecha: dict[str, str] = {}
    for cid, cuerpo in _CONTEXT_RE.findall(raw):
        m = _INSTANT_RE.search(cuerpo) or _ENDDATE_RE.search(cuerpo)
        if m:
            contexto_fecha[cid] = m.group(1)

    # 3) Los hechos de acciones, por concepto y fecha.
    hechos: dict[str, dict[str, float]] = {}
    patron = re.compile(
        r'<([\w\-]+:[\w\-]+)[^>]*\bcontextRef="([^"]+)"[^>]*\bunitRef="([^"]+)"[^>]*>([^<]+)</\1>'
    )
    for tag, cref, uref, valor in patron.findall(raw):
        if uref not in unidades_shares:
            continue
        concepto = tag.split(":")[-1]
        if concepto not in CONCEPTOS:
            continue
        try:
            v = float(valor.strip())
        except ValueError:
            continue
        if v <= 0:
            continue
        fecha = contexto_fecha.get(cref, "")
        hechos.setdefault(concepto, {})[fecha] = v

    if not hechos:
        return None

    # 4) Elegir. Primero el concepto más específico, y dentro de él la fecha del cierre
    #    del estado. Si no hay match exacto de fecha, la más reciente.
    for concepto in CONCEPTOS:
        por_fecha = hechos.get(concepto)
        if not por_fecha:
            continue
        if fecha_cierre and fecha_cierre in por_fecha:
            return por_fecha[fecha_cierre]
        fecha_max = max(por_fecha.keys())
        return por_fecha[fecha_max]

    return None


def acciones_por_periodo(empresa_dir: Path | str) -> dict[tuple[int, int], float]:
    """Mapa (año, trimestre) -> acciones en circulación, en unidades."""
    empresa_dir = Path(empresa_dir)
    resultado: dict[tuple[int, int], float] = {}
    if not empresa_dir.is_dir():
        return resultado

    for sub in sorted(empresa_dir.iterdir()):
        if not sub.is_dir():
            continue
        m = _PERIODO_RE.search(sub.name)
        if not m:
            continue
        anio, mes = int(m.group(1)), int(m.group(2))
        trimestre = {3: 1, 6: 2, 9: 3, 12: 4}.get(mes)
        if trimestre is None:
            continue
        xbrl = next(sub.glob("*.xbrl"), None)
        if xbrl is None:
            continue
        n = acciones_de_xbrl(xbrl, _fecha_cierre(f"{anio}{mes:02d}"))
        if n:
            resultado[(anio, trimestre)] = n

    return resultado
