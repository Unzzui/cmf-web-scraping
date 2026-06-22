#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Procesamiento de datos de presentation XBRL para construir estructura jerárquica.
"""

from __future__ import annotations
import os
import pandas as pd
from .mapping import guess_role_kind


def build_tree_and_order(pres: pd.DataFrame) -> pd.DataFrame:
    """Construye el árbol jerárquico desde el CSV de presentation."""
    if pres.empty:
        return pres
    
    # Asegurar que las columnas necesarias existen
    required_cols = ['concept', 'label', 'roleUri']
    missing_cols = [col for col in required_cols if col not in pres.columns]
    
    if missing_cols:
        print(f"⚠️  Columnas faltantes en presentation: {missing_cols}")
        # Crear columnas faltantes con valores por defecto
        for col in missing_cols:
            pres[col] = ''
    
    # Limpiar datos
    pres = pres.copy()
    pres['concept'] = pres['concept'].astype(str).str.strip()
    pres['label'] = pres['label'].astype(str).str.strip()
    pres['roleUri'] = pres['roleUri'].astype(str).str.strip()
    
    # Filtrar filas vacías
    pres = pres[
        (pres['concept'] != '') & 
        (pres['label'] != '') & 
        (pres['concept'] != 'nan') & 
        (pres['label'] != 'nan')
    ]
    
    if pres.empty:
        return pres
    
    # Añadir información de jerarquía si no existe
    if 'order' not in pres.columns:
        pres['order'] = range(len(pres))
    
    if 'depth' not in pres.columns:
        pres['depth'] = 0  # Por defecto, todos al mismo nivel
    
    # Determinar tipo de statement para cada fila
    pres['statement_kind'] = pres['roleUri'].apply(guess_role_kind)
    
    # Filtrar solo statements conocidos
    pres = pres[pres['statement_kind'].notna()]
    
    # Ordenar por statement_kind, luego por order
    pres = pres.sort_values(['statement_kind', 'order'])
    
    # Agrupar conceptos duplicados (mantener el primero)
    pres = pres.drop_duplicates(subset=['concept', 'roleUri'], keep='first')
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"🏗️  Árbol construido: {len(pres)} elementos")
        for kind in pres['statement_kind'].unique():
            count = len(pres[pres['statement_kind'] == kind])
            print(f"   {kind}: {count} elementos")
    
    return pres


def select_role_tree(p_tree: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Selecciona y filtra el árbol para un tipo específico de statement."""
    if p_tree.empty:
        return p_tree
    
    # Filtrar por tipo de statement
    filtered = p_tree[p_tree['statement_kind'] == kind].copy()
    
    if filtered.empty:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  No se encontraron elementos para {kind}")
        return pd.DataFrame()
    
    # Resetear índices y mantener orden
    filtered = filtered.reset_index(drop=True)
    
    # Asegurar que hay columnas necesarias para el procesamiento posterior
    required_cols = ['concept', 'label']
    for col in required_cols:
        if col not in filtered.columns:
            filtered[col] = ''
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"📋 Seleccionado {kind}: {len(filtered)} elementos")
    
    return filtered


def choose_label(group: pd.DataFrame) -> str:
    """Elige la mejor etiqueta de un grupo de conceptos duplicados."""
    if group.empty:
        return ""
    
    # Preferir etiquetas más largas y descriptivas
    labels = group['label'].dropna().astype(str)
    labels = labels[labels != '']
    
    if labels.empty:
        return ""
    
    # Criterios de selección (en orden de prioridad):
    # 1. Etiquetas sin [Abstract] o [Axis]
    non_abstract = labels[~labels.str.contains(r'\[(?:Abstract|Axis)\]', case=False, na=False)]
    if not non_abstract.empty:
        labels = non_abstract
    
    # 2. Etiquetas más largas (más descriptivas)
    if len(labels) > 1:
        max_length = labels.str.len().max()
        longest = labels[labels.str.len() == max_length]
        if not longest.empty:
            labels = longest
    
    # 3. Primera etiqueta alfabéticamente (para consistencia)
    return labels.sort_values().iloc[0]