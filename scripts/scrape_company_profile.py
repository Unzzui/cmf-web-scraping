#!/usr/bin/env python3
"""Perfil de empresa desde la CMF: 12 mayores accionistas + directorio -> Supabase.

Fuentes (``entidad.php`` de cmfchile.cl, por RUT):
  * pestania=5   -> 12 Mayores Accionistas (del último período informado)
  * pestania=46  -> Directores (composición actual)

Los accionistas se guardan en dos granularidades, porque la CMF publica ambas:
la fila consolidada por accionista (``serie IS NULL``) y, cuando la empresa tiene
más de una serie de acciones (p. ej. SQM: AA/BB), el desglose por serie.

Uso:
    python scripts/scrape_company_profile.py --limit 5 --dry-run
    python scripts/scrape_company_profile.py            # todas las del catálogo
"""

from __future__ import annotations

import argparse
import re
import sys
import time
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

ENTIDAD_URL = "https://www.cmfchile.cl/institucional/mercados/entidad.php"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

TAB_SHAREHOLDERS = 5
TAB_DIRECTORS = 46


@dataclass
class Shareholder:
    holder_name: str
    serie: str | None
    shares_subscribed: int | None
    shares_paid: int | None
    ownership_pct: float | None
    rank: int


@dataclass
class Director:
    person_rut: str | None
    person_name: str
    cargo: str | None
    appointed_at: date | None


def entidad_url(rut_numero: str, tab: int) -> str:
    return (f"{ENTIDAD_URL}?mercado=V&rut={rut_numero}&grupo=&tipoentidad=RVEMI"
            f"&row=&vig=VI&control=svs&pestania={tab}")


def _int(raw: str) -> int | None:
    """'62.556.568' -> 62556568."""
    s = re.sub(r"[^\d]", "", str(raw or ""))
    return int(s) if s else None


def _pct(raw: str) -> float | None:
    """'21,90%' -> 21.90 ; '21,90070' -> 21.90070."""
    s = str(raw or "").replace("%", "").strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _person_rut(raw: str) -> str | None:
    """'8.431.507-9' -> '8431507-9'."""
    m = re.match(r"^\s*([\d.]+)\s*-\s*([\dkK])\s*$", str(raw or ""))
    return f"{m.group(1).replace('.', '')}-{m.group(2).upper()}" if m else None


def _date(raw: str) -> date | None:
    try:
        return datetime.strptime(str(raw or "").strip(), "%d/%m/%Y").date()
    except ValueError:
        return None


