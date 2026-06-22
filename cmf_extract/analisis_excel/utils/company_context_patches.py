#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
from typing import Optional
import re
import pandas as pd


def _find_index(labels: list[str], text: str) -> int:
    try:
        return labels.index(text)
    except ValueError:
        return -1


def _range_between(indices: list[int], start_pos: int, next_breaks: list[int]) -> tuple[int, int]:
    """Devuelve (ini, fin_exclusive) dentro de indices dadas, desde start_pos hasta el siguiente break o fin.
    Si start_pos es -1, retorna (-1, -1).
    """
    if start_pos < 0:
        return -1, -1
    end = None
    for b in sorted([b for b in next_breaks if b > start_pos]):
        end = b
        break
    return (start_pos, end if end is not None else (indices[-1] + 1))


def _zero_labels_in_range(df: pd.DataFrame, row_indices: range, labels_to_zero: list[str]) -> pd.DataFrame:
    if not labels_to_zero:
        return df
    date_cols = [c for c in df.columns if isinstance(c, str) and re.match(r'^\d{4}(-\d{2}(-\d{2})?|Q[1-4])$', c)]
    for r in row_indices:
        try:
            lbl = str(df.iloc[r, 0]).strip()
        except Exception:
            continue
        if lbl in labels_to_zero:
            for c in date_cols:
                df.iat[r, df.columns.get_loc(c)] = None
    return df


def _reorder_nb_before_bank(df: pd.DataFrame, section_header: str) -> pd.DataFrame:
    """Reordena dentro de una sección para que 'Negocios no bancarios [sinopsis]' vaya antes de 'Servicios bancarios [sinopsis]'."""
    labels = df.iloc[:, 0].astype(str).str.strip().tolist()
    idx_section = _find_index(labels, section_header)
    if idx_section < 0:
        return df

    # Encontrar límites de la sección (hasta el siguiente gran header)
    big_headers = [
        'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
        'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]',
        'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]',
    ]
    # Siguientes breaks después del inicio de la sección actual
    idx_breaks = [_find_index(labels, h) for h in big_headers]
    idx_breaks = [i for i in idx_breaks if i > idx_section]
    end = min(idx_breaks) if idx_breaks else len(labels)

    # Sub-bloques
    idx_nb = _find_index(labels, 'Negocios no bancarios [sinopsis]')
    idx_bk = _find_index(labels, 'Servicios bancarios [sinopsis]')
    if idx_nb < 0 or idx_bk < 0:
        return df
    if not (idx_section < idx_nb < end and idx_section < idx_bk < end):
        return df

    if idx_nb < idx_bk:
        return df  # ya está en orden correcto

    # Determinar rangos de los sub-bloques
    # NB: desde NB hasta antes de SB
    nb_start = idx_nb
    nb_end = idx_bk
    # SB: desde SB hasta fin de la sección
    sb_start = idx_bk
    sb_end = end

    # Reconstruir sección con NB antes de SB
    top = df.iloc[:idx_section]
    head = df.iloc[idx_section:idx_section+1]
    nb_block = df.iloc[nb_start:nb_end]
    sb_block = df.iloc[sb_start:sb_end]
    tail = df.iloc[end:]

    new_df = pd.concat([top, head, nb_block, sb_block, tail], ignore_index=True)
    return new_df


def apply_cash_flow_company_patch(df: pd.DataFrame, company_hint: Optional[str] = None) -> pd.DataFrame:
    """
    Parche ligero para empresas con segmento bancario:
    - Reordena NB antes que Servicios dentro de Operación/Inversión/Financiación.
    - En Operación/Negocios no bancarios, fuerza '-' en cuentas que deben ir a Inversión/Financiación.

    Activación:
      - Por defecto activo (CMF_ENABLE_CASHFLOW_PATCH=1). Puede forzarse por empresa con CMF_COMPANY_HINT.
    """
    try:
        df = df.copy()
        labels = df.iloc[:, 0].astype(str).str.strip().tolist()

        # Reordenar dentro de cada gran sección
        for section_header in (
            'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
            'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]',
            'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]',
        ):
            df = _reorder_nb_before_bank(df, section_header)
            labels = df.iloc[:, 0].astype(str).str.strip().tolist()

        # Zero específicos SOLO en Operación / NB
        op_header = 'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]'
        idx_op = _find_index(labels, op_header)
        if idx_op >= 0:
            # Límite de la sección operación
            next_headers = [
                _find_index(labels, 'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]'),
                _find_index(labels, 'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]'),
            ]
            next_headers = [i for i in next_headers if i > idx_op]
            op_end = min(next_headers) if next_headers else len(labels)
            idx_nb = _find_index(labels, 'Negocios no bancarios [sinopsis]')
            if idx_nb > idx_op and idx_nb < op_end:
                # rango NB dentro de operación
                idx_sb = _find_index(labels, 'Servicios bancarios [sinopsis]')
                nb_end = idx_sb if (idx_sb > idx_nb and idx_sb < op_end) else op_end
                nb_range = range(idx_nb, nb_end)
                labels_to_zero = [
                    'Dividendos recibidos',
                    'Intereses pagados',
                    'Interés pagado en depósito pasivos clasificado como actividades operativas',
                    'Intereses recibidos',
                    'Intereses recibidos de préstamos y anticipos clasificados como actividades operativas',
                    'Interés recibido de deuda instrumentos retenidos clasificado como actividades operativas',
                ]
                df = _zero_labels_in_range(df, nb_range, labels_to_zero)

        return df
    except Exception:
        return df

