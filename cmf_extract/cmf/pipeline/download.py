"""Pipeline stage: download raw XBRL files from the CMF website.

Wraps ``cmf.scraping.xbrl_downloader.download_cmf_xbrl`` to download XBRL
datasets for a list of RUT numbers without any interactive prompts.

Public interface
----------------
::

    from cmf.pipeline.download import run
    result = run(config, ruts=["76036453-5", "76354771-9"], mode="total")

The *progress_callback* signature is::

    callback(message: str, current: int = 0, total: int = 0) -> None
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

from cmf.config import CMFConfig
from cmf.pipeline import PipelineResult

ProgressCallback = Callable[[str, int, int], None]
_NOOP: ProgressCallback = lambda msg, cur=0, tot=0: None  # noqa: E731

_VALID_MODES = {"total", "annual", "quarterly"}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(
    config: CMFConfig,
    ruts: list[str],
    mode: str = "total",
    start_year: int = 2024,
    end_year: int = 2014,
    progress_callback: ProgressCallback | None = None,
    max_browsers: int = 0,
) -> PipelineResult:
    """Download XBRL files for each RUT from the CMF website.

    Requires Selenium to be installed.  The function checks ``SELENIUM_AVAILABLE``
    at import time and returns an error immediately if it is ``False``.

    Downloads are placed in ``config.xbrl_base_dir`` (one sub-directory per
    company, following CMF naming conventions).

    Parameters
    ----------
    config:
        Populated :class:`~cmf.config.CMFConfig` instance.
    ruts:
        List of Chilean RUT strings (e.g. ``"76036453-5"``).
    mode:
        Download mode: ``"total"`` (annual + quarterly), ``"annual"``, or
        ``"quarterly"``.  Defaults to ``"total"``.
    start_year:
        Most-recent year to download (inclusive).
    end_year:
        Earliest year to download (inclusive).  Downloads proceed from
        *start_year* backwards to *end_year*.
    progress_callback:
        Optional callable invoked with ``(message, current, total)``
        throughout the operation.
    max_browsers:
        Number of parallel Chrome instances per RUT.  ``0`` (default) reads
        ``CMF_XBRL_MAX_BROWSERS`` env var (fallback ``1``).  When ``> 1``,
        periods are split across browsers for faster probing.

    Returns
    -------
    PipelineResult
        ``success`` contains RUT strings that were downloaded without error.
        ``errors`` maps RUT strings to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    if not ruts:
        return PipelineResult(success=[], errors={}, elapsed=0.0)

    mode = mode.lower()
    if mode not in _VALID_MODES:
        return PipelineResult(
            success=[],
            errors={"config": f"Invalid mode '{mode}'. Must be one of {sorted(_VALID_MODES)}."},
            elapsed=time.time() - start,
        )

    # --- Resolve max_browsers ---
    if max_browsers <= 0:
        max_browsers = int(os.environ.get("CMF_XBRL_MAX_BROWSERS", "1"))

    # --- Check Selenium availability ---
    try:
        from cmf.scraping.xbrl_downloader import (  # type: ignore[import]
            download_cmf_xbrl,
            download_cmf_xbrl_parallel,
            SELENIUM_AVAILABLE,
        )
    except ImportError as exc:
        return PipelineResult(
            success=[],
            errors={"import": f"Cannot import cmf.scraping.xbrl_downloader: {exc}"},
            elapsed=time.time() - start,
        )

    if not SELENIUM_AVAILABLE:
        return PipelineResult(
            success=[],
            errors={
                "selenium": (
                    "Selenium is not installed.  Install it with: "
                    "pip install selenium"
                )
            },
            elapsed=time.time() - start,
        )

    # Ensure the destination directory exists
    config.xbrl_base_dir.mkdir(parents=True, exist_ok=True)
    download_dir = str(config.xbrl_base_dir)

    total = len(ruts)
    cb(f"Descargando XBRL: {total} empresa(s) [{mode}, {start_year}-{end_year}]", 0, total)

    for idx, rut in enumerate(ruts, 1):
        cb(f"[{idx}/{total}] Descargando {rut}", idx, total)

        # Build a per-RUT progress hook that forwards messages to the callback.
        def _progress_hook(
            rut_: str,
            current: int,
            total_periods: int,
            year: int,
            month: int,
            eta_sec: float,
            status: str,
            _rut=rut,
            _idx=idx,
            _total=total,
        ) -> None:
            cb(
                f"  {_rut} | {year}-{month:02d} | {status} "
                f"({current}/{total_periods}, ETA {eta_sec:.0f}s)",
                _idx,
                _total,
            )

        try:
            download_cmf_xbrl_parallel(
                rut=rut,
                start_year=start_year,
                end_year=end_year,
                step=-1,
                headless=True,
                mode=mode,
                max_browsers=max(1, max_browsers),
                download_dir=download_dir,
                progress_hook=_progress_hook,
                skip_existing=True,
            )
            success.append(rut)
            cb(f"  Descarga OK: {rut}", idx, total)
        except Exception as exc:
            errors[rut] = str(exc)
            cb(f"  Error {rut}: {exc}", idx, total)

    elapsed = time.time() - start
    cb(
        f"Descarga lista: {len(success)}/{total} ok, {len(errors)} errores.",
        total,
        total,
    )
    return PipelineResult(success=success, errors=errors, elapsed=elapsed)
