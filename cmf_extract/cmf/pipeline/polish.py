"""Pipeline stage: add professional start sheet to analysis workbooks.

.. deprecated::
    Polish is now integrated into Phase 3 (analysis). The ``process_excel_file``
    call happens automatically at the end of ``run_products_analysis.process_one``.
    This module is kept for backward compatibility but is no longer registered
    as a separate pipeline phase.

Wraps ``add_start_sheet_v4.process_excel_file`` to insert a cover/dashboard
sheet into each analysis workbook produced by Phase 3.

Public interface
----------------
::

    from cmf.pipeline.polish import run
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

# Analysis filenames produced by run_products_analysis end with ``[ES].xlsx``.
_ANALYSIS_SUFFIX = "[ES].xlsx"


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    config: CMFConfig,
    company_dirs: list[Path],
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Attach a professional start sheet to each company's analysis workbook.

    For each company directory the function:

    1. Searches ``config.product_v1_dir`` for an analysis file whose name
       contains the company's RUT prefix and ends with ``[ES].xlsx``.
    2. Calls ``add_start_sheet_v4.process_excel_file`` on the latest match.

    Parameters
    ----------
    config:
        Populated :class:`~cmf.config.CMFConfig` instance.
    company_dirs:
        List of on-disk company directories inside ``config.xbrl_base_dir``.
    progress_callback:
        Optional callable invoked with ``(message, current, total)``
        throughout the operation.

    Returns
    -------
    PipelineResult
        ``success`` contains the names of companies whose analysis files were
        polished.  ``errors`` maps company names to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not company_dirs:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    # --- Import phase ---
    try:
        from add_start_sheet_v4 import process_excel_file  # type: ignore[import]
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import add_start_sheet_v4: {exc}"},
            elapsed=time.time() - start,
        )

    total = len(company_dirs)
    cb(f"Phase 4: polishing {total} company/companies", 0, total)

    for idx, company_dir in enumerate(company_dirs, 1):
        company_name = company_dir.name
        rut_prefix = company_name.split("_", 1)[0]
        cb(f"[{idx}/{total}] {company_name}", idx, total)

        analysis_file = _find_analysis_file(rut_prefix, config.product_v1_dir)
        if analysis_file is None:
            errors[company_name] = (
                f"No analysis file ending with '{_ANALYSIS_SUFFIX}' found "
                f"for RUT prefix '{rut_prefix}' in {config.product_v1_dir}"
            )
            continue

        cb(f"  Processing: {analysis_file.name}", idx, total)
        try:
            ok = process_excel_file(str(analysis_file))
            if ok:
                success.append(company_name)
                cb(f"  Start sheet added: {analysis_file.name}", idx, total)
            else:
                errors[company_name] = (
                    f"process_excel_file returned False for {analysis_file.name}"
                )
        except Exception as exc:
            errors[company_name] = str(exc)

    elapsed = time.time() - start
    cb(
        f"Polish done: {len(success)}/{total} ok, {len(errors)} errors.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)


# ---------------------------------------------------------------------------
# Helper (exposed for testing)
# ---------------------------------------------------------------------------

def _find_analysis_file(rut_prefix: str, product_v1_dir: Path) -> Path | None:
    """Return the most recent analysis file for *rut_prefix*, or None.

    The search uses a glob that matches filenames containing the RUT prefix
    and containing ``ES`` (e.g. ``...[ES].xlsx``).  Results are then filtered
    to those that literally end with ``[ES].xlsx`` to avoid false positives
    from the glob character-class expansion.
    """
    candidates = [
        f
        for f in product_v1_dir.glob(f"*{rut_prefix}*ES*.xlsx")
        if f.name.endswith(_ANALYSIS_SUFFIX)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_mtime)
