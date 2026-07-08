#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Genera Excel directamente desde primary_roles CSV manteniendo los estilos exactos de xbrl_to_excel.py

Uso:
  python primary_csv_to_excel.py <company_dir> <lang> [output_xlsx]
  
Ejemplo:
  python primary_csv_to_excel.py data/XBRL/Total/90227000-0_VIÑA_CONCHA_Y_TORO_SA es

Este script:
1. Lee los archivos primary_roles CSV de out_consolidated_*
2. Los organiza en las 3 hojas estándar (Balance Sheet, Income Statement, Cash Flow)  
3. Aplica exactamente el mismo formateo visual que xbrl_to_excel.py
4. Genera el archivo Excel final con datos EXACTOS del primary_roles CSV
"""

from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List

import pandas as pd


def detect_income_statement_role_from_primary(df: pd.DataFrame, company_rut: str = None) -> str:
    """
    Detecta automáticamente si usar rol 310000 (función) o 320000 (naturaleza)
    para el estado de resultados basado en estructura JSON específica por empresa.
    
    Prioridad de detección:
    1. Estructura específica en new_eeff_estructura.json por RUT
    2. RoleCode en DataFrame de primary_roles
    3. Default: 310000 (función)
    
    Returns:
        str: "310000" o "320000"
    """
    # PRIORIDAD 1: Buscar en estructura JSON específica por empresa
    if company_rut:
        try:
            import json
            from pathlib import Path
            
            estructura_file = Path(__file__).parent / "new_eeff_estructura.json"
            if estructura_file.exists():
                with open(estructura_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                for empresa in data.get('empresas', []):
                    if empresa.get('empresa', {}).get('rut') == company_rut:
                        for rol in empresa.get('roles', []):
                            role_id = rol.get('id')
                            if role_id in ['310000', '320000']:
                                titulo = rol.get('titulo', '')
                                print(f"📋 [primary-csv] Estructura JSON empresa {company_rut}: usando rol {role_id}")
                                if 'naturaleza' in titulo.lower():
                                    print(f"🎯 [primary-csv] Confirmado rol naturaleza: {titulo[:60]}...")
                                return role_id
                        break
        except Exception as e:
            print(f"⚠ [primary-csv] Error leyendo estructura JSON: {e}")
    
    # PRIORIDAD 2: Buscar códigos de rol únicos en el DataFrame
    if df is not None and not df.empty and 'RoleCode' in df.columns:
        role_codes = df['RoleCode'].astype(str).unique()
        if '320000' in role_codes:
            return "320000"
        elif '310000' in role_codes:
            return "310000"
    
    # Default fallback: función (310000)
    return "310000"


def find_primary_roles_files(company_dir: Path, lang: str) -> List[Path]:
    """Encuentra el archivo primary_roles CSV más reciente/amplio en out_consolidated_*.

    When multiple out_consolidated_* directories exist (e.g. after re-running
    consolidation with newer XBRL data), we must pick only the one with the
    widest date range.  Loading all of them and concatenating causes older rows
    (missing newer period columns) to shadow newer rows via the _filled flag
    in sort_by_hierarchical_keys(), leaving recent columns empty.
    """
    import re as _re

    primary_files: list[tuple[str, Path]] = []

    for out_dir in company_dir.glob("out_consolidated_*"):
        if not out_dir.is_dir():
            continue

        pattern = f"primary_roles_*_{lang}.csv"
        for primary_file in out_dir.glob(pattern):
            if primary_file.exists():
                # Extract the end-date portion from the dir or filename
                # e.g. out_consolidated_76129263-3_201403-202512 → "202512"
                m = _re.search(r'(\d{6})(?=[/\\]|$)', out_dir.name)
                end_period = m.group(1) if m else ""
                primary_files.append((end_period, primary_file))

    if not primary_files:
        return []

    # Pick only the file with the latest end-period (widest date range)
    primary_files.sort(key=lambda x: x[0], reverse=True)
    best = primary_files[0][1]
    return [best]


def load_and_combine_primary_roles(primary_files: List[Path]) -> pd.DataFrame:
    """Carga y combina múltiples archivos primary_roles CSV"""
    if not primary_files:
        raise ValueError("No se encontraron archivos primary_roles CSV")
    
    all_dfs = []
    
    for file_path in primary_files:
        # Cargando archivo primary_roles
        try:
            df = pd.read_csv(file_path)
            # RoleCode debe ser str en todo el pipeline; read_csv lo infiere
            # int y pandas >= 3 rechaza asignar int en columnas str.
            if 'RoleCode' in df.columns:
                df['RoleCode'] = df['RoleCode'].astype(str)
            all_dfs.append(df)
        except Exception as e:
            # Error cargando archivo
            continue
    
    if not all_dfs:
        raise ValueError("No se pudo cargar ningún archivo primary_roles CSV")
    
    # Combinar todos los DataFrames PRESERVANDO EL ORDEN ORIGINAL
    combined = pd.concat(all_dfs, ignore_index=True)
    
    # NO ELIMINAR DUPLICADOS - Los datos del primary_roles CSV son sagrados
    # Mantener TODO exactamente como está en el archivo original
    
    # ✨ CRUCIAL: Preservar orden original usando el índice implícito del CSV
    # El CSV fue generado con el orden correcto por generate_primary_roles_csv.py
    combined = combined.reset_index(drop=True)  # Mantener el orden secuencial
    
    # Archivos primary_roles combinados
    return combined


def sort_by_hierarchical_keys(df: pd.DataFrame, company_rut: str = None) -> pd.DataFrame:
    """
    FLUJO SECUENCIAL DE 3 PASOS:
    1. Crear estructura base del Excel usando "lineas" del JSON
    2. Llenar datos por mapeo exacto de Label (excluir conflictivas y [sinopsis])  
    3. Llenar cuentas conflictivas por LabelKeyIdExt (aunque no tengan valores)
    
    Args:
        df: DataFrame con los datos a ordenar
        company_rut: RUT de la empresa para buscar su estructura específica
    """
    if df.empty or 'Label' not in df.columns:
        return df
    
    # Iniciando procesamiento secuencial
    
    # PASO 1: CREAR ESTRUCTURA BASE DEL EXCEL usando "lineas" del JSON
    json_structure_by_role = {}
    try:
        import json
        from pathlib import Path
        estructura_file = Path(__file__).parent / "new_eeff_estructura.json"
        
        with open(estructura_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Buscar la empresa específica por RUT
        estructura_encontrada = False
        for empresa in data.get('empresas', []):
            if empresa.get('empresa', {}).get('rut') == company_rut:
                for rol in empresa.get('roles', []):
                    role_id = rol.get('id')
                    if role_id in ['210000', '310000', '320000', '510000']:
                        lineas = rol.get('lineas', [])
                        json_structure_by_role[role_id] = lineas
                        # Estructura específica cargada para RUT: company_rut
                estructura_encontrada = True
                break
        
        # Si no se encuentra estructura específica, usar QUIÑENCO como fallback
        if not estructura_encontrada:
            # No se encontró estructura para RUT, usando QUIÑENCO como fallback
            for empresa in data.get('empresas', []):
                if empresa.get('empresa', {}).get('rut') == '91705000-7':
                    for rol in empresa.get('roles', []):
                        role_id = rol.get('id')
                        if role_id in ['210000', '310000', '320000', '510000']:
                            lineas = rol.get('lineas', [])
                            json_structure_by_role[role_id] = lineas
                            # Usando estructura de QUIÑENCO como fallback
                    break
        
    except Exception as e:
        # Error cargando estructura
        return df
    
    # Detectar el role actual para esta función
    if df.empty:
        return df
    
    role_code = str(df.iloc[0].get('RoleCode', '')).strip()
    json_structure = json_structure_by_role.get(role_code, [])
    
    if not json_structure:
        # No se encontró estructura para role
        return df
    
    # PASO 1: Crear DataFrame base con estructura de las "lineas"
    # PASO 1: Creando estructura base
    base_rows = []
    for position, linea in enumerate(json_structure):
        # Crear fila base con la estructura pero sin datos
        base_row = {
            'Label': linea,
            'RoleCode': role_code,
            'LabelKeyIdExt': f"{role_code}||{linea}",  # Placeholder
            'LabelKeyId': f"{role_code}||{linea}",     # Placeholder  
            'SectionKey': linea,
            '_estructura_position': position,
            '_filled': False  # Marcador para saber si se llenó con datos
        }
        base_rows.append(base_row)
    
    base_df = pd.DataFrame(base_rows)
    # Estructura base creada
    
    # PASO 2: LLENAR DATOS por mapeo exacto de Label (excluir conflictivas)
    cuentas_conflictivas = {
        'Dividendos pagados', 'Dividendos recibidos', 'Intereses pagados', 
        'Intereses recibidos', 'Impuestos a las ganancias pagados (reembolsados)',
        'Otras entradas (salidas) de efectivo', 'Otros','Otros préstamos obtenidos a largo plazo',
    }
    
    # PASO 2: Mapeo exacto de datos
    filled_count = 0
    
    for idx, data_row in df.iterrows():
        data_label = str(data_row.get('Label', '')).strip()
        
        # Excluir cuentas conflictivas y [sinopsis] por ahora
        # Las cuentas conflictivas se procesarán SOLO en el PASO 3 con su LabelKeyIdExt correcto
        if data_label in cuentas_conflictivas or '[sinopsis]' in data_label:
            continue
            
        # Buscar coincidencia exacta en la estructura base
        matching_rows = base_df[base_df['Label'] == data_label]
        if not matching_rows.empty and not matching_rows.iloc[0]['_filled']:
            # Llenar con los datos reales
            match_idx = matching_rows.index[0]
            for col in data_row.index:
                if col not in ['_estructura_position', '_filled']:
                    base_df.at[match_idx, col] = data_row[col]
            base_df.at[match_idx, '_filled'] = True
            filled_count += 1
    
    # Mapeo exacto completado
    
    # PASO 3: LLENAR CUENTAS CONFLICTIVAS por LabelKeyIdExt
    # PASO 3: Procesando cuentas conflictivas
    conflictive_added = 0
    
    for idx, data_row in df.iterrows():
        data_label = str(data_row.get('Label', '')).strip()
        data_label_key_ext = str(data_row.get('LabelKeyIdExt', '')).strip()
        
        # Solo procesar cuentas conflictivas
        if data_label not in cuentas_conflictivas:
            continue
            
        # Usar LabelKeyIdExt para encontrar la categoría correcta donde debe ir esta cuenta conflictiva
        target_section_found = False
        
        if data_label_key_ext and '||' in data_label_key_ext:
            parts = data_label_key_ext.split('||')
            # Procesando cuenta conflictiva
            # LabelKeyIdExt identificado
            
            if len(parts) >= 3:
                # Extraer categoría principal y subcategoría del LabelKeyIdExt complejo
                # Para LabelKeyIdExt como: 510000||Flujos...[sinopsis]||Servicios bancarios [sinopsis]||...
                main_category = None
                subcategory = None
                
                # Buscar categorías [sinopsis] únicas (eliminar duplicados)
                unique_categories = []
                seen = set()
                for part in parts[1:]:  # Saltar el RoleCode
                    if part.strip() and '[sinopsis]' in part and part.strip() not in seen:
                        unique_categories.append(part.strip())
                        seen.add(part.strip())
                
                # Categorías únicas identificadas
                
                # Identificar categoría principal y subcategoría
                # Si hay categoría de "actividades", esa es la principal y la otra es subcategoría
                # Si NO hay categoría de "actividades", la única categoría es la principal
                activity_categories = [c for c in unique_categories if 'actividades' in c.lower()]
                other_categories = [c for c in unique_categories if 'actividades' not in c.lower()]
                
                if activity_categories:
                    # Caso con actividades: categoría de actividades + subcategoría
                    main_category = activity_categories[0]  # Tomar la primera (debería ser única)
                    subcategory = other_categories[0] if other_categories else None
                else:
                    # Caso sin actividades: solo categoría principal, no subcategoría
                    main_category = other_categories[0] if other_categories else None
                    subcategory = None
                
                # Categoría principal identificada
                # Subcategoría identificada
                
                # PASO 1: Encontrar la categoría principal
                main_section_start = None
                main_section_end = len(base_df)
                
                if main_category:
                    for idx, row in base_df.iterrows():
                        row_label = str(row['Label']).strip()
                        if main_category.lower() == row_label.lower():
                            main_section_start = idx
                            # Categoría principal encontrada
                            break
                
                # Encontrar el final de la categoría principal
                if main_section_start is not None:
                    for idx in range(main_section_start + 1, len(base_df)):
                        row_label = str(base_df.iloc[idx]['Label']).strip()
                        
                        if activity_categories:
                            # Si la categoría principal es de actividades, termina con otra categoría de actividades
                            if '[sinopsis]' in row_label and 'actividades' in row_label.lower():
                                main_section_end = idx
                                break
                        else:
                            # Si no es de actividades, termina con cualquier categoría [sinopsis] principal
                            if '[sinopsis]' in row_label and row_label != main_category:
                                main_section_end = idx
                                break
                    # Sección de categoría principal definida
                
                # PASO 2: Dentro de la categoría principal, encontrar la subcategoría
                section_start = None
                section_end = main_section_end
                
                if main_section_start is not None and subcategory:
                    # Buscar subcategoría solo dentro de la sección principal
                    main_section_df = base_df.iloc[main_section_start:main_section_end]
                    
                    for rel_idx, row in main_section_df.iterrows():
                        row_label = str(row['Label']).strip()
                        if subcategory.lower() == row_label.lower():
                            section_start = rel_idx
                            # Subcategoría encontrada
                            break
                    
                    # Encontrar el final de la subcategoría
                    if section_start is not None:
                        for idx in range(section_start + 1, main_section_end):
                            row_label = str(base_df.iloc[idx]['Label']).strip()
                            # Termina cuando encuentre otra subcategoría [sinopsis]
                            if '[sinopsis]' in row_label:
                                section_end = idx
                                break
                        # Sección de subcategoría definida
                else:
                    # Si no hay subcategoría, usar toda la sección principal
                    section_start = main_section_start
                    section_end = main_section_end
                
                # Buscar match exacto por Label dentro de la sección encontrada
                if section_start is not None:
                    section_df = base_df.iloc[section_start:section_end]
                    matching_rows = section_df[section_df['Label'] == data_label]
                    
                    if not matching_rows.empty:
                        # Encontrar la fila correcta y sobrescribirla con los valores
                        target_idx = matching_rows.index[0]
                        
                        # Sobrescribir con todos los datos de la cuenta conflictiva
                        for col in data_row.index:
                            if col not in ['_estructura_position', '_filled']:
                                base_df.at[target_idx, col] = data_row[col]
                        
                        base_df.at[target_idx, '_filled'] = True
                        target_section_found = True
                        conflictive_added += 1
                        # Fila sobrescrita con valores
                    else:
                        # Label exacto no encontrado en sección
                        pass
                else:
                    # Sección correcta no encontrada
                    pass
        
        if not target_section_found:
            # Cuenta conflictiva no procesada
            pass
    
    # Cuentas conflictivas procesadas
    
    # ORDENAR por la posición de estructura y limpiar
    final_df = base_df.sort_values('_estructura_position', kind='stable')
    final_df = final_df.drop(['_estructura_position', '_filled'], axis=1)
    final_df = final_df.reset_index(drop=True)

    # ─── Anexar items EXTRA que NO están en el template pero SÍ tienen data ───
    # Esto rescata filas inyectadas por fallbacks (D&A, Acciones emitidas, etc.)
    # que el template legacy no incluye. Se ponen al final, preservando los
    # valores reales para que data_extractor pueda encontrarlas.
    template_labels = set(base_df['Label'].astype(str))
    date_columns = [c for c in df.columns
                    if c not in ('LabelKeyId', 'LabelKeyIdExt', 'SectionKey',
                                 'Label', 'RoleCode')]
    extra_rows = []
    seen_extra_labels = set()
    for _, row in df.iterrows():
        label = str(row.get('Label', '')).strip()
        if not label or label in template_labels or label in seen_extra_labels:
            continue
        if '[sinopsis]' in label.lower():
            continue
        # Solo agregar si la fila tiene al menos una celda con valor numérico
        has_data = any(
            not (row.get(d) is None
                 or (isinstance(row.get(d), float) and pd.isna(row.get(d)))
                 or (isinstance(row.get(d), str) and not row.get(d).strip()))
            for d in date_columns if d in row.index
        )
        if has_data:
            extra_rows.append(row)
            seen_extra_labels.add(label)

    if extra_rows:
        extra_df = pd.DataFrame(extra_rows)
        # Conservar solo columnas que tiene final_df
        keep_cols = [c for c in final_df.columns if c in extra_df.columns]
        extra_df = extra_df[keep_cols].reset_index(drop=True)
        final_df = pd.concat([final_df, extra_df], ignore_index=True)

    # Flujo de procesamiento completado
    return final_df


def remove_subcategory_duplicates(df: pd.DataFrame) -> pd.DataFrame:
    """
    Elimina SOLO duplicados verdaderamente problemáticos (mismo LabelKeyIdExt exacto).
    PRESERVA duplicados válidos que representan diferentes contextos jerárquicos.
    """
    if df.empty:
        return df
    
    # Eliminando duplicados problemáticos
    
    # Identificar duplicados por LabelKeyIdExt exacto (estos son los problemáticos)
    duplicate_keys = []
    label_key_counts = df['LabelKeyIdExt'].value_counts()
    
    for label_key, count in label_key_counts.items():
        if count > 1:
            # Solo considerar problemáticos si es [sinopsis] Y tiene mismo LabelKeyIdExt
            sample_row = df[df['LabelKeyIdExt'] == label_key].iloc[0]
            if '[sinopsis]' in str(sample_row.get('Label', '')):
                duplicate_keys.append(label_key)
                # LabelKeyIdExt duplicado detectado
    
    if not duplicate_keys:
        # Sin duplicados problemáticos
        return df
    
    # Para cada LabelKeyIdExt duplicado, mantener solo la mejor instancia
    indices_to_remove = []
    
    for duplicate_key in duplicate_keys:
        duplicate_rows = df[df['LabelKeyIdExt'] == duplicate_key].copy()
        
        if len(duplicate_rows) <= 1:
            continue  # No es realmente duplicado
        
        # Mantener solo la primera instancia (más estable)
        # Las demás son duplicados verdaderamente problemáticos
        first_idx = duplicate_rows.index[0]
        
        for idx in duplicate_rows.index[1:]:
            indices_to_remove.append(idx)
            row = duplicate_rows.loc[idx]
            label = str(row.get('Label', ''))
            # Eliminando duplicado problemático
    
    # Eliminar solo duplicados verdaderamente problemáticos
    if indices_to_remove:
        df_clean = df.drop(index=indices_to_remove).reset_index(drop=True)
        # Duplicados problemáticos eliminados
        # Duplicados válidos preservados
        return df_clean
    
    return df


def split_by_role(df: pd.DataFrame, company_rut: str = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Separa el DataFrame por roles en las 3 hojas principales
    
    Args:
        df: DataFrame con todos los datos
        company_rut: RUT de la empresa para buscar su estructura específica
    """
    
    # Definir los roles principales con autodetección para income
    balance_role = "210000"  # Balance Sheet / Estado de Situación Financiera
    income_role = detect_income_statement_role_from_primary(df, company_rut)  # Autodetectar 310000 o 320000
    cashflow_role = "510000" # Cash Flow / Estado de Flujos de Efectivo
    
    # Log si se detectó 320000
    if income_role == "320000":
        print(f"🎯 [primary-csv] Detectado rol 320000 (naturaleza) para estado de resultados")
    
    # Filtrar por roles (usar RoleCode que es la columna real), ser robusto con valores
    # ✨ CRUCIAL: Mantener el orden original del DataFrame usando .loc para preservar secuencia
    balance_mask = df['RoleCode'].astype(str).str.strip() == balance_role
    income_mask = df['RoleCode'].astype(str).str.strip() == income_role
    cashflow_mask = df['RoleCode'].astype(str).str.strip() == cashflow_role
    
    balance_df = df.loc[balance_mask].copy()
    income_df = df.loc[income_mask].copy()
    cashflow_df = df.loc[cashflow_mask].copy()
    
    # ✅ ORDENAR USANDO CLAVES JERÁRQUICAS DEL CSV PARA TODAS LAS HOJAS
    # Usar las claves jerárquicas (LabelKeyId, LabelKeyIdExt, SectionKey) para crear orden perfecto
    balance_df = sort_by_hierarchical_keys(balance_df, company_rut)    # Balance ordenado jerárquicamente
    income_df = sort_by_hierarchical_keys(income_df, company_rut)      # Income ordenado jerárquicamente  
    cashflow_df = sort_by_hierarchical_keys(cashflow_df, company_rut)  # Cash Flow ordenado jerárquicamente
    
    # Preparar DataFrames para Excel: 'Label' como primera columna, luego fechas
    # FILTRAR cuentas intermedias que son solo estructura organizacional
    def prepare_for_excel(sheet_df):
        if sheet_df.empty:
            return pd.DataFrame()
        
        # Seleccionar solo Label y las columnas de fechas (saltar las primeras columnas de metadatos)
        date_columns = [col for col in sheet_df.columns if col not in ['LabelKeyId', 'LabelKeyIdExt', 'SectionKey', 'Label', 'RoleCode']]
        
        # ✨ Preparar datos para Excel manteniendo estructura jerárquica completa
        filtered_df = sheet_df.copy()
        
        # ✅ Preservar todas las cuentas [sinopsis] - son estructurales
        # Las cuentas [sinopsis] proporcionan la estructura jerárquica correcta
        # Preservando cuentas [sinopsis]
        
        # Mantener todas las cuentas sin filtrar 
        mask_to_keep = pd.Series([True] * len(filtered_df), index=filtered_df.index)
        
        # Manteniendo todas las cuentas
        
        # Aplicar filtro manteniendo el orden original
        filtered_df = filtered_df.loc[mask_to_keep].copy()
        
        # ✨ CRUCIAL: Crear DataFrame final preservando el ORDEN EXACTO del CSV original
        result_df = pd.DataFrame()
        result_df['Cuenta'] = filtered_df['Label'].copy()
        
        # Agregar columnas de fechas en el mismo orden que en el CSV
        for date_col in date_columns:
            result_df[date_col] = filtered_df[date_col].copy()
        
        # ✨ MANTENER el índice original para preservar el orden exacto del CSV
        # NO usar reset_index aquí para conservar la secuencia
        result_df.index = filtered_df.index
        
        return result_df
    
    balance_df = prepare_for_excel(balance_df)
    income_df = prepare_for_excel(income_df) 
    cashflow_df = prepare_for_excel(cashflow_df)
    
    # Balance Sheet procesado
    # Income Statement procesado  
    # Cash Flow procesado
    
    return balance_df, income_df, cashflow_df


