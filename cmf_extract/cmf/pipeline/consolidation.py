"""Pipeline stage: XBRL -> consolidated facts CSV (Phase 1).

Wraps ``batch_xbrl_to_excel`` to export Arelle facts/presentation data and
then generate a consolidated company CSV without any interactive prompts.

Public interface
----------------
::

    from cmf.pipeline.consolidation import run
    result = run(config, company_dirs=[Path("data/XBRL/Total/76036453-5_AGROSUPER")])

The *progress_callback* signature is::

    callback(message: str, current: int = 0, total: int = 0) -> None
"""

from __future__ import annotations

import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from cmf.config import CMFConfig
from cmf.pipeline import PipelineResult
from cmf.pipeline.arelle_cache import populate_arelle_cache

ProgressCallback = Callable[[str, int, int], None]
_NOOP: ProgressCallback = lambda msg, cur=0, tot=0: None  # noqa: E731


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    config: CMFConfig,
    company_dirs: list[Path],
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Export Arelle facts and generate consolidated facts CSV for each company.

    For a single company the function imports and calls the relevant functions
    from ``batch_xbrl_to_excel`` directly.  For multiple companies it patches
    ``sys.argv`` and delegates to ``batch_xbrl_to_excel.main()``.

    Parameters
    ----------
    config:
        Populated :class:`~cmf.config.CMFConfig` instance.  ``apply_env()``
        is called before any processing so that legacy environment variables
        are correctly set.
    company_dirs:
        List of on-disk company directories inside ``config.xbrl_base_dir``.
    progress_callback:
        Optional callable invoked with ``(message, current, total)``
        throughout the operation.

    Returns
    -------
    PipelineResult
        ``success`` contains the names of companies processed without error.
        ``errors`` maps company names to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not company_dirs:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    # Push config values into the environment before calling legacy code.
    config.apply_env()

    total = len(company_dirs)
    cb(f"Consolidando {total} empresa(s)", 0, total)

    for idx, company_dir in enumerate(company_dirs, 1):
        company_name = company_dir.name
        cb(f"[{idx}/{total}] {company_name}", idx, total)
        result = _run_single(config, company_dir, cb)
        success.extend(result.success)
        errors.update(result.errors)

    elapsed = time.time() - start
    cb(
        f"Consolidacion lista: {len(success)}/{total} ok, {len(errors)} errores.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_single(
    config: CMFConfig,
    company_dir: Path,
    cb: ProgressCallback,
) -> PipelineResult:
    """Process a single company directory using direct function calls."""
    success: list[str] = []
    errors: dict[str, str] = {}
    company_name = company_dir.name

    try:
        from batch_xbrl_to_excel import (  # type: ignore[import]
            find_datasets,
            find_xbrl_file,
            run_arelle_exports_progress,
            generate_consolidated_company,
        )
    except ImportError as exc:
        errors[company_name] = f"Cannot import batch_xbrl_to_excel: {exc}"
        return PipelineResult(success=success, errors=errors)

    try:
        # Escanear solo el directorio de la empresa (no todo xbrl_base_dir):
        # con cientos de empresas el walk completo por cada una es O(N²).
        all_datasets = [
            ds
            for ds in find_datasets(company_dir)
            if ds.company_dir == company_dir
        ]
    except Exception as exc:
        errors[company_name] = f"find_datasets: {exc}"
        return PipelineResult(success=success, errors=errors)

    if not all_datasets:
        errors[company_name] = "Sin datasets XBRL en este directorio"
        return PipelineResult(success=success, errors=errors)

    # Export each dataset with Arelle. Estrategia para evitar cuelgues:
    # Arelle se cuelga al ir a la red contra cmfchile.cl (la CMF nos throttlea/
    # bloquea y los timeouts HTTPS de Arelle son largos), pero el HTTP cache
    # local (~/.config/arelle/cache) tiene lo que necesitamos.
    #
    #  1) TODO offline en paralelo: Arelle usa solo cache local. Imposible
    #     colgarse. Workers cap = CMF_ARELLE_PARALLEL (default 6).
    #  2) Si algún dataset falla offline (cache no tiene la taxonomía), se
    #     reintenta una vez ONLINE serial (un solo subprocess, sin contención).
    #  3) Timeout duro por Arelle (CMF_ARELLE_TIMEOUT, default 180s) corta
    #     cualquier cuelgue residual.
    import os as _os
    try:
        arelle_parallel_cap = max(1, int(_os.getenv("CMF_ARELLE_PARALLEL", "6")))
    except ValueError:
        arelle_parallel_cap = 6

    sorted_datasets = sorted(all_datasets, key=lambda d: d.yyyyymm)
    total_ds = len(sorted_datasets)
    done_lock = threading.Lock()
    done = 0
    arelle_errors: dict[str, str] = {}

    def _process(ds, offline: bool):
        xbrl = find_xbrl_file(ds.dataset_dir, ds.stem)
        if not xbrl:
            # Antes se retornaba (ds, None) — es decir, ÉXITO — y el período
            # desaparecía de la serie sin dejar rastro. Un dataset sin .xbrl
            # (ni C ni I) es un error de descarga, no un no-op.
            return ds, RuntimeError(f"Sin .xbrl (C ni I) en {ds.dataset_dir.name}")
        out_dir = ds.dataset_dir / f"out_{ds.stem}"
        try:
            run_arelle_exports_progress(
                config.arelle_dir, xbrl, out_dir, ds.stem, config.langs,
                facts_strategy="es_only", force=False, offline=offline,
            )
            return ds, None
        except Exception as exc:
            return ds, exc

    def _bump_and_report(ds, exc, phase=""):
        nonlocal done
        with done_lock:
            done += 1
            cur = done
        if exc is not None:
            arelle_errors[ds.stem] = str(exc)[:120]
            cb(f"{company_name} - Error Arelle {ds.stem}{phase}: {str(exc)[:80]}",
               cur, total_ds)
        else:
            cb(f"{company_name} - Arelle {ds.stem}{phase} ({cur}/{total_ds})",
               cur, total_ds)
            arelle_errors.pop(ds.stem, None)

    # ---- 0a) Poblar Arelle HTTP cache con taxonomías faltantes ----
    # Necesario porque Arelle online se cuelga/recibe 403 al pedir
    # http://www.cmfchile.cl/... (CMF redirige a https y throttea).
    # requests sí sigue el redirect y baja todo de una.
    try:
        populate_arelle_cache(company_dir, cb)
    except Exception as exc:
        cb(f"{company_name} - WARN cache pre-population: {exc}", done, total_ds)

    # ---- 0b) Invalidar out_ dirs con extracción incompleta ----
    # Si una corrida previa generó facts con poca data (taxonomía incompleta
    # en cache de Arelle al momento), borramos el out_ para forzar re-extracción
    # con el cache ya poblado. El conteo bajo solo es sospechoso si el log de
    # Arelle registró errores de carga (IOerror por taxonomías faltantes):
    # una empresa chica con pocos facts y log limpio es legítima y no debe
    # re-extraerse en cada corrida.
    rescued = 0
    for ds in sorted_datasets:
        out_dir = ds.dataset_dir / f"out_{ds.stem}"
        if not out_dir.is_dir():
            continue
        facts = list(out_dir.glob("facts_*es.csv"))
        if not facts:
            continue
        try:
            with open(facts[0], encoding="utf-8-sig", errors="ignore") as fp:
                line_count = sum(1 for _ in fp)
        except Exception:
            continue
        if line_count >= 1000:
            continue
        log_file = out_dir / "arelle_facts_es.log"
        try:
            log_text = log_file.read_text(encoding="utf-8", errors="ignore")
            dirty = "IOerror" in log_text or "FileNotLoadable" in log_text
        except OSError:
            dirty = True  # sin log no hay evidencia de extracción sana
        if not dirty:
            continue
        import shutil as _shutil
        _shutil.rmtree(out_dir, ignore_errors=True)
        rescued += 1
    if rescued:
        cb(f"{company_name} - Invalidados {rescued} out_ con facts < 1000 líneas "
           f"y errores de carga en log (se re-extraerán con cache completo)",
           done, total_ds)

    # ---- 1) TODO OFFLINE paralelo ----
    max_workers = max(1, min(arelle_parallel_cap, config.workers or 1, total_ds))
    cb(f"{company_name} - Arelle OFFLINE paralelo {total_ds} ({max_workers} workers)",
       done, total_ds)
    offline_failed: list = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(_process, ds, True): ds for ds in sorted_datasets}
        for fut in as_completed(futures):
            ds, exc = fut.result()
            if exc is not None:
                offline_failed.append(ds)
            _bump_and_report(ds, exc, " [offline]")

    # ---- 2) Retry ONLINE serial para los que fallaron offline ----
    if offline_failed:
        cb(f"{company_name} - Retry ONLINE serial {len(offline_failed)} datasets "
           f"(cache miss, descargando taxonomía)", done, total_ds)
        with done_lock:
            done -= len(offline_failed)  # se vuelven a contar
        for ds in offline_failed:
            _, exc = _process(ds, offline=False)
            _bump_and_report(ds, exc, " [retry online]")

    if arelle_errors:
        bad = list(arelle_errors.keys())
        cb(f"{company_name} - {len(bad)} dataset(s) Arelle con error: "
           f"{', '.join(bad[:3])}{'...' if len(bad) > 3 else ''}",
           done, total_ds)

    # Generate consolidated facts CSV
    cb(f"{company_name} - Generando CSV consolidado", 0, 0)
    try:
        repo_root = config.xbrl_base_dir.parent.parent.parent
        generate_consolidated_company(
            company_dir,
            sorted(all_datasets, key=lambda d: d.yyyyymm),
            repo_root,
            config.langs,
            config.products_dir,
        )
        success.append(company_name)
    except Exception as exc:
        errors[company_name] = f"generate_consolidated_company: {exc}"

    return PipelineResult(success=success, errors=errors)


