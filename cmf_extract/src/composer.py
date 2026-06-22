#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compositor principal que integra todas las funciones para generar estados financieros.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
import pandas as pd
from .data_utils import _period_labels_from_dates, _period_sort_key, _coalesce_duplicate_named_columns
from .mapping import get_account_mapping, write_unmapped_accounts_report
from .facts_processing import normalize_facts, find_conceptual_mapping, calculate_keyword_similarity
from .statement_builder import create_legacy_merged_structure
from .presentation_processing import choose_label

# Importar Facts Enhancer para mejorar matching de datos
try:
    from facts_enhancer import apply_facts_enhancements
    FACTS_ENHANCER_AVAILABLE = True
except ImportError:
    FACTS_ENHANCER_AVAILABLE = False


def compose_statement(
    facts: pd.DataFrame,
    p_tree: pd.DataFrame,
    lang: str = "es",
    other_facts_raw: pd.DataFrame | None = None,
    other_lang: str = "en",
    max_dates: int | None = None,
    statement_kind: str = "BALANCE",
    allowed_months: tuple[str, str] | None = None,
    presentation_data: pd.DataFrame | None = None,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Función principal que compone un estado financiero completo.
    
    Args:
        facts: DataFrame con datos de facts XBRL
        p_tree: DataFrame con estructura de presentation
        lang: Idioma principal ('es' o 'en')
        other_facts_raw: Facts en el otro idioma para completar datos
        other_lang: El otro idioma
        max_dates: Máximo número de fechas a mostrar
        statement_kind: Tipo de estado ('BALANCE', 'RESULTADOS', 'FLUJO')
        allowed_months: Tupla con rango de meses permitidos
        presentation_data: Datos de presentation sin procesar
        output_dir: Directorio de salida para reportes de debug
        
    Returns:
        DataFrame con el estado financiero formateado
    """
    
    if facts.empty or p_tree.empty:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️ Datos vacíos para {statement_kind}: facts={len(facts)}, tree={len(p_tree)}")
        return pd.DataFrame()
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"🏗️ Componiendo {statement_kind} en idioma {lang}")
        print(f"   Facts: {len(facts)} filas")
        print(f"   Presentation tree: {len(p_tree)} elementos")
    
    # 1. Normalizar facts
    facts_normalized = normalize_facts(facts, lang)
    
    # 2. Aplicar Facts Enhancer si está disponible
    if FACTS_ENHANCER_AVAILABLE and output_dir:
        try:
            facts_normalized = apply_facts_enhancements(facts_normalized, str(output_dir))
            if os.getenv('X2E_DEBUG') == '1':
                print(f"✅ Facts Enhancer aplicado para {statement_kind}")
        except Exception as e:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"⚠️ Error en Facts Enhancer para {statement_kind}: {e}")
    
    # 3. Completar con datos del otro idioma si están disponibles
    if other_facts_raw is not None and not other_facts_raw.empty:
        other_facts_normalized = normalize_facts(other_facts_raw, other_lang)
        facts_normalized = _merge_multilingual_facts(facts_normalized, other_facts_normalized, lang, other_lang)
    
    # 4. Crear estructura del statement usando el nuevo sistema modular
    try:
        statement_df = create_legacy_merged_structure(
            facts_normalized, p_tree, lang, statement_kind
        )
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"❌ Error creando estructura para {statement_kind}: {e}")
        # Fallback al sistema legacy
        statement_df = _compose_statement_legacy(
            facts_normalized, p_tree, lang, statement_kind, 
            allowed_months, max_dates, presentation_data, output_dir
        )
    
    # 5. Aplicar filtros de fecha si se especifican
    if allowed_months and not statement_df.empty:
        statement_df = _apply_date_filters(statement_df, allowed_months)
    
    # 6. Limitar número de columnas si se especifica
    if max_dates and not statement_df.empty:
        statement_df = _limit_date_columns(statement_df, max_dates)
    
    # 7. Limpiar y optimizar el DataFrame final
    statement_df = _cleanup_final_dataframe(statement_df, statement_kind)
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"✅ {statement_kind} compuesto: {len(statement_df)} filas, {len(statement_df.columns) - 1} períodos")
        if not statement_df.empty:
            print(f"   Períodos: {list(statement_df.columns[1:])}")
    
    return statement_df


def _merge_multilingual_facts(
    facts_primary: pd.DataFrame,
    facts_secondary: pd.DataFrame,
    primary_lang: str,
    secondary_lang: str
) -> pd.DataFrame:
    """Combina facts de múltiples idiomas para completar datos faltantes."""
    
    if facts_secondary.empty:
        return facts_primary
    
    # Identificar columnas clave para el merge
    key_columns = ['concept']
    date_columns = [col for col in facts_primary.columns if 'date' in col.lower()]
    
    if date_columns:
        key_columns.extend(date_columns)
    
    # Realizar merge preservando idioma principal
    try:
        merged_facts = facts_primary.copy()
        
        # Añadir datos faltantes del idioma secundario
        for _, row in facts_secondary.iterrows():
            concept = row.get('concept')
            if pd.isna(concept):
                continue
                
            # Verificar si este concepto ya existe en facts primarios
            concept_exists = not merged_facts[merged_facts['concept'] == concept].empty
            
            if not concept_exists:
                # Añadir este concepto del idioma secundario
                merged_facts = pd.concat([merged_facts, pd.DataFrame([row])], ignore_index=True)
        
        if os.getenv('X2E_DEBUG') == '1':
            original_count = len(facts_primary)
            merged_count = len(merged_facts)
            added_count = merged_count - original_count
            if added_count > 0:
                print(f"🌐 Añadidos {added_count} conceptos desde {secondary_lang} a {primary_lang}")
        
        return merged_facts
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️ Error combinando idiomas: {e}")
        return facts_primary


def _apply_date_filters(df: pd.DataFrame, allowed_months: tuple[str, str]) -> pd.DataFrame:
    """Aplica filtros de fechas a las columnas del DataFrame."""
    if df.empty or not allowed_months:
        return df
    
    try:
        start_date, end_date = allowed_months
        start_dt = pd.to_datetime(start_date, errors='coerce')
        end_dt = pd.to_datetime(end_date, errors='coerce')
        
        if pd.isna(start_dt) or pd.isna(end_dt):
            return df
        
        # Filtrar columnas basándose en fechas
        columns_to_keep = ['Cuenta']  # Siempre mantener la columna de cuenta
        
        for col in df.columns[1:]:  # Saltar la columna 'Cuenta'
            try:
                # Intentar extraer fecha de la columna
                col_str = str(col)
                
                # Buscar patrones de fecha en el nombre de la columna
                date_match = re.search(r'(\d{4})-(\d{2})-(\d{2})', col_str)
                if date_match:
                    col_date = pd.to_datetime(f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}")
                    if start_dt <= col_date <= end_dt:
                        columns_to_keep.append(col)
                else:
                    # Si no hay fecha específica, mantener la columna
                    columns_to_keep.append(col)
            except Exception:
                # En caso de error, mantener la columna
                columns_to_keep.append(col)
        
        return df[columns_to_keep]
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️ Error aplicando filtros de fecha: {e}")
        return df


def _limit_date_columns(df: pd.DataFrame, max_dates: int) -> pd.DataFrame:
    """Limita el número de columnas de fechas mostradas."""
    if df.empty or max_dates <= 0:
        return df
    
    # Identificar columnas de fecha (todas excepto 'Cuenta')
    date_columns = [col for col in df.columns[1:]]  # Excluir 'Cuenta'
    
    if len(date_columns) <= max_dates:
        return df  # No necesita limitación
    
    # Ordenar columnas por fecha y tomar las más recientes
    try:
        sorted_columns = sorted(date_columns, key=_period_sort_key, reverse=True)
        limited_columns = sorted_columns[:max_dates]
        
        # Mantener el orden original en el DataFrame
        final_columns = ['Cuenta'] + [col for col in df.columns[1:] if col in limited_columns]
        
        return df[final_columns]
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️ Error limitando columnas de fecha: {e}")
        return df


def _cleanup_final_dataframe(df: pd.DataFrame, statement_kind: str) -> pd.DataFrame:
    """Limpia y optimiza el DataFrame final."""
    if df.empty:
        return df
    
    # 1. Eliminar filas completamente vacías
    value_columns = df.columns[1:]  # Todas excepto 'Cuenta'
    df = df.dropna(subset=value_columns, how='all')
    
    # 2. Consolidar columnas duplicadas
    for col in df.columns[1:]:
        _coalesce_duplicate_named_columns(df, col)
    
    # 3. Ordenar filas según importancia (categorías primero, luego cuentas)
    try:
        def sort_key(cuenta: str) -> tuple[int, str]:
            cuenta_str = str(cuenta)
            if cuenta_str.startswith('[') and ']' in cuenta_str:
                return (0, cuenta_str)  # Categorías primero
            elif any(word in cuenta_str.lower() for word in ['total', 'suma', 'subtotal']):
                return (2, cuenta_str)  # Totales al final de sus secciones
            else:
                return (1, cuenta_str)  # Cuentas regulares en el medio
        
        df = df.iloc[df['Cuenta'].apply(sort_key).argsort()]
        df = df.reset_index(drop=True)
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️ Error ordenando filas: {e}")
    
    # 4. Validar integridad de datos
    if 'Cuenta' not in df.columns:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"❌ Error crítico: Columna 'Cuenta' faltante en {statement_kind}")
        return pd.DataFrame()
    
    return df


def _compose_statement_legacy(
    facts: pd.DataFrame,
    p_tree: pd.DataFrame,
    lang: str,
    statement_kind: str,
    allowed_months: tuple[str, str] | None = None,
    max_dates: int | None = None,
    presentation_data: pd.DataFrame | None = None,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """Función legacy de composición para compatibilidad hacia atrás."""
    
    # Esta función mantiene la lógica original como fallback
    # En caso de que el nuevo sistema modular falle
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"🔄 Usando sistema legacy para {statement_kind}")
    
    # Obtener mapeo de cuentas
    account_mapping = get_account_mapping(lang, presentation_data)
    
    # Crear estructura básica
    structure_rows = []
    
    for _, row in p_tree.iterrows():
        concept = str(row.get('concept', ''))
        label = str(row.get('label', ''))
        
        if concept and label:
            structure_rows.append({
                'Cuenta': label,
                'concept': concept
            })
    
    if not structure_rows:
        return pd.DataFrame()
    
    result_df = pd.DataFrame(structure_rows)
    
    # Añadir columnas de períodos vacías
    date_columns = []
    if 'endDate' in facts.columns:
        unique_dates = facts['endDate'].dropna().dt.strftime('%Y-%m-%d').unique()
        period_labels = _period_labels_from_dates(unique_dates, statement_kind)
        date_columns = sorted(period_labels.values(), key=_period_sort_key, reverse=True)
    
    for col in date_columns:
        result_df[col] = pd.NA
    
    # Simplificar: solo mantener columna Cuenta y las de fechas
    final_columns = ['Cuenta'] + date_columns
    result_df = result_df[final_columns]
    
    return result_df