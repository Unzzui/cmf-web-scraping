#!/usr/bin/env python3
"""Benchmark de las estrategias de export Arelle (correr donde estén los datos).

Mide, sobre un dataset XBRL real:

  1. legacy : dos subprocess arelleCmdLine (facts y pre por separado)
  2. merged : un solo subprocess con --factTable y --pre juntos
  3. worker : pool persistente (arelle_worker.py), job merged en caliente

Uso::

    python bench_arelle.py --base-dir data/XBRL/Total --arelle-dir ~/Documents/Arelle
    python bench_arelle.py --dataset "data/XBRL/Total/<empresa>/Estados_financieros_(XBRL)..._extracted"

Los outputs van a un directorio temporal; no toca los out_ existentes.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from batch_xbrl_to_excel import (  # noqa: E402
    find_datasets,
    find_xbrl_file,
    run_cmd,
)

FACT_COLS = (
    "Label,localName,contextRef,unitRef,Dec,Prec,Lang,Value,"
    "entityIdentifier,periodStart,periodEnd,instant,endInstant,qname"
)


def _args_facts(xbrl: Path, out: Path) -> list[str]:
    return ['-f', str(xbrl), '--labelLang=es-CL',
            '--factTable', str(out / "facts.csv"),
            '--factTableCols', FACT_COLS,
            '--logFile', str(out / "facts.log"),
            '--internetConnectivity=offline']


def _args_pre(xbrl: Path, out: Path) -> list[str]:
    return ['-f', str(xbrl), '--labelLang=es-CL',
            '--pre', str(out / "pre.csv"),
            '--logFile', str(out / "pre.log"),
            '--internetConnectivity=offline']


def _args_merged(xbrl: Path, out: Path) -> list[str]:
    return ['-f', str(xbrl), '--labelLang=es-CL',
            '--factTable', str(out / "facts.csv"),
            '--factTableCols', FACT_COLS,
            '--pre', str(out / "pre.csv"),
            '--logFile', str(out / "run.log"),
            '--internetConnectivity=offline']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default="data/XBRL/Total")
    ap.add_argument("--arelle-dir", required=True)
    ap.add_argument("--dataset", help="Dataset dir específico (si no, el primero encontrado)")
    ap.add_argument("--repeat", type=int, default=2, help="Corridas por estrategia (se promedia)")
    args = ap.parse_args()

    arelle_dir = Path(args.arelle_dir).expanduser().resolve()
    arelle_python = arelle_dir / '.venv' / 'bin' / 'python'
    if not arelle_python.exists():
        arelle_python = Path(sys.executable)

    if args.dataset:
        ds_dir = Path(args.dataset).resolve()
        stem_dirs = [ds_dir]
    else:
        datasets = find_datasets(Path(args.base_dir))
        if not datasets:
            print(f"Sin datasets bajo {args.base_dir}", file=sys.stderr)
            return 1
        stem_dirs = [datasets[0].dataset_dir]

    ds_dir = stem_dirs[0]
    stem = ds_dir.name
    xbrl = find_xbrl_file(ds_dir, stem)
    if xbrl is None:
        print(f"Sin archivo .xbrl en {ds_dir}", file=sys.stderr)
        return 1
    xbrl = xbrl.resolve()
    print(f"Dataset : {ds_dir.name}")
    print(f"XBRL    : {xbrl.name}")
    print(f"Arelle  : {arelle_python}")
    print(f"Repeticiones por estrategia: {args.repeat}\n")

    tmp = Path(tempfile.mkdtemp(prefix="bench_arelle_"))
    results: dict[str, float] = {}
    try:
        # 1) legacy: facts y pre en subprocesos separados
        times = []
        for i in range(args.repeat):
            out = tmp / f"legacy_{i}"
            out.mkdir()
            t0 = time.perf_counter()
            run_cmd([str(arelle_python), 'arelleCmdLine.py', *_args_facts(xbrl, out)],
                    cwd=arelle_dir)
            run_cmd([str(arelle_python), 'arelleCmdLine.py', *_args_pre(xbrl, out)],
                    cwd=arelle_dir)
            times.append(time.perf_counter() - t0)
            print(f"  legacy run {i + 1}: {times[-1]:.1f}s")
        results["legacy (2 subprocess)"] = sum(times) / len(times)

        # 2) merged: un subprocess con ambos exports
        times = []
        for i in range(args.repeat):
            out = tmp / f"merged_{i}"
            out.mkdir()
            t0 = time.perf_counter()
            run_cmd([str(arelle_python), 'arelleCmdLine.py', *_args_merged(xbrl, out)],
                    cwd=arelle_dir)
            times.append(time.perf_counter() - t0)
            print(f"  merged run {i + 1}: {times[-1]:.1f}s")
        results["merged (1 subprocess)"] = sum(times) / len(times)

        # 3) worker persistente, merged en caliente (el primer job paga el
        #    arranque; se mide desde el segundo)
        from arelle_pool import ArelleWorkerPool, shutdown_all
        pool = ArelleWorkerPool.get(arelle_python, arelle_dir)
        out = tmp / "worker_warmup"
        out.mkdir()
        t0 = time.perf_counter()
        pool.run(_args_merged(xbrl, out), timeout=600)
        print(f"  worker warmup (arranque + job): {time.perf_counter() - t0:.1f}s")
        times = []
        for i in range(args.repeat):
            out = tmp / f"worker_{i}"
            out.mkdir()
            t0 = time.perf_counter()
            pool.run(_args_merged(xbrl, out), timeout=600)
            times.append(time.perf_counter() - t0)
            print(f"  worker run {i + 1}: {times[-1]:.1f}s")
        results["worker (persistente, caliente)"] = sum(times) / len(times)
        shutdown_all()

        base = results["legacy (2 subprocess)"]
        print("\n=== Resultados (promedio) ===")
        for name, secs in results.items():
            print(f"  {name:32s} {secs:6.1f}s   x{base / secs:.2f}")
        print("\nSi 'worker' gana con claridad: exporta CMF_ARELLE_WORKER=1 en el servidor.")
        print("'merged' ya es el modo por defecto tras esta optimización.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
