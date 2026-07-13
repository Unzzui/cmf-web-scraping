"""Lector de hechos XBRL. El cimiento de todo lo que se extraiga del documento fuente.

POR QUÉ EXISTE
--------------
FinDataChile depende de APIs externas (Yahoo) para datos que la empresa ya le declaró a
la CMF, firmados, en un documento público. Cada API es una dependencia que se cae, cambia
de contrato, cobra, o simplemente no cubre a las 176 empresas chilenas que no cotizan.

El XBRL tiene 2.005 conceptos distintos. Este módulo los lee TODOS, sin decidir por
adelantado cuáles importan: los extractores de arriba eligen.

LAS CUATRO TRAMPAS DEL XBRL (todas verificadas contra los archivos reales)
--------------------------------------------------------------------------

1) LA CODIFICACIÓN NO ES UNA. De los 74 archivos en disco, 22 declaran UTF-8 y 52
   ISO-8859-1. Forzar una sola convierte "Constitución" en "ConstituciÃ³n". Para las
   cifras no se nota; para nombres, direcciones y giros — que es justo lo que queremos
   rescatar — arruina el dato. Aquí se respeta lo que declara el archivo.

2) EL id DE LA UNIDAD MIENTE. En el XBRL de LATAM 2019Q3:

       <xbrli:unit id="CLP"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>

   Todos los hechos apuntan a unitRef="CLP" y la moneda real es el DÓLAR. El `id` es una
   etiqueta arbitraria del emisor; la única fuente de verdad es el <measure>, que es ISO
   4217. Leer el id habría dividido las cifras de LATAM por 900.

3) "TIENE DIMENSIÓN" NO ES "ES UN SEGMENTO". En Arauco, 2.147 de 2.154 contextos tienen
   dimensión — pero casi todas son desgloses de patrimonio, clases de activo fijo,
   tramos de morosidad… Tratar cualquier hecho dimensionado como un segmento de negocio
   importaría basura y, peor, DUPLICARÍA cifras que ya están en el consolidado.

   La regla: el hecho CONSOLIDADO es el que NO tiene dimensiones. Todo lo demás es un
   desglose a lo largo de un eje concreto, y hay que saber cuál.

4) EL VALOR ESTÁ EN UNIDADES DE LA MONEDA, NO EN MILES. El resto del pipeline divide por
   1.000 al guardar. Este módulo NO escala nada: devuelve el número tal como está en el
   documento. Quien guarde, escala — y que quede escrito dónde.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

# ─────────────────────────────────────────────────────────────── Codificación
_DECL_RE = re.compile(rb'encoding\s*=\s*["\']([\w\-]+)["\']', re.I)


def leer_texto(ruta: Path | str) -> str:
    """El contenido del XBRL, decodificado con la codificación que el archivo DECLARA.

    Ver trampa (1) del encabezado. Si la declaración miente o falta, se intenta UTF-8 y
    se cae a ISO-8859-1, que es lo que genera DBNeT.
    """
    crudo = Path(ruta).read_bytes()
    m = _DECL_RE.search(crudo[:200])
    declarada = m.group(1).decode("ascii", "replace").lower() if m else None

    for enc in (declarada, "utf-8", "iso-8859-1"):
        if not enc:
            continue
        try:
            return crudo.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return crudo.decode("iso-8859-1", errors="replace")


# ─────────────────────────────────────────────────────────────── Unidades
_UNIT_RE = re.compile(r'<xbrli:unit[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:unit>', re.S | re.I)
_ISO_RE = re.compile(r"iso4217:([A-Za-z]{3})")

MONEDAS_ISO = {"CLP", "USD", "EUR", "GBP", "JPY", "BRL", "ARS", "PEN", "COP", "MXN", "UF"}


@dataclass(frozen=True)
class Unidad:
    """Qué mide un hecho. `moneda` sólo tiene sentido si tipo == 'moneda'."""
    tipo: str                    # 'moneda' | 'acciones' | 'ratio' | 'otro'
    moneda: str | None = None    # código ISO 4217, resuelto del <measure>


def _unidades(raw: str) -> dict[str, Unidad]:
    """id de unidad → qué mide. Ver trampa (2): se lee el measure, NUNCA el id."""
    fuera: dict[str, Unidad] = {}
    for uid, cuerpo in _UNIT_RE.findall(raw):
        bajo = cuerpo.lower()
        iso = _ISO_RE.search(cuerpo)
        if iso:
            fuera[uid] = Unidad("moneda", iso.group(1).upper())
        elif "shares" in bajo:
            fuera[uid] = Unidad("acciones")
        elif "pure" in bajo:
            fuera[uid] = Unidad("ratio")
        else:
            fuera[uid] = Unidad("otro")
    return fuera


# ─────────────────────────────────────────────────────────────── Contextos
_CTX_RE = re.compile(r'<xbrli:context[^>]*id="([^"]+)"[^>]*>(.*?)</xbrli:context>', re.S | re.I)
_INSTANT_RE = re.compile(r"<xbrli:instant>([\d\-]+)</xbrli:instant>", re.I)
_INICIO_RE = re.compile(r"<xbrli:startDate>([\d\-]+)</xbrli:startDate>", re.I)
_FIN_RE = re.compile(r"<xbrli:endDate>([\d\-]+)</xbrli:endDate>", re.I)
_MIEMBRO_RE = re.compile(r'<xbrldi:(?:explicit|typed)Member[^>]*dimension="([^"]+)"[^>]*>([^<]*)<', re.I)


@dataclass(frozen=True)
class Contexto:
    """A qué período y a qué desglose pertenece un hecho."""
    id: str
    inicio: str | None            # None si es un saldo puntual (instant)
    fin: str | None               # la fecha del saldo, o el cierre del período
    ejes: tuple[tuple[str, str], ...] = ()   # ((eje, miembro), …), ya sin prefijo

    @property
    def es_saldo(self) -> bool:
        """Un saldo (activos al 31/3) vs un flujo (ventas de enero a marzo)."""
        return self.inicio is None

    @property
    def es_consolidado(self) -> bool:
        """Sin ejes = la cifra del consolidado. Ver trampa (3).

        Es la ÚNICA que se puede sumar con otras del mismo estado sin duplicar.
        """
        return not self.ejes


def _contextos(raw: str) -> dict[str, Contexto]:
    fuera: dict[str, Contexto] = {}
    for cid, cuerpo in _CTX_RE.findall(raw):
        inst = _INSTANT_RE.search(cuerpo)
        if inst:
            inicio, fin = None, inst.group(1)
        else:
            ini, f = _INICIO_RE.search(cuerpo), _FIN_RE.search(cuerpo)
            inicio = ini.group(1) if ini else None
            fin = f.group(1) if f else None
            if inicio is None and fin is None:
                continue

        ejes = tuple(
            (eje.split(":")[-1], miembro.split(":")[-1])
            for eje, miembro in _MIEMBRO_RE.findall(cuerpo)
        )
        fuera[cid] = Contexto(id=cid, inicio=inicio, fin=fin, ejes=ejes)
    return fuera


# ─────────────────────────────────────────────────────────────── Hechos
_HECHO_RE = re.compile(r'<([\w\-]+):([\w\-]+)\b([^>]*)\bcontextRef="([^"]+)"([^>]*)>([^<]*)</\1:\2>')
_UNITREF_RE = re.compile(r'unitRef="([^"]+)"')
_DECIMALS_RE = re.compile(r'decimals="([^"]+)"')

_IGNORAR_PREFIJO = {"xbrli", "link", "xlink", "xsi", "xbrldi"}


@dataclass(frozen=True)
class Hecho:
    concepto: str                 # sin prefijo: 'Revenue', 'TasaEfectiva'…
    valor: str                    # crudo, tal como viene. Ver trampa (4).
    contexto: Contexto
    unidad: Unidad | None = None  # None => es texto o fecha
    decimales: str | None = None

    @property
    def numero(self) -> float | None:
        """El valor como número, o None si no lo es. NO escala nada."""
        try:
            return float(self.valor.replace(",", "").strip())
        except (ValueError, AttributeError):
            return None

    @property
    def es_numerico(self) -> bool:
        return self.unidad is not None and self.numero is not None


@dataclass
class Documento:
    """Un estado financiero XBRL, ya parseado."""
    ruta: Path
    hechos: list[Hecho] = field(default_factory=list)

    # ---- consultas -----------------------------------------------------
    def consolidados(self, concepto: str) -> list[Hecho]:
        """Los hechos de un concepto SIN desglose. Los únicos comparables entre sí."""
        return [h for h in self.hechos
                if h.concepto == concepto and h.contexto.es_consolidado]

    def por_eje(self, eje: str, concepto: str | None = None) -> list[Hecho]:
        """Los hechos desglosados a lo largo de un eje (p. ej. 'OperatingSegmentsAxis')."""
        return [h for h in self.hechos
                if any(e == eje for e, _ in h.contexto.ejes)
                and (concepto is None or h.concepto == concepto)]

    def moneda(self) -> str | None:
        """La moneda de los hechos monetarios. Gana la que más hechos tiene."""
        conteo: dict[str, int] = {}
        for h in self.hechos:
            if h.unidad and h.unidad.tipo == "moneda" and h.unidad.moneda:
                conteo[h.unidad.moneda] = conteo.get(h.unidad.moneda, 0) + 1
        if not conteo:
            return None
        return max(conteo.items(), key=lambda kv: kv[1])[0]


def leer(ruta: Path | str) -> Documento:
    """Parsea un .xbrl completo. Todos los hechos, sin filtrar."""
    ruta = Path(ruta)
    raw = leer_texto(ruta)
    unidades = _unidades(raw)
    contextos = _contextos(raw)

    hechos: list[Hecho] = []
    for prefijo, concepto, antes, cref, despues, valor in _HECHO_RE.findall(raw):
        if prefijo.lower() in _IGNORAR_PREFIJO:
            continue
        valor = valor.strip()
        if not valor:
            continue
        ctx = contextos.get(cref)
        if ctx is None:
            continue

        attrs = antes + despues
        uref = _UNITREF_RE.search(attrs)
        dec = _DECIMALS_RE.search(attrs)
        hechos.append(Hecho(
            concepto=concepto,
            valor=valor,
            contexto=ctx,
            unidad=unidades.get(uref.group(1)) if uref else None,
            decimales=dec.group(1) if dec else None,
        ))

    return Documento(ruta=ruta, hechos=hechos)


# ─────────────────────────────────────────────────────────────── Etiquetas
# Los miembros de los ejes propios de la empresa NO se llaman por su nombre: se llaman
# `Item804`. El nombre humano vive en el linkbase de etiquetas, que es otro archivo:
#
#     <link:loc   xlink:href="…C.xsd#p0_Item804"  xlink:label="Item804"/>
#     <link:label xlink:label="label_Item804" …>CELULOSA</link:label>
#
# Sin esto, el segmento más grande de Arauco se llamaría "Item804" en la web.
_LOC_RE = re.compile(r'<link:loc[^>]*xlink:href="[^"#]*#[^"]*?([\w\-]+)"[^>]*xlink:label="([^"]+)"', re.I)
_LABEL_RE = re.compile(
    r'<link:label[^>]*xlink:label="([^"]+)"[^>]*xlink:role="[^"]*/label"[^>]*>([^<]*)</link:label>', re.I)
_ARC_RE = re.compile(
    r'<link:labelArc[^>]*xlink:from="([^"]+)"[^>]*xlink:to="([^"]+)"', re.I)


def etiquetas(xbrl_path: Path | str) -> dict[str, str]:
    """id de elemento → nombre humano, leído del linkbase de etiquetas del período.

    Devuelve {} si no hay archivo de etiquetas: preferimos un hueco a inventar un nombre.
    """
    xbrl_path = Path(xbrl_path)
    label_file = next(xbrl_path.parent.glob("*-label.xml"), None)
    if label_file is None:
        return {}

    raw = leer_texto(label_file)

    # locator: id del elemento (p0_Item804 → Item804) ← etiqueta xlink
    loc_a_elemento = {
        xlink: elem_id.replace("p0_", "").replace("p1_", "")
        for elem_id, xlink in _LOC_RE.findall(raw)
    }
    # recurso: etiqueta xlink → texto
    recurso_a_texto = dict(_LABEL_RE.findall(raw))
    # arco: locator → recurso
    fuera: dict[str, str] = {}
    for desde, hacia in _ARC_RE.findall(raw):
        elemento = loc_a_elemento.get(desde)
        texto = recurso_a_texto.get(hacia)
        if elemento and texto:
            fuera[elemento] = texto.strip()
    return fuera


# ─────────────────────────────────────────────────────────────── Jerarquía de miembros
# UN EJE NO ES UNA LISTA PLANA: ES UN ÁRBOL.
#
# Sumar todos los miembros de `OperatingSegmentsAxis` en Arauco daba 4.448 millones de
# ingresos contra 1.482 del consolidado — TRES VECES la cifra real. Porque el eje mezcla:
#
#     OperatingSegmentsMember          ← el total
#       ReportableSegmentsMember       ← subtotal
#         Item804  (CELULOSA)          ← segmento de verdad
#         Item805  (MADERAS)           ← segmento de verdad
#       AllOtherSegmentsMember         ← subtotal del residual
#         Item806 … Item808 (OTROS)    ← segmento de verdad
#
# Una lista negra de nombres estándar no basta: `AllOtherSegmentsMember` es un SUBTOTAL
# en Arauco (tiene tres hijos), pero en una empresa que no define hijos propios sería una
# HOJA, y excluirla dejaría fuera parte de los ingresos.
#
# La jerarquía está declarada en el linkbase de definiciones, arco por arco. Se lee de
# ahí. Una HOJA es un miembro que no es padre de nadie.
_DEFARC_RE = re.compile(
    r'<link:definitionArc[^>]*arcrole="[^"]*domain-member"[^>]*xlink:from="([^"]+)"[^>]*xlink:to="([^"]+)"',
    re.I,
)

# La jerarquía del archivo de la empresa no alcanza, y hay una razón concreta.
#
# En Aguas Andinas, `OperatingSegmentsMember` no tiene hijos declarados en su archivo, así
# que la regla "hoja = sin hijos" lo daba por segmento. Pero no es un miembro: es la RAÍZ
# del eje, y vale exactamente el consolidado. Contarlo sumaba el total junto a sus partes,
# y los ingresos daban 421 mil millones donde hay 210.
#
# La raíz no la declara la empresa: la declara la TAXONOMÍA de la CMF, que sí tenemos
# (docs/CMF_CLCI_2026). Antes esto era una lista escrita a mano por mí; ahora sale del
# paquete oficial, arco por arco — y si la CMF agrega un eje, funciona sin tocar nada.
#
# Fallback: si el paquete no está en disco, quedan sólo los padres del archivo local. Es
# peor, pero se degrada avisando, no en silencio.
_FALLBACK_SIN_TAXONOMIA = {
    "EntitysTotalMember",
    "OperatingSegmentsMember",
    "ReportableSegmentsMember",
    "MaterialReconcilingItemsMember",
    "EliminationOfIntersegmentAmountsMember",
}


def miembros_agregados(xbrl_path: Path | str) -> set[str]:
    """Los miembros que NO son una hoja: raíces de eje, subtotales y padres.

    Dos fuentes, y las dos hacen falta:
      · la TAXONOMÍA de la CMF — dice cuál es la raíz de cada eje y cuáles son los
        subtotales del estándar. El archivo de la empresa no lo declara.
      · el linkbase de definiciones de la EMPRESA — dice qué miembro tiene hijos en SU
        desglose (`AllOtherSegmentsMember` es un subtotal en Arauco y una hoja en otras).
    """
    from . import cmf_taxonomia

    agregados = set(cmf_taxonomia.miembros_agregados()) or set(_FALLBACK_SIN_TAXONOMIA)

    xbrl_path = Path(xbrl_path)
    def_file = next(xbrl_path.parent.glob("*-definition.xml"), None)
    if def_file is not None:
        raw = leer_texto(def_file)
        agregados |= {desde.split(":")[-1] for desde, _ in _DEFARC_RE.findall(raw)}
    return agregados


def arbol(xbrl_path: Path | str) -> dict[str, set[str]]:
    """padre → hijos. El árbol completo de miembros, de las DOS fuentes.

    La taxonomía de la CMF trae la parte estándar (OperatingSegmentsMember →
    ReportableSegmentsMember) y el archivo de la empresa trae la suya
    (ReportableSegmentsMember → Item804 "CELULOSA"). Ninguna de las dos basta sola.
    """
    from . import cmf_taxonomia

    hijos: dict[str, set[str]] = {}
    for padre, hijo in cmf_taxonomia.arcos_padre_hijo():
        hijos.setdefault(padre, set()).add(hijo)

    def_file = next(Path(xbrl_path).parent.glob("*-definition.xml"), None)
    if def_file is not None:
        raw = leer_texto(def_file)
        for padre, hijo in _DEFARC_RE.findall(raw):
            hijos.setdefault(padre.split(":")[-1], set()).add(hijo.split(":")[-1])
    return hijos


def hojas_bajo(hijos: dict[str, set[str]], ancestro: str) -> set[str]:
    """Las HOJAS que cuelgan de un ancestro. Éstas —y sólo éstas— suman su total.

    "Hoja del eje" NO es lo mismo que "segmento". En SMU, `UnallocatedAmountsMember` es
    una hoja perfectamente válida del eje… pero cuelga de MaterialReconcilingItems, no de
    OperatingSegments. Sumarla con los segmentos daba 721.591 millones donde el total de
    segmentos es 717.316:

        OperatingSegmentsAxis
          EntitysTotalMember
            OperatingSegmentsMember          <- lo que suman los segmentos
              ReportableSegmentsMember
                Segmento_1, Segmento_2       <- HOJAS, y son segmentos
              AllOtherSegmentsMember
            MaterialReconcilingItemsMember   <- reconciliación, NO son segmentos
              EliminationOfIntersegmentAmountsMember
              UnallocatedAmountsMember       <- HOJA, pero NO es un segmento

    Por eso se pide el ancestro: un segmento es una hoja que DESCIENDE de
    `OperatingSegmentsMember`. Una lista de exclusiones nunca habría capturado eso.
    """
    hojas: set[str] = set()
    visto: set[str] = set()
    pila = [ancestro]
    while pila:
        m = pila.pop()
        if m in visto:
            continue
        visto.add(m)
        descendencia = hijos.get(m)
        if descendencia:
            pila.extend(descendencia)
        elif m != ancestro:
            hojas.add(m)
    return hojas


def hojas_de_eje(doc: "Documento", eje: str, hojas: set[str],
                 concepto: str | None = None) -> list["Hecho"]:
    """Los hechos del eje cuyo miembro está en `hojas` (ver `hojas_bajo`).

    Se exige además que el hecho tenga ESE eje y ningún otro: un hecho cruzado
    (segmento × producto, p. ej.) es un desglose del desglose, y sumarlo con los
    segmentos duplicaría la cifra.
    """
    fuera = []
    for h in doc.hechos:
        if concepto is not None and h.concepto != concepto:
            continue
        if len(h.contexto.ejes) != 1:
            continue
        eje_h, miembro = h.contexto.ejes[0]
        if eje_h == eje and miembro in hojas:
            fuera.append(h)
    return fuera


# ─────────────────────────────────────────────────────────────── Recorrido
_PERIODO_RE = re.compile(r"_(\d{4})(\d{2})_extracted$")
_MES_A_TRIMESTRE = {3: 1, 6: 2, 9: 3, 12: 4}


def periodos_de(empresa_dir: Path | str) -> Iterator[tuple[int, int, Path]]:
    """(año, trimestre, ruta del .xbrl) por cada estado de la empresa, en orden."""
    empresa_dir = Path(empresa_dir)
    if not empresa_dir.is_dir():
        return
    for sub in sorted(empresa_dir.iterdir()):
        if not sub.is_dir():
            continue
        m = _PERIODO_RE.search(sub.name)
        if not m:
            continue
        trimestre = _MES_A_TRIMESTRE.get(int(m.group(2)))
        if trimestre is None:
            continue
        xbrl = next(sub.glob("*.xbrl"), None)
        if xbrl is not None:
            yield int(m.group(1)), trimestre, xbrl
