#!/usr/bin/env python3
"""Orquestador de actualización automática de FindataChile (CL + EEUU), calendario-driven.

La idea: correr esto en un contenedor, todas las noches, sin intervención. Detecta qué
empresas publicaron resultados nuevos (según el calendario) y corre SOLO para ellas el
pipeline completo — descargar/ingerir → regenerar estados y Excel → publicar en FinData.
En días sin publicaciones nuevas, los gates devuelven cero y el ciclo termina en segundos.

Gates incrementales (la pieza que faltaba: los calendarios ya se pueblan pero nadie los
leía para decidir qué actualizar):

  - CHILE:  report_publication_dates con fecha ≤ hoy cuyo (año, trimestre) todavía NO está
            en financial_data → esas empresas tienen resultados nuevos por bajar.
  - EEUU:   earnings_calendar (event_type='financials', un 10-K/10-Q) cuyo período todavía
            NO está en financial_data → ingesta EDGAR nueva.

DRY-RUN por defecto (calcula los pendientes y muestra el plan, sin tocar nada). Con --live
corre el pipeline y PUBLICA. Con --refresh-calendars refresca los calendarios primero.

Uso:
    python scripts/auto_update.py                 # dry-run: qué se actualizaría
    python scripts/auto_update.py --refresh-calendars
    python scripts/auto_update.py --live          # corre y publica (para el cron/container)
    python scripts/auto_update.py --live --only-us / --only-cl
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

CMF = Path(__file__).resolve().parent.parent          # cmf-web-scraping
FDC = Path(os.environ.get("FINDATACHILE_REPO", "/home/unzzui/Proyectos/FinDataChile"))
PY = sys.executable
FDC_URL = os.environ.get("FDC_URL", "https://www.findatachile.com")
EDGAR_UA = os.environ.get("EDGAR_USER_AGENT", "FindataChile contacto@findatachile.com")
PRODUCTS_US = CMF / "Product_v1_US"


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}Z] {msg}", flush=True)


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def connect(env: dict[str, str]):
    return psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", 5432), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"], sslmode="require")


# ---------------------------------------------------------------------------
# Gates incrementales
# ---------------------------------------------------------------------------

def cl_pendientes(conn, dias: int = 120) -> list[str]:
    """RUTs chilenos con un período RECIÉN publicado (últimos `dias`, fecha ≤ hoy) que aún
    no está en la BD. Sólo empresas que YA procesamos (tienen algún financial_data): el
    calendario de la CMF trae ~940 emisores, muchos sin XBRL o fuera de nuestro universo;
    sin este filtro se seleccionarían 277 que el pipeline igual rechaza.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT c.rut
            FROM report_publication_dates rpd
            JOIN companies c ON c.id = rpd.company_id
            WHERE rpd.publication_date IS NOT NULL
              AND rpd.publication_date <= CURRENT_DATE
              AND rpd.publication_date >= CURRENT_DATE - (%s || ' days')::interval
              AND COALESCE(c.market, 'CL') = 'CL'
              AND EXISTS (SELECT 1 FROM financial_data f2 WHERE f2.company_id = c.id)
              AND NOT EXISTS (
                    SELECT 1 FROM financial_data fd
                    WHERE fd.company_id = c.id
                      AND fd.period_year = rpd.period_year
                      AND fd.period_quarter = rpd.period_quarter)
            """, [dias])
        return [r[0] for r in cur.fetchall() if r[0]]


def us_pendientes(conn, dias: int = 120) -> list[tuple[int, str]]:
    """(company_id, cik) de EEUU con un 10-K/10-Q RECIÉN presentado (últimos `dias`) cuyo
    período aún no está ingerido. La recencia evita disparar por huecos históricos viejos
    (el calendario trae años de filings; sin esto salían 46 falsos positivos).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.cik
            FROM companies c
            WHERE c.market = 'US' AND c.cik IS NOT NULL
              AND EXISTS (
                    SELECT 1 FROM earnings_calendar ec
                    WHERE ec.company_id = c.id AND ec.event_type = 'financials'
                      AND ec.event_date <= CURRENT_DATE
                      AND ec.event_date >= CURRENT_DATE - (%s || ' days')::interval
                      -- filing de un período MÁS NUEVO que el último que tenemos ingerido.
                      -- Comparar el máximo (no cada período) evita los falsos positivos por
                      -- desfase de convención entre el calendario y financial_data.
                      AND (ec.period_year * 10 + ec.period_quarter) > COALESCE((
                            SELECT MAX(fd.period_year * 10 + fd.period_quarter)
                            FROM financial_data fd WHERE fd.company_id = c.id), 0))
            """, [dias])
        return [(int(i), str(k)) for i, k in cur.fetchall()]


def us_tickers(conn, ids: list[int]) -> list[str]:
    if not ids:
        return []
    with conn.cursor() as cur:
        cur.execute("SELECT ticker FROM companies WHERE id = ANY(%s) AND ticker IS NOT NULL", [ids])
        return [r[0] for r in cur.fetchall()]


def _max_periodo(conn, cid: int) -> int:
    conn.rollback()  # cierra la transacción para ver lo recién commiteado por los subprocess
    with conn.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(period_year*10+period_quarter),0) "
                    "FROM financial_data WHERE company_id = %s", [cid])
        return int(cur.fetchone()[0])


# ---------------------------------------------------------------------------
# Ejecución de pasos
# ---------------------------------------------------------------------------

def run(cmd: list[str], cwd: Path, env: dict, paso: str, timeout: int = 3600) -> bool:
    log(f"  → {paso}: {' '.join(cmd[:6])}…")
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=env, timeout=timeout,
                           capture_output=True, text=True)
        if p.returncode != 0:
            log(f"    ✗ {paso} rc={p.returncode}: {(p.stderr or p.stdout)[-300:]}")
            return False
        log(f"    ✓ {paso}")
        return True
    except subprocess.TimeoutExpired:
        log(f"    ✗ {paso}: TIMEOUT ({timeout}s)")
        return False
    except Exception as exc:  # noqa: BLE001
        log(f"    ✗ {paso}: {exc}")
        return False


def refrescar_calendarios(sub_env: dict, live: bool) -> None:
    log("Refrescando calendarios (CMF + EDGAR)…")
    anio = datetime.now().year
    run([PY, str(CMF / "scripts" / "scrape_report_dates.py"),
         "--years", f"{anio-1},{anio}", "--refresh-filing-year", str(anio)],
        CMF, sub_env, "calendario CMF", timeout=900)
    cmd = [PY, str(CMF / "scripts" / "ingest_us_calendar.py")]
    if live:
        cmd.append("--supabase-live")
    run(cmd, CMF, sub_env, "calendario EDGAR", timeout=1200)


def ciclo_cl(ruts: list[str], sub_env: dict, live: bool) -> None:
    if not ruts:
        log("CL: 0 empresas con resultados nuevos. Nada que hacer.")
        return
    log(f"CL: {len(ruts)} empresas con resultados nuevos → {sorted(ruts)[:10]}…")
    cmd = [PY, str(CMF / "run_pipeline_cli.py"),
           "--stages", "download,consolidate,upload",
           "--companies", ",".join(ruts),
           "--fdc", "--fdc-url", FDC_URL, "--supabase"]
    if live:
        cmd.append("--supabase-live")
    else:
        log("  (dry-run: run_pipeline_cli corre en modo seguro sin --supabase-live)")
    run(cmd, CMF, sub_env, "pipeline CL", timeout=7200)


def ciclo_us(pend: list[tuple[int, str]], conn, sub_env: dict, live: bool,
             forzar: bool = False, no_publish: bool = False) -> None:
    if not pend:
        log("US: 0 empresas con filings nuevos. Nada que hacer.")
        return
    ids = [i for i, _ in pend]
    tickers = us_tickers(conn, ids)
    log(f"US: {len(pend)} {'FORZADAS' if forzar else 'con el calendario adelantado'} → {tickers[:10]}…")
    if not live:
        log("  (dry-run: no se corre la secuencia US. Con --live se ejecuta.)")
        return

    # PASO 1: ingesta EDGAR de todas las candidatas (barato: 1 req/empresa). Captura lo que
    # companyfacts tenga AHORA — que puede ir detrás del calendario de submissions.
    antes = {cid: _max_periodo(conn, cid) for cid, _ in pend}
    if not run([PY, str(CMF / "scripts" / "ingest_edgar.py"), "--tickers", ",".join(tickers),
                "--supabase-live"], CMF, {**sub_env, "EDGAR_USER_AGENT": EDGAR_UA}, "ingesta EDGAR"):
        return
    # PASO 2: solo se regenera Excel/publica para las que REALMENTE avanzaron de período
    # (con --force-us se saltea este guard). Si companyfacts todavía no reflejó el filing, no
    # avanzó nada y no se re-genera nada caro.
    if forzar:
        avanzaron = [cid for cid, _ in pend]
    else:
        avanzaron = [cid for cid, _ in pend if _max_periodo(conn, cid) > antes[cid]]
    ciks_av = [k for cid, k in pend if cid in avanzaron]
    if not avanzaron:
        log("  US: la ingesta corrió pero ningún dato avanzó (companyfacts aún no refleja el "
            "filing). No se regenera Excel ni se publica.")
        return
    log(f"  US: {len(avanzaron)} a regenerar" + (" (subida en DRY-RUN, --no-publish)" if no_publish else " y publicar"))
    ids = avanzaron
    ids_csv = ",".join(str(i) for i in ids)
    inp = str(PRODUCTS_US / "estados")
    out = str(PRODUCTS_US / "analisis")
    # AISLAR la corrida: limpiar los dirs para regenerar/analizar SOLO estas empresas. Sin
    # esto, run_products_analysis reprocesa todos los estados acumulados de corridas previas.
    shutil.rmtree(inp, ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    subir = [PY, str(CMF / "scripts" / "upload_us_products.py"), "--dir", out, "--url", FDC_URL,
             "--user", sub_env.get("FDC_ADMIN_USER", ""), "--password", sub_env.get("FDC_ADMIN_PASS", "")]
    if not no_publish:
        subir.append("--live")
    pasos = [
        ([PY, str(CMF / "scripts" / "enrich_us_market_data.py"), "--apply", "--only", ids_csv], CMF, "market data"),
        ([PY, str(CMF / "scripts" / "refresh_us_kd.py"), "--save", "--user-agent", EDGAR_UA, "--only", ",".join(ciks_av)], CMF, "Kd declarado"),
        ([PY, str(CMF / "scripts" / "build_us_estados.py"), "--only", ids_csv, "--out-dir", inp + "/Total"], CMF, "estados US"),
        # cwd = cmf_extract A PROPÓSITO: desde la raíz del repo, run_products_analysis ve
        # data/XBRL/Total (los XBRL chilenos) y su paso "ensure-combined" intenta procesar
        # TODA la data CL → se cuelga. Desde cmf_extract ese path no existe y no se dispara.
        ([PY, str(CMF / "cmf_extract" / "run_products_analysis.py"), "--input-dir", inp, "--output-dir", out, "--frequency", "Total", "--langs", "es", "--workers", "2"], CMF / "cmf_extract", "análisis US"),
        (subir, CMF, "publicar US" + (" (dry-run)" if no_publish else "")),
        ([PY, str(CMF / "scripts" / "refresh_ratios_dcf.py"), "--only", ids_csv], CMF / "scripts", "ratios+DCF"),
    ]
    # OJO: los pasos corren SIN EDGAR_UA en el entorno. refresh_us_kd ya pobló us_costo_deuda
    # (toma el user-agent por --arg), así que el análisis lee la deuda declarada de la BD, sin
    # parsear el 10-K en vivo. Con EDGAR_UA seteado, get_deuda_detalle live-parsea el 10-K de
    # cada empresa sin deuda declarada (NVDA) y se cuelga por rate-limit de la SEC.
    for cmd, cwd, paso in pasos:
        ok = run(cmd, cwd, sub_env, paso, timeout=1800)
        if not ok and paso in ("estados US", "análisis US"):
            log(f"  ⚠ paso crítico '{paso}' falló; se corta el ciclo US.")
            return


def us_forzadas(conn, spec: str) -> list[tuple[int, str]]:
    toks = [t.strip() for t in spec.split(",") if t.strip()]
    ids = [int(t) for t in toks if t.isdigit()]
    tks = [t.upper() for t in toks if not t.isdigit()]
    with conn.cursor() as cur:
        cur.execute("SELECT id, cik FROM companies WHERE market='US' AND cik IS NOT NULL "
                    "AND (id = ANY(%s) OR UPPER(ticker) = ANY(%s))", [ids, tks])
        return [(int(i), str(k)) for i, k in cur.fetchall()]


def backup(sub_env: dict, live: bool) -> None:
    script = CMF / "scripts" / "backup_to_drive.sh"
    if live and script.exists():
        run(["bash", str(script)], CMF, sub_env, "backup a Drive", timeout=1800)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="Correr y PUBLICAR (default: dry-run)")
    ap.add_argument("--refresh-calendars", action="store_true", help="Refrescar calendarios primero")
    ap.add_argument("--only-cl", action="store_true")
    ap.add_argument("--only-us", action="store_true")
    ap.add_argument("--no-publish", action="store_true",
                    help="No publica a FinData (subida en dry-run). Para probar el pipeline sin tocar el catálogo.")
    ap.add_argument("--force-us", default="",
                    help="Tickers/IDs US a forzar por el pipeline completo, salteando el gate (para probar).")
    ap.add_argument("--loop", type=int, default=0, help="Si >0, repite cada N horas (para el container)")
    args = ap.parse_args()

    env = load_env(CMF / ".env") or load_env(FDC / ".env")
    sub_env = {**os.environ, **env}

    while True:
        t0 = time.perf_counter()
        log("=" * 60)
        log(f"CICLO {'LIVE' if args.live else 'DRY-RUN'} — {'refresh cal, ' if args.refresh_calendars else ''}"
            f"{'solo CL' if args.only_cl else 'solo US' if args.only_us else 'CL+US'}")

        if args.refresh_calendars:
            refrescar_calendarios(sub_env, args.live)

        conn = connect(env)
        try:
            if not args.only_us and not args.force_us:
                ciclo_cl(cl_pendientes(conn), sub_env, args.live)
            if not args.only_cl:
                pend = us_forzadas(conn, args.force_us) if args.force_us else us_pendientes(conn)
                ciclo_us(pend, conn, sub_env, args.live,
                         forzar=bool(args.force_us), no_publish=args.no_publish)
        finally:
            conn.close()

        if args.live:
            backup(sub_env, args.live)

        log(f"CICLO terminado en {(time.perf_counter()-t0)/60:.1f} min")
        if args.loop <= 0:
            break
        log(f"Durmiendo {args.loop}h hasta el próximo ciclo…")
        time.sleep(args.loop * 3600)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
