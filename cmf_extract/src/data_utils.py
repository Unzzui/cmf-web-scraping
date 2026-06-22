#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilidades para manejo de datos y fechas en el procesamiento XBRL.
"""

from __future__ import annotations
import re
import os
from pathlib import Path
import pandas as pd


def _quarter_from_month(m: int) -> str | None:
    """Convierte mes a trimestre."""
    try:
        m_int = int(m)
    except Exception:
        return None
    return {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}.get(m_int)


def _period_labels_from_dates(date_cols: list[str], kind: str) -> dict[str, str]:
    """
    Convierte columnas 'YYYY-MM-DD' en etiquetas normalizadas:
      - Dic (Q4) -> 'YYYYQ4'; Mar/Jun/Sep -> 'YYYYQn'
      - Otros meses -> 'YYYY'
    Q4 siempre produce 'YYYYQ4' para consistencia.
    """
    mapping: dict[str, str] = {}
    for dc in date_cols:
        try:
            d = pd.to_datetime(dc, errors='raise')
        except Exception:
            # Mantener tal cual si no es fecha limpia
            continue
        q = _quarter_from_month(d.month)
        if q:
            # Todos los trimestres (Q1-Q4) usan formato YYYYQn
            mapping[dc] = f"{d.year}{q}"
        else:
            mapping[dc] = str(d.year)
    return mapping


def _period_sort_key(lbl: str) -> tuple[int, int]:
    """Ordena períodos cronológicamente."""
    # '2025' -> (2025, 0) ; '2025Q1' -> (2025, 1) ; otros -> (9999, 9)
    s = str(lbl).split("\n", 1)[0]
    if s.isdigit():
        # Año sin quarter: ordenar como Q4 para que quede al final del mismo año
        return (int(s), 4)
    if len(s) >= 6 and s[:4].isdigit() and s[4] == 'Q' and s[5].isdigit():
        return (int(s[:4]), int(s[5]))
    return (9999, 9)


def _coalesce_duplicate_named_columns(df: pd.DataFrame, name: str) -> None:
    """Consolida columnas duplicadas con el mismo nombre."""
    cols = [c for c in df.columns if str(c).startswith(f"{name}_")]
    if len(cols) < 2:
        return
    s = df[cols].bfill(axis=1).iloc[:, 0]
    df.drop(columns=cols, inplace=True)
    df[name] = s


def guess_role_kind(role_uri: str) -> str | None:
    """Determina el tipo de estado financiero basado en el role URI."""
    u = str(role_uri).lower()
    if any(x in u for x in ['210000', 'balance', 'position']):
        return 'BALANCE'
    elif any(x in u for x in ['310000', 'income', 'profit', 'result']):
        return 'RESULTADOS'
    elif any(x in u for x in ['510000', 'cash', 'flow', 'flujo']):
        return 'FLUJO'
    return None


def load_inputs(out_dir: Path, stem: str, lang: str = "es"):
    """Carga los archivos CSV de facts y presentation."""
    facts_path = out_dir / f"facts_{stem}_{lang}.csv"
    pres_path = out_dir / f"presentation_{stem}_{lang}.csv"
    
    if not facts_path.exists():
        facts_path = out_dir / f"facts_{stem}.csv"
    if not pres_path.exists():
        pres_path = out_dir / f"presentation_{stem}.csv"
    
    if not facts_path.exists() or not pres_path.exists:
        print(f"Error: No se encontraron facts y presentation en {out_dir}")
        exit(1)
    
    facts = pd.read_csv(facts_path, dtype=str)
    pres = pd.read_csv(pres_path, dtype=str)
    return facts, pres