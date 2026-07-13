"""La taxonomía oficial de la CMF (paquete CL-CI), leída una vez y cacheada.

POR QUÉ IMPORTA
---------------
Todo lo que este repo sabía del XBRL estaba INFERIDO de los archivos: qué miembro es un
subtotal, qué concepto es una tasa, cómo se llama cada cosa en español. Inferir funciona
hasta que no funciona — y cuando falla, falla en silencio y con números que parecen
razonables.

El paquete oficial (docs/CMF_CLCI_2026) lo declara todo. Este módulo lo lee.

QUÉ RESUELVE, CON AUTORIDAD EN VEZ DE OLFATO
---------------------------------------------
1) LOS AGREGADOS DE CADA EJE. La jerarquía de segmentos es:

       OperatingSegmentsAxis
         └─ EntitysTotalMember              <- la raíz del eje
              └─ OperatingSegmentsMember
                   ├─ ReportableSegmentsMember
                   └─ AllOtherSegmentsMember

   Sumar el eje entero sin distinguir daba 4.448 millones de ingresos donde Arauco tiene
   1.482. Yo tenía esa lista escrita a mano; ahora sale del paquete, y si la CMF agrega
   un eje el año que viene, funciona sin tocar nada.

2) EL TIPO DE CADA CONCEPTO. Monetario, acciones, fecha, texto, porcentaje.

3) EL NOMBRE EN ESPAÑOL de cada concepto, para que la base no guarde
   `RevenuesFromExternalCustomersAndTransactions…` y se lo muestre así a un usuario.

LO QUE LA TAXONOMÍA **NO** RESUELVE (y hay que decirlo)
-------------------------------------------------------
`TasaEfectiva` está declarada como ``xbrli:decimalItemType``: un decimal a secas, SIN
semántica de porcentaje. Y la taxonomía sí tiene un tipo `num:percentItemType` — que usa
en otros dos conceptos — pero eligió no usarlo aquí.

O sea que la norma NO dice si un 5,26 es 5,26% o 526%. Por eso 17 empresas declaran sus
tasas en decimal y en porcentaje dentro del MISMO archivo. La ambigüedad es de la norma,
no de nuestra lectura, y no hay forma de resolverla sin una heurística (ver xbrl_deuda).
"""

from __future__ import annotations

import functools
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "docs" / "CMF_CLCI_2026"

_LOC_RE = re.compile(r"<link:loc[^>]*>", re.I)
_ARC_RE = re.compile(r"<link:definitionArc[^>]*>", re.I)
_HREF_RE = re.compile(r'xlink:href="([^"]+)"')
_LABEL_RE = re.compile(r'xlink:label="([^"]+)"')
_FROM_RE = re.compile(r'xlink:from="([^"]+)"')
_TO_RE = re.compile(r'xlink:to="([^"]+)"')
_ARCROLE_RE = re.compile(r'arcrole="([^"]+)"')

# El .xsd de la CMF usa el prefijo `xs:`, no `xsd:`, y pone los atributos en cualquier
# orden. Se parsea la etiqueta entera y después cada atributo por su nombre: asumir el
# orden es la clase de suposición que devuelve cero resultados sin decir por qué.
_ELEMENTO_RE = re.compile(r"<(?:xs|xsd):element[^>]*>", re.I)
_ATTR_NOMBRE_RE = re.compile(r'\bname="([^"]+)"')
_ATTR_TIPO_RE = re.compile(r'\btype="([^"]+)"')


def disponible() -> bool:
    """¿Está el paquete oficial en disco? Sin él, los extractores caen a heurística."""
    return RAIZ.is_dir()


def _leer(ruta: Path) -> str:
    """El contenido, decodificado de verdad.

    UTF-8 estricto PRIMERO, y sólo después lo que el archivo declara. Porque el linkbase
    de etiquetas de la CMF declara `iso-8859-1` y su contenido es UTF-8: obedecerle
    devuelve "amortizaciÃ³n" en vez de "amortización". Un archivo que decodifica como
    UTF-8 válido casi nunca es latin-1 por casualidad; al revés sí pasa.
    """
    crudo = ruta.read_bytes()
    try:
        return crudo.decode("utf-8")
    except UnicodeDecodeError:
        pass
    m = re.search(rb'encoding\s*=\s*["\']([\w\-]+)["\']', crudo[:200])
    declarada = m.group(1).decode("ascii", "replace") if m else None
    for enc in (declarada, "iso-8859-1"):
        if not enc:
            continue
        try:
            return crudo.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return crudo.decode("iso-8859-1", errors="replace")


@functools.lru_cache(maxsize=1)
def arcos_padre_hijo() -> tuple[tuple[str, str], ...]:
    """Los arcos (padre, hijo) del estándar. El esqueleto del árbol de miembros.

    Un conjunto de "agregados" no basta para saber qué es un segmento: en SMU,
    `UnallocatedAmountsMember` es una hoja del eje pero cuelga de las partidas de
    RECONCILIACIÓN, no de los segmentos. Para distinguirlo hace falta el árbol, no una
    lista. Ver `xbrl_facts.hojas_bajo`.
    """
    if not disponible():
        return ()

    arcos: set[tuple[str, str]] = set()
    for definicion in RAIZ.rglob("def_*.xml"):
        raw = _leer(definicion)

        locators: dict[str, str] = {}
        for tag in _LOC_RE.findall(raw):
            href = _HREF_RE.search(tag)
            etiqueta = _LABEL_RE.search(tag)
            if href and etiqueta:
                locators[etiqueta.group(1)] = href.group(1).split("#")[-1].split("_", 1)[-1]

        for tag in _ARC_RE.findall(raw):
            arcrole = _ARCROLE_RE.search(tag)
            desde = _FROM_RE.search(tag)
            hacia = _TO_RE.search(tag)
            if not (arcrole and desde and hacia):
                continue
            if arcrole.group(1).rsplit("/", 1)[-1] not in ("dimension-domain", "domain-member"):
                continue
            padre = locators.get(desde.group(1))
            hijo = locators.get(hacia.group(1))
            if padre and hijo:
                arcos.add((padre, hijo))

    return tuple(sorted(arcos))


