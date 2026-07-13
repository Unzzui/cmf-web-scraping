#!/usr/bin/env python3
"""Repara los datasets cuyo export de Arelle salió vacío (sólo cabecera).

Causas conocidas:
  a) taxonomía incompleta en el cache -> Arelle offline no resuelve el DTS
  b) falta el _shell.xsd del emisor en el dataset -> hay que re-descargarlo

Re-exporta cada dataset afectado y reporta cuáles siguen fallando (esos necesitan
re-descarga).

Uso: python scripts/repair_empty_arelle.py [--limit N] [--workers 4] [--dry-run]
"""
from __future__ import annotations

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "cmf_extract"))

BASE = ROOT / "data" / "XBRL" / "Total"
ARELLE = ROOT / "tools" / "Arelle"


def facts_vacio(csv: Path) -> bool:
    try:
        with csv.open("rb") as fh:
            return sum(1 for _ in fh) <= 1
    except OSError:
        return True


def afectados() -> list[tuple[Path, Path, str]]:
    """Devuelve (dataset_dir, out_dir, stem) de cada export vacío."""
    out = []
    for csv in BASE.glob("*/Estados_financieros_*_extracted/out_*/facts_*_es.csv"):
        if not facts_vacio(csv):
            continue
        out_dir = csv.parent
        ds = out_dir.parent
        stem = out_dir.name.replace("out_", "", 1)
        out.append((ds, out_dir, stem))
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    import batch_xbrl_to_excel as b
    from cmf.pipeline.arelle_cache import populate_arelle_cache

    items = afectados()
    if args.limit:
        items = items[: args.limit]
    print(f"Datasets con export vacío: {len(items)}")

    sin_shell = [d for d, _, _ in items if not any(d.glob("*_shell.xsd"))]
    print(f"  sin _shell.xsd (necesitan re-descarga): {len(sin_shell)}")
    print(f"  con _shell.xsd (se re-exportan)       : {len(items) - len(sin_shell)}")
    if args.dry_run:
        return 0

    # Pre-poblar el cache de taxonomías por empresa (una vez), ahora con reintentos.
    empresas = sorted({d.parent for d, _, _ in items})
    print(f"\nPre-poblando cache de taxonomías para {len(empresas)} empresa(s)...")
    for i, emp in enumerate(empresas, 1):
        try:
            n = populate_arelle_cache(emp)
            if n:
                print(f"  [{i}/{len(empresas)}] {emp.name[:44]}: +{n} URLs")
        except Exception as exc:
            print(f"  [{i}/{len(empresas)}] {emp.name[:44]}: cache falló ({exc})")

    print(f"\nRe-exportando {len(items)} dataset(s) con {args.workers} workers...")
    t0 = time.perf_counter()
    ok, fail = 0, []

    def work(item):
        ds, out_dir, stem = item
        xbrl = next(iter(ds.glob("*.xbrl")), None)
        if xbrl is None:
            return item, False, "sin .xbrl"
        try:
            b.run_arelle_exports(ARELLE, xbrl, out_dir, stem, ["es"], force=True)
        except Exception as exc:
            return item, False, str(exc)[:90]
        csv = out_dir / f"facts_{stem}_es.csv"
        return item, (not facts_vacio(csv)), ""

    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futs = [pool.submit(work, it) for it in items]
        for fut in as_completed(futs):
            item, bien, err = fut.result()
            done += 1
            if bien:
                ok += 1
            else:
                fail.append((item[0].name, err))
            if done % 20 == 0 or done == len(items):
                el = time.perf_counter() - t0
                print(f"  [{done}/{len(items)}] {ok} recuperados, {len(fail)} fallan "
                      f"({el/60:.1f} min)", flush=True)

    print(f"\nRecuperados : {ok}/{len(items)}")
    print(f"Siguen mal  : {len(fail)}")
    for name, err in fail[:15]:
        print(f"   {name[:60]}  {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
