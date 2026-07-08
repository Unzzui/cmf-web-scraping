#!/usr/bin/env python3
"""Añade la columna `Categoria` al CSV de empresas (banco/afp/seguros/ifrs).

El pipeline XBRL-IFRS solo funciona para sociedades que reportan IFRS a la
CMF. Bancos (SBIF), AFPs y aseguradoras reportan con otros formatos y rompen
o ensucian la corrida completa. Esta clasificación queda versionada como DATO
en el CSV — el CLI la usa para enrutar/omitir, y se corrige editando la celda.

Fuentes de clasificación, en orden de precedencia:
  1. BANKS_RUTS de src/scrapers/cmf_bank_scraper.py (extraído vía ast, sin
     importar el módulo para no requerir sus dependencias)
  2. Heurística por razón social (regex)

Uso::

    python scripts/classify_companies.py            # escribe in-place (con .bak)
    python scripts/classify_companies.py --dry-run  # solo muestra el resultado

Solo stdlib: corre con cualquier Python 3.9+.
"""

from __future__ import annotations

import argparse
import ast
import csv
import re
import shutil
import sys
import unicodedata
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = PROJECT_ROOT / "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
BANK_SCRAPER = PROJECT_ROOT / "src/scrapers/cmf_bank_scraper.py"

# (patrón sobre razón social normalizada, categoría)
PATRONES_NO_IFRS = [
    (re.compile(r"\bBANCO\b|\bBANK\b"), "banco"),
    (re.compile(r"FONDOS? DE PENSIONES|\bAFP\b"), "afp"),
    (re.compile(r"\bSEGUROS\b"), "seguros"),
]
# Corredores/asesores de seguros son sociedades normales, no aseguradoras.
EXCLUYE_SEGUROS = re.compile(r"CORREDOR|ASESOR")


def load_banks_ruts() -> set[str]:
    """RUTs numéricos (sin DV) de BANKS_RUTS, extraídos por ast del scraper."""
    tree = ast.parse(BANK_SCRAPER.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "BANKS_RUTS":
                    values = ast.literal_eval(node.value)
                    return {v.split("-")[0] for v in values.values()}
    raise SystemExit(f"No se encontró BANKS_RUTS en {BANK_SCRAPER}")


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.upper()).encode("ascii", "ignore").decode()


def clasificar(razon_social: str, rut_numero: str, banks: set[str]) -> str:
    if str(rut_numero).strip() in banks:
        return "banco"
    nombre = _norm(razon_social)
    for patron, cat in PATRONES_NO_IFRS:
        if patron.search(nombre):
            if cat == "seguros" and EXCLUYE_SEGUROS.search(nombre):
                continue
            return cat
    return "ifrs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--csv", default=str(DEFAULT_CSV))
    ap.add_argument("--dry-run", action="store_true",
                    help="No escribe; muestra conteos y las empresas no-IFRS")
    args = ap.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"CSV no encontrado: {csv_path}", file=sys.stderr)
        return 1

    banks = load_banks_ruts()

    with open(csv_path, newline="", encoding="utf-8-sig") as fp:
        reader = csv.DictReader(fp)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    if "Razón Social" not in fieldnames or "RUT_Numero" not in fieldnames:
        print(f"Columnas esperadas ausentes; encontradas: {fieldnames}", file=sys.stderr)
        return 1

    counts: dict[str, int] = {}
    no_ifrs: list[tuple[str, str, str]] = []
    for row in rows:
        cat = clasificar(row["Razón Social"], row["RUT_Numero"], banks)
        # Respetar correcciones manuales previas: si ya hay una Categoria
        # distinta de vacío y la heurística no la contradice con un match de
        # banco por RUT (fuente dura), se conserva.
        previa = (row.get("Categoria") or "").strip()
        if previa and not (cat == "banco" and str(row["RUT_Numero"]).strip() in banks):
            cat = previa
        row["Categoria"] = cat
        counts[cat] = counts.get(cat, 0) + 1
        if cat != "ifrs":
            no_ifrs.append((row["RUT"], row["Razón Social"], cat))

    print("Conteo por categoría:")
    for cat, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:8s} {n}")
    if no_ifrs:
        print(f"\nEmpresas no-IFRS ({len(no_ifrs)}) — revisar y corregir a mano si hace falta:")
        for rut, nombre, cat in no_ifrs:
            print(f"  [{cat:7s}] {rut:12s} {nombre}")

    if args.dry_run:
        print("\n(dry-run: no se escribió nada)")
        return 0

    if "Categoria" not in fieldnames:
        fieldnames.append("Categoria")
    backup = csv_path.with_suffix(".csv.bak")
    shutil.copy2(csv_path, backup)
    with open(csv_path, "w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\nEscrito {csv_path} (respaldo en {backup.name})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
