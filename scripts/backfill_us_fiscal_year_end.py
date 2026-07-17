#!/usr/bin/env python3
"""CLI: mes de cierre del año fiscal de las empresas de EEUU -> companies.fiscal_year_end_month.

Las gringas rotulan sus estados por trimestre FISCAL ("2025Q4"), que no es calendario: el
Q4 de Apple cierra en septiembre, el de Nike en mayo. Con el mes de cierre (1-12) la web
deriva el mes real de cada trimestre y deja de mostrar el ambiguo "2025Q4". Este valor sale
del `reportDate` de los 10-K en el `submissions` de la SEC (moda del mes).

Sólo toca EEUU; en Chile la columna queda NULL (la CMF reporta en trimestres calendario).

Por defecto NO escribe: Supabase es producción. Para escribir, `--supabase-live`.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.edgar.api_client import EdgarClient, NoDataError  # noqa: E402
from src.edgar.calendar import fiscal_year_end_month  # noqa: E402
from src.edgar.endpoints import submissions_url  # noqa: E402

_MESES = ["", "ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic"]


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def connect(env: dict):
    import psycopg2

    missing = [k for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not env.get(k)]
    if missing:
        raise SystemExit(f"Faltan credenciales PG en .env: {', '.join(missing)}")
    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", "5432"), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"],
    )
    conn.autocommit = False
    return conn


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Mes de cierre fiscal US (SEC submissions)")
    p.add_argument("--tickers", default="", help="Tickers separados por coma; vacío = las 49")
    p.add_argument("--supabase-live", action="store_true", help="ESCRIBE en producción")
    p.add_argument("--rate", type=float, default=8.0)
    args = p.parse_args(argv)

    env = load_env(REPO_ROOT / ".env")
    user_agent = env.get("EDGAR_USER_AGENT")
    if not user_agent:
        print("Falta EDGAR_USER_AGENT en .env", file=sys.stderr)
        return 2

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    dry_run = not args.supabase_live

    conn = connect(env)
    try:
        with conn.cursor() as cur:
            base = "SELECT id, cik, ticker FROM companies WHERE market = 'US' AND cik IS NOT NULL"
            if tickers:
                cur.execute(base + " AND ticker = ANY(%s) ORDER BY ticker", (tickers,))
            else:
                cur.execute(base + " ORDER BY ticker")
            companies = [(int(r[0]), r[1], r[2]) for r in cur.fetchall()]

        modo = "DRY-RUN (no escribe)" if dry_run else "*** LIVE: ESCRIBE EN PRODUCCIÓN ***"
        print(f"[{modo}] {len(companies)} empresas\n")

        client = EdgarClient(user_agent, rate_per_sec=args.rate)
        ok = fail = sin = 0
        for company_id, cik, ticker in companies:
            try:
                sub = client.get_json(submissions_url(cik))
                fye = fiscal_year_end_month(sub)
                if fye is None:
                    sin += 1
                    print(f"  {ticker:<6} sin 10-K con reportDate")
                    continue
                if not dry_run:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE companies SET fiscal_year_end_month = %s WHERE id = %s",
                            (fye, company_id),
                        )
                    conn.commit()
                ok += 1
                print(f"  {ticker:<6} cierre = {fye:>2} ({_MESES[fye]})")
            except NoDataError:
                fail += 1
                print(f"  {ticker:<6} sin submissions")
            except Exception as exc:  # noqa: BLE001
                fail += 1
                if not dry_run:
                    conn.rollback()
                print(f"  {ticker:<6} FALLA  {str(exc)[:80]}")

        print(f"\n{ok} ok, {sin} sin dato, {fail} con error")
        if dry_run:
            print("\nNada se escribió. Para escribir de verdad: --supabase-live")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
