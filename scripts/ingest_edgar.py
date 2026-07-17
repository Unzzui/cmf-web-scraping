#!/usr/bin/env python3
"""CLI: ingesta de estados financieros de EEUU desde SEC EDGAR a financial_*.

Por defecto NO escribe: Supabase es producción. Para escribir hay que pasar
`--supabase-live` a propósito.

Ejemplos:
    # Una empresa, sin tocar la base (lo que pide el spec §9.1 para empezar)
    python scripts/ingest_edgar.py --tickers AAPL

    # Las 49, dry-run, con detalle de validación
    python scripts/ingest_edgar.py --verbose

    # De verdad (sólo si Diego lo pidió)
    python scripts/ingest_edgar.py --tickers AAPL --supabase-live

El User-Agent sale de EDGAR_USER_AGENT en .env y la SEC lo exige con contacto real.
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.edgar.api_client import EdgarClient  # noqa: E402
from src.edgar.loader import EdgarLoader  # noqa: E402
from src.edgar.runner import DEFAULT_MIN_YEAR, ingest_company  # noqa: E402


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingesta de estados financieros US (SEC EDGAR)")
    p.add_argument("--tickers", default="",
                   help="Tickers separados por coma; vacío = las 49 de market='US'")
    p.add_argument("--min-year", type=int, default=DEFAULT_MIN_YEAR,
                   help=f"Año fiscal mínimo (default {DEFAULT_MIN_YEAR}: antes no hay XBRL)")
    p.add_argument("--supabase-live", action="store_true",
                   help="ESCRIBE en producción. Sin esto es dry-run.")
    p.add_argument("--rate", type=float, default=8.0,
                   help="Requests/segundo a la SEC (el límite duro es 10)")
    p.add_argument("--verbose", action="store_true",
                   help="Detalle de los chequeos de validación por empresa")
    return p


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


def select_companies(conn, tickers: list[str]) -> list[tuple[str, str]]:
    """[(cik, ticker)] de market='US'. El filtro por market no es opcional (spec §3)."""
    with conn.cursor() as cur:
        if tickers:
            cur.execute(
                "SELECT cik, ticker FROM companies "
                "WHERE market = 'US' AND cik IS NOT NULL AND ticker = ANY(%s) "
                "ORDER BY ticker",
                (tickers,),
            )
        else:
            cur.execute(
                "SELECT cik, ticker FROM companies "
                "WHERE market = 'US' AND cik IS NOT NULL ORDER BY ticker"
            )
        return [(r[0], r[1]) for r in cur.fetchall()]


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    env = load_env(REPO_ROOT / ".env")

    user_agent = env.get("EDGAR_USER_AGENT")
    if not user_agent:
        print(
            "Falta EDGAR_USER_AGENT en .env. La SEC exige identificarse con nombre y "
            "contacto reales o responde 403 a todo, ej.:\n"
            "  EDGAR_USER_AGENT=FindataChile contacto@findatachile.com",
            file=sys.stderr,
        )
        return 2

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    dry_run = not args.supabase_live

    conn = connect(env)
    try:
        loader = EdgarLoader(conn, dry_run=dry_run)
        if not dry_run and not loader.has_source_columns():
            print(
                "Falta la migración 011 (source_tag/source_label) en la base.\n"
                "Aplicar en el repo web: \\i migrations/011_line_item_source_tag.sql",
                file=sys.stderr,
            )
            return 2

        companies = select_companies(conn, tickers)
        if not companies:
            print(f"Sin empresas para {tickers or 'market=US'}", file=sys.stderr)
            return 2

        # §8.6: las chilenas tienen que quedar intactas. Se cuenta antes y después.
        cl_before = loader.count_rows("CL")
        us_before = loader.count_rows("US")

        modo = "DRY-RUN (no escribe)" if dry_run else "*** LIVE: ESCRIBE EN PRODUCCIÓN ***"
        print(f"[{modo}] {len(companies)} empresas, desde el año fiscal {args.min_year}\n")

        client = EdgarClient(user_agent, rate_per_sec=args.rate)
        results = []
        for cik, ticker in companies:
            result = ingest_company(client, loader, cik, min_year=args.min_year)
            results.append(result)
            if not dry_run:
                conn.commit()
            rango = f"{result.years[0]}-{result.years[1]}" if result.years else "-"
            flags = []
            if result.identity_errors:
                flags.append(f"CUADRATURA×{result.identity_errors}")
            if result.accumulation_errors:
                flags.append(f"ACUMULACIÓN×{result.accumulation_errors}")
            if result.drift_warnings:
                flags.append(f"drift×{result.drift_warnings}")
            alerta = ("  ⚠ " + " ".join(flags)) if flags else ""
            print(
                f"  {ticker:<6} {result.status:<10} líneas={result.line_items:<4} "
                f"celdas={result.cells:<6} años={rango:<10}{alerta}"
                + (f"  {result.message}" if result.message else ""),
                flush=True,
            )

        ok = [r for r in results if r.status == "completed"]
        malos = [r for r in results if r.identity_errors or r.accumulation_errors]
        print(f"\n{len(ok)}/{len(results)} completadas, {sum(r.cells for r in ok):,} celdas")
        if malos:
            print(f"⚠  {len(malos)} con problemas de validación: "
                  f"{', '.join(r.ticker or r.cik for r in malos)}")

        cl_after = loader.count_rows("CL")
        us_after = loader.count_rows("US")
        print(f"\nCL líneas/celdas: {cl_before} -> {cl_after}"
              + ("  OK intactas" if cl_before == cl_after else "  ⚠ CAMBIARON"))
        print(f"US líneas/celdas: {us_before} -> {us_after}")
        if dry_run:
            print("\nNada se escribió. Para escribir de verdad: --supabase-live")
        return 0 if not malos else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
