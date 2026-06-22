"""Pipeline stage: primary Excel -> financial analysis workbook (Phase 3).

Wraps ``run_products_analysis.process_one`` to execute the financial ratio
and metrics analysis for each company without any interactive prompts.

Public interface
----------------
::

    from cmf.pipeline.analysis import run
    result = run(config, company_dirs=[Path("data/XBRL/Total/76036453-5_AGROSUPER")])

The *progress_callback* signature is::

    callback(message: str, current: int = 0, total: int = 0) -> None
"""

from __future__ import annotations

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
    """Run the financial analysis for each company.

    For each company directory:

    1. Locate the most recently modified ``estados_<rut>_*_es.xlsx`` file
       inside ``Products/Total``.
    2. Call ``run_products_analysis.process_one`` with that file as input.
    3. Output is written to ``config.product_v1_dir``.

    Parameters
    ----------
    config:
        Populated :class:`~cmf.config.CMFConfig` instance.  ``apply_env()``
        is called before any processing.
    company_dirs:
        List of on-disk company directories inside ``config.xbrl_base_dir``.
    progress_callback:
        Optional callable invoked with ``(message, current, total)``
        throughout the operation.

    Returns
    -------
    PipelineResult
        ``success`` contains the names of companies analysed without error.
        ``errors`` maps company names to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not company_dirs:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    config.apply_env()

    # Ensure output directory exists
    config.product_v1_dir.mkdir(parents=True, exist_ok=True)

    # --- Import phase ---
    try:
        from run_products_analysis import process_one  # type: ignore[import]
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import run_products_analysis: {exc}"},
            elapsed=time.time() - start,
        )

    products_total_dir = config.products_dir / "Total"
    total = len(company_dirs)
    cb(f"Analisis financiero para {total} empresa(s)", 0, total)

    for idx, company_dir in enumerate(company_dirs, 1):
        company_name = company_dir.name
        rut_prefix = company_name.split("_", 1)[0]
        cb(f"[{idx}/{total}] {company_name}", idx, total)

        # Locate the latest primary Excel for this company
        excel_files = list(products_total_dir.glob(f"estados_{rut_prefix}_*_es.xlsx"))
        if not excel_files:
            errors[company_name] = (
                f"No se encontro Excel 'estados_{rut_prefix}_*_es.xlsx' "
                f"en {products_total_dir}"
            )
            continue

        latest_file = max(excel_files, key=lambda f: f.stat().st_mtime)
        file_age_minutes = (time.time() - latest_file.stat().st_mtime) / 60
        cb(
            f"  Analysing: {latest_file.name} "
            f"(generated {file_age_minutes:.1f} min ago)",
            idx,
            total,
        )

        try:
            out_path, err = process_one(
                latest_file,
                config.product_v1_dir,
                workers=2,
                frequency="Total",
            )
            if err:
                errors[company_name] = err
            else:
                success.append(company_name)
                out_name = out_path.name if out_path else "unknown"
                cb(f"  Analysis complete: {out_name}", idx, total)
        except Exception as exc:
            errors[company_name] = str(exc)

    elapsed = time.time() - start
    cb(
        f"Analisis listo: {len(success)}/{total} ok, {len(errors)} errores.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)


# ---------------------------------------------------------------------------
# Helper (exposed for testing)
# ---------------------------------------------------------------------------

def find_latest_primary_excel(rut_prefix: str, products_total_dir: Path) -> Path | None:
    """Return the most recently modified primary Excel for *rut_prefix*, or None."""
    candidates = list(products_total_dir.glob(f"estados_{rut_prefix}_*_es.xlsx"))
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)
