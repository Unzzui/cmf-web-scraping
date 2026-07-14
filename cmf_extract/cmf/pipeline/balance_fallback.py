"""Fallback de Balance desde Notes cuando el XBRL no trae [210000].

Algunas empresas (ej. SQM 2019 quarterlies) no publican la sección
``[210000] Estado de Situación Financiera`` en su XBRL. Los items del Balance
viven en notes como ``[800100] Subclasificaciones de activos, pasivos y
patrimonios`` y ``[610000] Estado de Cambios en el Patrimonio``.

Este módulo:

1. **Mapea** filas de esas notes al RoleCode 210000 cuando sus labels (con
   normalización: strip "Total de", "Total", sufijo " totales") coinciden con
   el template del Balance de la empresa en ``new_eeff_estructura.json``.

2. **Fusiona** los valores en las filas 210000 existentes (no duplica): para
   cada celda vacía del Balance original, copia el valor del fallback.

3. **Deriva subtotales** por identidades IFRS cuando faltan:
       Total de activos no corrientes = Total activos − Activos corrientes totales
       Total de pasivos no corrientes = Total pasivos − Pasivos corrientes totales
       Total de patrimonio y pasivos  = Patrimonio total + Total de pasivos
       Total de X corrientes distintos de... = X corrientes totales

Entrada: el DataFrame ``df`` filtrado a primary_roles. Devuelve el mismo
``df`` con filas 210000 enriquecidas.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


_DATE_COL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# RoleCodes que NO consideramos notes (son los estados financieros primarios).
# Cualquier otro RoleCode es una "note" y se escanea por labels Balance.
# Razón: las empresas distribuyen items del Balance en distintas notes:
#   [800100] Subclasificaciones (Plusvalía, PPE, Inversiones...)
#   [872500] Análisis de activos y pasivos (51 matches en SQM 2019)
#   [832610] Arrendamientos NIIF 16 (Activos por derecho de uso)
#   [835110] Impuestos diferidos
#   [818000] Partes relacionadas (Cuentas por cobrar/pagar)
#   [822400] Instrumentos financieros (Deudores, Cuentas por cobrar)
#   [832410] Deterioro (Plusvalía)
#   [842000] Segmentos (Activos/Pasivos corrientes/no corrientes)
#   [851100] Efectivo
#   [861200] Capital emitido y pagado
#   [871100] Resúmenes financieros
#   [610000] Estado de cambios en Patrimonio (Patrimonio total)
_PRIMARY_STATEMENT_ROLES = {"210000", "310000", "320000", "410000", "420000", "510000"}

# Aliases específicos: labels que NO se resuelven con la normalización genérica
# pero apuntan al mismo concepto del Balance.
_BALANCE_ALIASES = {
    # Note → Template
    "patrimonio al final del periodo": "Patrimonio total",
}

# Labels del Balance que se derivan aritméticamente cuando los componentes
# están presentes en df pero el subtotal está vacío.
_LABEL_TOTAL_ACTIVOS = "Total de activos"
_LABEL_ACT_CORR_TOTAL = "Activos corrientes totales"
_LABEL_TOTAL_ACT_NC = "Total de activos no corrientes"
_LABEL_TOTAL_PASIVOS = "Total de pasivos"
_LABEL_PAS_CORR_TOTAL = "Pasivos corrientes totales"
_LABEL_TOTAL_PAS_NC = "Total de pasivos no corrientes"
_LABEL_PATRIMONIO_TOTAL = "Patrimonio total"
_LABEL_TOTAL_PAT_Y_PAS = "Total de patrimonio y pasivos"
_LABEL_CORR_DIST_ACT = (
    "Total de activos corrientes distintos de los activo o "
    "grupos de activos para su disposición clasificados como "
    "mantenidos para la venta o como mantenidos para distribuir "
    "a los propietarios"
)
_LABEL_CORR_DIST_PAS = (
    "Total de pasivos corrientes distintos de los pasivos "
    "incluidos en grupos de activos para su disposición "
    "clasificados como mantenidos para la venta"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_label(lbl) -> str:
    """Normaliza un label para matching tolerante."""
    s = str(lbl or "").strip().lower()
    s = re.sub(r"^total de\s+", "", s)
    s = re.sub(r"^total\s+", "", s)
    s = re.sub(r"\s+totales?$", "", s)
    return s.strip()


def _empty(v) -> bool:
    """True si el valor es None / NaN / string vacío."""
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def _to_num(v) -> Optional[float]:
    try:
        if _empty(v):
            return None
        return float(v)
    except Exception:
        return None


def _date_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if isinstance(c, str) and _DATE_COL_RE.match(c)]


# ---------------------------------------------------------------------------
# Fusion: copiar valores de notes a filas 210000 existentes
# ---------------------------------------------------------------------------


def _build_template_lookup(template_labels: Iterable[str]) -> dict[str, str]:
    """Mapa: label normalizado → label original (capitalización del template).

    Incluye los aliases específicos del Balance.
    """
    lookup = {_normalize_label(l): l for l in template_labels}
    template_set = set(template_labels)
    for alias_norm, tgt_label in _BALANCE_ALIASES.items():
        if tgt_label in template_set:
            lookup[alias_norm] = tgt_label
    return lookup


def _fuse_note_values_into_balance(df: pd.DataFrame,
                                   matched_notes: pd.DataFrame,
                                   date_cols: list[str]) -> tuple[int, list[dict]]:
    """Para cada fila del fallback, rellena celdas vacías de la fila 210000
    homónima. Si el label no existe en 210000, retorna como new_row.

    Returns (cell_fills, new_rows_dicts).
    """
    bal_mask = df["RoleCode"].astype(str) == "210000"
    fills = 0
    new_rows: list[dict] = []
    for _, frow in matched_notes.iterrows():
        label = frow["Label"]
        existing_idx = df.index[bal_mask & (df["Label"] == label)]
        if len(existing_idx) == 0:
            new_row = frow.to_dict()
            new_row["RoleCode"] = "210000"
            new_rows.append(new_row)
            continue
        for col in date_cols:
            if col not in df.columns or col not in frow.index:
                continue
            fval = frow.get(col)
            if _empty(fval):
                continue
            for ei in existing_idx:
                cur = df.at[ei, col]
                if _empty(cur):
                    df.at[ei, col] = fval
                    fills += 1
                    break  # solo la primera fila existente
    return fills, new_rows


# ---------------------------------------------------------------------------
# Derived subtotals (IFRS identities)
# ---------------------------------------------------------------------------


def _row_index_for_label(df: pd.DataFrame, label: str) -> Optional[int]:
    """Primer índice de fila con RoleCode=210000 y este Label."""
    mask = (df["RoleCode"].astype(str) == "210000") & (df["Label"] == label)
    idxs = df.index[mask]
    return idxs[0] if len(idxs) else None


def _derive_balance_subtotals(df: pd.DataFrame,
                              template_set: set[str],
                              date_cols: list[str]) -> int:
    """Llena subtotales del Balance por identidades IFRS cuando los
    componentes existen pero el subtotal está vacío. Retorna nº de fills."""
    derived_idx = {
        lbl: _row_index_for_label(df, lbl) for lbl in [
            _LABEL_TOTAL_ACTIVOS, _LABEL_ACT_CORR_TOTAL, _LABEL_TOTAL_ACT_NC,
            _LABEL_TOTAL_PASIVOS, _LABEL_PAS_CORR_TOTAL, _LABEL_TOTAL_PAS_NC,
            _LABEL_PATRIMONIO_TOTAL, _LABEL_TOTAL_PAT_Y_PAS,
            _LABEL_CORR_DIST_ACT, _LABEL_CORR_DIST_PAS,
        ]
        if lbl in template_set
    }

    fills = 0
    for col in date_cols:
        if col not in df.columns:
            continue

        def val(lbl):
            idx = derived_idx.get(lbl)
            return _to_num(df.at[idx, col]) if idx is not None else None

        def set_if_empty(lbl, value):
            nonlocal fills
            if value is None:
                return
            idx = derived_idx.get(lbl)
            if idx is None:
                return
            if _empty(df.at[idx, col]):
                df.at[idx, col] = value
                fills += 1

        tot_act = val(_LABEL_TOTAL_ACTIVOS)
        ac_tot = val(_LABEL_ACT_CORR_TOTAL)
        tot_pas = val(_LABEL_TOTAL_PASIVOS)
        pc_tot = val(_LABEL_PAS_CORR_TOTAL)
        pat_tot = val(_LABEL_PATRIMONIO_TOTAL)

        if tot_act is not None and ac_tot is not None:
            set_if_empty(_LABEL_TOTAL_ACT_NC, tot_act - ac_tot)
        if tot_pas is not None and pc_tot is not None:
            set_if_empty(_LABEL_TOTAL_PAS_NC, tot_pas - pc_tot)
        if pat_tot is not None and tot_pas is not None:
            set_if_empty(_LABEL_TOTAL_PAT_Y_PAS, pat_tot + tot_pas)
        # "Distintos de..." asume cero assets/liab para disposición.
        if ac_tot is not None:
            set_if_empty(_LABEL_CORR_DIST_ACT, ac_tot)
        if pc_tot is not None:
            set_if_empty(_LABEL_CORR_DIST_PAS, pc_tot)
    return fills


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def apply_balance_fallback(df: pd.DataFrame,
                           df_facts: pd.DataFrame,
                           template_labels: list[str],
                           enable_log: bool = False) -> pd.DataFrame:
    """Aplica el fallback Balance a ``df`` in-place y lo retorna.

    Parameters
    ----------
    df:
        DataFrame filtrado a primary_roles (210000, 310000/320000, 510000).
    df_facts:
        DataFrame consolidado completo (con todas las RoleCodes), del que se
        leen las notes [800100]/[610000].
    template_labels:
        Las cuentas del rol 210000 de esta empresa, en orden, tal como las declara su
        linkbase de presentacion (`presentation_order.orden_empresa`). Antes se leian de
        `new_eeff_estructura.json`, que solo cubria 53 de 145 empresas: al resto no se le
        aplicaba el fallback.
    enable_log:
        Si True, imprime resumen del fallback aplicado.
    """
    if "RoleCode" not in df_facts.columns:
        return df

    if not template_labels:
        return df

    template_set = set(template_labels)
    template_lookup = _build_template_lookup(template_labels)
    date_cols = _date_columns(df)

    notes = df_facts[
        ~df_facts["RoleCode"].astype(str).isin(_PRIMARY_STATEMENT_ROLES)
    ].copy()
    if notes.empty or "Label" not in notes.columns:
        return df

    notes["_norm"] = notes["Label"].apply(_normalize_label)
    matched = notes[notes["_norm"].isin(template_lookup.keys())].copy()
    if matched.empty:
        return df

    # Renombrar a la capitalización exacta del template.
    matched["Label"] = matched["_norm"].map(template_lookup)
    matched = matched.drop(columns=["_norm"])

    fills, new_rows = _fuse_note_values_into_balance(df, matched, date_cols)
    if new_rows:
        new_df = pd.DataFrame(new_rows)
        new_df["RoleCode"] = "210000"
        df = pd.concat([df, new_df], ignore_index=True)

    derived_fills = _derive_balance_subtotals(df, template_set, date_cols)

    if enable_log:
        print(f"[primary-csv] 🔁 Fallback [800100/610000]→Balance: "
              f"{fills} celdas rellenadas, +{len(new_rows)} filas nuevas, "
              f"{derived_fills} subtotales derivados")
    return df
