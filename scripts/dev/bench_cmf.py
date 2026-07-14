#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Benchmark de concurrencia para CMF (Checker y Downloader)
- Mide tiempo total, throughput, errores y latencias (p50/p95) por período.
- Explora N workers para encontrar el sweet spot (2..8 por defecto).

Uso:
  python bench_cmf.py check   --module checker_module --class CMFXBRLChecker --company "" --workers 2 3 4 5 6
  python bench_cmf.py download --module downloader_module --ruts 91041000 93834000 --start 2024 --end 2022 --modes quarterly --http-workers 6 --workers 2 4 6

Notas:
- --module es el nombre del módulo Python donde viven tus funciones/clases.
  Ej: si tu checker está en src/cmf/checker.py => --module src.cmf.checker
"""

import argparse, importlib, sys, time, statistics, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# -----------------------
# Utilidades generales
# -----------------------

def now_ts():
    return time.perf_counter()

def dur(s, e):
    return e - s

def fmt_secs(s):
    m, sec = divmod(int(s), 60)
    return f"{m}m {sec}s"

def p50(values):
    return statistics.median(values) if values else 0.0

def p95(values):
    if not values:
        return 0.0
    return statistics.quantiles(values, n=20)[18]  # ~p95

def read_last_summary_path_from_log(text: str) -> Path | None:
    """
    Intenta detectar: 'Resumen guardado en: /.../xbrl_summary_YYYYMMDD_HHMMSS.txt'
    """
    m = re.search(r"Resumen guardado en:\s*(/.*xbrl_summary_\d{8}_\d{6}\.txt)", text)
    return Path(m.group(1)) if m else None

def parse_summary_file(path: Path):
    """
    Lee el txt de summary del checker y devuelve métricas simples.
    """
    if not path or not path.exists():
        return None
    total_companies = companies_with_new = total_new_periods = None
    try:
        content = path.read_text(encoding="utf-8", errors="ignore")
        m = re.search(r"Total empresas:\s*(\d+)", content)
        if m: total_companies = int(m.group(1))
        m = re.search(r"Empresas con XBRL nuevo:\s*(\d+)", content)
        if m: companies_with_new = int(m.group(1))
        m = re.search(r"Total períodos nuevos:\s*(\d+)", content)
        if m: total_new_periods = int(m.group(1))
        return {
            "total_companies": total_companies,
            "companies_with_new_xbrl": companies_with_new,
            "total_new_periods": total_new_periods,
        }
    except Exception:
        return None

# -----------------------
# A) Bench del Checker
# -----------------------

def bench_checker(module_name: str, class_name: str, workers_list: list[int], company_filter: str | None):
    """
    Importa tu clase CMFXBRLChecker y ejecuta run_check(max_workers=N) para N en workers_list.
    Mide wall-clock; intenta leer métricas del summary txt.
    Mejora opcional recomendada: que run_check RETORNE el dict summary.
    """
    mod = importlib.import_module(module_name)
    CheckerCls = getattr(mod, class_name)

    results = []
    for n in workers_list:
        # Captura de logs en memoria (stderr/stdout) de forma simple
        # (Si usas logging a archivo, puedes omitir esto)
        start = now_ts()
        checker = CheckerCls(headless=True, debug=False)

        # --- OPCIONAL (mejor): si tu run_check retorna summary, úsalo directamente ---
        returned_summary = None
        try:
            returned_summary = checker.run_check(company_filter=company_filter, max_workers=n)
        except TypeError:
            # Tu versión no retorna; solo imprime y guarda txt. Continuamos.
            checker.run_check(company_filter=company_filter, max_workers=n)
            returned_summary = None

        end = now_ts()
        wall = dur(start, end)

        # Si no retornó summary, intenta leer el último archivo de output/xbrl_checker/
        summary = None
        if isinstance(returned_summary, dict):
            summary = returned_summary
        else:
            outdir = Path(__file__).resolve().parent / "output" / "xbrl_checker"
            summaries = sorted(outdir.glob("xbrl_summary_*.txt"))
            summary = parse_summary_file(summaries[-1]) if summaries else None

        results.append({
            "workers": n,
            "wall_sec": wall,
            "summary": summary or {},
        })

        print(f"[CHECK] workers={n} → {fmt_secs(wall)} | {summary or {}}")

    # Resumen “sweet spot” (mínimo wall)
    best = min(results, key=lambda r: r["wall_sec"])
    print("\n=== RESULTADOS CHECKER ===")
    for r in results:
        print(f"workers={r['workers']:>2}  time={fmt_secs(r['wall_sec'])}  metrics={r['summary']}")
    print(f"\nSWEET SPOT (checker): workers={best['workers']} ({fmt_secs(best['wall_sec'])})")
    return results

# -----------------------
# B) Bench del Downloader
# -----------------------

def bench_downloader(module_name: str, ruts: list[str], start_year: int, end_year: int,
                     mode: str, workers_list: list[int], max_http_workers: int):
    """
    Usa download_cmf_xbrl con un progress_hook para medir latencias por período (year,month).
    Ejecuta process_multiple_companies_xbrl con max_workers=N y agrupa métricas.
    """

    mod = importlib.import_module(module_name)
    dl_func = getattr(mod, "download_cmf_xbrl")
    multi_func = getattr(mod, "process_multiple_companies_xbrl")

    # Latencias por período (por worker-run)
    # clave: (rut, yyyymm) -> lista de latencias
    period_latencies = defaultdict(list)
    period_start_ts  = {}  # (rut, y, m) -> start_time
    period_errors = 0
    completed_periods = 0

    def mk_hook(tag):
        def hook(rut, cur, tot, y, m, eta, status):
            # status interesantes: 'in_progress', 'period_completed', 'skipped_period', 'diag_*', etc.
            key = (rut, int(y) if y else None, int(m) if m else None)
            if status in ("in_progress",):
                period_start_ts[key] = now_ts()
            elif status in ("period_completed",):
                st = period_start_ts.pop(key, None)
                if st:
                    period_latencies[(rut, y*100 + m)].append(dur(st, now_ts()))
                nonlocal completed_periods
                completed_periods += 1
            elif "No hay enlace" in str(status) or "ERROR" in str(status):
                nonlocal period_errors
                period_errors += 1
        return hook

    results = []
    for n in workers_list:
        # limpia buffers
        period_latencies.clear()
        period_start_ts.clear()
        period_errors = 0
        completed_periods = 0

        start = now_ts()

        # Creamos un wrapper que inyecta el hook sin cambiar tu API pública
        def runner(rut, idx):
            # Selección de modo
            is_quarterly = (mode == "quarterly" or mode == "total")
            return dl_func(
                rut=rut,
                start_year=start_year,
                end_year=end_year,
                step=-1 if is_quarterly else -2,
                headless=True,
                quarterly=is_quarterly,
                mode=mode if mode in {"annual", "quarterly", "total"} else None,
                progress_hook=mk_hook(f"w{n}"),
                strategy="browser",           # medimos Selenium puro; si quieres probar "direct", cambia aquí
                max_http_workers=max_http_workers
            )

        # Ejecuta en paralelo N (usa tu process_multiple_companies_xbrl pero con nuestro runner)
        # Reusamos tu executor por simplicidad: pasamos max_workers=n y que llame a download_cmf_xbrl
        # Sugerencia: si no deseas modificar process_multiple_companies_xbrl, ejecuta cada rut con nuestro runner manualmente.
        # Aquí clonamos la idea de tu "multi" con nuestro propio loop ligero.
        from concurrent.futures import ThreadPoolExecutor, as_completed
        def run_multi(ruts_list, mw):
            outs = []
            with ThreadPoolExecutor(max_workers=mw) as ex:
                futs = [ex.submit(runner, r, i) for i, r in enumerate(ruts_list)]
                for f in as_completed(futs):
                    try:
                        outs.append(f.result())
                    except Exception as e:
                        print(f"[download] error: {e}")
            return outs

        _outs = run_multi(ruts, n)
        wall = dur(start, now_ts())

        # Agrega métricas
        all_lat = [lat for _, latlist in period_latencies.items() for lat in latlist]
        result = {
            "workers": n,
            "wall_sec": wall,
            "completed_periods": completed_periods,
            "error_periods": period_errors,
            "throughput_pps": (completed_periods / wall) if wall > 0 else 0.0,
            "lat_p50": p50(all_lat),
            "lat_p95": p95(all_lat),
        }
        results.append(result)
        print(f"[DL] workers={n} → {fmt_secs(wall)} | periods={completed_periods} | p50={result['lat_p50']:.2f}s p95={result['lat_p95']:.2f}s | err={period_errors}")

    # Resumen y sweet spot (mayor throughput con error_rate bajo)
    best = max(results, key=lambda r: (r["throughput_pps"] if r["error_periods"] <= 1 else 0))
    print("\n=== RESULTADOS DOWNLOADER ===")
    for r in results:
        print(f"workers={r['workers']:>2}  time={fmt_secs(r['wall_sec'])}  p50={r['lat_p50']:.2f}s  p95={r['lat_p95']:.2f}s  thr={r['throughput_pps']:.2f} p/s  errors={r['error_periods']}")
    print(f"\nSWEET SPOT (downloader): workers={best['workers']}  thr={best['throughput_pps']:.2f} p/s  p95={best['lat_p95']:.2f}s  errors={best['error_periods']}")
    return results

# -----------------------
# CLI
# -----------------------

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_check = sub.add_parser("check")
    ap_check.add_argument("--module", required=True, help="Módulo del checker (p.ej. src.checkers.check_xbrl_availability)")
    ap_check.add_argument("--class", dest="cls", default="CMFXBRLChecker")
    ap_check.add_argument("--company", default=None)
    ap_check.add_argument("--workers", nargs="+", type=int, default=[2,3,4,5,6,7,8])

    ap_dl = sub.add_parser("download")
    ap_dl.add_argument("--module", required=True, help="Módulo del downloader (p.ej. src.cmf.downloader)")
    ap_dl.add_argument("--ruts", nargs="+", required=True)
    ap_dl.add_argument("--start", type=int, default=2024)
    ap_dl.add_argument("--end", type=int, default=2022)
    ap_dl.add_argument("--modes", choices=["annual","quarterly","total"], default="quarterly")
    ap_dl.add_argument("--workers", nargs="+", type=int, default=[2,4,6])
    ap_dl.add_argument("--http-workers", type=int, default=6)

    args = ap.parse_args()

    if args.cmd == "check":
        bench_checker(args.module, args.cls, args.workers, args.company)
    else:
        bench_downloader(args.module, args.ruts, args.start, args.end, args.modes, args.workers, args.http_workers)

if __name__ == "__main__":
    main()

# python bench_cmf.py check --module src.checkers.check_xbrl_availability --class CMFXBRLChecker --workers 2 3 4 5 6
