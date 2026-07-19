#!/usr/bin/env python3
"""Puebla `us_costo_deuda`: el Kd DECLARADO de las empresas de EEUU, del 10-K.

Para cada empresa US (companies.market='US' con cik) baja el último 10-K, parsea la tasa
efectiva ponderada por instrumento con `src/edgar/deuda.py`, calcula la COBERTURA contra la
deuda del balance, y (con --save) hace upsert en `us_costo_deuda`. Las empresas que no
taggean tasas (la mayoría) no generan fila: el DCF cae a la estimación InterestExpense/deuda.

DRY-RUN por defecto (no escribe). Uso:
    python scripts/refresh_us_kd.py --user-agent "Tu Nombre tu@correo.com"
    python scripts/refresh_us_kd.py --save --user-agent "..." [--only CIK,CIK]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import psycopg2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.edgar.api_client import EdgarClient, ApiError, NoDataError  # noqa: E402
from src.edgar.deuda import costo_de_deuda, a_dict_excel  # noqa: E402

FDC = Path(os.environ.get("FDC_DIR", "/home/unzzui/Proyectos/FinDataChile"))

# Deuda financiera del balance, para la cobertura (mismos labels que el catálogo EDGAR).
_DEUDA_LABELS = (
    "otros pasivos financieros corrientes",
    "otros pasivos financieros no corrientes",
)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def connect(env: dict[str, str]):
    return psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", 5432), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"], sslmode="require")


def us_companies(conn, only: set[str] | None) -> list[tuple[int, str, str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, cik, razon_social FROM companies "
            "WHERE market = 'US' AND cik IS NOT NULL ORDER BY id")
        rows = cur.fetchall()
    if only:
        rows = [r for r in rows if str(r[1]).lstrip("0") in {o.lstrip("0") for o in only}
                or str(r[0]) in only]
    return [(int(i), str(c), n) for i, c, n in rows]


def balance_debt_miles(conn, company_id: int) -> float | None:
    """Deuda financiera del balance (corriente + no corriente) al último cierre anual, en miles."""
    with conn.cursor() as cur:
        like = " OR ".join(["LOWER(TRIM(fli.label)) = %s"] * len(_DEUDA_LABELS))
        cur.execute(
            f"""
            SELECT COALESCE(SUM(v.value), 0) FROM (
                SELECT fli.label, fd.value,
                       ROW_NUMBER() OVER (PARTITION BY fli.label ORDER BY fd.period_year DESC) rn
                FROM financial_data fd
                JOIN financial_line_items fli ON fd.line_item_id = fli.id
                WHERE fd.company_id = %s AND fd.period_quarter = 4
                  AND fd.value IS NOT NULL AND ({like})
            ) v WHERE v.rn = 1
            """,
            [company_id, *_DEUDA_LABELS],
        )
        row = cur.fetchone()
    total = float(row[0]) if row and row[0] is not None else 0.0
    return total or None


def upsert(conn, company_id: int, cd, filing, deuda_cubierta_miles: float,
           cobertura: float | None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO us_costo_deuda
              (company_id, period_year, period_quarter, kd, deuda_cubierta, n_creditos,
               cobertura, por_instrumento, detalle, fuente, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, NOW())
            ON CONFLICT (company_id, period_year, period_quarter) DO UPDATE SET
              kd = EXCLUDED.kd, deuda_cubierta = EXCLUDED.deuda_cubierta,
              n_creditos = EXCLUDED.n_creditos, cobertura = EXCLUDED.cobertura,
              por_instrumento = EXCLUDED.por_instrumento, detalle = EXCLUDED.detalle,
              fuente = EXCLUDED.fuente, updated_at = NOW()
            """,
            [company_id, filing.period_year, filing.period_quarter, round(cd.kd, 6),
             round(deuda_cubierta_miles, 2), cd.n_creditos,
             round(cobertura, 4) if cobertura is not None else None,
             json.dumps({k: round(v, 2) for k, v in cd.por_instrumento.items()}),
             json.dumps(a_dict_excel(cd)), filing.instancia_url],
        )
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="Escribir en us_costo_deuda (default: dry-run)")
    ap.add_argument("--only", default="", help="CIKs o IDs separados por coma")
    ap.add_argument("--user-agent", default=os.environ.get("EDGAR_UA", ""),
                    help="User-Agent SEC (nombre y correo reales; obligatorio)")
    args = ap.parse_args()

    if not args.user_agent or "@" not in args.user_agent:
        print("ERROR: la SEC exige --user-agent con nombre y correo reales "
              "(o la env EDGAR_UA). Ej: 'Diego Bravo diego@correo.com'.")
        return 2

    env = load_env(FDC / ".env")
    conn = connect(env)
    client = EdgarClient(user_agent=args.user_agent)
    only = {x.strip() for x in args.only.split(",") if x.strip()} or None
    targets = us_companies(conn, only)

    print(f"Empresas US: {len(targets)} | modo: {'LIVE (--save)' if args.save else 'DRY-RUN'}")
    con_kd = sin_kd = baja_cob = 0
    for cid, cik, name in targets:
        try:
            r = costo_de_deuda(client, cik)
        except (ApiError, NoDataError) as exc:
            print(f"  {name[:26]:28} — sin 10-K/datos ({type(exc).__name__})")
            sin_kd += 1
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  {name[:26]:28} — ERROR {type(exc).__name__}: {str(exc)[:60]}")
            sin_kd += 1
            continue
        if r is None:
            sin_kd += 1
            continue
        cd, filing = r
        cubierta_miles = cd.deuda_cubierta / 1000.0  # dólares → miles
        bd = balance_debt_miles(conn, cid)
        cobertura = (cubierta_miles / bd) if bd else None
        flag = ""
        if cobertura is not None and cobertura < 0.5:
            baja_cob += 1
            flag = "  (cobertura baja → el DCF caerá a estimación)"
        con_kd += 1
        print(f"  {name[:26]:28} Kd={cd.kd:6.2%}  n={cd.n_creditos:>2}  "
              f"cob={cobertura:.0%}" if cobertura is not None else
              f"  {name[:26]:28} Kd={cd.kd:6.2%}  n={cd.n_creditos:>2}  cob=?", end="")
        print(flag)
        if args.save:
            upsert(conn, cid, cd, filing, cubierta_miles, cobertura)

    conn.close()
    print(f"\nCon Kd declarado: {con_kd}  ·  sin tasas: {sin_kd}  ·  cobertura baja: {baja_cob}")
    if not args.save:
        print("DRY-RUN: no se escribió nada. Repetí con --save para poblar us_costo_deuda.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