def _run_batch(
    config: CMFConfig,
    company_dirs: list[Path],
    cb: ProgressCallback,
) -> PipelineResult:
    """Process multiple companies via ``batch_xbrl_to_excel.main()``."""
    success: list[str] = []
    errors: dict[str, str] = {}

    try:
        from batch_xbrl_to_excel import main as batch_main  # type: ignore[import]
    except ImportError as exc:
        errors["batch"] = f"Cannot import batch_xbrl_to_excel: {exc}"
        return PipelineResult(success=success, errors=errors)

    cb(f"Running batch consolidation for {len(company_dirs)} companies", 0, len(company_dirs))

    old_argv = sys.argv.copy()
    try:
        sys.argv = [
            "batch_xbrl_to_excel.py",
            "--base-dir", str(config.xbrl_base_dir),
            "--arelle-dir", str(config.arelle_dir),
            "--langs", *config.langs,
            "--products-dir", str(config.products_dir),
        ]
        rc = batch_main()
        if rc != 0:
            errors["batch"] = f"batch_xbrl_to_excel.main() returned exit code {rc}"
        else:
            # Report all supplied companies as succeeded when batch exits cleanly
            success.extend(d.name for d in company_dirs)
    except SystemExit as exc:
        if exc.code != 0:
            errors["batch"] = f"batch_xbrl_to_excel raised SystemExit({exc.code})"
        else:
            success.extend(d.name for d in company_dirs)
    except Exception as exc:
        errors["batch"] = str(exc)
    finally:
        sys.argv = old_argv

    return PipelineResult(success=success, errors=errors)
