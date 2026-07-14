"""Pipeline stage: export analysis workbooks to CSV for database import (Phase 4).

Wraps ``excel_to_csv_mapping.process_excel_files`` to generate one CSV per
company from the analysis Excel files in ``Product_v1/Total``.

Public interface
----------------
::

    from cmf.pipeline.to_sql import run
    result = run(config, company_dirs=[Path("data/XBRL/Total/76036453-5_AGROSUPER")])

The *progress_callback* signature is::

    callback(message: str, current: int = 0, total: int = 0) -> None
"""

from __future__ import annotations

import re
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
    """Export analysis workbooks to CSV files for database import.

    For each company directory the function:

    1. Extracts the RUT from the directory name.
    2. Passes the filtered RUT set to ``excel_to_csv_mapping.process_excel_files``.
    3. Output CSVs are written to ``config.product_v1_dir / "TO_SQL"``.

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
        ``success`` contains the names of companies exported without error.
        ``errors`` maps company names to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not company_dirs:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    # --- Import phase ---
    try:
        from excel_to_csv_mapping import process_excel_files  # type: ignore[import]
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import excel_to_csv_mapping: {exc}"},
            elapsed=time.time() - start,
        )

    # Resolve paths
    input_dir = str(config.product_v1_dir)
    output_dir = str(config.product_v1_dir / "TO_SQL")

    # Validate inputs
    if not Path(input_dir).is_dir():
        return PipelineResult(
            success=[],
            errors={"input_dir": f"Input directory does not exist: {input_dir}"},
            elapsed=time.time() - start,
        )

    # Build RUT filter from company directories
    filter_ruts: set[str] = set()
    company_names_by_rut: dict[str, str] = {}
    for company_dir in company_dirs:
        company_name = company_dir.name
        rut_prefix = company_name.split("_", 1)[0]
        # Match RUT pattern: 8-9 digits + dash + check digit
        rut_match = re.search(r'(\d{8,9}-[\dkK])', company_name)
        if rut_match:
            rut = rut_match.group(1)
            filter_ruts.add(rut)
            company_names_by_rut[rut] = company_name
        else:
            # Try using the prefix directly
            filter_ruts.add(rut_prefix)
            company_names_by_rut[rut_prefix] = company_name

    total = len(company_dirs)
    cb(f"Exportando {total} empresa(s) a CSV", 0, total)

    try:
        files_processed, records = process_excel_files(
            input_dir=input_dir,
            output_dir=output_dir,
            progress_callback=cb,
            filter_ruts=filter_ruts if filter_ruts else None,
        )
        # Una empresa sólo es un éxito si realmente quedó su CSV en TO_SQL. Antes
        # se marcaban todas como ok aunque process_excel_files no escribiera nada
        # (p. ej. RUT sin plantilla JSON), y la fase reportaba "ok" con TO_SQL vacío.
        out_path = Path(output_dir)
        for company_dir in company_dirs:
            rut_match = re.search(r'(\d{8,9}-[\dkK])', company_dir.name)
            rut = rut_match.group(1) if rut_match else company_dir.name.split("_", 1)[0]
            if any(out_path.glob(f"*{rut}*.csv")):
                success.append(company_dir.name)
            else:
                errors[company_dir.name] = (
                    f"TO_SQL no generó CSV para {rut} "
                    f"(revisa que el Excel de análisis exista y tenga datos)"
                )

    except Exception as exc:
        for company_dir in company_dirs:
            errors[company_dir.name] = str(exc)

    elapsed = time.time() - start
    cb(
        f"TO_SQL done: {len(success)}/{total} ok, {len(errors)} errors.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)
