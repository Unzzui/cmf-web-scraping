#!/usr/bin/env python3
"""Fechas de publicación de EEFF informadas a la CMF -> Supabase.

Fuente: https://www.cmfchile.cl/institucional/mercados/novedades_envio_fechas_eeff.php
La página es un POST simple (``aaaa=<año>``), así que no necesita Selenium.

Escribe en dos lugares:

1. ``report_publication_dates`` (migración 013) — fuente de verdad, con dimensión
   de año, así que soporta varios años a la vez y el histórico.
2. ``companies.filing_marzo/junio/septiembre/diciembre`` — 4 fechas sueltas sin
   año que la web YA consume (``app/api/utils/filing-dates``, página de empresa).
   Se refrescan con el año en curso para que la UI existente deje de mostrar datos
   viejos, sin tocar el frontend.

Un guión en la tabla de la CMF significa "el emisor aún no informó esa fecha",
no "no hay entrega": esas celdas no se insertan.

Uso:
    python scripts/scrape_report_dates.py --years 2026,2027 --dry-run
    python scripts/scrape_report_dates.py --years 2026,2027 --refresh-filing-year 2026
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.gui.pipeline.supabase_uploader import (  # noqa: E402
    load_env_file,
    resolve_pg_conn,
)

CMF_URL = ("https://www.cmfchile.cl/institucional/mercados/"
           "novedades_envio_fechas_eeff.php")
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# Orden de las columnas de fecha en la tabla de la CMF.
QUARTER_BY_COLUMN = {2: 1, 3: 2, 4: 3, 5: 4}  # Marzo, Junio, Septiembre, Diciembre
FILING_COLUMN = {1: "filing_marzo", 2: "filing_junio",
                 3: "filing_septiembre", 4: "filing_diciembre"}

_RUT_RE = re.compile(r"^\s*([\d.]+)\s*-\s*([\dkK])\s*$")


@dataclass(frozen=True)
class PublicationDate:
    rut: str
    razon_social: str
    period_year: int
    period_quarter: int
    publication_date: date


def normalize_rut(raw: str) -> str | None:
    """'96.874.030 - K' -> '96874030-K'. None si no parsea."""
    m = _RUT_RE.match(str(raw or ""))
    if not m:
        return None
    return f"{m.group(1).replace('.', '')}-{m.group(2).upper()}"


def parse_date(raw: str) -> date | None:
    """'29/05/2026' -> date. El guión ('-') significa 'aún no informada'."""
    s = str(raw or "").strip()
    if not s or s == "-":
        return None
    try:
        return datetime.strptime(s, "%d/%m/%Y").date()
    except ValueError:
        return None


def fetch_year(session: requests.Session, year: int) -> list[PublicationDate]:
    """Descarga y parsea la tabla de un año."""
    resp = session.post(CMF_URL, data={"aaaa": str(year)}, timeout=45)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = None
    for candidate in soup.find_all("table"):
        head = " ".join(th.get_text(" ", strip=True)
                        for th in candidate.find_all("th"))
        if "RUT" in head and "Raz" in head:
            table = candidate
            break
    if table is None:
        raise RuntimeError(f"No se encontró la tabla de fechas para {year}")

    out: list[PublicationDate] = []
    for tr in table.find_all("tr"):
        cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
        if len(cells) < 6:
            continue
        rut = normalize_rut(cells[1])
        if not rut:
            continue
        razon = re.sub(r"\s+", " ", cells[0]).strip()
        for col, quarter in QUARTER_BY_COLUMN.items():
            pub = parse_date(cells[col])
            if pub is not None:
                out.append(PublicationDate(rut, razon, year, quarter, pub))
    return out


def upsert(conn, rows: list[PublicationDate]) -> tuple[int, int]:
    """Inserta/actualiza en report_publication_dates. Devuelve (filas, con_company_id)."""
    cur = conn.cursor()
    # company_id se resuelve por la parte numérica del RUT: en `companies` el DV
    # viene con mayúsculas y minúsculas mezcladas ('77465741-k').
    cur.executemany(
        """
        INSERT INTO report_publication_dates
            (rut, company_id, razon_social_cmf, period_year, period_quarter,
             publication_date)
        VALUES (
            %(rut)s,
            (SELECT id FROM companies
              WHERE rut_numero::text = split_part(%(rut)s, '-', 1) LIMIT 1),
            %(razon)s, %(year)s, %(quarter)s, %(pub)s
        )
        ON CONFLICT (rut, period_year, period_quarter) DO UPDATE
           SET publication_date = EXCLUDED.publication_date,
               company_id       = COALESCE(EXCLUDED.company_id,
                                           report_publication_dates.company_id),
               razon_social_cmf = EXCLUDED.razon_social_cmf,
               updated_at       = NOW()
        """,
        [{"rut": r.rut, "razon": r.razon_social, "year": r.period_year,
          "quarter": r.period_quarter, "pub": r.publication_date} for r in rows],
    )
    cur.execute("SELECT COUNT(*), COUNT(company_id) FROM report_publication_dates")
    total, matched = cur.fetchone()
    return total, matched


def refresh_filing_columns(conn, year: int) -> int:
    """Copia las fechas de `year` a companies.filing_*, que es lo que la web lee hoy."""
    cur = conn.cursor()
    sets = ", ".join(
        f"{col} = d.q{q}" for q, col in FILING_COLUMN.items()
    )
    cur.execute(
        f"""
        WITH d AS (
            SELECT company_id,
                   MAX(publication_date) FILTER (WHERE period_quarter = 1) AS q1,
                   MAX(publication_date) FILTER (WHERE period_quarter = 2) AS q2,
                   MAX(publication_date) FILTER (WHERE period_quarter = 3) AS q3,
                   MAX(publication_date) FILTER (WHERE period_quarter = 4) AS q4
              FROM report_publication_dates
             WHERE period_year = %s AND company_id IS NOT NULL
             GROUP BY company_id
        )
        UPDATE companies c SET {sets}, updated_at = NOW()
          FROM d WHERE c.id = d.company_id
        """,
        (year,),
    )
    return cur.rowcount


def clear_stale_filing(conn, year: int) -> int:
    """Borra companies.filing_* de emisores sin fechas informadas para `year`.

    Una empresa que salió del registro de la CMF (p. ej. Telefónica del Sur, que
    está en la tabla 2025 y no en la 2026) conservaba sus fechas del año anterior,
    y la web —que no distingue el año— las mostraba como próxima entrega. Dejarlas
    en NULL es más honesto que mostrar una fecha pasada.
    """
    cur = conn.cursor()
    nulls = ", ".join(f"{col} = NULL" for col in FILING_COLUMN.values())
    cur.execute(
        f"""
        UPDATE companies c SET {nulls}, updated_at = NOW()
         WHERE (c.filing_marzo IS NOT NULL OR c.filing_junio IS NOT NULL
                OR c.filing_septiembre IS NOT NULL OR c.filing_diciembre IS NOT NULL)
           AND NOT EXISTS (
                 SELECT 1 FROM report_publication_dates r
                  WHERE r.company_id = c.id AND r.period_year = %s)
        """,
        (year,),
    )
    return cur.rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--years", default="2026,2027",
                    help="Años a ingestar, separados por coma (default: 2026,2027)")
    ap.add_argument("--env-file",
                    default="/home/unzzui/Proyectos/FinDataChile/.env",
                    help="`.env` con las vars PG* de Supabase")
    ap.add_argument("--refresh-filing-year", type=int, default=None,
                    help="Copiar las fechas de ese año a companies.filing_* "
                         "(lo que ya lee la web). Ej: 2026")
    ap.add_argument("--clear-stale-filing", action="store_true",
                    help="Dejar en NULL companies.filing_* de emisores sin fechas "
                         "en --refresh-filing-year (salieron del registro CMF)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Scrapear y mostrar, sin escribir en la BD")
    args = ap.parse_args()

    if args.clear_stale_filing and not args.refresh_filing_year:
        ap.error("--clear-stale-filing requiere --refresh-filing-year")

    years = [int(y) for y in args.years.split(",") if y.strip()]

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    rows: list[PublicationDate] = []
    for year in years:
        year_rows = fetch_year(session, year)
        companies = len({r.rut for r in year_rows})
        print(f"  {year}: {len(year_rows)} fechas informadas por {companies} emisores")
        rows.extend(year_rows)

    if not rows:
        print("[error] La CMF no devolvió ninguna fecha")
        return 1

    print(f"\nTotal: {len(rows)} fechas, {len({r.rut for r in rows})} emisores")
    upcoming = sorted((r for r in rows if r.publication_date >= date.today()),
                      key=lambda r: r.publication_date)
    print(f"Futuras (>= hoy): {len(upcoming)}")
    for r in upcoming[:5]:
        print(f"   {r.publication_date}  Q{r.period_quarter} {r.period_year}  "
              f"{r.razon_social[:44]}")

    if args.dry_run:
        print("\ndry-run -> no se escribe en la BD")
        return 0

    import psycopg2  # import tardío: el dry-run no necesita la BD

    conn = psycopg2.connect(**resolve_pg_conn(load_env_file(Path(args.env_file))))
    try:
        total, matched = upsert(conn, rows)
        print(f"\nreport_publication_dates: {total} filas "
              f"({matched} enlazadas a una empresa del catálogo)")
        if args.refresh_filing_year:
            n = refresh_filing_columns(conn, args.refresh_filing_year)
            print(f"companies.filing_*: {n} empresas actualizadas "
                  f"con fechas {args.refresh_filing_year}")
        if args.clear_stale_filing:
            n = clear_stale_filing(conn, args.refresh_filing_year)
            print(f"companies.filing_*: {n} empresas limpiadas "
                  f"(sin fechas informadas para {args.refresh_filing_year})")
        conn.commit()
        print("commit ok")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
