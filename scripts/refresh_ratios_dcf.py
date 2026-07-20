#!/usr/bin/env python3
"""Recalcula ratios + DCF para las empresas que ya tienen datos en Supabase.

Existe porque `upload_to_supabase.py --with-all` obliga a repetir el upload (~1 h)
sólo para llegar a los derivados. Esto ataca directamente las empresas que ya están
en `financial_data`, y en paralelo.

Uso:
    python scripts/refresh_ratios_dcf.py [--workers 6] [--only RUT,RUT] [--skip-dcf]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import psycopg2

# La ruta del repo FinDataChile es distinta en el host (~/Proyectos/FinDataChile) y en el
# contenedor (montado en /app/fdc). Se toma de FDC_DIR/FINDATACHILE_REPO; el default sólo
# aplica en la máquina de desarrollo.
FDC = Path(os.environ.get("FDC_DIR") or os.environ.get("FINDATACHILE_REPO")
           or "/home/unzzui/Proyectos/FinDataChile")
SCRIPTS = FDC / "scripts"


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def companies_with_data(env: dict[str, str]) -> list[tuple[int, str]]:
    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", 5432), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"], sslmode="require",
    )
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.razon_social
            FROM companies c
            WHERE EXISTS (SELECT 1 FROM financial_data fd WHERE fd.company_id = c.id)
            ORDER BY c.id
            """
        )
        rows = cur.fetchall()
    conn.close()
    return rows


def run(cmd: list[str], cwd: Path, env: dict[str, str], timeout: int) -> tuple[bool, str]:
    try:
        p = subprocess.run(cmd, cwd=str(cwd), env=env, timeout=timeout,
                           capture_output=True, text=True)
        return p.returncode == 0, (p.stderr or p.stdout or "")[-200:]
    except subprocess.TimeoutExpired:
        return False, "timeout"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)[:200]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--skip-ratios", action="store_true")
    ap.add_argument("--skip-dcf", action="store_true")
    ap.add_argument("--only", default="", help="IDs de empresa separados por coma")
    args = ap.parse_args()

    env_file = load_env(FDC / ".env")
    sub_env = {**os.environ, **{k: v for k, v in env_file.items() if k.startswith("PG")}}
    py = sys.executable

    targets = companies_with_data(env_file)
    if args.only:
        keep = {int(x) for x in args.only.split(",") if x.strip()}
        targets = [t for t in targets if t[0] in keep]

    print(f"Empresas con datos: {len(targets)} | workers: {args.workers}")
    t0 = time.perf_counter()
    ok_r = fail_r = ok_d = fail_d = 0
    fallos: list[str] = []

    def work(item: tuple[int, str]) -> tuple[str, bool, bool]:
        cid, name = item
        r_ok = d_ok = True
        if not args.skip_ratios:
            r_ok, err = run([py, str(SCRIPTS / "ratio_calculator_postgresql.py"),
                             "--save", "--company-id", str(cid)],
                            SCRIPTS, sub_env, 900)
            if not r_ok:
                fallos.append(f"ratios {name} (id={cid}): {err}")
        if not args.skip_dcf:
            d_ok, err = run([py, "-m", "dcf", "--save", "--method", "excel-aligned",
                             "--company-id", str(cid)],
                            SCRIPTS, sub_env, 900)
            if not d_ok:
                fallos.append(f"dcf {name} (id={cid}): {err}")
        return name, r_ok, d_ok

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = {pool.submit(work, t): t for t in targets}
        for fut in as_completed(futs):
            name, r_ok, d_ok = fut.result()
            ok_r += r_ok; fail_r += not r_ok
            ok_d += d_ok; fail_d += not d_ok
            done += 1
            if done % 10 == 0 or done == len(targets):
                el = time.perf_counter() - t0
                eta = el / done * (len(targets) - done)
                print(f"  [{done}/{len(targets)}] {el/60:.1f} min transcurridos, "
                      f"~{eta/60:.1f} min restantes", flush=True)

    el = time.perf_counter() - t0
    print(f"\nRatios: {ok_r} ok, {fail_r} fallidos")
    print(f"DCF   : {ok_d} ok, {fail_d} fallidos")
    print(f"Tiempo: {el/60:.1f} min")
    if fallos:
        print("\nFallos:")
        for f in fallos[:20]:
            print("  -", f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
