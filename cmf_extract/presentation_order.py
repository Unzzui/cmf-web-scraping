"""El orden de las cuentas de cada empresa, leido de su propio XBRL.

POR QUE EXISTE
--------------
Hasta ahora el orden de las filas del Excel salia de `new_eeff_estructura.json`: una
lista escrita a mano, con 53 de las 75 empresas. Una empresa que no estuviera en esa
lista heredaba la plantilla de QUINENCO -- un holding CON NEGOCIO BANCARIO. SONDA
terminaba con 120 filas (64 propias), 67 vacias y 12 cuentas de banco que no tiene.

El orden no hay que inventarlo: cada XBRL trae su linkbase de presentacion, que ES el
orden en que la empresa declara sus cuentas, con sus extensiones propias. Arelle ya lo
exporta en la fase 1 (`presentation_<rut>_<periodo>_es.csv`). Este modulo lo lee.

POR QUE SE FUSIONAN TODOS LOS PERIODOS Y NO SOLO EL ULTIMO
-----------------------------------------------------------
El plan de cuentas cambia con los anios. QUINENCO consolidaba Banco de Chile hasta 2021:
"Ingresos netos por comisiones" y otras 8 cuentas bancarias estan en su rol 310000 hasta
202112 y desaparecen en 202203. Pero los datos historicos siguen ahi -- 35 periodos con
cifras reales. Leer solo la ultima presentacion las borraria del Excel.

Por eso se recorren los periodos de mas nuevo a mas viejo y se van insertando las cuentas
que solo existieron antes, cada una despues de la cuenta que la precedia en su periodo.
El resultado es la union historica, en orden -- que es justo lo que la lista a mano
codificaba, pero derivado del dato en vez de mantenido a pulso.

LAS ETIQUETAS SE CANONICALIZAN AL FUSIONAR
-------------------------------------------
La CMF renombra etiquetas entre versiones de la taxonomia sin que el elemento cambie
("Deterioro de valor de ganancias..." gano el sufijo "...determinado de acuerdo con la
NIIF"). Fusionando en crudo, la variante vieja y la nueva entran como DOS filas de una
misma cuenta, con series de tiempo partidas. `label_rename` ya tiene el mapa
elemento->etiqueta canonica; se aplica antes de fusionar, asi las variantes colapsan.

FALLBACK
--------
Sin presentacion en disco se cae a la taxonomia oficial de la CMF (`cmf_taxonomia`), que
declara el orden estandar de los cuatro estados primarios. Eso cubre las cuentas IFRS
pero no las extensiones de la empresa. Es un ultimo recurso, no el camino normal.
"""

from __future__ import annotations

import csv
import functools
import re
from pathlib import Path

# Los cuatro estados primarios que el pipeline arma como hoja de Excel.
ROLES_PRIMARIOS = ("210000", "310000", "320000", "510000")

# La cabecera de rol en el reporte de Arelle: "[310000] Estado del resultado, por..."
_ROLE_RE = re.compile(r"^\[(\d{6})\]")

# "presentation_91705000-7_201403-202603_es.csv" / "presentation_91705000_202512_es.csv"
_PERIODO_RE = re.compile(r"_(\d{6})_[a-z]{2}\.csv$")


def _ancho_arbol(cabeceras: list[str]) -> int:
    """Cuantas columnas forman el arbol indentado.

    El arbol es la columna 0 mas las columnas de indentacion que la siguen; despues vienen
    "Pref. Label", "Type" y "References", que NO son parte del arbol -- si se cuelan, el
    "Type" de una fila se leeria como si fuera una cuenta.

    Arelle nombra esas columnas de indentacion de dos formas segun el export: vacias en
    los reportes por periodo, y "Unnamed: 1".. en el consolidado. Se aceptan ambas.
    """
    ancho = 1
    for c in cabeceras[1:]:
        cab = c.strip()
        if cab and not cab.startswith("Unnamed"):
            break
        ancho += 1
    return ancho


