#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Constructor de estados financieros a partir de datos XBRL procesados.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
import pandas as pd
from .data_utils import _period_labels_from_dates, _period_sort_key
from .mapping import get_account_mapping, write_unmapped_accounts_report
from .facts_processing import normalize_facts, find_conceptual_mapping, calculate_keyword_similarity
from .presentation_processing import choose_label


def build_complete_statement_structure(
    facts_df: pd.DataFrame, 
    presentation_tree: pd.DataFrame, 
    lang: str = "es", 
    statement_kind: str = "BALANCE"
) -> pd.DataFrame:
    """Construye la estructura completa del estado financiero."""
    
    if presentation_tree.empty:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  Presentation tree vacío para {statement_kind}")
        return pd.DataFrame()
    
    # Obtener mapeo de cuentas
    account_mapping = get_account_mapping(lang, presentation_tree)
    
    # Crear estructura base del statement
    structure_rows = []
    
    # Procesar cada elemento del presentation tree
    for _, row in presentation_tree.iterrows():
        concept = str(row.get('concept', ''))
        label = str(row.get('label', ''))
        depth = int(row.get('depth', 0))
        
        if not concept or not label:
            continue
        
        # Determinar si es una categoría (header) o cuenta individual
        is_category = (
            '[Abstract]' in label or 
            '[Axis]' in label or
            depth == 0 or
            concept.endswith('Abstract') or
            concept.endswith('Axis')
        )
        
        structure_rows.append({
            'concept': concept,
            'label': label,
            'depth': depth,
            'is_category': is_category,
            'statement_kind': statement_kind
        })
    
    if not structure_rows:
        return pd.DataFrame()
    
    structure_df = pd.DataFrame(structure_rows)
    
    # Añadir información de mapeo
    structure_df['mapped'] = structure_df['concept'].apply(
        lambda c: any(c in accounts for accounts in account_mapping.values())
    )
    
    if os.getenv('X2E_DEBUG') == '1':
        total_concepts = len(structure_df)
        mapped_concepts = structure_df['mapped'].sum()
        print(f"📊 Estructura {statement_kind}: {total_concepts} conceptos, {mapped_concepts} mapeados")
    
    return structure_df


def fill_values_from_facts(
    structure_df: pd.DataFrame,
    facts_df: pd.DataFrame,
    statement_kind: str,
    lang: str = "es",
    max_dates: int | None = None,
    allowed_months: tuple[str, str] | None = None
) -> pd.DataFrame:
    """Llena los valores desde facts_df hacia la estructura del statement."""
    
    if structure_df.empty or facts_df.empty:
        return structure_df
    
    # Normalizar facts
    facts_normalized = normalize_facts(facts_df, lang)
    
    # Detectar columnas de fecha en facts
    date_columns = []
    for col in facts_normalized.columns:
        if any(date_indicator in col.lower() for date_indicator in ['date', 'period']):
            if facts_normalized[col].dtype == 'datetime64[ns]' or 'date' in str(facts_normalized[col].dtype):
                date_columns.append(col)
    
    if not date_columns:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  No se encontraron columnas de fecha en facts para {statement_kind}")
        return structure_df
    
    # Usar la columna de fecha más apropiada (generalmente 'endDate')
    primary_date_col = next((col for col in date_columns if 'end' in col.lower()), date_columns[0])
    
    # Filtrar facts por rango de fechas si se especifica
    if allowed_months:
        start_date, end_date = allowed_months
        try:
            start_dt = pd.to_datetime(start_date)
            end_dt = pd.to_datetime(end_date)
            facts_normalized = facts_normalized[
                (facts_normalized[primary_date_col] >= start_dt) & 
                (facts_normalized[primary_date_col] <= end_dt)
            ]
        except Exception:
            pass
    
    # Obtener períodos únicos ordenados
    unique_periods = facts_normalized[primary_date_col].dropna().dt.strftime('%Y-%m-%d').unique()
    period_labels = _period_labels_from_dates(unique_periods, statement_kind)
    
    # Limitar número de períodos si se especifica
    if max_dates and len(period_labels) > max_dates:
        sorted_periods = sorted(period_labels.items(), key=lambda x: _period_sort_key(x[1]), reverse=True)
        period_labels = dict(sorted_periods[:max_dates])
    
    # Crear DataFrame resultado con columnas de períodos
    result_columns = ['Cuenta'] + sorted(period_labels.values(), key=_period_sort_key, reverse=True)
    result_df = pd.DataFrame(columns=result_columns)
    
    # Procesar cada concepto en la estructura
    for _, row in structure_df.iterrows():
        concept = row['concept']
        label = row['label']
        is_category = row.get('is_category', False)
        
        # Para categorías, solo añadir la etiqueta sin valores
        if is_category:
            new_row = {'Cuenta': f"[{label}]"}
            for period_col in result_columns[1:]:
                new_row[period_col] = None
            result_df = pd.concat([result_df, pd.DataFrame([new_row])], ignore_index=True)
            continue
        
        # Buscar valores en facts para este concepto
        concept_facts = facts_normalized[facts_normalized['concept'] == concept]
        
        if concept_facts.empty:
            # Intentar mapeo fuzzy si no hay coincidencia exacta
            similar_concepts = facts_normalized[
                facts_normalized['concept'].str.contains(concept.split(':')[-1], case=False, na=False)
            ]
            
            if not similar_concepts.empty:
                concept_facts = similar_concepts
        
        # Crear fila para el concepto
        new_row = {'Cuenta': label}
        
        # Llenar valores por período
        for original_date, period_label in period_labels.items():
            # Buscar valor para esta fecha
            date_facts = concept_facts[
                concept_facts[primary_date_col].dt.strftime('%Y-%m-%d') == original_date
            ]
            
            value = None
            if not date_facts.empty:
                # Tomar el valor más reciente si hay múltiples
                if 'value' in date_facts.columns:
                    values = date_facts['value'].dropna()
                    if not values.empty:
                        value = values.iloc[-1]  # Último valor
            
            new_row[period_label] = value
        
        result_df = pd.concat([result_df, pd.DataFrame([new_row])], ignore_index=True)
    
    # Limpiar filas completamente vacías
    value_cols = result_columns[1:]
    result_df = result_df.dropna(subset=value_cols, how='all')
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"💾 Statement {statement_kind} construido: {len(result_df)} filas, {len(value_cols)} períodos")
    
    return result_df


