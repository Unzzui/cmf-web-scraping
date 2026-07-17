#!/usr/bin/env python3
"""CLI: genera los Excel de producto de bancos desde las tablas bank_*.

Lee de la base (no del API), así que corre después de scripts/ingest_banks.py.

Ejemplos:
    python scripts/export_banks_excel.py --out Products/Bancos
    python scripts/export_banks_excel.py --only 001 --out /tmp/prueba
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from scripts.ingest_banks import load_env  # noqa: E402
from src.banks import excel  # noqa: E402


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Excel de producto de bancos")
    p.add_argument("--out", default="Products/Bancos", help="Directorio de salida")
    p.add_argument("--banks", default="", help="Códigos separados por coma; vacío = todos")
    p.add_argument("--only", default="", help="Alias de --banks para un solo código")
    p.add_argument("--incluir-agregados", action="store_true",
                   help="Incluye el código 999 (sistema bancario), excluido por defecto")
    p.add_argument("--dry-run", action="store_true",
                   help="Lista qué libros generaría, sin escribir archivos")
    return p


def listar_bancos(conn, codes: list[str], incluir_agregados: bool) -> list[tuple[str, str]]:
    sql = """
        SELECT i.codigo_institucion, i.nombre_institucion
        FROM bank_institutions i
        WHERE EXISTS (SELECT 1 FROM bank_financial_data f
                      WHERE f.codigo_institucion = i.codigo_institucion)
    """
    params: list = []
    if not incluir_agregados:
        # El nombre vacío es la otra cara de is_aggregate: el catálogo de la CMF trae los
        # subtotales (900/970/980/999) sin nombre. Se filtra por ambos por si la CMF suma
        # un agregado nuevo que _AGGREGATE_CODES todavía no conozca: un banco sin nombre
        # no puede ser un producto (el server deduce la empresa del nombre del archivo).
        sql += " AND i.is_aggregate = false AND coalesce(trim(i.nombre_institucion),'') <> ''"
    if codes:
        sql += " AND i.codigo_institucion = ANY(%s)"
        params.append(codes)
    sql += " ORDER BY i.codigo_institucion"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return [(r[0], r[1]) for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    codes = [c.strip() for c in (args.banks or args.only).split(",") if c.strip()]

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
    try:
        bancos = listar_bancos(conn, codes, args.incluir_agregados)
        if not bancos:
            print("Ningún banco con datos financieros para exportar", file=sys.stderr)
            return 1
        out_dir = Path(args.out)
        if not args.dry_run:
            out_dir.mkdir(parents=True, exist_ok=True)

        for cod, nombre in bancos:
            wb, meta = excel.construir_libro(conn, cod, nombre)
            fname = excel.nombre_archivo(nombre, meta.rut, meta.periodos)
            hojas = ", ".join(wb.sheetnames)
            if args.dry_run:
                print(f"[dry-run] {cod}: {fname}")
                print(f"          hojas: {hojas}")
                continue
            wb.save(out_dir / fname)
            n = len(meta.periodos)
            print(f"{cod}: {fname}  ({n} períodos, hojas: {hojas})")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