def leer_presentacion_con_nivel(ruta: Path) -> dict[str, list[tuple[int, str]]]:
    """rol -> [(profundidad, cuenta)] en el orden en que la empresa las declara.

    La profundidad es la columna donde Arelle indenta la cuenta: es el arbol de
    presentacion. Devuelve solo los roles primarios; el reporte trae ademas las ~40 notas.

    Se lee con el modulo `csv` y no con pandas a proposito. Este archivo se recorre una
    vez por periodo y por empresa -- 232 empresas x ~49 periodos -- y `DataFrame.iterrows`
    construye una Series por fila: sobre ~3.800 filas x 11.000 archivos, eso dominaba el
    tiempo de la fase 2.
    """
    # utf-8-sig: Arelle antepone un BOM. Sin esto la primera cabecera llega como
    # "﻿Presentation Relationships" y no matchea nada.
    try:
        with open(ruta, newline="", encoding="utf-8-sig", errors="replace") as fh:
            filas = list(csv.reader(fh))
    except OSError:
        return {}

    if not filas:
        return {}

    ancho = _ancho_arbol(filas[0])
    if ancho < 2:
        return {}

    fuera: dict[str, list[tuple[int, str]]] = {}
    rol_actual: str | None = None

    for fila in filas[1:]:
        if not fila:
            continue

        cabecera = fila[0].strip() if fila[0] else ""
        if cabecera:
            m = _ROLE_RE.match(cabecera)
            if m:
                rol_actual = m.group(1)
                if rol_actual in ROLES_PRIMARIOS:
                    fuera.setdefault(rol_actual, [])
                continue

        if rol_actual not in fuera:
            continue

        # La cuenta vive en la primera columna con contenido: esa es su profundidad.
        for nivel in range(1, min(ancho, len(fila))):
            valor = fila[nivel].strip()
            if valor:
                fuera[rol_actual].append((nivel, valor))
                break

    return fuera


def leer_presentacion(ruta: Path) -> dict[str, list[str]]:
    """rol -> cuentas en orden, sin la profundidad."""
    return {rol: [lab for _, lab in filas]
            for rol, filas in leer_presentacion_con_nivel(ruta).items()}


def _fusionar(maestro: list[str], viejo: list[str]) -> list[str]:
    """Inserta en `maestro` las cuentas de `viejo` que no estan, en su posicion relativa.

    Cada cuenta ausente se ancla despues de su predecesora en `viejo` que SI exista en
    `maestro`. Si no hay predecesora conocida (la cuenta abria el estado), va al inicio.

    Ejemplo: maestro=[A, C], viejo=[A, B, C] -> [A, B, C]. B se ancla tras A.
    """
    if not maestro:
        return list(viejo)

    posicion = {lab: i for i, lab in enumerate(maestro)}
    resultado = list(maestro)
    ancla = -1  # indice en `resultado` tras el cual insertar

    for lab in viejo:
        if lab in posicion:
            # Cuenta conocida: mueve el ancla. Se recalcula sobre `resultado` porque las
            # inserciones previas corrieron los indices.
            ancla = resultado.index(lab)
            continue
        # Cuenta que solo existio en periodos viejos: va justo despues del ancla.
        ancla += 1
        resultado.insert(ancla, lab)
        posicion[lab] = ancla

    return resultado


def _presentaciones_por_periodo(dir_empresa: Path) -> list[Path]:
    """Las presentaciones de la empresa, de la mas nueva a la mas vieja.

    Se ignora la consolidada (`out_consolidated_*`): es un unico periodo y no trae el
    historico. El orden lo da el periodo del nombre, no el mtime.
    """
    rutas = [
        p for p in dir_empresa.glob("*_extracted/out_*/presentation_*.csv")
        if _PERIODO_RE.search(p.name)
    ]
    return sorted(rutas, key=lambda p: _PERIODO_RE.search(p.name).group(1), reverse=True)


