"""Company registry: CSV database + on-disk XBRL discovery."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from cmf.config import CMFConfig


@dataclass
class Company:
    """A single company entry."""

    name: str
    rut: str  # e.g. "76036453-5"
    rut_number: str  # e.g. "76036453"
    dv: str  # e.g. "5"
    xbrl_dir: Path | None = None  # path inside data/XBRL/Total/
    periods_available: dict[str, str] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        return f"{self.rut} -- {self.name}"

    @property
    def short_name(self) -> str:
        return self.name[:40]


class CompanyRegistry:
    """Loads companies from CSV and discovers XBRL directories."""

    def __init__(self, config: CMFConfig | None = None) -> None:
        self.config = config or CMFConfig()
        self._by_rut: dict[str, Company] = {}
        self._by_rut_number: dict[str, Company] = {}
        self._load_csv()
        self._discover_xbrl_dirs()

    def _load_csv(self) -> None:
        csv_path = self.config.companies_csv
        if not csv_path.exists():
            return
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                name = row.get("Razón Social") or row.get("Razon Social", "")
                rut_full = row.get("RUT", "")
                rut_num = row.get("RUT_Numero", "")
                dv = row.get("DV", "")

                if not rut_full or not name:
                    continue

                periods = {}
                for col_key, period_label in [
                    ("Intermedio (Marzo)", "Q1"),
                    ("Intermedio (Junio)", "Q2"),
                    ("Intermedio (Septiembre)", "Q3"),
                    ("Anual (Diciembre)", "Annual"),
                ]:
                    val = row.get(col_key, "-")
                    if val and val != "-":
                        periods[period_label] = val

                company = Company(
                    name=name.strip(),
                    rut=rut_full.strip(),
                    rut_number=rut_num.strip(),
                    dv=dv.strip(),
                    periods_available=periods,
                )
                self._by_rut[company.rut] = company
                if company.rut_number:
                    self._by_rut_number[company.rut_number] = company

    def _discover_xbrl_dirs(self) -> None:
        """Match on-disk XBRL directories to known companies."""
        xbrl_dir = self.config.xbrl_base_dir
        if not xbrl_dir.exists():
            return

        for d in sorted(xbrl_dir.iterdir()):
            if not d.is_dir():
                continue
            dir_name = d.name
            # Directory format: "76036453-5_AGROSUPER_SA"
            rut_part = dir_name.split("_", 1)[0]
            rut_number = rut_part.split("-")[0] if "-" in rut_part else rut_part

            # Try to match to CSV-loaded company
            company = self._by_rut.get(rut_part) or self._by_rut_number.get(
                rut_number
            )
            if company:
                # If xbrl_dir is already set, prefer directory with more data
                if company.xbrl_dir is not None and company.xbrl_dir != d:
                    old_count = sum(1 for x in company.xbrl_dir.iterdir() if x.is_dir() and "extracted" in x.name)
                    new_count = sum(1 for x in d.iterdir() if x.is_dir() and "extracted" in x.name)
                    if new_count > old_count:
                        company.xbrl_dir = d
                else:
                    company.xbrl_dir = d
            else:
                # Company on disk but not in CSV - create from directory name
                name_part = (
                    dir_name.split("_", 1)[1].replace("_", " ")
                    if "_" in dir_name
                    else dir_name
                )
                dv = rut_part.split("-")[1] if "-" in rut_part else ""
                company = Company(
                    name=name_part,
                    rut=rut_part,
                    rut_number=rut_number,
                    dv=dv,
                    xbrl_dir=d,
                )
                self._by_rut[rut_part] = company
                if rut_number:
                    self._by_rut_number[rut_number] = company

    @property
    def companies(self) -> list[Company]:
        """All known companies, sorted by name."""
        return sorted(self._by_rut.values(), key=lambda c: c.name)

    @property
    def companies_with_xbrl(self) -> list[Company]:
        """Companies that have XBRL data on disk."""
        return [c for c in self.companies if c.xbrl_dir is not None]

    def get(self, rut: str) -> Company | None:
        """Lookup by full RUT (e.g. '76036453-5') or number only."""
        return self._by_rut.get(rut) or self._by_rut_number.get(rut)

    def search(self, query: str) -> list[Company]:
        """Search companies by name or RUT substring."""
        q = query.lower()
        return [
            c
            for c in self.companies
            if q in c.name.lower() or q in c.rut.lower()
        ]

    def __len__(self) -> int:
        return len(self._by_rut)

    def __iter__(self) -> Iterator[Company]:
        return iter(self.companies)