def parse_shareholders(html: str) -> tuple[tuple[int, int] | None, list[Shareholder]]:
    """Devuelve ((año, mes) informado, accionistas)."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    period = None
    m = re.search(r"Per[ií]odo:\s*(\d{2})\s*/\s*(\d{4})", text)
    if m:
        period = (int(m.group(2)), int(m.group(1)))

    out: list[Shareholder] = []
    seen: set[tuple[str, str | None]] = set()

    for table in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True) for th in table.find_all("th")]
        if not any("acciones suscritas" in h.lower() for h in heads):
            continue
        # La tabla con columna "Serie" trae el desglose; la otra, el consolidado.
        serie_idx = next((i for i, h in enumerate(heads)
                          if h.strip().lower() == "serie"), None)

        rank = 0
        last_name = ""
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            # Las filas de cabecera/período traen una sola celda.
            if len(cells) < len(heads):
                continue
            name = re.sub(r"\s+", " ", cells[0]).strip()
            if name.lower().startswith("per"):
                continue
            # La CMF aplica rowspan al nombre: si un accionista tiene acciones en
            # dos series, la segunda fila viene con la celda de nombre VACÍA. Sin
            # arrastrar el último nombre se perdían esas filas en silencio.
            if not name:
                if not last_name:
                    continue
                name = last_name
            else:
                last_name = name
            serie = cells[serie_idx].strip() if serie_idx is not None else None
            if serie == "":
                serie = None
            key = (name, serie)
            if key in seen:
                continue
            seen.add(key)
            rank += 1
            # Las 2 últimas columnas numéricas son acciones pagadas y %; la
            # anterior, suscritas.
            out.append(Shareholder(
                holder_name=name,
                serie=serie,
                shares_subscribed=_int(cells[-3]),
                shares_paid=_int(cells[-2]),
                ownership_pct=_pct(cells[-1]),
                rank=rank,
            ))
    return period, out


def parse_directors(html: str) -> list[Director]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Director] = []
    for table in soup.find_all("table"):
        heads = [th.get_text(" ", strip=True).lower() for th in table.find_all("th")]
        if not ("cargo" in heads and "nombre" in heads):
            continue
        for tr in table.find_all("tr"):
            cells = [td.get_text(" ", strip=True) for td in tr.find_all("td")]
            if len(cells) < 3:
                continue
            name = re.sub(r"\s+", " ", cells[1]).strip()
            if not name:
                continue
            out.append(Director(
                person_rut=_person_rut(cells[0]),
                person_name=name,
                cargo=cells[2].strip() or None,
                appointed_at=_date(cells[3]) if len(cells) > 3 else None,
            ))
        break
    return out


def fetch(session: requests.Session, rut_numero: str, tab: int) -> str:
    resp = session.get(entidad_url(rut_numero, tab), timeout=45)
    resp.raise_for_status()
    return resp.text


def upsert_shareholders(conn, rut: str, period: tuple[int, int],
                        rows: list[Shareholder]) -> int:
    year, month = period
    cur = conn.cursor()
    cur.executemany(
        """
        INSERT INTO company_shareholders
            (rut, company_id, period_year, period_month, holder_name, serie,
             shares_subscribed, shares_paid, ownership_pct, rank)
        VALUES (
            %(rut)s,
            (SELECT id FROM companies
              WHERE rut_numero::text = split_part(%(rut)s, '-', 1) LIMIT 1),
            %(year)s, %(month)s, %(name)s, %(serie)s,
            %(subs)s, %(paid)s, %(pct)s, %(rank)s)
        ON CONFLICT (rut, period_year, period_month, holder_name, COALESCE(serie, ''))
        DO UPDATE SET shares_subscribed = EXCLUDED.shares_subscribed,
                      shares_paid       = EXCLUDED.shares_paid,
                      ownership_pct     = EXCLUDED.ownership_pct,
                      rank              = EXCLUDED.rank,
                      company_id        = COALESCE(EXCLUDED.company_id,
                                                   company_shareholders.company_id),
                      updated_at        = NOW()
        """,
        [{"rut": rut, "year": year, "month": month, "name": s.holder_name,
          "serie": s.serie, "subs": s.shares_subscribed, "paid": s.shares_paid,
          "pct": s.ownership_pct, "rank": s.rank} for s in rows],
    )
    return len(rows)


def replace_directors(conn, rut: str, rows: list[Director]) -> int:
    """El directorio es una foto del presente: se reemplaza entero."""
    cur = conn.cursor()
    cur.execute("DELETE FROM company_directors WHERE rut = %s", (rut,))
    cur.executemany(
        """
        INSERT INTO company_directors
            (rut, company_id, person_rut, person_name, cargo, appointed_at)
        VALUES (
            %(rut)s,
            (SELECT id FROM companies
              WHERE rut_numero::text = split_part(%(rut)s, '-', 1) LIMIT 1),
            %(prut)s, %(name)s, %(cargo)s, %(app)s)
        """,
        [{"rut": rut, "prut": d.person_rut, "name": d.person_name,
          "cargo": d.cargo, "app": d.appointed_at} for d in rows],
    )
    return len(rows)


def ruts_with_xbrl(xbrl_base_dir: Path) -> set[str]:
    """Parte numérica del RUT de las empresas con XBRL descargado.

    Sólo esas llegan a ser producto en FinDataChile; scrapear las ~520 del
    registro CMF es trabajo (y carga sobre la CMF) que no se usa.
    """
    out: set[str] = set()
    if not xbrl_base_dir.is_dir():
        return out
    for d in xbrl_base_dir.iterdir():
        m = re.match(r"^(\d{4,9})-[\dkK]_", d.name)
        if d.is_dir() and m:
            out.add(m.group(1))
    return out


def load_targets(conn, limit: int, only: list[str],
                 xbrl_base_dir: Path | None) -> list[tuple[str, str]]:
    """(rut_completo, razon_social) de las empresas objetivo."""
    cur = conn.cursor()
    if only:
        wanted = [r.split("-")[0] for r in only]
    elif xbrl_base_dir is not None:
        wanted = sorted(ruts_with_xbrl(xbrl_base_dir))
        if not wanted:
            raise SystemExit(f"No hay empresas con XBRL en {xbrl_base_dir}")
    else:
        cur.execute("SELECT rut, razon_social FROM companies ORDER BY razon_social")
        rows = cur.fetchall()
        return rows[:limit] if limit else rows

    cur.execute(
        """SELECT rut, razon_social FROM companies
            WHERE rut_numero::text = ANY(%s) ORDER BY razon_social""",
        (wanted,))
    rows = cur.fetchall()
    return rows[:limit] if limit else rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default="/home/unzzui/Proyectos/FinDataChile/.env")
    ap.add_argument("--only", default="", help="RUTs separados por coma")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--xbrl-base-dir", default="data/XBRL/Total",
                    help="Sólo empresas con XBRL descargado aquí (las que llegan a "
                         "ser producto). '' = todo el catálogo CMF")
    ap.add_argument("--delay", type=float, default=0.7,
                    help="Pausa entre empresas, para no gatillar el throttle de la CMF")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import psycopg2

    conn = psycopg2.connect(**resolve_pg_conn(load_env_file(Path(args.env_file))))
    only = [r.strip() for r in args.only.split(",") if r.strip()]
    xbrl_dir = Path(args.xbrl_base_dir) if args.xbrl_base_dir else None
    targets = load_targets(conn, args.limit, only, xbrl_dir)
    scope = "con XBRL" if xbrl_dir and not only else "del catálogo"
    print(f"{len(targets)} empresa(s) {scope} a procesar\n")

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    n_sh = n_dir = n_err = 0
    for i, (rut, razon) in enumerate(targets, 1):
        rut_num = rut.split("-")[0]
        try:
            period, shareholders = parse_shareholders(
                fetch(session, rut_num, TAB_SHAREHOLDERS))
            directors = parse_directors(fetch(session, rut_num, TAB_DIRECTORS))
        except Exception as exc:
            n_err += 1
            print(f"  [{i}/{len(targets)}] {razon[:38]:40s} ERROR: {exc}")
            continue

        per_txt = f"{period[1]:02d}/{period[0]}" if period else "sin período"
        print(f"  [{i}/{len(targets)}] {razon[:38]:40s} "
              f"accionistas={len(shareholders):2d} ({per_txt})  "
              f"directores={len(directors):2d}")

        if not args.dry_run:
            try:
                if shareholders and period:
                    n_sh += upsert_shareholders(conn, rut, period, shareholders)
                if directors:
                    n_dir += replace_directors(conn, rut, directors)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                n_err += 1
                print(f"      [error] rollback: {exc}")
        time.sleep(args.delay)

    print(f"\naccionistas: {n_sh} filas | directores: {n_dir} filas | errores: {n_err}")
    if args.dry_run:
        print("dry-run -> no se escribió en la BD")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