def _canonicalizador():
    """La funcion que lleva cada etiqueta a su forma canonica, o la identidad.

    Si el mapa de renombres no esta en disco, no se canonicaliza nada y el pipeline
    sigue igual que antes -- salvo que las variantes de una cuenta renombrada saldran
    como filas separadas, que es exactamente el estado previo a este modulo.
    """
    try:
        from label_rename import canonicalize_label, load_rename_map
    except ImportError:
        return lambda rol, lab: lab

    mapa = load_rename_map()
    if not mapa:
        return lambda rol, lab: lab
    return lambda rol, lab: canonicalize_label(rol, lab, mapa)


@functools.lru_cache(maxsize=512)
def _estructura(dir_empresa: str) -> tuple[
        dict[str, tuple[str, ...]],
        dict[str, tuple[tuple[str, tuple[str, ...]], ...]]]:
    """(orden, arbol) de la empresa, en UNA sola pasada por sus presentaciones.

    Antes esto eran dos funciones cacheadas por separado, y cada una releia los ~49
    archivos de presentacion de la empresa: el doble de trabajo sobre el paso mas caro de
    la fase 2. Los dos resultados salen del mismo recorrido.
    """
    base = Path(dir_empresa)
    canonicalizar = _canonicalizador()

    orden: dict[str, list[str]] = {}
    paths: dict[str, dict[str, tuple[str, ...]]] = {}

    for ruta in _presentaciones_por_periodo(base):
        for rol, filas in leer_presentacion_con_nivel(ruta).items():
            cuentas: list[str] = []
            destino = paths.setdefault(rol, {})
            pila: dict[int, str] = {}  # profundidad -> cuenta abierta a ese nivel

            for nivel, cuenta in filas:
                cuenta = canonicalizar(rol, cuenta)
                cuentas.append(cuenta)

                # El path jerarquico: los ancestros abiertos por encima de este nivel.
                # Gana el periodo mas reciente, que es el primero que se recorre.
                pila = {d: c for d, c in pila.items() if d < nivel}
                pila[nivel] = cuenta
                if cuenta not in destino:
                    destino[cuenta] = tuple(pila[d] for d in sorted(pila))

            orden[rol] = _fusionar(orden.get(rol, []), cuentas)

    return (
        {rol: tuple(c) for rol, c in orden.items() if c},
        {rol: tuple(d.items()) for rol, d in paths.items() if d},
    )


def orden_empresa(dir_empresa: Path | str) -> dict[str, list[str]]:
    """rol -> cuentas en orden, fusionando todos los periodos de la empresa.

    `dir_empresa` es la carpeta de la empresa bajo data/XBRL/Total, la que contiene los
    `Estados_financieros_(XBRL)*_extracted/`.
    """
    orden, _ = _estructura(str(dir_empresa))
    return {rol: list(c) for rol, c in orden.items()}


def arbol_empresa(dir_empresa: Path | str) -> dict[str, dict[str, list[str]]]:
    """rol -> {cuenta: [ancestros..., cuenta]}. El path jerarquico de cada cuenta.

    Es lo que el pipeline llama `LabelKeyIdExt`
    ("510000||Flujos de actividades de operacion [sinopsis]||Cobros a clientes"). Antes
    salia del campo `tree` de `new_eeff_estructura.json`; ahora se deriva de la
    indentacion del propio linkbase.
    """
    _, arbol = _estructura(str(dir_empresa))
    return {rol: {c: list(p) for c, p in items} for rol, items in arbol.items()}


def rol_estado_resultados(orden: dict[str, list[str]]) -> str | None:
    """310000 (por funcion) o 320000 (por naturaleza): el que la empresa declara.

    Si declara los dos -- pasa, algunas presentan ambos -- gana el que trae mas cuentas,
    que es el que efectivamente llenaron. Antes esto se adivinaba mirando si el string
    'costo de ventas' aparecia en la hoja.
    """
    candidatos = [(len(orden.get(r, [])), r) for r in ("310000", "320000") if orden.get(r)]
    if not candidatos:
        return None
    return max(candidatos)[1]
