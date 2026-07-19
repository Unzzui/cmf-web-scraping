#!/usr/bin/env python3
"""Sube los Excel de análisis de EEUU al catálogo de FinDataChile (leg 3A), por CIK.

El uploader chileno (`findatachile_uploader.py`) identifica la empresa por RUT y crearía una
empresa duplicada para las US. Este script postea al MISMO endpoint `/api/admin/process-files`
pero con `metadata.cik`, que el route resuelve contra `companies` por CIK (sin crear). Así el
Excel US se vincula al `company_id` real.

DRY-RUN por defecto (no postea). El POST real necesita la app de FinDataChile corriendo y las
credenciales de admin. Uso:
    # ver qué se subiría (mapea archivo → CIK, sin postear):
    python scripts/upload_us_products.py --dir <dir_con_xlsx>
    # subir de verdad (app corriendo):
    python scripts/upload_us_products.py --dir <dir> --live \
        --url https://www.findatachile.com --user admin --password ****
"""
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path

import psycopg2

FDC = Path(os.environ.get("FDC_DIR", "/home/unzzui/Proyectos/FinDataChile"))
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_TOKEN_RE = re.compile(r" - (\d{4,8})-[0-9kK] - ")  # "... - 1108524-5 - ..."


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def cik_de_archivo(conn, name: str) -> tuple[str, int, str] | None:
    """(cik_padded, company_id, razon_social) para el token del nombre, o None si no es US."""
    m = _TOKEN_RE.search(name)
    if not m:
        return None
    token = m.group(1)
    cik_padded = token.zfill(10)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT cik, id, razon_social FROM companies "
            "WHERE market = 'US' AND (cik = %s OR cik = %s) LIMIT 1",
            [token, cik_padded])
        row = cur.fetchone()
    return (str(row[0]), int(row[1]), row[2]) if row else None


def parse_version(name: str) -> dict:
    lang = "EN" if re.search(r"\[EN\]", name, re.I) else "ES"
    m = re.search(r"(\d{4})-(\d{4})\s*Q([1-4])", name, re.I) or re.search(r"(\d{4})\s*Q([1-4])", name, re.I)
    if m and m.lastindex == 3:
        year, quarter = int(m.group(2)), int(m.group(3))
    elif m:
        year, quarter = int(m.group(1)), int(m.group(2))
    else:
        mr = re.search(r"(\d{4})-(\d{4})", name)
        year, quarter = (int(mr.group(2)) if mr else 0), 0
    return {"language": lang, "year": year, "quarter": quarter}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Carpeta con los Excel de análisis US")
    ap.add_argument("--live", action="store_true", help="Postear de verdad (default: dry-run)")
    ap.add_argument("--url", default=os.environ.get("FDC_URL", "http://localhost:3000"))
    ap.add_argument("--user", default=os.environ.get("FDC_ADMIN_USER", ""))
    ap.add_argument("--password", default=os.environ.get("FDC_ADMIN_PASS", ""))
    ap.add_argument("--price", type=int, default=int(os.environ.get("FDC_PRICE", "7500")))
    ap.add_argument("--only", default="", help="Substring del nombre para filtrar (ej. Salesforce)")
    args = ap.parse_args()

    env = load_env(FDC / ".env")
    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", 5432), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"], sslmode="require")

    files = sorted(p for p in Path(args.dir).rglob("*.xlsx")
                   if not p.name.startswith("~") and (not args.only or args.only.lower() in p.name.lower()))
    print(f"Excel US: {len(files)} | modo: {'LIVE (--live)' if args.live else 'DRY-RUN'}")

    session = None
    if args.live:
        import requests
        if not args.user or not args.password:
            print("ERROR: --user y --password (o FDC_ADMIN_USER/PASS) son obligatorios con --live.")
            return 2
        session = requests.Session()
        r = session.post(args.url.rstrip("/") + "/api/admin/login",
                         json={"username": args.user, "password": args.password}, timeout=30)
        if r.status_code != 200:
            print(f"ERROR login admin: {r.status_code} {r.text[:200]}")
            return 2

    ok = skip = fail = 0
    for path in files:
        info = cik_de_archivo(conn, path.name)
        if not info:
            print(f"  SKIP (no es US / sin CIK): {path.name}")
            skip += 1
            continue
        cik, company_id, razon = info
        v = parse_version(path.name)
        metadata = {
            "cik": cik,
            "periodType": "completo",
            "language": v["language"],
            "versionInfo": {"year": v["year"], "quarter": v["quarter"], "isVersioned": True},
            "createVersion": True, "isNewVersion": True, "overwriteExisting": True,
            "priceOverride": args.price,
        }
        print(f"  {razon[:26]:28} cik={cik} id={company_id} {v['year']}Q{v['quarter']} [{v['language']}]"
              + ("" if args.live else "  (dry-run)"))
        if args.live and session is not None:
            with open(path, "rb") as fh:
                resp = session.post(
                    args.url.rstrip("/") + "/api/admin/process-files",
                    files={"file": (path.name, fh, _XLSX_MIME)},
                    data={"metadata": json.dumps(metadata, ensure_ascii=False)}, timeout=180)
            if resp.status_code == 200:
                ok += 1
            else:
                fail += 1
                print(f"      ERROR {resp.status_code}: {resp.text[:160]}")

    conn.close()
    print(f"\nOK: {ok}  ·  saltados: {skip}  ·  fallidos: {fail}")
    if not args.live:
        print("DRY-RUN: no se subió nada. Repetí con --live (app corriendo) para publicar.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