def _quarter_from_month(m: int) -> str | None:
    """Convierte mes (3,6,9,12) a trimestre (Q1,Q2,Q3,Q4)"""
    try:
        m_int = int(m)
    except Exception:
        return None
    return {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}.get(m_int)


def _period_sort_key(lbl: str) -> tuple[int, int]:
    """Clave de ordenamiento para columnas de períodos: '2025' -> (2025, 0) ; '2025Q1' -> (2025, 1)"""
    s = str(lbl).split("\n", 1)[0]
    if s.isdigit():
        # Año sin quarter: ordenar como Q4 para que quede al final del mismo año
        return (int(s), 4)
    if len(s) >= 6 and s[:4].isdigit() and s[4] == 'Q' and s[5].isdigit():
        return (int(s[:4]), int(s[5]))
    # Intentar fecha completa YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        year = int(m.group(1))
        month = int(m.group(2))
        q = _quarter_from_month(month)
        return (year, {None: 0, 'Q1': 1, 'Q2': 2, 'Q3': 3, 'Q4': 4}[q])
    return (9999, 9)


def _period_labels_from_dates(date_cols: list[str]) -> dict[str, str]:
    """
    Convierte columnas 'YYYY-MM-DD' en etiquetas normalizadas:
      - Dic (Q4) -> 'YYYYQ4'
      - Mar/Jun/Sep -> 'YYYYQn' (trimestres)
      - Otros meses -> 'YYYY'

    Q4 (diciembre) siempre produce 'YYYYQ4' para consistencia con otros trimestres.
    """
    mapping: dict[str, str] = {}
    for dc in date_cols:
        try:
            d = pd.to_datetime(dc, errors='raise')
        except Exception:
            # Si no es fecha válida, mantener tal cual
            mapping[dc] = dc
            continue

        q = _quarter_from_month(d.month)

        if q:
            # Todos los trimestres (Q1-Q4) usan formato YYYYQn
            mapping[dc] = f"{d.year}{q}"
        else:
            # Meses no fin de trimestre -> año
            mapping[dc] = str(d.year)
    return mapping


