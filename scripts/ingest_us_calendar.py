#!/usr/bin/env python3
"""CLI: calendario de resultados de EEUU (SEC `submissions`) -> tabla earnings_calendar.

Puebla las fechas de resultados de las empresas de EEUU, que la web no tenía: el 8-K item
2.02 (anuncio de resultados, con hora), el 10-Q/10-K (estados) y la próxima fecha estimada
por cadencia. Las chilenas ya viven en report_publication_dates y la vista v_company_calendar
une ambas — este script sólo escribe el lado gringo.

Por defecto NO escribe: Supabase es producción. Para escribir, `--supabase-live`.

Ejemplos:
    python scripts/ingest_us_calendar.py --tickers AAPL         # dry-run
    python scripts/ingest_us_calendar.py                        # las 49, dry-run
    python scripts/ingest_us_calendar.py --supabase-live        # de verdad
"""

import argparse
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.edgar.api_client import EdgarClient, NoDataError  # noqa: E402
from src.edgar.calendar import build_events, estimate_next  # noqa: E402
from src.edgar.endpoints import submissions_url  # noqa: E402


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


def select_companies(conn, tickers: list[str]) -> list[tuple[int, str, str]]:
    with conn.cursor() as cur:
        base = ("SELECT id, cik, ticker FROM companies "
                "WHERE market = 'US' AND cik IS NOT NULL")
        if tickers:
            cur.execute(base + " AND ticker = ANY(%s) ORDER BY ticker", (tickers,))
        else:
            cur.execute(base + " ORDER BY ticker")
        return [(int(r[0]), r[1], r[2]) for r in cur.fetchall()]


_UPSERT = """
    INSERT INTO earnings_calendar
        (company_id, event_type, event_date, event_time, timing,
         period_year, period_quarter, form, accession, status, source, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sec_edgar', now())
    ON CONFLICT (company_id, event_type, event_date) DO UPDATE SET
        event_time = EXCLUDED.event_time,
        timing = EXCLUDED.timing,
        period_year = EXCLUDED.period_year,
        period_quarter = EXCLUDED.period_quarter,
        form = EXCLUDED.form,
        accession = EXCLUDED.accession,
        status = EXCLUDED.status,
        updated_at = now()
"""


def write_events(cur, company_id: int, events, estimated) -> int:
    # La estimada es una sola por empresa y su fecha cambia entre corridas; se borra la
    # anterior antes de insertar para no dejar dos estimadas. Los confirmados los desempata
    # el UNIQUE (company_id, event_type, event_date).
    cur.execute(
        "DELETE FROM earnings_calendar WHERE company_id = %s AND event_type = 'estimated'",
        (company_id,),
    )
    written = 0
    to_write = list(events) + ([estimated] if estimated else [])
    for e in to_write:
        cur.execute(_UPSERT, (
            company_id, e.event_type, e.event_date, e.event_time, e.timing,
            e.period_year, e.period_quarter, e.form, e.accession, e.status,
        ))
        written += 1
    return written


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Calendario de resultados US (SEC EDGAR)")
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
    today = date.today()

    conn = connect(env)
    try:
        companies = select_companies(conn, tickers)
        if not companies:
            print(f"Sin empresas para {tickers or 'market=US'}", file=sys.stderr)
            return 2

        modo = "DRY-RUN (no escribe)" if dry_run else "*** LIVE: ESCRIBE EN PRODUCCIÓN ***"
        print(f"[{modo}] {len(companies)} empresas\n")

        client = EdgarClient(user_agent, rate_per_sec=args.rate)
        ok = fail = total = con_estimada = 0
        for company_id, cik, ticker in companies:
            try:
                sub = client.get_json(submissions_url(cik))
                events = build_events(sub)
                estimated = estimate_next(events, today)
                if not dry_run:
                    with conn.cursor() as cur:
                        write_events(cur, company_id, events, estimated)
                    conn.commit()
                ok += 1
                total += len(events)
                con_estimada += 1 if estimated else 0
                earn = sum(1 for e in events if e.event_type == "earnings")
                fin = sum(1 for e in events if e.event_type == "financials")
                est = f"est {estimated.event_date}" if estimated else "sin estimada"
                print(f"  {ticker:<6} ok  earnings={earn:<3} financials={fin:<3} {est}", flush=True)
            except NoDataError:
                fail += 1
                print(f"  {ticker:<6} sin submissions", flush=True)
            except Exception as exc:  # noqa: BLE001 - una empresa no aborta el lote
                fail += 1
                if not dry_run:
                    conn.rollback()
                print(f"  {ticker:<6} FALLA  {str(exc)[:80]}", flush=True)

        print(f"\n{ok}/{len(companies)} ok, {fail} con error · {total} eventos confirmados, "
              f"{con_estimada} con próxima fecha estimada")
        if dry_run:
            print("\nNada se escribió. Para escribir de verdad: --supabase-live")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
