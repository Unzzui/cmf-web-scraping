#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unificación de cuentas renombradas por la taxonomía CMF.

Contexto: la identidad de una cuenta en el pipeline se basa en el TEXTO del
preferred-label de la taxonomía CMF. Cuando CMF renombra el label de un mismo
elemento entre versiones de taxonomía (p. ej. "Instrumentos de deuda emitidos"
-> "Instrumentos financieros de deuda emitidos" en 2022, ambos el elemento
`cl-hb:InstrumentosDeudaEmitidosBancos`), la misma línea económica se parte en
dos filas con series de tiempo disjuntas.

`taxonomy_label_renames.json` mapea, por role_code, cada label histórico a su
label canónico (= el del período MÁS RECIENTE). El mapa se deriva de la
identidad real del elemento en el presentation linkbase (ver
scripts de extracción con la API de Arelle), no de heurísticas de texto.

Este módulo:
  - `canonicalize_label`: traduce un label a su forma canónica.
  - `unify_renamed_accounts`: fusiona filas del primary_roles combinado que
    son el mismo elemento bajo labels distintos, conservando el label canónico
    y coalesciendo las columnas de período (la fila de la era más antigua gana
    en los períodos solapados = valor tal-como-reportado, consistente con el
    resto de la serie histórica).
"""
from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

_META_COLS = ("LabelKeyId", "LabelKeyIdExt", "SectionKey", "Label", "RoleCode")


@lru_cache(maxsize=4)
def load_rename_map(path: str | None = None) -> dict[str, dict[str, str]]:
    """Carga el mapa {role_code: {label_historico: label_canonico}}.

    Devuelve dict vacío si el archivo no existe (fail-safe: el pipeline sigue
    funcionando exactamente como antes, sin unificar).
    """
    if path is None:
        path = str(Path(__file__).parent / "taxonomy_label_renames.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        if os.getenv("X2E_DEBUG") == "1":
            print(f"⚠️  taxonomy_label_renames.json no disponible en {path}")
        return {}
    # normalizar claves a str
    return {str(rc): {str(k): str(v) for k, v in m.items()} for rc, m in data.items()}


def canonicalize_label(role_code, label: str, rename_map: dict[str, dict[str, str]]) -> str:
    """Traduce `label` a su forma canónica dentro de `role_code` (o lo deja igual)."""
    if not label:
        return label
    role_map = rename_map.get(str(role_code).strip(), {})
    return role_map.get(label.strip(), label)


def _period_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in _META_COLS]


def _era_key(row: pd.Series, period_cols: list[str]) -> str:
    """Última columna de período con dato (para ordenar filas viejas -> nuevas)."""
    latest = ""
    for c in period_cols:
        v = row.get(c)
        if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() != "":
            if c > latest:
                latest = c
    return latest


def _is_empty(v) -> bool:
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and str(v).strip() == "")


def _coalesce_into(base: pd.Series, other: pd.Series, period_cols: list[str]) -> None:
    """Rellena en `base` (in-place) los períodos vacíos con los de `other`.
    `base` (era más antigua) gana en los períodos solapados = valor tal-como-reportado."""
    for c in period_cols:
        if _is_empty(base.get(c)):
            base[c] = other.get(c)


def unify_renamed_accounts(
    df: pd.DataFrame,
    rename_map: dict[str, dict[str, str]] | None = None,
) -> pd.DataFrame:
    """Fusiona SOLO filas que son un rename real de la taxonomía CMF.

    Regla de seguridad: una fila solo se toca si su label es una VARIANTE
    conocida en `rename_map` (un label viejo detectado por identidad de elemento
    XBRL). Toda otra fila pasa intacta bit a bit — así NO se fusionan cuentas
    legítimas con el mismo label en secciones distintas (p. ej. 'Impuestos
    corrientes' activo vs pasivo, que NO están en el mapa).

    Para cada fila-variante (label viejo):
      - se busca su fila destino = fila del MISMO RoleCode con label == canónico;
        si hay varias, se prefiere la de igual SectionKey.
      - si existe destino: se coalescen los períodos (la era más antigua gana en
        solapes) sobre la fila de era más nueva, se conserva su metadata y el
        label canónico, y se elimina la fila-variante.
      - si NO existe destino: solo se renombra el label de la variante al canónico
        (actualización de display, sin fusión).
    Se preserva el orden original de las filas.
    """
    if rename_map is None:
        rename_map = load_rename_map()
    if not rename_map or df.empty or "Label" not in df.columns or "RoleCode" not in df.columns:
        return df

    period_cols = _period_columns(df)
    df = df.reset_index(drop=True)
    rows = [r.copy() for _, r in df.iterrows()]
    drop_idx: set[int] = set()
    n_merged = 0
    n_renamed = 0

    for i, row in enumerate(rows):
        if i in drop_idx:
            continue
        rc = str(row.get("RoleCode", "")).strip()
        lbl = str(row.get("Label", "")).strip()
        role_map = rename_map.get(rc, {})
        if lbl not in role_map:
            continue  # no es una variante conocida -> intacta
        canon = role_map[lbl]
        # candidatos destino: mismo rol, label == canónico, no ya consumidos, no la misma fila
        targets = [
            j for j, rj in enumerate(rows)
            if j != i and j not in drop_idx
            and str(rj.get("RoleCode", "")).strip() == rc
            and str(rj.get("Label", "")).strip() == canon
        ]
        if not targets:
            # sin destino: solo actualizar el label al canónico
            row["Label"] = canon
            n_renamed += 1
            continue
        # preferir destino con misma SectionKey
        sk = str(row.get("SectionKey", "")).strip()
        same_sec = [j for j in targets if str(rows[j].get("SectionKey", "")).strip() == sk]
        tgt = (same_sec or targets)[0]
        target = rows[tgt]
        # decidir cuál fila es la "vieja" (era más antigua) para que gane en solapes
        old, new = (row, target) if _era_key(row, period_cols) <= _era_key(target, period_cols) else (target, row)
        base = new.copy()                      # metadata desde la era más nueva
        _coalesce_into(base_old := old.copy(), new, period_cols)  # old gana solapes
        for c in period_cols:                  # aplicar el resultado coalescido a base
            base[c] = base_old[c]
        base["Label"] = canon
        rows[tgt] = base
        drop_idx.add(i)
        n_merged += 1

    out = pd.DataFrame([r for k, r in enumerate(rows) if k not in drop_idx]).reset_index(drop=True)
    if os.getenv("X2E_DEBUG") == "1":
        print(f"🔗 unify_renamed_accounts: {len(df)} -> {len(out)} filas "
              f"({n_merged} fusionadas, {n_renamed} solo-renombradas)")
    return out