def normalize_date_column_headers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza las columnas de fechas YYYY-MM-DD a formato YYYYQX exactamente como xbrl_to_excel.py
    """
    if df.empty:
        return df
    
    # Obtener todas las columnas excepto 'Cuenta' 
    date_columns = [col for col in df.columns if col != 'Cuenta']
    
    # Convertir fechas a etiquetas normalizadas (2025Q2, 2025Q1, etc.)
    period_map = _period_labels_from_dates(date_columns)
    

    
    # Aplicar el renombrado
    df_renamed = df.rename(columns=period_map)
    
    # Ordenar las columnas por período (más reciente primero) - como en xbrl_to_excel.py
    cuenta_col = df_renamed[['Cuenta']]
    period_cols = [col for col in df_renamed.columns if col != 'Cuenta']
    
    # Mantener tanto años como trimestres en modo combinado, ordenar por año descendente
    combined_mode = os.getenv('X2E_COMBINED', '0') == '1'
    if combined_mode:
        # Ordenar por período descendente (más reciente primero)
        ordered_periods = sorted(period_cols, key=_period_sort_key, reverse=True)
    else:
        ordered_periods = period_cols
    
    # Reconstruir DataFrame con columnas ordenadas
    ordered_data = pd.concat([cuenta_col, df_renamed[ordered_periods]], axis=1)
    
    return ordered_data


def add_cash_beginning_period(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega fila 'Efectivo y equivalentes al efectivo al principio del periodo'
    antes de 'Efectivo y equivalentes al efectivo al final del periodo'.
    
    Los valores son el 'Efectivo al final del periodo' del período anterior.
    Solo agrega si no existe ya una cuenta de "al principio del periodo".
    """
    if df.empty:
        return df
    
    # Verificar si ya existe "Efectivo al principio del periodo" (ES/EN)
    principio_patterns = [
        'Efectivo y equivalentes al efectivo al principio del periodo',
        'Cash and cash equivalents at beginning of period',
        'Cash and cash equivalents at the beginning of the period',
    ]
    principio_regex = '|'.join([re.escape(p) for p in principio_patterns])
    efectivo_principio_mask = df['Cuenta'].astype(str).str.contains(
        principio_regex, na=False, case=False
    )
    
    if efectivo_principio_mask.any():
        # Ya existe - se recalculará y reposicionará justo arriba del '... al final ...'
        # 'Efectivo al principio' existe - recalculando
        pass
    
    # Buscar la fila de "Efectivo al final del periodo" (ES/EN)
    final_patterns = [
        'Efectivo y equivalentes al efectivo al final del periodo',
        'Cash and cash equivalents at end of period',
        'Cash and cash equivalents at the end of the period',
    ]
    final_regex = '|'.join([re.escape(p) for p in final_patterns])
    efectivo_final_mask = df['Cuenta'].astype(str).str.contains(
        final_regex, na=False, case=False
    )
    
    if not efectivo_final_mask.any():
        # No se encontró 'Efectivo al final del periodo'
        return df
    
    efectivo_final_row = df[efectivo_final_mask].iloc[0]
    efectivo_final_index = df[efectivo_final_mask].index[0]
    
    # Determinar si crear nueva fila o actualizar existente
    create_new_row = not efectivo_principio_mask.any()
    efectivo_principio_index = None
    
    if create_new_row:
        # Crear nueva fila de "Efectivo al principio del periodo"
        efectivo_principio_row = efectivo_final_row.copy()
        efectivo_principio_row['Cuenta'] = 'Efectivo y equivalentes al efectivo al principio del periodo'
        # Preservar valores manuales preexistentes (overrides) que ya hubieran
        # llegado a la fila final por algún path raro; sobreescribir solo lo
        # que vayamos a derivar abajo.
    else:
        # Usar la fila existente pero copiar la estructura de la final
        efectivo_principio_index = efectivo_principio_mask.idxmax()
        efectivo_principio_row = df.loc[efectivo_principio_index].copy()
        # Actualizando fila existente 'Efectivo al principio'
    # Snapshot de los valores que YA traía la fila 'al principio' (típicamente
    # vienen de manual_overrides.json). Los respetaremos abajo cuando el
    # cálculo derivado quedaría vacío.
    preexisting_principio = {}
    if efectivo_principio_index is not None:
        for col in df.columns:
            if col == 'Cuenta':
                continue
            v = df.at[efectivo_principio_index, col]
            if v is not None and not (isinstance(v, float) and pd.isna(v)) and str(v).strip() not in ('', 'nan'):
                preexisting_principio[col] = v

    # Obtener columnas de fechas (excluyendo 'Cuenta')
    date_columns = [col for col in df.columns if col != 'Cuenta']

    # Desplazar valores: inicio de período actual = final de período anterior
    if len(date_columns) > 1:
        # Procesar desde el primer período hasta el penúltimo
        for i in range(len(date_columns)):
            current_col = date_columns[i]
            if i == len(date_columns) - 1:
                # La última columna (período más antiguo) queda vacía,
                # SALVO que el usuario haya provisto un override.
                if current_col in preexisting_principio:
                    efectivo_principio_row[current_col] = preexisting_principio[current_col]
                else:
                    efectivo_principio_row[current_col] = pd.NA
            else:
                # Valor del principio del período actual = Valor del final del período siguiente
                prev_col = date_columns[i + 1]
                raw_value = efectivo_final_row[prev_col]
                
                # Convertir y limpiar el valor a numérico (consistente con xbrl_to_excel)
                if pd.notna(raw_value) and raw_value is not None:
                    try:
                        if isinstance(raw_value, str):
                            s = raw_value.replace('\xa0', ' ').strip()
                            s = s.replace('−', '-').replace('–', '-').replace('—', '-')
                            if s == '' or s == '-':
                                efectivo_principio_row[current_col] = pd.NA
                            else:
                                neg = False
                                if s.startswith('(') and s.endswith(')'):
                                    neg = True
                                    s = s[1:-1].strip()
                                if s.endswith('-') and not s.startswith('-'):
                                    neg = True
                                    s = s[:-1].strip()
                                s_clean = s.replace(',', '').replace(' ', '').replace('.', '')
                                s_clean = re.sub(r'(?<!^)[^0-9]', '', s_clean)
                                if s_clean == '':
                                    efectivo_principio_row[current_col] = pd.NA
                                else:
                                    if s.startswith('-') and not s_clean.startswith('-'):
                                        s_clean = '-' + s_clean
                                    val = float(s_clean)
                                    if neg:
                                        val = -val
                                    efectivo_principio_row[current_col] = val
                        else:
                            # Ya es numérico, usar directamente
                            efectivo_principio_row[current_col] = raw_value
                    except (ValueError, TypeError):
                        # Cálculo falló pero hay override del usuario: lo respetamos.
                        if current_col in preexisting_principio:
                            efectivo_principio_row[current_col] = preexisting_principio[current_col]
                        else:
                            efectivo_principio_row[current_col] = pd.NA
                else:
                    # No hay 'final' del período anterior. Si el usuario tiene
                    # override manual para este período, usarlo.
                    if current_col in preexisting_principio:
                        efectivo_principio_row[current_col] = preexisting_principio[current_col]
                    else:
                        efectivo_principio_row[current_col] = pd.NA
    
    # Reordenar para el flujo correcto:
    # 1. [Todos los flujos de operación, inversión, financiación]
    # 2. Efectivo y equivalentes al efectivo al principio del periodo
    # 3. Efectivo y equivalentes al efectivo al final del periodo ← ÚLTIMA LÍNEA
    
    # Eliminar cualquier fila existente de 'al principio' 
    df_wo_begin = df[~efectivo_principio_mask].copy()
    
    # Verificar que existe la fila de 'al final' en el DataFrame limpio
    efectivo_final_mask_clean = df_wo_begin['Cuenta'].astype(str).str.contains(final_regex, na=False, case=False)
    
    if not efectivo_final_mask_clean.any():
        # Error: No se encuentra 'Efectivo al final del periodo'
        return df
    
    # Extraer y remover la fila de 'al final' de su posición actual
    efectivo_final_idx = efectivo_final_mask_clean.idxmax()  # Usar idxmax() en lugar de index[0]
    efectivo_final_row_extracted = df_wo_begin.loc[efectivo_final_idx].copy()
    
    # 'Efectivo al final' encontrado
    
    # DataFrame sin 'al principio' ni 'al final'
    df_wo_both = df_wo_begin.drop(index=efectivo_final_idx).reset_index(drop=True)
    
    # Crear DataFrames para las dos líneas de efectivo
    try:
        principio_row_df = pd.DataFrame([efectivo_principio_row])
        final_row_df = pd.DataFrame([efectivo_final_row_extracted])
        
        # Preparando concatenación de componentes
        # df_wo_both preparado
        # principio_row_df preparado  
        # final_row_df preparado
        
        # Orden correcto: todo el contenido + al principio + al final (última línea)
        result_df = pd.concat([df_wo_both, principio_row_df, final_row_df], ignore_index=True)
        # Orden correcto aplicado
        
    except Exception as e:
        # Error en concatenación
        # Debug info:
        # df_wo_both shape disponible
        # efectivo_principio_row type registrado
        # efectivo_final_row_extracted type registrado
        return df

    return result_df


