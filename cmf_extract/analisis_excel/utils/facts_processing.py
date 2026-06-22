"""
Módulo de procesamiento de facts EXACTO como generate_primary_roles_csv.py
Incluye:
1. Carga de facts consolidados con fallback a agregación en memoria  
2. Filtrado y validación de labels (incluyendo [sinopsis])
3. Deduplicación por contexto
4. Conservación de cuentas [sinopsis] sin valores
5. Ordenamiento perfecto basado en JSON

Usado por generate_primary_roles_csv.py, batch_xbrl_to_excel.py y xbrl_to_excel.py
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import pandas as pd

from .json_ordering import (
    load_json_structure, 
    get_synopsis_accounts_from_json,
    get_json_hierarchical_position
)


def load_consolidated_facts(company_dir: Path, lang: str = 'es', enable_log: bool = False) -> Optional[pd.DataFrame]:
    """
    Carga facts consolidados EXACTAMENTE como generate_primary_roles_csv.py
    
    1. Busca facts_*_es.csv en out_consolidated
    2. Si no existe, usa _aggregate_facts_for_company como fallback
    """
    # Buscar directorio out_consolidated
    ocands = [d for d in company_dir.iterdir() 
              if d.is_dir() and d.name.startswith('out_consolidated')]
    if not ocands:
        if enable_log:
            # No hay out_consolidated en company_dir
            pass
        return None
    out_dir = ocands[0]

    # Buscar facts consolidados en out_consolidated (facts_*_es.csv)  
    facts_files = sorted(out_dir.glob(f'facts_*_{lang}.csv'))
    if not facts_files:
        # Fallback: construir en memoria con _aggregate_facts_for_company
        if enable_log:
            # No hay facts CSV, usando agregación en memoria
            pass
        try:
            # Import batch module for aggregation
            import sys
            sys.path.append(str(Path(__file__).parent.parent.parent))
            import batch_xbrl_to_excel as bmod
            
            ds_all = [d for d in bmod.find_datasets(company_dir) if getattr(d, 'company_dir', None) == company_dir]
            if not ds_all:
                return None
            df_facts = bmod._aggregate_facts_for_company(ds_all, lang, company_dir.parent.parent.parent)
        except Exception as e:
            if enable_log:
                # Agregación falló
                pass
            return None
    else:
        df_facts = pd.read_csv(facts_files[0], engine='python')

    if df_facts is None or df_facts.empty:
        if enable_log:
            # Facts consolidados vacíos
            pass
        return None

    return df_facts


def process_facts_data_for_consolidated(df_facts: pd.DataFrame, company_dir: Path, lang: str = 'es', 
                                       enable_log: bool = False) -> Optional[pd.DataFrame]:
    """
    Procesa facts data para CONSOLIDADO (incluye TODOS los roles - notas, etc)
    
    Solo aplica:
    1. Identificación de columnas de fecha puras
    2. Validación básica de labels
    3. Deduplicación por contexto
    NO filtra roles - debe mantener TODOS para el facts consolidado completo
    """
    # Identificar columnas de fecha puras YYYY-MM-DD
    date_cols = [c for c in df_facts.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]
    if not date_cols:
        if enable_log:
            # Sin columnas de fecha puras en consolidado
            pass
        return None

    # NO filtrar roles - mantener TODOS (incluye notas y otros roles)
    if 'RoleCode' not in df_facts.columns:
        if enable_log:
            # Facts consolidado sin RoleCode
            pass
        return None
    df = df_facts.copy()  # Mantener TODOS los roles

    # Validación básica de labels (sin filtrado agresivo)
    def _is_valid_basic_label(s: str) -> bool:
        if not s:
            return False
        l = s.strip().lower()
        if l in ('nan','none'):
            return False
        if '[bloque de texto]' in l:
            return False
        return True

    df['Label'] = df['Label'].astype(str)
    df = df[df['Label'].map(_is_valid_basic_label)].copy()

    # Deduplicación básica por contexto
    def _is_num(x) -> bool:
        try:
            if x is None:
                return False
            if isinstance(x, str):
                s = x.strip()
                if s == '' or s == '-':
                    return False
                s2 = s.replace('.', '').replace(',', '')
                float(s2)
                return True
            float(x)
            return True
        except Exception:
            return False

    # Conservar solo columnas relevantes
    df = df[[c for c in df.columns if c in ('LabelKeyId','LabelKeyIdExt','RoleCode','SectionKey','Label') or c in date_cols]]
    
    # Deduplicación por contexto
    df['_num_count'] = df[date_cols].apply(lambda r: sum(_is_num(r[c]) for c in date_cols), axis=1)
    if len(df):
        try:
            keep_idx = df.groupby(['RoleCode','Label','SectionKey'], dropna=False)['_num_count'].idxmax()
            df = df.loc[keep_idx].copy()
        except Exception:
            df = df.sort_values('_num_count', ascending=False).drop_duplicates(['RoleCode','Label','SectionKey'], keep='first').copy()
    df.drop(columns=['_num_count'], inplace=True, errors='ignore')

    if enable_log:
        # Facts consolidado procesado (todos los roles)
        pass
    
    return df


def process_facts_data_for_excel(df_facts: pd.DataFrame, company_dir: Path, lang: str = 'es', 
                                enable_log: bool = False) -> Optional[pd.DataFrame]:
    """
    Procesa facts data para EXCEL (solo roles principales) EXACTAMENTE como generate_primary_roles_csv.py
    
    Incluye:
    1. Identificación de columnas de fecha puras
    2. Filtrado de roles principales (210000, 310000, 510000)
    3. Carga de estructura JSON
    4. Validación de labels (conservando [sinopsis])
    5. Filtrado de filas sin datos (conservando [sinopsis] del JSON)
    6. Deduplicación por contexto
    7. Ordenamiento perfecto basado en JSON
    """
    # Identificar columnas de fecha puras YYYY-MM-DD
    date_cols = [c for c in df_facts.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]
    if not date_cols:
        if enable_log:
            # Sin columnas de fecha puras en consolidado
            pass
        return None

    # Filtrar solo roles principales PARA EXCEL
    if 'RoleCode' not in df_facts.columns:
        if enable_log:
            # Facts consolidado sin RoleCode
            pass
        return None
    df = df_facts[df_facts['RoleCode'].astype(str).isin(['210000','310000','510000'])].copy()

    # Cargar estructura JSON
    struct_by_role = load_json_structure(company_dir, lang)
    
    # Determinar qué cuentas [sinopsis] incluir
    json_synopsis_accounts = get_synopsis_accounts_from_json(struct_by_role)
    
    if enable_log:
        # Cuentas [sinopsis] definidas en JSON
        pass
    
    def _is_json_synopsis(row) -> bool:
        """Check if this row is a [sinopsis] account defined in the JSON structure"""
        role_code = str(row.get('RoleCode', ''))
        label = str(row.get('Label', '')).strip()
        return (role_code, label) in json_synopsis_accounts

    # Limpiar rows inválidos/narrativas pero MANTENER [sinopsis] según estructura JSON
    def _is_valid_label(s: str) -> bool:
        if not s:
            return False
        l = s.strip().lower()
        if l in ('nan','none','no hay informacion','no hay información adicional','no hay informacion adicional'):
            return False
        if '[bloque de texto]' in l:
            return False
        if re.match(r'^\s*\[(\d{6})\]', s):
            return False
        # NO filtrar [sinopsis] - las necesitamos según el JSON
        return True

    df['Label'] = df['Label'].astype(str)
    # Filtrar labels inválidos pero conservar [sinopsis] que están en la estructura JSON
    def _is_valid_or_json_synopsis(row) -> bool:
        label = str(row.get('Label', ''))
        if _is_valid_label(label):
            return True
        # Si no es válido normalmente, verificar si es [sinopsis] del JSON
        return _is_json_synopsis(row)
    
    df = df[df.apply(_is_valid_or_json_synopsis, axis=1)].copy()

    # Conservar filas con valores numéricos O que sean [sinopsis] definidas en JSON
    def _row_has_numeric(row) -> bool:
        for c in date_cols:
            v = row.get(c)
            try:
                if v is None:
                    continue
                if isinstance(v, str) and v.strip() == '':
                    continue
                f = float(str(v).replace( ',',''))
                return True
            except Exception:
                continue
        return False

    df = df[[c for c in df.columns if c in ('LabelKeyId','LabelKeyIdExt','RoleCode','SectionKey','Label') or c in date_cols]]
    # Incluir filas con valores numéricos O [sinopsis] definidas en JSON
    df = df[df.apply(lambda r: _row_has_numeric(r) or _is_json_synopsis(r), axis=1)].copy()

    # Deduplicación por contexto: si hay múltiples filas con el mismo
    # (RoleCode, Label, SectionKey), conservar la que tenga más valores numéricos
    def _is_num(x) -> bool:
        try:
            if x is None:
                return False
            if isinstance(x, str):
                s = x.strip()
                if s == '' or s == '-':
                    return False
                # remover separadores comunes de miles
                s2 = s.replace('.', '').replace(',', '')
                float(s2)
                return True
            float(x)
            return True
        except Exception:
            return False

    df['_num_count'] = df[date_cols].apply(lambda r: sum(_is_num(r[c]) for c in date_cols), axis=1)
    if len(df):
        try:
            keep_idx = df.groupby(['RoleCode','Label','SectionKey'], dropna=False)['_num_count'].idxmax()
            df = df.loc[keep_idx].copy()
        except Exception:
            # en caso de falla, al menos eliminar duplicados manteniendo la primera
            df = df.sort_values('_num_count', ascending=False).drop_duplicates(['RoleCode','Label','SectionKey'], keep='first').copy()
    df.drop(columns=['_num_count'], inplace=True, errors='ignore')

    # Aplicar ordenamiento perfecto basado en JSON
    if struct_by_role:
        # Generar ordenamiento jerárquico considerando contexto completo
        df['__json_ord'] = df.apply(lambda r: get_json_hierarchical_position(
            str(r['RoleCode']), 
            str(r['Label']), 
            str(r.get('SectionKey', '')),
            str(r.get('LabelKeyIdExt', '')),
            struct_by_role
        ), axis=1)
        
        # Ordenamiento 100% basado en estructura JSON
        df['__role_ord'] = df['RoleCode'].astype(str).map({'210000':1,'310000':2,'510000':3}).fillna(9).astype(int)
        
        # Ordenación jerárquica completa
        def _create_hierarchical_sort_key(row):
            role_ord = row['__role_ord']
            json_ord = row['__json_ord']
            
            # Usar la tupla jerárquica completa
            if isinstance(json_ord, tuple) and len(json_ord) >= 8:
                super_ord, main_ord, sub_ord, is_synopsis, synopsis_depth, synopsis_hash, duplicate_suffix, json_pos = json_ord[:8]
                return (role_ord, super_ord, main_ord, sub_ord, is_synopsis, synopsis_depth, synopsis_hash, duplicate_suffix, json_pos)
            
            # Fallback para cuentas sin mapeo JSON
            return (role_ord, 999, 0, 0, 1, 0, 0, 0, 999999)
        
        # Aplicar ordenamiento jerárquico
        sort_keys = df.apply(_create_hierarchical_sort_key, axis=1)
        df['__sort_key'] = sort_keys
        df = df.sort_values('__sort_key', kind='stable')
        df.drop(columns=['__json_ord', '__sort_key'], inplace=True)
    else:
        # Sin estructura JSON, ordenar por RoleCode, SectionKey, Label
        df = df.sort_values(['RoleCode','SectionKey','Label'], kind='stable')
    
    df.drop(columns=['__role_ord'], inplace=True)

    if enable_log:
        # Procesamiento completo
        pass
    
    return df


def process_facts_exactly_like_primary_csv(company_dir: Path, lang: str = 'es', 
                                          enable_log: bool = False) -> Optional[pd.DataFrame]:
    """
    Procesa facts EXACTAMENTE como generate_primary_roles_csv.py
    
    Esta es la función principal que combina carga + procesamiento
    """
    # 1. Cargar facts consolidados con fallback
    df_facts = load_consolidated_facts(company_dir, lang, enable_log)
    if df_facts is None:
        return None
    
    # 2. Procesar datos con toda la lógica de generate_primary_roles_csv.py
    return process_facts_data_for_excel(df_facts, company_dir, lang, enable_log)


def get_date_columns(df: pd.DataFrame) -> List[str]:
    """
    Extrae columnas de fecha puras YYYY-MM-DD exactamente como generate_primary_roles_csv.py
    """
    return [c for c in df.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]


def apply_consolidated_processing(df: pd.DataFrame, company_dir: Path, 
                                 lang: str = 'es', enable_log: bool = False) -> pd.DataFrame:
    """
    Aplica procesamiento para FACTS CONSOLIDADO (mantiene TODOS los roles)
    
    Para batch_xbrl_to_excel.py - debe mantener notas y todos los roles
    """
    return process_facts_data_for_consolidated(df, company_dir, lang, enable_log)


def apply_excel_processing_like_primary_csv(df: pd.DataFrame, company_dir: Path, 
                                           lang: str = 'es', enable_log: bool = False) -> pd.DataFrame:
    """
    Aplica el mismo procesamiento que generate_primary_roles_csv.py para EXCEL
    
    Solo roles principales (210000, 310000, 510000) con ordenamiento perfecto
    """
    return process_facts_data_for_excel(df, company_dir, lang, enable_log)


# Alias para compatibilidad hacia atrás
apply_same_data_processing_as_primary_csv = apply_excel_processing_like_primary_csv