@functools.lru_cache(maxsize=1)
def miembros_agregados() -> frozenset[str]:
    """Los miembros que NO son una hoja: la raíz de cada eje y todo miembro con hijos.

    Se recorren los linkbase de definiciones del paquete y se juntan:
      · el destino de cada arco `dimension-domain` — la RAÍZ del eje, que vale el total;
      · el origen de cada arco `domain-member`     — todo lo que tiene hijos.

    Un hecho cuyo miembro esté aquí es un total o un subtotal. Sumarlo junto a las hojas
    duplica la cifra.
    """
    if not disponible():
        return frozenset()

    agregados: set[str] = set()
    for definicion in RAIZ.rglob("def_*.xml"):
        raw = _leer(definicion)

        locators: dict[str, str] = {}
        for tag in _LOC_RE.findall(raw):
            href = _HREF_RE.search(tag)
            etiqueta = _LABEL_RE.search(tag)
            if href and etiqueta:
                # ".../archivo.xsd#ifrs-full_OperatingSegmentsMember" → OperatingSegmentsMember
                elemento = href.group(1).split("#")[-1]
                locators[etiqueta.group(1)] = elemento.split("_", 1)[-1]

        for tag in _ARC_RE.findall(raw):
            arcrole = _ARCROLE_RE.search(tag)
            desde = _FROM_RE.search(tag)
            hacia = _TO_RE.search(tag)
            if not (arcrole and desde and hacia):
                continue
            tipo = arcrole.group(1).rsplit("/", 1)[-1]

            if tipo == "dimension-domain":
                raiz = locators.get(hacia.group(1))
                if raiz:
                    agregados.add(raiz)          # la raíz del eje: vale el consolidado
            elif tipo == "domain-member":
                padre = locators.get(desde.group(1))
                if padre:
                    agregados.add(padre)         # tiene hijos ⇒ es un subtotal

    return frozenset(agregados)


@functools.lru_cache(maxsize=1)
def tipos() -> dict[str, str]:
    """concepto → tipo declarado ('monetaryItemType', 'decimalItemType', 'dateItemType'…).

    OJO con `decimalItemType`: es un decimal SIN semántica. La taxonomía tiene
    `percentItemType` y no lo usa para las tasas — ver el encabezado del módulo.
    """
    if not disponible():
        return {}
    fuera: dict[str, str] = {}
    for xsd in RAIZ.rglob("*.xsd"):
        for tag in _ELEMENTO_RE.findall(_leer(xsd)):
            nombre = _ATTR_NOMBRE_RE.search(tag)
            tipo = _ATTR_TIPO_RE.search(tag)
            if nombre and tipo:
                fuera[nombre.group(1)] = tipo.group(1).split(":")[-1]
    return fuera


# Igual que arriba: en el linkbase, `xlink:to` viene ANTES que `xlink:from`. Parsear por
# posición devolvía cero etiquetas, en silencio.
_LAB_LOC_TAG = re.compile(r"<link:loc[^>]*>", re.I)
_LAB_RES_TAG = re.compile(r"<link:label\b([^>]*)>([^<]*)</link:label>", re.I)
_LAB_ARC_TAG = re.compile(r"<link:labelArc[^>]*>", re.I)
_ATTR_ROLE_RE = re.compile(r'xlink:role="([^"]+)"')


@functools.lru_cache(maxsize=1)
def etiquetas() -> dict[str, str]:
    """concepto → nombre oficial en español.

    Para que la base no guarde `RevenuesFromExternalCustomersAndTransactionsWith…` y se
    lo muestre así a un analista.
    """
    if not disponible():
        return {}

    fuera: dict[str, str] = {}
    for lab in RAIZ.rglob("*lab*.xml"):
        raw = _leer(lab)

        loc: dict[str, str] = {}
        for tag in _LAB_LOC_TAG.findall(raw):
            href = _HREF_RE.search(tag)
            xlabel = _LABEL_RE.search(tag)
            if href and xlabel:
                # "...cor.xsd#cl-ci_TasaEfectiva" → "TasaEfectiva"
                loc[xlabel.group(1)] = href.group(1).split("#")[-1].split("_", 1)[-1]

        recurso: dict[str, str] = {}
        for attrs, texto in _LAB_RES_TAG.findall(raw):
            rol = _ATTR_ROLE_RE.search(attrs)
            # La etiqueta estándar, no las variantes ("terse", "verbose", "documentation").
            if rol and not rol.group(1).endswith("/label"):
                continue
            xlabel = _LABEL_RE.search(attrs)
            if xlabel and texto.strip():
                recurso[xlabel.group(1)] = texto.strip()

        for tag in _LAB_ARC_TAG.findall(raw):
            desde = _FROM_RE.search(tag)
            hacia = _TO_RE.search(tag)
            if not (desde and hacia):
                continue
            concepto = loc.get(desde.group(1))
            texto = recurso.get(hacia.group(1))
            if concepto and texto and concepto not in fuera:
                fuera[concepto] = texto
    return fuera
