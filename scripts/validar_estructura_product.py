#!/usr/bin/env python3
"""Valida que el Excel de producto de cada empresa refleje SU propio XBRL.

QUE COMPRUEBA
-------------
1. NADA HEREDADO. Toda cuenta del Excel tiene que estar en el linkbase de presentacion de
   la empresa (o venir de sus facts). Antes, una empresa fuera de `new_eeff_estructura.json`
   heredaba la plantilla de QUINENCO -- un holding CON NEGOCIO BANCARIO: SONDA terminaba con
   120 filas de balance (64 propias), 67 vacias y 12 cuentas de banco que no tiene.

2. EL ROL DEL ER ES EL QUE LA EMPRESA DECLARA. 310000 (por funcion) o 320000 (por
   naturaleza), segun su presentacion. No el default.

3. NO SE PIERDEN DATOS. Toda cuenta con cifras en el CSV primario llega al Excel.

4. EL BALANCE NO ESTA VACIO. VOLCOM reporta el suyo en el rol 220000 (orden de liquidez),
   que el pipeline no procesa, y su balance sale en blanco.

Uso:
    python scripts/validar_estructura_product.py                 # todas
    python scripts/validar_estructura_product.py --ruts 83628100-4,76833300-9
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "cmf_extract"))

import presentation_order as po  # noqa: E402

XBRL_BASE = Path(os.getenv("CMF_XBRL_BASE_DIR", REPO / "data" / "XBRL" / "Total"))
PRODUCT = REPO / "cmf_extract" / "Product_v1" / "Total"

HOJAS = {
    "210000": "Balance General",
    "310000": "Estado de Resultados",
    "320000": "Estado de Resultados",
    "510000": "Flujo Efectivo",
}

# Cuentas de negocio bancario. Una empresa que no consolida un banco no puede tenerlas: si
# aparecen, vienen de la plantilla de otra.
_BANCARIO = re.compile(r"bancari|servicios bancarios|riesgo de cr[eé]dito|comisiones", re.I)

# Cuentas que el pipeline funde a proposito en otra: son la misma linea economica bajo
# etiquetas que la CMF cambio entre versiones de la taxonomia. La fuente desaparece como
# fila y sus cifras quedan en el destino (ver los `merge_pairs_*` de primary_csv_to_excel).
# Sin esto, el validador las reportaba como datos perdidos.
_FUNDIDAS = {
    "Diferencias de cambio": "Resultados por unidades de reajuste",
    "Capital emitido": "Capital emitido y pagado",
    "Pagos de pasivos por arrendamientos financieros": "Pagos de pasivos por arrendamientos",
    "Flujos de efectivo netos procedentes (utilizados en) operaciones":
        "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
    "Flujos de efectivo netos procedentes de (utilizados en) la operación":
        "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
    "Pagos de préstamos a entidades relacionadas":
        "Pagos de préstamos de entidades relacionadas",
}


def _cuentas_de_hoja(xlsx: Path, hoja: str) -> dict[str, int]:
    """{cuenta: nro de periodos con dato} de una hoja del Excel."""
    df = pd.read_excel(xlsx, sheet_name=hoja, header=None)
    fila = next((i for i, r in df.iterrows() if str(r.iloc[0]).strip() == "Cuenta"), None)
    if fila is None:
        return {}
    cuerpo = df.iloc[fila + 1:]
    fuera = {}
    for _, r in cuerpo.iterrows():
        lab = str(r.iloc[0]).strip()
        if lab in ("", "nan"):
            continue
        fuera[lab] = int(r.iloc[1:].notna().sum())
    return fuera


def validar(company_dir: Path) -> list[str]:
    """Los problemas de esta empresa. Lista vacia = todo bien."""
    rut = company_dir.name.split("_", 1)[0]
    fallos: list[str] = []

    xlsx = glob.glob(str(PRODUCT / f"*{rut}*.xlsx"))
    if not xlsx:
        return [f"sin Excel de producto"]
    xlsx = Path(xlsx[0])

    orden = po.orden_empresa(company_dir)
    if not orden:
        return ["sin linkbase de presentacion"]

    rol_er = po.rol_estado_resultados(orden)
    declarados = {c for cuentas in orden.values() for c in cuentas}

    # Las cuentas que la empresa reporta, con cifras, en su CSV primario. El Excel puede
    # traerlas aunque no esten en la presentacion (se agregan desde los facts).
    csvs = glob.glob(str(company_dir / "out_consolidated_*" / "primary_roles_*.csv"))
    con_datos: set[str] = set()
    if csvs:
        prim = pd.read_csv(csvs[0])
        fechas = [c for c in prim.columns if c[:4].isdigit()]
        for _, r in prim.iterrows():
            if r[fechas].notna().any():
                con_datos.add(str(r["Label"]).strip())

    legitimas = declarados | con_datos

    for rol, hoja in (("210000", "Balance General"),
                      (rol_er or "310000", "Estado de Resultados"),
                      ("510000", "Flujo Efectivo")):
        try:
            cuentas = _cuentas_de_hoja(xlsx, hoja)
        except Exception as exc:
            fallos.append(f"{hoja}: no se pudo leer ({exc})")
            continue

        if not cuentas:
            fallos.append(f"{hoja}: hoja vacia")
            continue

        # 4. Balance en blanco
        if rol == "210000" and not any(cuentas.values()):
            fallos.append("Balance General: TODAS las filas sin datos "
                          "(reporta en rol 220000?)")

        # 1. Cuentas heredadas de otra empresa
        ajenas = [c for c in cuentas if c not in legitimas]
        if ajenas:
            bancarias = [c for c in ajenas if _BANCARIO.search(c)]
            fallos.append(
                f"{hoja}: {len(ajenas)} cuenta(s) que la empresa NO declara ni reporta"
                + (f", {len(bancarias)} de negocio bancario: {bancarias[:2]}" if bancarias
                   else f": {ajenas[:2]}")
            )

        # 3. Datos perdidos. Una cuenta fundida no se perdio: sus cifras estan en el
        #    destino, que si tiene que estar presente.
        del_rol = set(orden.get(rol, []))
        perdidas = []
        for c in con_datos:
            if c not in del_rol or c in cuentas:
                continue
            destino = _FUNDIDAS.get(c)
            if destino and destino in cuentas:
                continue
            perdidas.append(c)
        if perdidas:
            fallos.append(f"{hoja}: {len(perdidas)} cuenta(s) CON DATOS perdidas: {perdidas[:2]}")

    return fallos


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ruts", help="lista separada por comas; por defecto, todas")
    args = ap.parse_args()

    dirs = sorted(d for d in XBRL_BASE.iterdir() if d.is_dir())
    if args.ruts:
        pedidos = {r.strip().upper() for r in args.ruts.split(",")}
        dirs = [d for d in dirs if d.name.split("_", 1)[0].upper() in pedidos]

    ok = 0
    con_fallos: list[tuple[str, list[str]]] = []

    for d in dirs:
        fallos = validar(d)
        if fallos:
            con_fallos.append((d.name, fallos))
        else:
            ok += 1

    print(f"\n{'=' * 74}")
    print(f"  {ok} empresa(s) OK   |   {len(con_fallos)} con problemas")
    print("=" * 74)
    for nombre, fallos in con_fallos:
        print(f"\n{nombre}")
        for f in fallos:
            print(f"    - {f}")

    return 1 if con_fallos else 0


if __name__ == "__main__":
    raise SystemExit(main())
