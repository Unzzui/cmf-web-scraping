#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
import pytest

try:
    from validate_final_excel_es import validate_workbook  # same dir import
except Exception:
    # Allow running via repo root where tests is a package dir
    from .validate_final_excel_es import validate_workbook  # type: ignore


def _collect_excels() -> list[Path]:
    base = Path(os.getenv('CMF_PRODUCT_V1_DIR', 'Product_v1/Total'))
    if not base.exists():
        return []
    pattern = os.getenv('CMF_PYTEST_GLOB') or '*.xlsx'
    files = sorted(base.glob(pattern))
    # Prefer ES only by name
    es_files = [p for p in files if (' [ES]' in p.name) or p.name.endswith('_es.xlsx') or 'ES' in p.name]
    return es_files or files


EXCEL_FILES = _collect_excels()


@pytest.mark.skipif(not EXCEL_FILES, reason="No se encontraron Excels en Product_v1/Total")
@pytest.mark.parametrize('excel_path', EXCEL_FILES[: int(os.getenv('CMF_TEST_MAX_FILES', '12'))])
def test_excel_structure_integrity(excel_path: Path):
    errors = validate_workbook(excel_path)
    assert not errors, "\n" + "\n".join(errors)