def propagate_ganancia_perdida_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    Propaga los valores de 'Ganancia (pérdida)' a todas sus apariciones en el estado de resultados.
    
    La cuenta 'Ganancia (pérdida)' puede aparecer múltiples veces:
    1. Como resultado principal (con valor)
    2. Como cuenta de agrupación (sin valor)
    
    Esta función encuentra la aparición con valores y los propaga a todas las demás.
    """
    if df.empty or 'Cuenta' not in df.columns:
        return df
    
    # Buscar todas las apariciones de "Ganancia (pérdida)"
    ganancia_perdida_patterns = [
        'Ganancia (pérdida)',
        'Profit (loss)',
        'Net income (loss)'
    ]
    
    ganancia_perdida_regex = '|'.join([f'^{re.escape(p)}$' for p in ganancia_perdida_patterns])
    ganancia_mask = df['Cuenta'].astype(str).str.contains(ganancia_perdida_regex, na=False, case=False)
    
    if not ganancia_mask.any():
        # No se encontraron apariciones de 'Ganancia (pérdida)'
        return df
    
    ganancia_rows = df[ganancia_mask].copy()
    # Apariciones de 'Ganancia (pérdida)' encontradas
    
    # Encontrar la fila que tiene valores (no vacía)
    date_columns = [col for col in df.columns if col != 'Cuenta']
    source_row = None
    source_idx = None
    
    for idx, row in ganancia_rows.iterrows():
        # Verificar si esta fila tiene al menos un valor no vacío
        has_values = False
        for col in date_columns:
            val = row[col]
            if val is not None and not pd.isna(val) and str(val).strip() not in ('', 'nan', '0'):
                has_values = True
                break
        
        if has_values:
            source_row = row
            source_idx = idx
            # Fila fuente encontrada con valores
            break
    
    if source_row is None:
        # No se encontró fila de 'Ganancia (pérdida)' con valores
        return df
    
    # Propagar valores desde la fila fuente a todas las demás apariciones
    result_df = df.copy()
    propagated_count = 0
    
    for idx, row in ganancia_rows.iterrows():
        if idx != source_idx:  # No propagar a sí misma
            # Copiar valores de la fila fuente
            for col in date_columns:
                source_val = source_row[col]
                current_val = row[col]
                
                # Solo propagar si la celda actual está vacía
                if (current_val is None or pd.isna(current_val) or str(current_val).strip() in ('', 'nan', '0')):
                    result_df.at[idx, col] = source_val
            
            propagated_count += 1
            # Valores propagados
    
    # Propagación de valores completada
    return result_df


def merge_accounts_fill_then_drop(df: pd.DataFrame, pairs: list[tuple[str, str]]) -> pd.DataFrame:
    """Para cada par (principal, secundaria):
    - Copia valores de la secundaria hacia la principal solo cuando la principal no tiene dato.
    - Elimina la fila de la secundaria.
    Empareja por igualdad de texto case-insensitive en la columna 'Cuenta'.
    """
    if df.empty or 'Cuenta' not in df.columns:
        return df
    out = df.copy()
    date_cols = [c for c in out.columns if c != 'Cuenta']
    # Índice auxiliar por nombre normalizado
    name_to_index = {str(n).strip().lower(): i for i, n in zip(out.index, out['Cuenta'])}
    rows_to_drop = []
    for principal, secundaria in pairs:
        p_key = principal.strip().lower()
        s_key = secundaria.strip().lower()
        if p_key in name_to_index and s_key in name_to_index:
            p_idx = name_to_index[p_key]
            s_idx = name_to_index[s_key]
            for col in date_cols:
                p_val = out.at[p_idx, col]
                s_val = out.at[s_idx, col]
                if (p_val is None) or pd.isna(p_val) or str(p_val).strip() in ('', 'nan'):
                    if s_val is not None and not pd.isna(s_val) and str(s_val).strip() not in ('', 'nan'):
                        out.at[p_idx, col] = s_val
            rows_to_drop.append(s_idx)
    if rows_to_drop:
        out = out.drop(index=rows_to_drop)
        out.reset_index(drop=True, inplace=True)
    return out


def filter_out_years(df: pd.DataFrame, years_to_remove: list[int]) -> pd.DataFrame:
    """Elimina columnas de períodos cuyos años estén en years_to_remove.

    Maneja etiquetas tipo 'YYYY', 'YYYYQn' y deja 'Cuenta' intacta.
    """
    if df.empty:
        return df
    years_set = set(int(y) for y in years_to_remove)
    keep_cols = ['Cuenta'] if 'Cuenta' in df.columns else []
    for col in df.columns:
        if col == 'Cuenta':
            continue
        s = str(col).strip().split('\n', 1)[0]
        m_q = re.match(r'^(\d{4})Q([1-4])$', s)
        m_y = re.match(r'^(\d{4})$', s)
        y_val = None
        if m_q:
            y_val = int(m_q.group(1))
        elif m_y:
            y_val = int(m_y.group(1))
        # Si no es parsable como año/quarter, conservar la columna
        if y_val is None or y_val not in years_set:
            keep_cols.append(col)
    removed = [c for c in df.columns if c not in keep_cols]
    if removed:
        # Eliminando columnas de años anteriores
        pass
    return df[keep_cols]


def normalize_date_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normaliza las columnas de fecha para ordenamiento correcto"""
    df_copy = df.copy()
    
    # Reordenar columnas: 'Cuenta' primero, luego fechas ordenadas
    if 'Cuenta' in df_copy.columns:
        cuenta_col = df_copy[['Cuenta']]
        date_cols = df_copy.drop('Cuenta', axis=1)
        
        # Ordenar columnas de fecha de manera inteligente
        date_col_names = list(date_cols.columns)
        
        try:
            # Intentar ordenar por año/trimestre si es formato YYYY o YYYYQX
            def sort_key(col_name):
                col_str = str(col_name).strip()
                # Formato YYYYQX
                match_q = re.match(r'^(\d{4})Q([1-4])$', col_str)
                if match_q:
                    return (int(match_q.group(1)), int(match_q.group(2)))
                # Formato YYYY
                match_y = re.match(r'^(\d{4})$', col_str) 
                if match_y:
                    return (int(match_y.group(1)), 0)  # Año tiene prioridad sobre trimestres
                # Otros formatos, al final
                return (9999, 9999)
            
            sorted_date_cols = sorted(date_col_names, key=sort_key)
            df_copy = pd.concat([cuenta_col, date_cols[sorted_date_cols]], axis=1)
            
        except Exception:
            # Si falla el ordenamiento, mantener orden original
            pass
    
    return df_copy


