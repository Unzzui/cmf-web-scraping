"""Centralized configuration for CMF Extract."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _repo_root() -> Path:
    """Detect repository root (parent of cmf/ package)."""
    return Path(__file__).resolve().parent.parent


@dataclass
class CMFConfig:
    """All paths and settings in one place.

    Values are resolved in order:
      1. Explicit constructor argument
      2. Environment variable
      3. Sensible default derived from repo root
    """

    repo_root: Path = field(default_factory=_repo_root)

    # --- Paths ---
    arelle_dir: Path = field(default=None)  # type: ignore[assignment]
    xbrl_base_dir: Path = field(default=None)  # type: ignore[assignment]
    products_dir: Path = field(default=None)  # type: ignore[assignment]
    product_v1_dir: Path = field(default=None)  # type: ignore[assignment]
    companies_csv: Path = field(default=None)  # type: ignore[assignment]
    scraping_repo: Path | None = None

    # --- Processing ---
    workers: int = 0
    langs: list[str] = field(default_factory=lambda: ["es"])
    debug: bool = False

    # --- Combined / TTM ---
    combined: bool = True
    keep_all_dates: bool = True
    combined_ttm_last_n: int = 3

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root)

        if self.arelle_dir is None:
            self.arelle_dir = Path(
                os.environ.get("CMF_ARELLE_DIR", Path.home() / "Documents" / "Arelle")
            )
        self.arelle_dir = Path(self.arelle_dir)

        if self.xbrl_base_dir is None:
            self.xbrl_base_dir = Path(
                os.environ.get(
                    "CMF_XBRL_BASE_DIR", self.repo_root / "data" / "XBRL" / "Total"
                )
            )
        self.xbrl_base_dir = Path(self.xbrl_base_dir)

        if self.products_dir is None:
            self.products_dir = Path(
                os.environ.get("CMF_PRODUCTS_DIR", self.repo_root / "Products")
            )
        self.products_dir = Path(self.products_dir)

        if self.product_v1_dir is None:
            self.product_v1_dir = Path(
                os.environ.get(
                    "CMF_PRODUCT_V1_DIR", self.repo_root / "Product_v1" / "Total"
                )
            )
        self.product_v1_dir = Path(self.product_v1_dir)

        if self.companies_csv is None:
            self.companies_csv = Path(
                os.environ.get(
                    "CMF_COMPANIES_CSV",
                    self.repo_root / "data" / "companies" / "RUT_Chilean_Companies.csv",
                )
            )
        self.companies_csv = Path(self.companies_csv)

        if self.scraping_repo is None:
            env = os.environ.get("CMF_SCRAPING_REPO")
            if env:
                self.scraping_repo = Path(env)

        if self.workers <= 0:
            self.workers = int(
                os.environ.get("CMF_WORKERS", max(1, os.cpu_count() or 4))
            )

        self.debug = self.debug or os.environ.get("X2E_DEBUG", "") == "1"
        self.combined = self.combined or os.environ.get("X2E_COMBINED", "") == "1"

        # Parse combined_ttm_last_n from env
        ttm_env = os.environ.get("CMF_COMBINED_TTM_LAST_N")
        if ttm_env:
            self.combined_ttm_last_n = int(ttm_env)

    def apply_env(self) -> None:
        """Push config values into environment variables for legacy scripts."""
        os.environ["CMF_WORKERS"] = str(self.workers)
        os.environ["CMF_ANALYSIS_COMBINED"] = "1" if self.combined else "0"
        os.environ["X2E_COMBINED"] = "1" if self.combined else "0"
        os.environ["X2E_KEEP_ALL_DATES"] = "1" if self.keep_all_dates else "0"
        os.environ.setdefault(
            "CMF_COMBINED_TTM_LAST_N", str(self.combined_ttm_last_n)
        )
        os.environ["CMF_SKIP_OLD_EXCEL"] = "1"
        if self.debug:
            os.environ["X2E_DEBUG"] = "1"

    def ensure_dirs(self) -> None:
        """Create output directories if they don't exist."""
        self.products_dir.mkdir(parents=True, exist_ok=True)
        (self.products_dir / "Total").mkdir(parents=True, exist_ok=True)
        self.product_v1_dir.mkdir(parents=True, exist_ok=True)
