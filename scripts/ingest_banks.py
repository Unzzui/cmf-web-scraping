#!/usr/bin/env python3
"""CLI: ingesta de bancos desde la API CMF a la base.

Ejemplos:
    python scripts/ingest_banks.py --from 01/2022 --to 05/2025
    python scripts/ingest_banks.py --from 05/2025 --to 05/2025 --only 001 --dry-run
"""

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.banks import runner  # noqa: E402
from src.banks.api_client import CMFApiClient, NoDataError  # noqa: E402
from src.banks.loader import BankLoader  # noqa: E402


def parse_period(text: str) -> tuple[int, int]:
    if "/" not in text:
        raise ValueError(f"Período inválido '{text}', use MM/YYYY")
    mm, yyyy = text.split("/", 1)
    month, year = int(mm), int(yyyy)
    if not (1 <= month <= 12):
        raise ValueError(f"Mes fuera de rango: {month}")
    if not (2000 <= year <= 2100):
        raise ValueError(f"Año fuera de rango: {year}")
    return (year, month)


def iter_months(desde: tuple[int, int], hasta: tuple[int, int]) -> list[tuple[int, int]]:
    (y0, m0), (y1, m1) = desde, hasta
    out: list[tuple[int, int]] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


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
    p = argparse.ArgumentParser(description="Ingesta de bancos desde la API CMF")
    p.add_argument("--from", dest="desde", required=True, help="Período inicial MM/YYYY")
    p.add_argument("--to", dest="hasta", required=True, help="Período final MM/YYYY")
    p.add_argument("--banks", default="", help="Códigos separados por coma; vacío = todos")
    p.add_argument("--only", default="", help="Alias de --banks para un solo código")
    p.add_argument("--reports", default="", help="Reports separados por coma; vacío = todos")
    p.add_argument("--dry-run", action="store_true", help="No escribe a la base")
    p.add_argument("--pause", type=float, default=0.3,
                   help="Segundos de espera entre llamadas al API (throttle)")
    p.add_argument("--workers", type=int, default=1,
                   help="Bancos procesados en paralelo (1 = secuencial). El cuello de "
                        "botella es el API de la CMF, no la BD.")
    return p


def _ingest_un_banco(env, apikey, pause, cod, y, m, reports) -> tuple[str, dict | None, str | None]:
    """Procesa un banco/período con conexión y cliente propios (corre en un thread)."""
    import psycopg2

    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", "5432"), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"],
    )
    conn.autocommit = False
    try:
        client = CMFApiClient(apikey, pause=pause)
        loader = BankLoader(conn)
        result: dict[str, str] = {}
        # Un commit por report, no uno al final de los seis: si la transacción abarcara
        # todos, el worker retendría los locks de bank_accounts (catálogo compartido)
        # durante los ~14s que tarda la llamada del report siguiente, y los demás workers
        # deadlockearían contra él.
        for report in reports:
            result.update(runner.ingest_period(client, loader, cod, y, m, (report,)))
            conn.commit()
        return (cod, result, None)
    except Exception as exc:  # noqa: BLE001 - un banco que revienta no aborta el backfill
        conn.rollback()
        return (cod, None, str(exc))
    finally:
        conn.close()


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    try:
        desde = parse_period(args.desde)
        hasta = parse_period(args.hasta)
    except ValueError as exc:
        print(f"Periodo invalido: {exc}", file=sys.stderr)
        return 2
    meses = iter_months(desde, hasta)
    if not meses:
        print(
            f"Rango vacio: --from {args.desde} es posterior a --to {args.hasta}",
            file=sys.stderr,
        )
        return 2
    reports = tuple(r.strip() for r in args.reports.split(",") if r.strip()) \
        or runner.REPORTS_DEFAULT
    codes = [c.strip() for c in (args.banks or args.only).split(",") if c.strip()]

    env = load_env(REPO_ROOT / ".env")
    apikey = env.get("CMF_API_KEY")
    if not apikey:
        print("Falta CMF_API_KEY en .env", file=sys.stderr)
        return 2

    client = CMFApiClient(apikey, pause=args.pause)

    if args.dry_run:
        print(f"[dry-run] meses={len(meses)} reports={reports} bancos={codes or 'todos'}")
        return 0

    import psycopg2

    missing = [k for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not env.get(k)]
    if missing:
        print(f"Faltan credenciales PG en .env: {', '.join(missing)}", file=sys.stderr)
        return 2

    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", "5432"), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"],
    )
    conn.autocommit = False
    loader = BankLoader(conn)
    try:
        loader.apply_schema()
        conn.commit()
        explicit_codes = codes
        for (y, m) in meses:
            try:
                period_codes = runner.sync_institutions(client, loader, y, m)
                conn.commit()
            except NoDataError:
                print(f"{y}-{m:02d}: sin catalogo de instituciones, se omite")
                continue
            run_codes = explicit_codes if explicit_codes else period_codes
            if args.workers <= 1:
                for cod in run_codes:
                    result = runner.ingest_period(client, loader, cod, y, m, reports)
                    conn.commit()
                    done = sum(1 for s in result.values() if s == "completed")
                    print(f"{y}-{m:02d} {cod}: {done}/{len(result)} completed", flush=True)
            else:
                with ThreadPoolExecutor(max_workers=args.workers) as pool:
                    futuros = [
                        pool.submit(_ingest_un_banco, env, apikey, args.pause, cod, y, m,
                                    reports)
                        for cod in run_codes
                    ]
                    for fut in as_completed(futuros):
                        cod, result, error = fut.result()
                        if error is not None:
                            print(f"{y}-{m:02d} {cod}: ERROR {error}", flush=True)
                            continue
                        done = sum(1 for s in result.values() if s == "completed")
                        print(f"{y}-{m:02d} {cod}: {done}/{len(result)} completed",
                              flush=True)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