def apply_excel_formatting(workbook, worksheet, df: pd.DataFrame, sheet_name: str, 
                         entity_name: str, lang: str = 'es'):
    """Aplica el formateo exacto del xbrl_to_excel.py"""
    
    # Paleta corporativa y tipografía (copiado exacto de xbrl_to_excel.py)
    brand_primary = '#0F172A'   # Navy oscuro
    brand_secondary = '#1F2937' # Gris azulado oscuro
    brand_accent = '#2563EB'    # Azul acento sobrio
    brand_gray_100 = '#F7F7F7'
    brand_gray_150 = '#F0F0F0'
    base_font = 'Calibri'
    
    # Formatos (copiados exactos de xbrl_to_excel.py)
    title_format = workbook.add_format({
        'bold': True,
        'font_size': 16,
        'font_name': base_font,
        'font_color': '#FFFFFF',
        'bg_color': brand_primary,
        'align': 'center',
        'valign': 'vcenter'
    })
    
    subtitle_format = workbook.add_format({
        'font_size': 11,
        'font_name': base_font,
        'font_color': '#111827',
        'align': 'center',
        'valign': 'vcenter'
    })
    
    header_format = workbook.add_format({
        'bold': True,
        'font_size': 11,
        'font_name': base_font,
        'bg_color': brand_secondary,
        'font_color': '#FFFFFF',
        'border': 0,
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': True
    })
    
    number_format = workbook.add_format({
        'num_format': '#,##0',
        'align': 'right',
        'border': 0,
        'font_size': 10,
        'font_name': base_font
    })
    
    negative_number_format = workbook.add_format({
        'num_format': '#,##0_);[Red](#,##0)',
        'align': 'right',
        'border': 0,
        'font_size': 10,
        'font_name': base_font,
        'font_color': '#CC0000'
    })
    
    concept_format = workbook.add_format({
        'border': 0,
        'align': 'left',
        'valign': 'vcenter',
        'font_size': 10,
        'font_name': base_font,
        'bg_color': brand_gray_100
    })
    
    concept_format_alt = workbook.add_format({
        'border': 0,
        'align': 'left',
        'valign': 'vcenter',
        'font_size': 10,
        'font_name': base_font,
        'bg_color': brand_gray_150
    })
    
    category_format = workbook.add_format({
        'bold': True,
        'font_size': 11,
        'font_name': base_font,
        'bg_color': brand_primary,
        'font_color': '#FFFFFF',
        'align': 'left',
        'valign': 'vcenter'
    })
    
    empty_category_format = workbook.add_format({
        'bg_color': brand_primary,
        'align': 'center'
    })
    
    subcategory_format = workbook.add_format({
        'border': 0,
        'align': 'left',
        'valign': 'vcenter',
        'indent': 1,
        'font_size': 10,
        'font_name': base_font,
        'bg_color': '#FAFAFA'
    })
    
    subcategory_format_alt = workbook.add_format({
        'border': 0,
        'align': 'left',
        'valign': 'vcenter',
        'indent': 1,
        'font_size': 10,
        'font_name': base_font,
        'bg_color': '#F5F5F5'
    })
    
    total_format = workbook.add_format({
        'bold': True,
        'font_size': 10,
        'font_name': base_font,
        'bg_color': '#E0E7FF',
        'align': 'left',
        'valign': 'vcenter'
    })
    
    total_number_format = workbook.add_format({
        'bold': True,
        'num_format': '#,##0',
        'align': 'right',
        'font_size': 10,
        'font_name': base_font,
        'bg_color': '#E0E7FF'
    })
    
    # Configuración de la hoja
    worksheet.set_tab_color(brand_accent)
    worksheet.hide_gridlines(2)
    worksheet.set_landscape()
    worksheet.set_paper(9)  # A4
    worksheet.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
    worksheet.set_zoom(110)
    worksheet.set_default_row(15)
    
    # Configurar anchos de columnas
    for i, col in enumerate(df.columns):
        if i == 0:
            max_len = min(max(14, df[col].astype(str).str.len().max() + 5), 80)
            worksheet.set_column(i, i, max_len)
        else:
            worksheet.set_column(i, i, 18 if i > 0 else 14)
    
    # Título y subtítulo
    ncols = len(df.columns)
    header_row = 2
    title_text = f"{sheet_name} — {entity_name}"
    
    # Construir subtítulo con unidad y períodos
    date_cols = [str(c) for c in df.columns[1:]]
    unit_header_note = 'Miles CLP' if lang == 'es' else 'Thousands CLP'
    
    if lang == 'es':
        periods_label = 'Períodos'
        unit_label = 'Unidad'
    else:
        periods_label = 'Periods'
        unit_label = 'Unit'
    
    if date_cols:
        try:
            years = sorted({str(c)[:4] for c in date_cols})
            periods_text = f"{years[0]} - {years[-1]}" if years else '-'
        except Exception:
            periods_text = ', '.join(date_cols[:4])
    else:
        periods_text = '-'
    
    subtitle_text = f"{unit_label}: {unit_header_note}    •    {periods_label}: {periods_text}"
    
    # Escribir título y subtítulo
    worksheet.merge_range(0, 0, 0, ncols - 1, title_text, title_format)
    worksheet.merge_range(1, 0, 1, ncols - 1, subtitle_text, subtitle_format)
    worksheet.set_row(0, 26)
    worksheet.set_row(1, 18)
    
    # Escribir encabezados
    for col_num, value in enumerate(df.columns.values):
        header_text = value
        worksheet.write(header_row, col_num, header_text, header_format)
    worksheet.set_row(header_row, 22)
    
    # ✨ AGRUPACIÓN AVANZADA POR AÑOS (modo combinado) ✨
    if os.getenv('X2E_COMBINED', '0') == '1':
        try:
            import re as _re
            year_to_qcols: dict[str, list[int]] = {}
            year_col_index: dict[str, int] = {}
            
            # Mapear columnas por año y trimestre con detección mejorada
            for c_idx, lbl in enumerate(df.columns):
                if c_idx == 0:
                    continue  # 'Cuenta'
                
                s = str(lbl).strip().split("\n", 1)[0]
                m_q = _re.match(r"^(\d{4})Q([1-4])$", s)
                m_y = _re.match(r"^(\d{4})$", s)
                if m_q:
                    y = m_q.group(1)
                    year_to_qcols.setdefault(y, []).append(c_idx)

                elif m_y:
                    year_col_index[m_y.group(1)] = c_idx
           
            

            latest_year = None
            try:
                latest_year = max(int(y) for y in year_to_qcols.keys()) if year_to_qcols else None
                # Año más reciente identificado
            except Exception:
                latest_year = None
            
            def _q_sort_key(idx: int) -> tuple[int, int]:
                s2 = str(df.columns[idx]).strip()
                mm = _re.match(r"^(\d{4})Q([1-4])$", s2)
                return (int(mm.group(1)), int(mm.group(2))) if mm else (9999, 9)
            
            groups_applied = 0
            for y, cols in year_to_qcols.items():
                if not cols:
                    continue
                cols_sorted = sorted(cols, key=_q_sort_key)
                is_latest_year = (latest_year is not None and int(y) == int(latest_year))
                
                start_ci = min(cols_sorted)
                end_ci = max(cols_sorted)
                
                # ✨ Crear agrupación funcional con xlsxwriter (método alternativo)
                # Usar set_column con level para crear agrupaciones reales
                worksheet.set_column(start_ci, end_ci, None, None, {
                    'level': 1,                      # Nivel de agrupación (1-7 soportado)
                    'hidden': (not is_latest_year),  # Ocultar grupos antiguos inicialmente
                    'collapsed': (not is_latest_year) # Colapsar grupos antiguos inicialmente
                })
                
                
                # Usar la columna del año como resumen (a la izquierda del bloque) - EXACTO como xbrl_to_excel.py
                sum_col = year_col_index.get(y)
                if sum_col is not None:
                    worksheet.set_column(sum_col, sum_col, None, None, {
                        'collapsed': (not is_latest_year)
                    })
                
                groups_applied += 1
            
            # ✨ Habilitar outline/agrupación visual - versión simplificada y funcional
            try:
                # Configuración mínima que funciona bien con xlsxwriter
                worksheet.outline_settings(visible=True, symbols_below=False, symbols_right=False)
                # Outline funcional habilitado
                # Agrupación por años configurada
                # Botones +/- disponibles para expandir/colapsar
            except Exception as e:
                # Error configurando outline
                pass
                
        except Exception as e:
            # Error en agrupación por años
            pass
    else:
        # Modo combinado deshabilitado
        pass
    
    # Pie de página
    ts_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    worksheet.repeat_rows(0, header_row)
    worksheet.set_footer(f"&L{sheet_name}  |  {entity_name}&RGenerado: {ts_str}   Página &P de &N")
    
    # ✨ Escribir datos con alternancia y formateo - PRESERVAR ORDEN DEL CSV
    data_start_row = header_row + 1
    
    # Mantener el orden jerárquico exacto del CSV (SIN reordenar por índice)
    # El CSV ya viene con el ordenamiento jerárquico correcto de generate_primary_roles_csv.py
    
    for r_index, (original_index, row) in enumerate(df.iterrows()):
        row_num = data_start_row + r_index
        cuenta = str(row['Cuenta'])
        
        # Alternancia
        is_alternate = (r_index % 2 == 1)
        
        # Identificar tipo de cuenta para formateo (lógica exacta de xbrl_to_excel.py)
        cuentas_total_es = [
            'Ganancia bruta',
            'Ganancias (pérdidas) de actividades operacionales',
            'Ganancia (pérdida), antes de impuestos',
            'Ganancia (pérdida)',
            'Flujos de efectivo netos procedentes de (utilizados en) operaciones',
            'Flujos de efectivo netos procedentes de (utilizados en) actividades de operación',
            'Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión',
            'Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación',
            'Efectivo y equivalentes al efectivo al principio del periodo',
            'Efectivo y equivalentes al efectivo al final del periodo'
        ]
        cuentas_total_en = [
            'Gross profit',
            'Profit (loss) from operating activities',
            'Profit (loss)',
            'Net cash flows from (used in) operations',
            'Net cash flows from (used in) investing activities'
        ]
        cuentas_total_ifrs = [
            'ifrs-full:CashAndCashEquivalentsIfDifferentFromStatementOfFinancialPosition'
        ]
        totales = ['total', 'suma', 'subtotal']
        
        cuenta_lower = cuenta.lower()
        is_category = (cuenta_lower.startswith('[') and ']' in cuenta_lower)
        is_sinopsis_cat = any(tag in cuenta_lower for tag in ('[sinopsis]', '[abstract]', '[resumen]'))
        if is_sinopsis_cat:
            is_category = True
        is_total = (
            any(word in cuenta_lower for word in totales)
            or cuenta.strip() in cuentas_total_es
            or cuenta.strip() in cuentas_total_en
            or cuenta.strip() in cuentas_total_ifrs
        )
        
        if is_category:
            concept_cell_format = category_format
        elif is_total:
            concept_cell_format = total_format
        elif is_alternate:
            concept_cell_format = subcategory_format_alt
        else:
            concept_cell_format = subcategory_format
        
        worksheet.write(row_num, 0, cuenta, concept_cell_format)
        
        # Helper para parsear números (copiado exacto de xbrl_to_excel.py)
        def _parse_numeric_thousands(v) -> float | None:
            if v is None:
                return None
            # If already numeric
            if isinstance(v, (int, float)) and not pd.isna(v):
                try:
                    return float(v) / 1000.0
                except Exception:
                    return None
            try:
                s = str(v)
            except Exception:
                return None
            # Normalize whitespace and dashes
            s = s.replace('\xa0', ' ').strip()
            # Normalize unicode minus/dashes to '-'
            s = s.replace('−', '-').replace('–', '-').replace('—', '-')
            if s == '' or s == '-':
                return None
            neg = False
            # Parentheses negative
            if s.startswith('(') and s.endswith(')'):
                neg = True
                s = s[1:-1].strip()
            # Trailing minus
            if s.endswith('-') and not s.startswith('-'):
                neg = True
                s = s[:-1].strip()
            # Remove thousands separators and spaces
            s_clean = s.replace(',', '').replace(' ', '').replace('.', '')
            # Remove any stray non-digit except possible leading '-'
            s_clean = re.sub(r'(?<!^)[^0-9]', '', s_clean)
            if s_clean == '':
                return None
            try:
                # Preserve leading minus if present
                if s.startswith('-') and not s_clean.startswith('-'):
                    s_clean = '-' + s_clean
                val = float(s_clean)
            except Exception:
                return None
            if neg:
                val = -val
            return val / 1000.0
        
        # Escribir valores numéricos
        for col_num in range(1, len(df.columns)):
            value = row.iloc[col_num]
            
            if is_category:
                worksheet.write(row_num, col_num, "", empty_category_format)
            else:
                num_thousands = _parse_numeric_thousands(value)
                if num_thousands is not None:
                    if is_total:
                        cell_format = total_number_format
                    elif num_thousands < 0:
                        cell_format = negative_number_format
                    else:
                        cell_format = number_format
                    worksheet.write(row_num, col_num, num_thousands, cell_format)
                else:
                    empty_format = concept_format_alt if is_alternate else concept_format
                    worksheet.write(row_num, col_num, "", empty_format)


