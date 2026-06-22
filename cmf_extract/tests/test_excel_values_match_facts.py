#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
from pathlib import Path
from functools import lru_cache
from typing import Optional

import numpy as np
import pandas as pd
import pytest


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


@lru_cache(maxsize=1)
def _all_datasets_cached(base_dir: Path):
    from batch_xbrl_to_excel import find_datasets
    return find_datasets(base_dir)


@lru_cache(maxsize=256)
def _facts_for_company(rut_with_dv: str, lang: str, project_root: Path) -> pd.DataFrame:
    from batch_xbrl_to_excel import _aggregate_facts_for_company, DatasetInfo
    rut_plain = rut_with_dv.split('-')[0]
    all_ds = _all_datasets_cached(project_root / 'data/XBRL/Total')
    ds = [d for d in all_ds if isinstance(d, DatasetInfo) and d.rut == rut_plain] if all_ds else []
    df = _aggregate_facts_for_company(ds, lang, project_root)
    return df


def _period_label_to_date(label: str) -> Optional[str]:
    label = str(label).strip()
    if label.isdigit() and len(label) == 4:
        return f"{label}-12-31"
    m = re.match(r"(\d{4})Q([1-4])", label)
    if m:
        year, q = m.groups()
        end = {'1': '03-31', '2': '06-30', '3': '09-30', '4': '12-31'}[q]
        return f"{year}-{end}"
    return None


def _parse_rut_lang_from_name(name: str) -> tuple[Optional[str], Optional[str]]:
    # Pretty final name: "<Empresa> - <RUT> - ... [ES|EN].xlsx"
    m = re.search(r" - (\d+-?[\dKk]) - .*?\[(ES|EN)\]", name)
    if not m:
        return None, None
    rut, lang = m.groups()
    return rut, lang.lower()


@pytest.mark.skipif(not EXCEL_FILES, reason="No se encontraron Excels en Product_v1/Total")
@pytest.mark.skipif(os.getenv('CMF_RUN_SLOW', '0') != '1', reason="Prueba pesada desactivada (CMF_RUN_SLOW!=1)")
@pytest.mark.parametrize('excel_path', EXCEL_FILES[: int(os.getenv('CMF_TEST_MAX_FILES', '6'))])
def test_excel_values_match_facts(excel_path: Path):
    project_root = Path(__file__).resolve().parents[1]
    rut_with_dv, lang = _parse_rut_lang_from_name(excel_path.name)
    if not rut_with_dv or not lang:
        pytest.skip("Nombre de archivo no sigue patrón esperado con [ES|EN]")

    # Recrear facts consolidados
    facts_df = _facts_for_company(rut_with_dv, lang, project_root)
    if facts_df is None or facts_df.empty:
        pytest.skip("Facts consolidados vacíos para la empresa")
    facts_df = facts_df.set_index('Label')

    # Leer hojas en pandas (fila 3 como encabezado)
    xls = pd.read_excel(excel_path, sheet_name=None, engine='openpyxl', header=2)
    sheets = [s for s in xls if s in ("Balance General", "Estado de Resultados", "Flujo Efectivo")] \
             or [s for s in xls if s in ("Balance Sheet", "Income Statement", "Cash Flow")]

    mismatches = []
    verified = 0
    total_numeric = 0

    for sh in sheets:
        df = xls[sh]
        if df.empty:
            continue
        concept_col = df.columns[0]
        for _, row in df.iterrows():
            concept = row[concept_col]
            if not isinstance(concept, str) or not concept.strip():
                continue
            concept = concept.strip()
            for period_lbl in df.columns[1:]:
                val = row[period_lbl]
                if not isinstance(val, (int, float)) or pd.isna(val):
                    continue
                total_numeric += 1
                expected = val * 1000  # Excel está en miles
                fact_col = _period_label_to_date(period_lbl)
                if not fact_col:
                    continue
                if (concept in facts_df.index) and (fact_col in facts_df.columns):
                    try:
                        raw = facts_df.loc[concept, fact_col]
                        if pd.notna(raw):
                            actual = float(str(raw).replace(',', ''))
                            if not np.isclose(expected, actual, atol=1.0):
                                mismatches.append((sh, concept, period_lbl, val, expected, actual))
                            else:
                                verified += 1
                    except Exception:
                        pass

    # Aserciones finales
    assert mismatches == [], (
        "\nDiferencias encontradas:\n" +
        "\n".join(
            f"[{sh}] {concept} @ {per}: excel={val:.0f}K -> expected={exp:.0f} vs facts={act:.0f}"
            for (sh, concept, per, val, exp, act) in mismatches[:50]
        )
    )
