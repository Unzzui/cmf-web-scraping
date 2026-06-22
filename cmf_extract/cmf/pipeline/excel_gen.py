"""Pipeline stage: facts CSV -> primary Excel workbook (Phase 2).

Wraps ``primary_csv_to_excel`` and ``generate_primary_roles_csv`` to produce
a structured Excel workbook per company without any interactive prompts.

Public interface
----------------
::

    from cmf.pipeline.excel_gen import run
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

# File-name patterns used when cleaning up stale Excel files.
_EXCEL_SUFFIXES = {".xlsx", ".xls"}
_CLEAN_PATTERNS = [
    "estados_{rut}_*",
    "estados_{rut}-*",
    "*{rut}*estados*",
    "{rut}_*",
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    config: CMFConfig,
    company_dirs: list[Path],
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Generate a primary Excel workbook from the consolidated facts CSV.

    For each company:

    1. Optionally run ``watts_data_enhancer.enhance_watts_data`` (if available).
    2. Build the primary-roles CSV via ``generate_primary_roles_csv._build_primary_roles_csv``.
    3. Remove any stale ``estados_<rut>_*`` Excel files from ``Products/Total``.
    4. Generate the Excel workbook via ``primary_csv_to_excel.generate_excel_from_primary_csv``.

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
        ``success`` contains the names of companies whose Excel files were
        generated.  ``errors`` maps company names to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not company_dirs:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    config.apply_env()

    products_total_dir = config.products_dir / "Total"
    products_total_dir.mkdir(parents=True, exist_ok=True)

    # --- Import phase (fail fast with a clear message) ---
    try:
        from primary_csv_to_excel import (  # type: ignore[import]
            generate_excel_from_primary_csv,
        )
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import primary_csv_to_excel: {exc}"},
            elapsed=time.time() - start,
        )

    try:
        import generate_primary_roles_csv as _gpr  # type: ignore[import]
        build_primary_roles_csv = _gpr._build_primary_roles_csv
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import generate_primary_roles_csv: {exc}"},
            elapsed=time.time() - start,
        )

    # Optional WATTS enhancer - import failure is non-fatal.
    try:
        from watts_data_enhancer import enhance_watts_data  # type: ignore[import]
        _watts_available = True
    except ImportError:
        enhance_watts_data = None  # type: ignore[assignment]
        _watts_available = False

    total = len(company_dirs)
    cb(f"Generando Excel para {total} empresa(s)", 0, total)

    # Pre-pass: clean ALL stale Excel files for the requested companies so that
    # subsequent phases always use the freshly generated output.
    cleaned = _clean_stale_excels(company_dirs, products_total_dir, cb)
    if cleaned:
        cb(f"Eliminados {cleaned} Excel antiguos", 0, total)

    for idx, company_dir in enumerate(company_dirs, 1):
        company_name = company_dir.name
        rut_prefix = company_name.split("_", 1)[0]
        cb(f"[{idx}/{total}] {company_name}", idx, total)

        try:
            # 1. Optional data enhancement for specific companies (e.g. WATTS SA)
            if _watts_available and enhance_watts_data is not None:
                try:
                    enhance_watts_data(company_dir)
                except Exception as exc:
                    cb(f"  Warning: watts_data_enhancer failed: {exc}", idx, total)

            # 2. Build primary-roles CSV
            primary_csv = build_primary_roles_csv(company_dir, "es")
            if not primary_csv:
                errors[company_name] = "No se pudo generar CSV primary_roles"
                continue

            # 3. Remove any remaining stale Excel files for this company before
            #    generating the new one (covers patterns not caught in pre-pass).
            _clean_company_excels(rut_prefix, products_total_dir)

            # 4. Generate Excel
            excel_path: Path | None = generate_excel_from_primary_csv(company_dir, "es")

            if excel_path and excel_path.exists():
                success.append(company_name)
                cb(
                    f"  Excel generated: {excel_path.name} "
                    f"({excel_path.stat().st_size:,} bytes)",
                    idx,
                    total,
                )
            else:
                errors[company_name] = "No se genero archivo Excel"

        except Exception as exc:
            errors[company_name] = str(exc)

    elapsed = time.time() - start
    cb(
        f"Excel listo: {len(success)}/{total} ok, {len(errors)} errores.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _clean_stale_excels(
    company_dirs: list[Path],
    target_dir: Path,
    cb: ProgressCallback,
) -> int:
    """Remove stale Excel files for all requested companies in one pass."""
    removed = 0
    for company_dir in company_dirs:
        rut_prefix = company_dir.name.split("_", 1)[0]
        removed += _clean_company_excels(rut_prefix, target_dir)
    return removed


def _clean_company_excels(rut_prefix: str, target_dir: Path) -> int:
    """Delete Excel files matching known naming patterns for *rut_prefix*."""
    removed = 0
    patterns = [p.format(rut=rut_prefix) for p in _CLEAN_PATTERNS]
    for pattern in patterns:
        for stale in target_dir.glob(pattern):
            if stale.suffix in _EXCEL_SUFFIXES:
                try:
                    stale.unlink()
                    removed += 1
                except OSError:
                    pass
    return removed