def extract_company_name(company_dir: Path) -> str:
    """Extrae el nombre de la empresa del directorio"""
    try:
        raw = company_dir.name  # ej. 90227000-0_VIÑA_CONCHA_Y_TORO_SA
        name_part = raw.split('_', 1)[1] if '_' in raw else raw
        human = name_part.replace('_', ' ').strip()
        return human or company_dir.name
    except Exception:
        return company_dir.name


def generate_excel_from_primary_csv(company_dir: Path, lang: str = 'es', 
                                  output_xlsx: Path | None = None) -> Path:
    """
    Genera archivo Excel directamente desde primary_roles CSV
    
    Args:
        company_dir: Directorio de la empresa (contiene out_consolidated_*)
        lang: Idioma ('es' o 'en')
        output_xlsx: Ruta de salida (opcional, se auto-genera si no se especifica)
    
    Returns:
        Path del archivo Excel generado
    """
    
    # Generando Excel desde primary_roles CSV
    # Procesando empresa
    # Idioma configurado
    
    # Habilitar modo combinado y configuraciones como en xbrl_to_excel.py
    os.environ['X2E_COMBINED'] = '1'
    os.environ['X2E_KEEP_ALL_DATES'] = '1'
    os.environ['X2E_DECEMBER_AS_YEAR'] = '0'  # Usar 2025Q4 en lugar de 2025 para diciembre
    # Modo combinado habilitado
    # Configuración de trimestres
    
    # Extraer RUT del nombre del directorio
    # Formato esperado: RUT_NOMBRE_EMPRESA (ej: 91705000-7_QUIÑENCO_SA)
    company_rut = None
    try:
        dir_name = company_dir.name
        if '_' in dir_name:
            company_rut = dir_name.split('_')[0]
            # RUT extraído del directorio
    except Exception:
        company_rut = None
    
    # 1. Encontrar archivos primary_roles CSV
    primary_files = find_primary_roles_files(company_dir, lang)
    if not primary_files:
        raise ValueError(f"No se encontraron archivos primary_roles_{lang}.csv en {company_dir}")
    
    # 2. Cargar y combinar datos
    combined_df = load_and_combine_primary_roles(primary_files)
    
    # 3. Separar por roles (3 hojas) - pasar el RUT para usar estructura específica
    balance_df, income_df, cashflow_df = split_by_role(combined_df, company_rut)
    
    # 4. Normalizar encabezados de fechas YYYY-MM-DD a formato YYYYQX (como xbrl_to_excel.py)
    # Normalizando encabezados de fecha
    
    if not balance_df.empty:
        # Balance Sheet normalizando
        balance_df = normalize_date_column_headers(balance_df)
    
    if not income_df.empty:
        # Income Statement normalizando
        income_df = normalize_date_column_headers(income_df)
    
    if not cashflow_df.empty:
        # Cash Flow normalizando
        cashflow_df = normalize_date_column_headers(cashflow_df)
    
    # 4.5. Eliminar años 2012 y 2013 de todas las hojas
    # Eliminando años 2012 y 2013
    if not balance_df.empty:
        balance_df = filter_out_years(balance_df, [2012, 2013])
    if not income_df.empty:
        income_df = filter_out_years(income_df, [2012, 2013])
    if not cashflow_df.empty:
        cashflow_df = filter_out_years(cashflow_df, [2012, 2013])

    # 5. Aplicar cálculos automáticos avanzados como en xbrl_to_excel.py
    # Aplicando cálculos automáticos avanzados

    # Agregar "Efectivo al principio del periodo" automáticamente al Cash Flow
    if not cashflow_df.empty:
        # Calculando 'Efectivo al principio del periodo'
        cashflow_df = add_cash_beginning_period(cashflow_df)
        # Cash Flow actualizado

    # 5.1 Propagar valores de "Ganancia (pérdida)" a todas sus apariciones
    if not income_df.empty:
        # Propagando valores de 'Ganancia (pérdida)'
        income_df = propagate_ganancia_perdida_values(income_df)
    
    # 5.2 Fusionar cuentas secundarias dentro de las principales y eliminar duplicadas
    # Income Statement: "Resultados por unidades de reajuste" <- "Diferencias de cambio"
    # Balance: "Capital emitido y pagado" <- "Capital emitido"
    merge_pairs_income_es = [
        ("Resultados por unidades de reajuste", "Diferencias de cambio"),    ]
   
    merge_pairs_balance_es = [
        ("Capital emitido y pagado", "Capital emitido"),
    ]
    merge_pairs_cashflow_es = [
        ("Flujos de efectivo netos procedentes de (utilizados en) operaciones", "Flujos de efectivo netos procedentes (utilizados en) operaciones"),
        ("Flujos de efectivo netos procedentes de (utilizados en) operaciones", "Flujos de efectivo netos procedentes de (utilizados en) la operación"),
        ("Pagos de pasivos por arrendamientos", "Pagos de pasivos por arrendamientos financieros"),
        ("Pagos de préstamos de entidades relacionadas", "Pagos de préstamos a entidades relacionadas"),
    ]
    # EN equivalents (best-effort common labels)
    merge_pairs_income_en = [
        ("Result from indexation units", "Foreign exchange differences"),
    ]
    merge_pairs_balance_en = [
        ("Issued and paid-in capital", "Issued capital"),
    ]
    merge_pairs_cashflow_en = [
        ("Net cash flows from (used in) operating activities", "Net cash flows from (used in) operations"),
        ("Payments of lease liabilities", "Payments of finance lease liabilities"),
        ("Payments of loans to related parties", "Payments of loans from related parties"),
    ]

    if lang == 'es':
        if not income_df.empty:
            # Fusionando cuentas (ER): secundarias → principales
            income_df = merge_accounts_fill_then_drop(income_df, merge_pairs_income_es)
        if not balance_df.empty:
            # Fusionando cuentas (Balance): secundarias → principales
            balance_df = merge_accounts_fill_then_drop(balance_df, merge_pairs_balance_es)
        if not cashflow_df.empty:
            # Fusionando cuentas (Cash Flow): secundarias → principales
            cashflow_df = merge_accounts_fill_then_drop(cashflow_df, merge_pairs_cashflow_es)
    else:
        if not income_df.empty:
            # Merging accounts (IS): secondary → primary
            income_df = merge_accounts_fill_then_drop(income_df, merge_pairs_income_en)
        if not balance_df.empty:
            # Merging accounts (Balance): secondary → primary
            balance_df = merge_accounts_fill_then_drop(balance_df, merge_pairs_balance_en)
        if not cashflow_df.empty:
            # Merging accounts (Cash Flow): secondary → primary
            cashflow_df = merge_accounts_fill_then_drop(cashflow_df, merge_pairs_cashflow_en)
    # 5. Generar nombre de archivo si no se especifica
    if output_xlsx is None:
        rut_prefix = company_dir.name.split('_', 1)[0]
        
        # Extraer rango de fechas dinámicamente desde los datos
        date_range = "consolidado"  # Default
        try:
            # Buscar columnas de fecha en los datos combinados
            import re
            all_date_cols = []
            for df in [balance_df, income_df, cashflow_df]:
                if not df.empty:
                    date_cols = [col for col in df.columns if re.match(r'^\d{4}', str(col))]
                    all_date_cols.extend(date_cols)
            
            if all_date_cols:
                # Extraer años únicos
                years = set()
                for col in all_date_cols:
                    year_match = re.match(r'^(\d{4})', str(col))
                    if year_match:
                        years.add(int(year_match.group(1)))
                
                if len(years) > 1:
                    min_year = min(years)
                    max_year = max(years)
                    date_range = f"{max_year}-{min_year}"
                elif len(years) == 1:
                    date_range = str(list(years)[0])
                    
                # Rango extraído automáticamente
                pass
        except Exception as e:
            # No se pudo extraer rango de fechas
            pass
            
        output_xlsx = company_dir / f"estados_{rut_prefix}_{date_range}_{lang}_from_primary.xlsx"
    
    # 6. Crear Excel con xlsxwriter
    try:
        excel_writer = pd.ExcelWriter(output_xlsx, engine="xlsxwriter")
    except ImportError:
        # xlsxwriter no disponible, utilizando openpyxl
        excel_writer = pd.ExcelWriter(output_xlsx, engine="openpyxl")
    
    entity_name = extract_company_name(company_dir)
    
    # Nombres de las hojas (compatibles con analisis_excel)
    if lang == 'es':
        sheet_names = [
            "Balance General",              # Compatible con analisis_excel
            "Estado de Resultados",         # Compatible con analisis_excel  
            "Flujo Efectivo"                # Compatible con analisis_excel (sin "de")
        ]
    else:
        sheet_names = [
            "Balance Sheet",
            "Income Statement", 
            "Cash Flow"                     # Simplificado para compatibilidad
        ]
    
    hojas = [balance_df, income_df, cashflow_df]
    
    with excel_writer as writer:
        workbook = writer.book
        
        # Propiedades del documento
        try:
            if hasattr(workbook, 'set_properties'):
                workbook.set_properties({
                    'title': f"Estados financieros {company_dir.name.split('_', 1)[0]}",
                    'subject': 'Reporte financiero generado desde primary_roles CSV',
                    'category': 'Financial Statements',
                    'comments': f'Generado automáticamente desde primary_roles_{lang}.csv'
                })
            else:
                # openpyxl method
                workbook.properties.title = f"Estados financieros {company_dir.name.split('_', 1)[0]}"
                workbook.properties.subject = 'Reporte financiero generado desde primary_roles CSV'
                workbook.properties.category = 'Financial Statements'
        except Exception:
            pass
        
        # Generando hojas Excel
        
        for df, sheet_name in zip(hojas, sheet_names):
            
            # Crear hoja de trabajo
            worksheet = workbook.add_worksheet(sheet_name)
            
            # Aplicar formateo exacto
            apply_excel_formatting(workbook, worksheet, df, sheet_name, entity_name, lang)
    
    # Excel generado
    
    # Si no se especificó ruta de salida personalizada, copiar también a Products/Total
    # para que el análisis lo encuentre automáticamente
    if output_xlsx.parent == company_dir:  # Se generó en directorio de empresa (modo automático)
        try:
            # Products/Total siempre vive junto a este script (cmf_extract/Products/Total),
            # no donde corra el usuario ni en el nombre histórico 'CMF_extract'.
            cmf_extract_dir = Path(__file__).resolve().parent
            repo_root = cmf_extract_dir
            products_total = repo_root / "Products" / "Total"
            products_total.mkdir(parents=True, exist_ok=True)
            
            # Debug copia: preparando directorios
            
            # Crear copia en Products/Total con el nombre estándar (sin _from_primary)
            products_copy = products_total / f"estados_{rut_prefix}_{date_range}_{lang}.xlsx"
            
            # Eliminar versiones previas
            for old_file in products_total.glob(f"estados_{rut_prefix}_*"):
                try:
                    old_file.unlink()
                    # Archivo previo eliminado
                except Exception:
                    pass
            
            import shutil
            shutil.copy2(output_xlsx, products_copy)
            # Copia creada para análisis
            
        except Exception as e:
            import traceback
            # No se pudo copiar a Products/Total
            # Debug info:
            # output_xlsx registrado
            # company_dir registrado
            # output_xlsx.parent registrado
            # repo_root calculado
            traceback.print_exc()
    
    return output_xlsx


def main():
    """Función principal del CLI"""
    if len(sys.argv) < 3:
        print("Uso: python primary_csv_to_excel.py <company_dir> <lang> [output_xlsx]")
        print("")
        print("Ejemplos:")
        print("  python primary_csv_to_excel.py data/XBRL/Total/90227000-0_VIÑA_CONCHA_Y_TORO_SA es")
        print("  python primary_csv_to_excel.py data/XBRL/Total/76455830-8_WATTS_SA en /tmp/watts_en.xlsx")
        return 1
    
    company_dir = Path(sys.argv[1])
    lang = sys.argv[2]
    output_xlsx = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    
    if not company_dir.exists():
        print(f"❌ Error: El directorio {company_dir} no existe")
        return 1
    
    if lang not in ['es', 'en']:
        print(f"❌ Error: El idioma debe ser 'es' o 'en', no '{lang}'")
        return 1
    
    try:
        result_path = generate_excel_from_primary_csv(company_dir, lang, output_xlsx)
        # Excel generado exitosamente
        print(f"{result_path}")
        return 0
    except Exception as e:
        print(f"Error generando Excel: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())