#!/usr/bin/env python3
"""CLI: genera el Excel de analisis bancario por institucion, leyendo de las tablas bank_*.

Ejemplos:
    python scripts/generate_bank_excel.py --only 001
    python scripts/generate_bank_excel.py --banks 001,037,016 --out cmf_extract/Product_v1_Banks/Total
"""

import argparse
import re
import sys
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from cmf_extract.analisis_bancos import db_reader, workbook  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "cmf_extract" / "Product_v1_Banks" / "Total"


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def _slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    t = re.sub(r"[^A-Za-z0-9 .-]", "", t).strip()
    return re.sub(r"\s+", " ", t)


def pretty_name(data) -> str:
    rng = ""
    if data.periods:
        y0, m0 = data.periods[0]
        y1, m1 = data.periods[-1]
        rng = f" {y0}{m0:02d}-{y1}{m1:02d}"
    return f"{_slug(data.nombre)} - {data.rut or data.codigo_institucion} - Analisis Bancario{rng} [ES].xlsx"


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Genera el Excel de analisis bancario")
    p.add_argument("--banks", default="", help="Codigos separados por coma; vacio = todos")
    p.add_argument("--only", default="", help="Alias de --banks para un solo codigo")
    p.add_argument("--out", default=str(OUT_DEFAULT), help="Directorio de salida")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    env = load_env(REPO_ROOT / ".env")
    missing = [k for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not env.get(k)]
    if missing:
        print(f"Faltan credenciales PG en .env: {', '.join(missing)}", file=sys.stderr)
        return 2

    import psycopg2

    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", "5432"), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"],
    )
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    codes = [c.strip() for c in (args.banks or args.only).split(",") if c.strip()]
    try:
        if not codes:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo_institucion FROM bank_institutions ORDER BY 1")
                codes = [r[0] for r in cur.fetchall()]
        for cod in codes:
            data = db_reader.read_bank(conn, cod)
            if not data.periods:
                print(f"{cod} {data.nombre}: sin datos 2022+, se omite")
                continue
            wb = workbook.build_workbook(data)
            path = out_dir / pretty_name(data)
            wb.save(path)
            print(f"{cod} {data.nombre}: {len(data.periods)} meses -> {path.name}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
