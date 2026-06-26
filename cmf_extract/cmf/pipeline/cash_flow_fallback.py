"""Fallback de Flujo de Efectivo cuando faltan items de cierre.

El item ``Efectivo y equivalentes al efectivo al final del periodo`` del rol
``[510000]`` puede estar ausente en algunos XBRL (típicamente el reporte del
trimestre actual). El mismo valor existe en el Balance bajo
``Efectivo y equivalentes al efectivo``.

Cuando el item de Cash Flow está vacío para un período pero el Balance lo
tiene, lo copiamos. Esto también arregla el ``al principio del periodo`` del
trimestre siguiente porque ``add_cash_beginning_period`` lo calcula como el
``final del periodo`` del período anterior.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd


_DATE_COL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_LABEL_CF_FINAL = "Efectivo y equivalentes al efectivo al final del periodo"
_LABEL_CF_PRINCIPIO = "Efectivo y equivalentes al efectivo al principio del periodo"
_LABEL_BAL_EFECTIVO = "Efectivo y equivalentes al efectivo"


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _date_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if isinstance(c, str) and _DATE_COL_RE.match(c)]


def _row_index_for(df: pd.DataFrame, role: str, label: str) -> Optional[int]:
    """Primer índice de la fila con (RoleCode, Label) dados."""
    mask = (df["RoleCode"].astype(str) == role) & (df["Label"] == label)
    idxs = df.index[mask]
    return idxs[0] if len(idxs) else None


def apply_cash_flow_fallback(df: pd.DataFrame, enable_log: bool = False) -> pd.DataFrame:
    """Rellena ``Efectivo al final del periodo`` del Cash Flow (rol 510000)
    desde el Balance (rol 210000) cuando está vacío.

    Esto, al combinarse con el cálculo posterior de ``al principio del periodo``
    (que toma el ``al final`` del período anterior), recupera ambos items.

    Devuelve ``df`` con celdas posiblemente actualizadas.
    """
    if "RoleCode" not in df.columns or "Label" not in df.columns:
        return df

    bal_idx = _row_index_for(df, "210000", _LABEL_BAL_EFECTIVO)
    cf_final_idx = _row_index_for(df, "510000", _LABEL_CF_FINAL)
    if bal_idx is None or cf_final_idx is None:
        return df

    date_cols = _date_columns(df)
    fills = 0
    for col in date_cols:
        if col not in df.columns:
            continue
        cf_val = df.at[cf_final_idx, col]
        if not _empty(cf_val):
            continue
        bal_val = df.at[bal_idx, col]
        if _empty(bal_val):
            continue
        df.at[cf_final_idx, col] = bal_val
        fills += 1

    if enable_log and fills:
        print(f"[primary-csv] 🔁 Fallback Cash Flow 'al final del periodo': "
              f"{fills} celdas rellenadas desde Balance.Efectivo")
    return df
