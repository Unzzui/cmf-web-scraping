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

import sys
import time
from pathlib import Path
from typing import Callable

from cmf.config import CMFConfig
from cmf.pipeline import PipelineResult

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
        all_datasets = [
            ds
            for ds in find_datasets(config.xbrl_base_dir)
            if ds.company_dir == company_dir
        ]
    except Exception as exc:
        errors[company_name] = f"find_datasets: {exc}"
        return PipelineResult(success=success, errors=errors)

    if not all_datasets:
        errors[company_name] = "Sin datasets XBRL en este directorio"
        return PipelineResult(success=success, errors=errors)

    # Export each dataset with Arelle
    total_ds = len(all_datasets)
    for idx, ds in enumerate(sorted(all_datasets, key=lambda d: d.yyyyymm), 1):
        cb(f"{company_name} - Arelle {ds.stem} ({idx}/{total_ds})", idx, total_ds)
        xbrl = find_xbrl_file(ds.dataset_dir, ds.stem)
        if not xbrl:
            continue
        out_dir = ds.dataset_dir / f"out_{ds.stem}"
        try:
            run_arelle_exports_progress(
                config.arelle_dir,
                xbrl,
                out_dir,
                ds.stem,
                config.langs,
                facts_strategy="es_only",
                force=False,
            )
        except Exception as exc:
            cb(f"{company_name} - Error Arelle {ds.stem}: {exc}", idx, total_ds)

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
