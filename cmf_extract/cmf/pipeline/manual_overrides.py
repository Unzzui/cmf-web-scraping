"""Inyección de valores manuales en el primary CSV cuando los XBRL no los traen.

Para empresas/períodos donde la CMF entregó XBRL incompleto y ni el Balance
fallback ni los cálculos derivados rescatan el valor, el usuario puede
llenarlo a mano en ``cmf_extract/manual_overrides.json``. Este módulo lee
ese JSON y lo aplica al DataFrame del primary CSV ANTES de generar el Excel.

Formato del JSON (sparse — solo lo que el usuario sepa):

::

    {
      "93007000-9": {
        "Balance General": {
          "Activos por derecho de uso": {
            "2019Q1": 45115000,
            "2019Q2": 47200000
          },
          "Pasivos por arrendamientos no corrientes": {
            "2019Q1": 30000000
          }
        },
        "Estado de Resultados": {
          "Ingresos de actividades ordinarias": {
            "2014Q1": 500000000
          }
        },
        "Flujo Efectivo": {}
      }
    }

Reglas:

* Las hojas se mapean a RoleCodes: ``Balance General → 210000``,
  ``Estado de Resultados → 310000/320000``, ``Flujo Efectivo → 510000``.
* La clave de período acepta tanto ``2019Q1`` como ``2019-03-31``.
* ``null`` significa "no sé el valor" — se ignora (útil para el template
  que genera el test ``--export-missing``).
* Si el override apunta a un Label que NO existe como fila en el primary CSV,
  se crea la fila nueva con ese Label.
* Si la celda ya tiene un valor del XBRL, el override **no la sobrescribe**
  (no destruye data oficial; solo llena huecos). Para forzar override usa
  ``{"_force": true, "2019Q1": ...}``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import pandas as pd


_QUARTER_TO_MONTH = {"Q1": "03-31", "Q2": "06-30", "Q3": "09-30", "Q4": "12-31"}

_SHEET_TO_ROLE = {
    "Balance General": "210000",
    "Estado de Resultados": ["310000", "320000"],  # cualquiera de los dos
    "Flujo Efectivo": "510000",
}


def _period_to_date_col(period: str) -> Optional[str]:
    """Acepta 'YYYY-MM-DD' tal cual o convierte 'YYYYQn' → 'YYYY-MM-DD'."""
    period = str(period).strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", period):
        return period
    m = re.fullmatch(r"(\d{4})(Q[1-4])", period)
    if m:
        return f"{m.group(1)}-{_QUARTER_TO_MONTH[m.group(2)]}"
    return None


def _resolve_role_codes(sheet_name: str, df: pd.DataFrame) -> list[str]:
    """Devuelve los RoleCodes válidos para esta hoja, filtrando a los presentes."""
    spec = _SHEET_TO_ROLE.get(sheet_name)
    if spec is None:
        return []
    codes = spec if isinstance(spec, list) else [spec]
    if "RoleCode" not in df.columns:
        return []
    present = set(df["RoleCode"].astype(str).unique())
    return [c for c in codes if c in present] or codes[:1]


def _empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and pd.isna(v):
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def load_overrides(path: Path) -> dict:
    """Lee el JSON de overrides. Devuelve ``{}`` si no existe o está malformado."""
    try:
        if not path.is_file():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        # No interrumpir el pipeline por un JSON mal escrito; solo avisar.
        print(f"[overrides] ⚠ No se pudo cargar {path}: {e}")
        return {}


def apply_manual_overrides(df: pd.DataFrame,
                           rut_with_dv: str,
                           overrides_path: Path,
                           enable_log: bool = False) -> pd.DataFrame:
    """Aplica overrides manuales a ``df`` (primary CSV). Devuelve df modificado.

    Idempotente: si las celdas ya están pobladas, no las toca (a menos que
    el override use ``_force: true``).
    """
    overrides = load_overrides(overrides_path)
    company = overrides.get(rut_with_dv)
    if not company:
        return df
    if "Label" not in df.columns or "RoleCode" not in df.columns:
        return df

    fills = 0
    new_rows: list[dict] = []
    for sheet_name, by_label in company.items():
        role_codes = _resolve_role_codes(sheet_name, df)
        if not role_codes:
            continue
        # Usar el primer role presente para asignar Label nuevo si hace falta.
        default_role = role_codes[0]
        for label, by_period in (by_label or {}).items():
            if not isinstance(by_period, dict):
                continue
            force = bool(by_period.get("_force"))
            mask = (df["RoleCode"].astype(str).isin(role_codes)) & (df["Label"] == label)
            row_idxs = df.index[mask]

            for period, val in by_period.items():
                if period == "_force":
                    continue
                if val is None:
                    continue  # template sin valor
                date_col = _period_to_date_col(period)
                if not date_col or date_col not in df.columns:
                    continue

                if len(row_idxs) == 0:
                    # Crear fila nueva con este Label en el role default.
                    new_row = {col: None for col in df.columns}
                    new_row["RoleCode"] = default_role
                    new_row["Label"] = label
                    new_row[date_col] = val
                    new_rows.append(new_row)
                    fills += 1
                    continue

                for ei in row_idxs:
                    cur = df.at[ei, date_col]
                    if force or _empty(cur):
                        df.at[ei, date_col] = val
                        fills += 1
                        break

    if new_rows:
        df = pd.concat([df, pd.DataFrame(new_rows)], ignore_index=True)

    if enable_log and fills:
        print(f"[overrides] 🔁 Aplicados {fills} valores manuales "
              f"desde {overrides_path.name}")
    return df