def enhance_account_mapping(
    base_df: pd.DataFrame,
    facts_df: pd.DataFrame, 
    presentation_df: pd.DataFrame,
    statement_kind: str,
    lang: str = "es"
) -> pd.DataFrame:
    """Mejora el mapeo de cuentas usando múltiples estrategias."""
    
    if base_df.empty:
        return base_df
    
    enhanced_df = base_df.copy()
    
    # Obtener conceptos únicos de facts que no están en el statement actual
    if not facts_df.empty and 'concept' in facts_df.columns:
        facts_concepts = set(facts_df['concept'].dropna().unique())
        current_concepts = set()
        
        # Extraer conceptos actuales del DataFrame (buscar en labels que podrían contener conceptos IFRS)
        for label in enhanced_df['Cuenta'].dropna():
            # Buscar patrones de conceptos IFRS en las etiquetas
            ifrs_match = re.search(r'(ifrs-[a-zA-Z0-9\-:]+)', str(label))
            if ifrs_match:
                current_concepts.add(ifrs_match.group(1))
        
        missing_concepts = facts_concepts - current_concepts
        
        if missing_concepts and os.getenv('X2E_DEBUG') == '1':
            print(f"🔍 Encontrados {len(missing_concepts)} conceptos potencialmente faltantes en {statement_kind}")
        
        # Intentar mapear conceptos faltantes
        unmapped_accounts = []
        
        for concept in missing_concepts:
            # Buscar etiqueta en presentation
            concept_label = None
            if not presentation_df.empty and 'concept' in presentation_df.columns:
                matching_rows = presentation_df[presentation_df['concept'] == concept]
                if not matching_rows.empty and 'label' in presentation_df.columns:
                    concept_label = choose_label(matching_rows)
            
            if not concept_label:
                concept_label = concept  # Usar el concepto como etiqueta fallback
            
            # Verificar si este concepto tiene datos en facts
            concept_facts = facts_df[facts_df['concept'] == concept]
            if concept_facts.empty or (
                'value' in concept_facts.columns and 
                concept_facts['value'].dropna().empty
            ):
                continue  # Saltar conceptos sin datos
            
            # Intentar mapeo conceptual
            mapped_label = find_conceptual_mapping(concept_label, statement_kind)
            
            if mapped_label:
                # Añadir a enhanced_df si no existe ya
                existing_labels = enhanced_df['Cuenta'].str.lower()
                if mapped_label.lower() not in existing_labels.values:
                    # Crear nueva fila con valores vacíos para los períodos
                    new_row = {'Cuenta': mapped_label}
                    for col in enhanced_df.columns[1:]:
                        new_row[col] = None
                    enhanced_df = pd.concat([enhanced_df, pd.DataFrame([new_row])], ignore_index=True)
            else:
                unmapped_accounts.append(concept_label)
        
        # Escribir reporte de cuentas no mapeadas
        if unmapped_accounts:
            try:
                output_dir = Path.cwd()  # Directorio actual como fallback
                write_unmapped_accounts_report(unmapped_accounts, statement_kind, output_dir)
            except Exception:
                pass
    
    return enhanced_df


def create_legacy_merged_structure(
    facts_df: pd.DataFrame,
    tree_df: pd.DataFrame,
    lang: str = "es",
    statement_kind: str = "BALANCE"
) -> pd.DataFrame:
    """Crea estructura legacy combinando múltiples fuentes (para compatibilidad)."""
    
    # Construir estructura base
    base_structure = build_complete_statement_structure(
        facts_df, tree_df, lang, statement_kind
    )
    
    # Llenar con valores
    filled_structure = fill_values_from_facts(
        base_structure, facts_df, statement_kind, lang
    )
    
    # Mejorar mapeo
    enhanced_structure = enhance_account_mapping(
        filled_structure, facts_df, tree_df, statement_kind, lang
    )
    
    return enhanced_structure