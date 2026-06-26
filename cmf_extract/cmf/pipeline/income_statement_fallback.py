"""Fallback de Estado de Resultados desde notas: D&A y otros items derivables.

El Estado de Resultados estándar (rol 310000/320000) en CMF rara vez incluye
``Depreciación`` y ``Amortización`` como líneas separadas — están en notas:

  * ``[800200]`` Análisis de ingresos y gastos
        "Gasto por depreciación y amortización"
        "Gastos por depreciación"
        "Gastos por amortización"
  * ``[822100]`` Propiedades, planta y equipo
        "Depreciación, propiedades, planta y equipo"
  * ``[823180]`` Activos intangibles distintos de la plusvalía
        "Amortización, activos intangibles distintos de la plusvalía"

El analyzer (``data_extractor.py``) las busca por label exacto en df_pl;
sin estas filas no puede calcular el EBITDA Margin. Este módulo:

1. Busca las labels en las notes listadas.
2. Las inyecta como filas nuevas con ``RoleCode = income_role`` (310000/320000)
   para que entren en el Estado de Resultados.

También cubre **Número de acciones emitidas** (rol [861200]) para que esté
disponible en cálculos por acción.
"""

from __future__ import annotations

import re
from typing import Optional

import pandas as pd


_DATE_COL_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# (label_destino_en_pl, lista de labels candidatos en notas, RoleCodes a buscar)
# Orden importa: el primer candidato encontrado con data gana.
_PL_INJECTIONS = [
    (
        "Depreciación",
        ["Gastos por depreciación",
         "Depreciación, propiedades, planta y equipo"],
        ["800200", "822100"],
    ),
    (
        "Amortización",
        ["Gastos por amortización",
         "Amortización, activos intangibles distintos de la plusvalía"],
        ["800200", "823180"],
    ),
    # D&A combinado: si existe como "Gasto por depreciación y amortización"
    # en [800200], lo añadimos también. data_extractor calcula DA = Dep + Amort,
    # pero algunas empresas solo reportan el total combinado.
    (
        "Depreciación y amortización",
        ["Gasto por depreciación y amortización"],
        ["800200"],
    ),
]

# Acciones emitidas: similar mecanismo, se inyectan en el Estado de Resultados
# para que estén disponibles. data_extractor puede buscarlas si las necesita.
_SHARES_INJECTIONS = [
    (
        "Número de acciones emitidas",
        ["Total número de acciones emitidas",
         "Número de acciones emitidas y completamente pagadas",
         "Número de acciones en circulación al final del periodo"],
        ["861200"],
    ),
]


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
    mask = (df["RoleCode"].astype(str) == role) & (df["Label"] == label)
    idxs = df.index[mask]
    return idxs[0] if len(idxs) else None


def _find_value_in_notes(df_facts: pd.DataFrame, candidates: list[str],
                        roles: list[str], date_col: str) -> Optional[float]:
    """Busca candidatos en orden, devuelve el primer valor no vacío encontrado."""
    if date_col not in df_facts.columns:
        return None
    for label in candidates:
        mask = (df_facts["Label"] == label) & (
            df_facts["RoleCode"].astype(str).isin(roles)
        )
        for _, row in df_facts[mask].iterrows():
            v = row.get(date_col)
            if not _empty(v):
                try:
                    return float(v)
                except Exception:
                    continue
    return None


def apply_income_statement_fallback(df: pd.DataFrame,
                                    df_facts: pd.DataFrame,
                                    income_role: str,
                                    enable_log: bool = False) -> pd.DataFrame:
    """Inyecta D&A y acciones emitidas en el rol del Estado de Resultados.

    Parameters
    ----------
    df:
        DataFrame ya filtrado a primary_roles.
    df_facts:
        DataFrame consolidado completo (con todas las RoleCodes).
    income_role:
        ``"310000"`` o ``"320000"`` según ``detect_income_statement_role_from_facts``.
    enable_log:
        Si True, imprime resumen.
    """
    if "RoleCode" not in df.columns or "Label" not in df.columns:
        return df

    date_cols = _date_columns(df)
    if not date_cols:
        return df

    injections = _PL_INJECTIONS + _SHARES_INJECTIONS
    fills = 0
    new_rows: list[dict] = []

    for dest_label, candidates, source_roles in injections:
        # ¿La fila ya existe en el income role? Si no, la creamos.
        existing_idx = _row_index_for(df, income_role, dest_label)
        period_values: dict[str, float] = {}
        for col in date_cols:
            v = _find_value_in_notes(df_facts, candidates, source_roles, col)
            if v is not None:
                period_values[col] = v

        if not period_values:
            continue  # no hay nada que inyectar

        if existing_idx is not None:
            # Llenar celdas vacías sin sobrescribir las que ya tienen valor.
            for col, val in period_values.items():
                if _empty(df.at[existing_idx, col]):
                    df.at[existing_idx, col] = val
                    fills += 1
        else:
            new_row = {col: None for col in df.columns}
            new_row["RoleCode"] = income_role
            new_row["Label"] = dest_label
            for col, val in period_values.items():
                new_row[col] = val
            new_rows.append(new_row)
            fills += len(period_values)

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    if enable_log and fills:
        print(f"[primary-csv] 🔁 Fallback PL (D&A/acciones): "
              f"{fills} celdas inyectadas, +{len(new_rows)} filas nuevas")
    return df
