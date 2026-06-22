#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Convierte:
  - facts_<stem>.csv  (generado con: --facts y --factListCols)
  - presentation_<stem>.csv (generado con: --pre)
en:
  - estados_<stem>.xlsx con hojas: Balance / Resultados / Flujo_de_Caja

MEJORAS v2.0 - Mapeo dinámico de cuentas:
  - Usa taxonomia_ilustrada.json como fuente completa de mapeo IFRS
  - Mapeo automático por roles (210000-Balance, 310000-Resultados, 510000-Flujo)
  - Soporte de idioma dinámico (español/inglés) 
  - Fallback inteligente a cuentas.json para compatibilidad
  - Reportes de debug con cuentas no mapeadas
  - Mapeo fuzzy para cuentas similares

Variables de entorno de debug:
  - X2E_DEBUG=1: Habilitar logging detallado
  - X2E_KEEP_ALL_DATES=1: No recortar fechas automáticamente
  - X2E_DECEMBER_AS_YEAR=1: Usar año en lugar de Q4 para diciembre

Uso:
  python xbrl_to_excel.py <out_dir> <stem> [lang]

Ejemplo:
  python xbrl_to_excel.py "/ruta/out_91041000_202412" "91041000_202412" "es"
  X2E_DEBUG=1 python xbrl_to_excel.py "/ruta/out_91041000_202412" "91041000_202412" "en"
"""

from __future__ import annotations
import re
import sys
from pathlib import Path
import os
import csv
import json
from datetime import datetime
from functools import lru_cache
import pandas as pd

# Import our perfect JSON-based ordering and data processing
from analisis_excel.utils.json_ordering import apply_perfect_json_ordering
from analisis_excel.utils.facts_processing import apply_excel_processing_like_primary_csv



# Opción introducida en pandas 2.2; en versiones anteriores no existe.
try:
    pd.set_option('future.no_silent_downcasting', True)
except Exception:
    pass
# Importar Facts Enhancer para mejorar matching de datos
try:
    from facts_enhancer import apply_facts_enhancements
    FACTS_ENHANCER_AVAILABLE = True
except ImportError:
    FACTS_ENHANCER_AVAILABLE = False
    if os.getenv('X2E_DEBUG') == '1':
        print("WARNING: facts_enhancer.py no disponible, funcionalidades limitadas")

# Cachés simples en memoria para acelerar corridas sin cambiar resultados
_TAXONOMY_CACHE: dict[str, dict[str, list[tuple[str, str]]]] = {}
_FLATTEN_CACHE: dict[int, dict] = {}


def _quarter_from_month(m: int) -> str | None:
    try:
        m_int = int(m)
    except Exception:
        return None
    return {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}.get(m_int)
def strip_foreign_role_segments(df: pd.DataFrame, expected_role: str) -> pd.DataFrame:
    """
    Quita segmentos completos que empiezan en un header [XXXXXX] distinto a expected_role,
    hasta el siguiente header.
    """
    if df is None or df.empty or 'Cuenta' not in df.columns:
        return df
    out_rows = []
    keep = True
    header_re = re.compile(r'^\s*["\']?\[(\d{6})\]')

    for _, r in df.iterrows():
        lbl = str(r.get('Cuenta', '') or '')
        m = header_re.match(lbl)
        if m:
            keep = (m.group(1) == expected_role)
        if keep:
            out_rows.append(r)

    return pd.DataFrame(out_rows, columns=df.columns)


def _period_labels_from_dates(date_cols: list[str], kind: str) -> dict[str, str]:
    """
    Convierte columnas 'YYYY-MM-DD' en etiquetas normalizadas:
      - Dic (Q4) -> 'YYYYQ4'; Mar/Jun/Sep -> 'YYYYQn'
      - Otros meses -> 'YYYY'
    Q4 siempre produce 'YYYYQ4' para consistencia.
    """
    mapping: dict[str, str] = {}
    for dc in date_cols:
        try:
            d = pd.to_datetime(dc, errors='raise')
        except Exception:
            # Mantener tal cual si no es fecha limpia
            continue
        q = _quarter_from_month(d.month)
        if q:
            # Todos los trimestres (Q1-Q4) usan formato YYYYQn
            mapping[dc] = f"{d.year}{q}"
        else:
            mapping[dc] = str(d.year)
    return mapping


def _period_sort_key(lbl: str) -> tuple[int, int]:
    # '2025' -> (2025, 0) ; '2025Q1' -> (2025, 1) ; otros -> (9999, 9)
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



def extract_company_rut(stem: str) -> str | None:
    """
    Extrae el RUT de la empresa del stem.
    Ejemplos: "91705000-7_202312-202506" -> "91705000-7"
    """
    if not stem:
        return None
    
    # Buscar patrón RUT al inicio del stem
    import re
    rut_match = re.match(r'^(\d{1,9}-[\dkK])', stem)
    if rut_match:
        return rut_match.group(1)
    
    return None


def load_company_specific_structure(company_rut: str, lang: str = "es") -> dict[str, list[tuple[str, str]]]:
    """
    Carga estructura específica por empresa desde estructura_eeff_empresas.json
    Retorna dict con estructura: {role_id: [(qname, label)]} para preservar orden
    """
    current_dir = Path(__file__).parent
    structure_path = current_dir / "analisis_excel" / "estructura_eeff_empresas.json"
    
    if not structure_path.exists():
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontró estructura_eeff_empresas.json en {structure_path}")
        return {}
    
    try:
        with open(structure_path, 'r', encoding='utf-8') as f:
            estructura = json.load(f)
        
        # Buscar la empresa específica
        empresa_data = None
        for empresa in estructura.get('empresas', []):
            if empresa.get('empresa', {}).get('rut') == company_rut:
                empresa_data = empresa
                break
        
        if not empresa_data:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: No se encontró estructura específica para empresa {company_rut}")
            return {}
        
        # Verificar idioma
        if empresa_data.get('lang') != lang:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Idioma de estructura ({empresa_data.get('lang')}) no coincide con solicitado ({lang})")
            return {}
        
        # Construir mapeo
        mapping = {}
        for role in empresa_data.get('roles', []):
            role_id = role.get('id', '')
            if not role_id:
                continue
                
            role_items = []
            for line in role.get('lineas', []):
                if line:
                    # Usar la línea como qname y label (estructura simplificada)
                    role_items.append((f"custom:{line}", line))
            
            if role_items:
                mapping[role_id] = role_items
        
        if os.getenv('X2E_DEBUG') == '1':
            total_items = sum(len(items) for items in mapping.values())
            print(f"DEBUG: Estructura específica cargada para {company_rut}. Total elementos: {total_items}")
            for role_id, role_items in mapping.items():
                print(f"DEBUG: Role {role_id}: {len(role_items)} elementos")
        
        return mapping
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Error cargando estructura específica: {e}")
        return {}


def build_complete_mapping(lang: str = "es", company_rut: str = None) -> dict[str, list[tuple[str, str]]]:
    """
    Construye mapeo completo con prioridad:
    1. Estructura específica por empresa (si existe)
    2. Fallback a taxonomia_ilustrada.json
    Retorna dict con estructura: {role_id: [(qname, label)]} para preservar orden
    """
    # Intentar primero estructura específica por empresa
    if company_rut:
        company_mapping = load_company_specific_structure(company_rut, lang)
        if company_mapping:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Usando estructura específica para empresa {company_rut}")
            return company_mapping
    
    # Fallback a taxonomía general
    # Buscar el archivo de taxonomía
    current_dir = Path(__file__).parent
    taxonomia_path = current_dir / "analisis_excel" / "utils" / "testeo_pdf" / "taxonomia" / "taxonomia_ilustrada.json"
    
    if not taxonomia_path.exists():
        # Fallback a buscar en otros directorios
        alt_paths = [
            current_dir / "taxonomia_ilustrada.json",
            current_dir / "analisis_excel" / "taxonomia_ilustrada.json",
            current_dir.parent / "taxonomia_ilustrada.json"
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                taxonomia_path = alt_path
                break
        else:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: No se encontró taxonomia_ilustrada.json. Usando mapeo básico.")
            return {}
    
    try:
        # Cache por idioma para evitar reparsear la taxonomía en la misma corrida
        cache_key = lang or "es"
        if cache_key in _TAXONOMY_CACHE:
            return _TAXONOMY_CACHE[cache_key]
        with open(taxonomia_path, 'r', encoding='utf-8') as f:
            taxonomia = json.load(f)
        
        mapping = {}
        for section in taxonomia:
            role_id = section.get('id', '')
            # Incluir TODOS los roles de estados financieros principales
            financial_statement_roles = [
                '210000',  # Balance situación financiera corriente/no corriente
               
                '310000',  # Resultados por función de gasto
                '320000',  # Resultados por naturaleza de gasto
                '420000',  # Estado de Resultados Integral
                '510000',  # Flujo efectivo método directo
              
                '610000',  # Estado de Cambio en el Patrimonio
            ]
            if role_id not in financial_statement_roles:
                continue
                
            role_items = []
            for item in section.get('items', []):
                prefijo = item.get('prefijo', '')
                nombre = item.get('nombre', '')
                etiqueta = item.get('etiqueta', '')
                
                if not nombre or not etiqueta:
                    continue
                    
                # Construir qname completo
                qname = f"{prefijo}:{nombre}" if prefijo else nombre
                
                # Solo procesamos español
                
                # Solo agregar elementos con prefijo para evitar duplicados
                if ':' in qname:
                    role_items.append((qname, etiqueta))
                
            if role_items:
                mapping[role_id] = role_items
                
        if os.getenv('X2E_DEBUG') == '1':
            total_items = sum(len(items) for items in mapping.values())
            print(f"DEBUG: Mapeo completo cargado. Total elementos: {total_items}")
            for role_id, role_items in mapping.items():
                print(f"DEBUG: Role {role_id}: {len(role_items)} elementos")
        _TAXONOMY_CACHE[cache_key] = mapping
        return mapping
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Error cargando taxonomía: {e}")
        return {}


def load_legacy_mapping() -> dict[str, dict[str, str]]:
    """
    Carga el mapeo legacy desde cuentas.json como fallback.
    """
    current_dir = Path(__file__).parent
    cuentas_path = current_dir / "analisis_excel" / "utils" / "cuentas.json"
    
    if not cuentas_path.exists():
        return {}
        
    try:
        with open(cuentas_path, 'r', encoding='utf-8') as f:
            cuentas = json.load(f)
        
        # Convertir formato legacy a nuevo formato
        mapping = {
            "210000": cuentas.get("balance", {}),
            "310000": cuentas.get("estado_resultados", {}),
            "320000": cuentas.get("estado_resultados", {}),  # Resultados por naturaleza usa misma estructura
            "510000": cuentas.get("flujo_caja", {})
        }
        
        # Invertir mapeo: english -> spanish a spanish -> spanish para consistencia
        for role_id in mapping:
            role_mapping = mapping[role_id]
            inverted = {}
            for spanish, english in role_mapping.items():
                inverted[spanish] = spanish  # mapear spanish a sí mismo
                inverted[english] = spanish  # mapear english a spanish
            mapping[role_id] = inverted
            
        return mapping
        
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Error cargando cuentas.json: {e}")
        return {}


def detect_income_statement_role(presentation_data: pd.DataFrame = None, facts_df: pd.DataFrame = None, company_rut: str = None) -> str:
    """
    Detecta automáticamente si usar rol 310000 (función) o 320000 (naturaleza)
    para el estado de resultados basado en estructura JSON específica por empresa.
    
    Prioridad de detección:
    1. Estructura específica en new_eeff_estructura.json por RUT
    2. Headers en presentation data 
    3. RoleCode en facts DataFrame
    4. Default: 310000 (función)
    
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
                                if os.getenv('X2E_DEBUG') == '1':
                                    titulo = rol.get('titulo', '')
                                    print(f"DEBUG: Estructura JSON empresa {company_rut}: usando rol {role_id}")
                                    if '320000' in titulo:
                                        print(f"DEBUG: Confirmado por título: {titulo[:50]}...")
                                return role_id
                        break
        except Exception as e:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Error leyendo estructura JSON: {e}")
    
    # PRIORIDAD 2: Buscar en presentation si está disponible
    if presentation_data is not None and not presentation_data.empty:
        all_text = presentation_data.astype(str).values.flatten()
        text_combined = " ".join(all_text)
        
        if '[320000]' in text_combined or 'role-320000' in text_combined:
            return "320000"
        elif '[310000]' in text_combined or 'role-310000' in text_combined:
            return "310000"
    
    # PRIORIDAD 3: Buscar en facts si está disponible
    if facts_df is not None and not facts_df.empty and 'RoleCode' in facts_df.columns:
        role_codes = facts_df['RoleCode'].astype(str).unique()
        if '320000' in role_codes:
            return "320000"
        elif '310000' in role_codes:
            return "310000"
    
    # Default fallback: función (310000)
    return "310000"


def flatten_presentation_accounts(presentation_data: pd.DataFrame) -> dict:
    """
    Aplana el presentation.csv extrayendo todas las cuentas organizadas por role,
    sin importar la indentación jerárquica.
    
    Returns:
        dict: {role_id: [account_labels]}
    """
    if presentation_data is None or presentation_data.empty:
        return {}
    
    # Cache de aplanamiento por id(DataFrame) para reuso en los 3 estados
    cache_key = id(presentation_data)
    if cache_key in _FLATTEN_CACHE:
        return _FLATTEN_CACHE[cache_key]

    flattened = {}
    current_role_id = None
    first_col = presentation_data.columns[0] if len(presentation_data.columns) > 0 else None
    
    if not first_col:
        return {}
    
    for _, row in presentation_data.iterrows():
        content = str(row[first_col]) if pd.notna(row[first_col]) else ''
        
        # Detectar role header - formato flexible para manejar "[XXXXXX]" o comillas
        role_match = re.match(r'^"?\[(\d{6})\]\s*(.+)', content) if content and content != 'nan' else None
        if role_match:
            current_role_id = role_match.group(1)
            if current_role_id not in flattened:
                flattened[current_role_id] = []
            continue
        
        # Si no tenemos role activo, saltar
        if not current_role_id:
            continue
        
        # IMPORTANTE: No hacer continue si content está vacío, 
        # porque las cuentas pueden estar en otras columnas
            
        # Buscar cuentas en todas las columnas (para manejar indentación)
        for col in presentation_data.columns:
            cell_content = str(row[col]) if pd.notna(row[col]) else ''
            if not cell_content or cell_content == 'nan':
                continue
                
            # Limpiar el contenido removiendo espacios
            original_content = cell_content.strip(' \t,')
            clean_label = original_content

            # Detectar si la fila corresponde a una categoría [sinopsis]
            # Nota: mantenemos explícitamente el tag [sinopsis] en el label
            lower_original = original_content.lower()
            is_sinopsis = ('[sinopsis]' in lower_original) or lower_original.endswith('sinopsis')

            # Remover etiquetas entre corchetes EXCEPTO [sinopsis]; normalizar espacios
            if is_sinopsis:
                # Eliminar otros tags entre corchetes pero conservar [sinopsis]/[abstract]/[resumen]
                clean_label = re.sub(r'\[(?!\s*(sinopsis|abstract|resumen)\s*\]).*?\]', '', clean_label, flags=re.I)
            else:
                # Eliminar todos los tags entre corchetes (p.ej. [bloque de texto], etc.)
                clean_label = re.sub(r'\[.*?\]', '', clean_label)
            clean_label = re.sub(r'\s+', ' ', clean_label).strip()

            # Si es una cuenta válida (incluyendo categorías [sinopsis])
            if (clean_label and 
                len(clean_label) > 3 and
                clean_label not in ['', ',', ',,', ',,,'] and
                not re.match(r'^"?\[(\d{6})\]', clean_label) and
                not clean_label.lower() in ['nan', 'none', 'null']):
                
                if clean_label not in flattened[current_role_id]:
                    flattened[current_role_id].append(clean_label)
                    # Debug para cuentas bancarias específicas
                    if any(x in clean_label.lower() for x in ['ingreso neto por intereses', 'resultado financiero neto', 'servicios bancarios']):
                        if os.getenv('X2E_DEBUG') == '1':
                            print(f"DEBUG: Cuenta bancaria encontrada en aplanamiento: {clean_label}")
                break  # Solo tomar la primera cuenta válida por fila
            elif is_sinopsis and os.getenv('X2E_DEBUG') == '1':
                # Si llega aquí, no se consideró válida por alguna otra razón
                print(f"DEBUG: Fila [sinopsis] no agregada (posible label corto/ruidoso): {original_content}")
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: flatten_presentation_accounts procesó {len(presentation_data)} filas")
        for role_id, accounts in flattened.items():
            print(f"DEBUG: Role {role_id} tiene {len(accounts)} cuentas aplanadas")
            if role_id == '310000':
                print(f"DEBUG: Role 310000 primeras 10 cuentas: {accounts[:10]}")
            
    _FLATTEN_CACHE[cache_key] = flattened
    return flattened


def _add_missing_facts_preserve_order(presentation_tree: pd.DataFrame, facts_df: pd.DataFrame, statement_kind: str, lang: str = "es") -> pd.DataFrame:
    """
    Para facts consolidados: Usar directamente el orden del facts en lugar del presentation.
    El facts consolidado ya tiene el orden correcto de la CMF.
    """
    if presentation_tree is None or presentation_tree.empty or facts_df is None or facts_df.empty:
        return presentation_tree
    
    # Mapear statement_kind a role_id con autodetección para RESULTADOS
    if statement_kind == "RESULTADOS":
        income_role = detect_income_statement_role(presentation_tree, facts_df)
        role_mapping = {"BALANCE": "210000", "RESULTADOS": income_role, "FLUJO": "510000"}
    else:
        role_mapping = {"BALANCE": "210000", "RESULTADOS": "310000", "FLUJO": "510000"}
    target_role = role_mapping.get(statement_kind)
    
    if not target_role:
        return presentation_tree
        
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: _add_missing_facts_preserve_order - Usando orden directo del facts consolidado")
    
    # NUEVA ESTRATEGIA: Usar directamente el facts como estructura base
    # El facts consolidado YA tiene el orden correcto de la CMF
    # Usar la misma lógica de filtrado que usamos en filter_facts_by_statement
    from xbrl_to_excel import filter_facts_by_statement
    facts_filtered = filter_facts_by_statement(facts_df, statement_kind)
    
    if facts_filtered.empty:
        return presentation_tree
    
    # Crear estructura directamente desde facts (en su orden original)
    new_structure = []
    
    # Agregar header primero
    header_pattern = f'[{target_role}]'
    header_account = f"[{target_role}] Estado de flujos de efectivo, método directo"
    new_structure.append(header_account)
    
    # Agregar TODAS las cuentas del facts EN SU ORDEN ORIGINAL
    for _, row in facts_filtered.iterrows():
        account_name = str(row.get('Label', '')).strip()
        
        # Saltar headers (ya agregamos uno estándar arriba)
        if account_name.startswith('[') and ']' in account_name:
            continue
            
        if account_name:
            new_structure.append(account_name)
    
    # Crear nuevo DataFrame
    result_df = pd.DataFrame({'Cuenta': new_structure})
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Nueva estructura desde facts consolidado: {len(result_df)} cuentas")
        print(f"DEBUG: Primeras 3: {result_df['Cuenta'].head(3).tolist()}")
        print(f"DEBUG: Últimas 3: {result_df['Cuenta'].tail(3).tolist()}")
    
    return result_df


def add_missing_facts_accounts(presentation_tree: pd.DataFrame, facts_df: pd.DataFrame, statement_kind: str, lang: str = "es") -> pd.DataFrame:
    """
    Agrega cuentas que aparecen en facts pero no están en el presentation restructured,
    insertándolas en la posición jerárquica apropiada basándose en el contexto del facts.
    """
    if presentation_tree is None or presentation_tree.empty or facts_df is None or facts_df.empty:
        return presentation_tree
    
    # Mapear statement_kind a role_id con detección inteligente para RESULTADOS
    role_mapping = {
        "BALANCE": "210000",
        "RESULTADOS": "310000", 
        "FLUJO": "510000"
    }
    
    target_role_id = role_mapping.get(statement_kind, "210000")
    
    # Detección especial para RESULTADOS - verificar si hay [320000] en presentation
    if statement_kind == "RESULTADOS":
        # Buscar [320000] en el presentation actual
        for _, row in presentation_tree.iterrows():
            cuenta = str(row.get('Cuenta', '')).strip()
            if '[320000]' in cuenta:
                target_role_id = "320000"
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Detectado [320000] en presentation, usando role 320000 para RESULTADOS")
                break
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Buscando cuentas nuevas en facts para {statement_kind} (role {target_role_id})")
    
    # Obtener cuentas que existen en facts del statement correspondiente
    facts_filtered = filter_facts_by_statement(facts_df, statement_kind)
    
    if facts_filtered.empty:
        return presentation_tree
    
    # Extraer todas las cuentas que tienen datos en facts
    facts_accounts = set()
    date_columns = [c for c in facts_filtered.columns if c != 'Label' and isinstance(c, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', c)]
    
    for _, row in facts_filtered.iterrows():
        label = str(row.get('Label', '')).strip()
        
        # Saltar headers de role y categorías
        if re.match(r'^\s*\[(\d{6})\]', label) or '[sinopsis]' in label.lower() or '[abstract]' in label.lower():
            continue
            
        # Solo incluir cuentas que tengan valores reales en alguna fecha
        if date_columns and row[date_columns].notna().any():
            clean_label = re.sub(r'\s+', ' ', label).strip()
            if clean_label and clean_label not in ['', 'nan']:
                facts_accounts.add(clean_label)
    
    # Obtener cuentas que ya existen en presentation
    existing_accounts = set()
    for _, row in presentation_tree.iterrows():
        cuenta = str(row.get('Cuenta', '')).strip()
        if cuenta:
            existing_accounts.add(cuenta)
    
    # Encontrar cuentas nuevas (están en facts pero no en presentation)
    new_accounts = facts_accounts - existing_accounts
    
    if not new_accounts:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontraron cuentas nuevas para agregar en {statement_kind}")
        return presentation_tree
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Encontradas {len(new_accounts)} cuentas nuevas para agregar:")
        for acc in sorted(new_accounts):
            print(f"DEBUG:   - {acc}")
    
    # Convertir presentation_tree a lista para manipulación
    presentation_list = presentation_tree['Cuenta'].tolist()
    
    # Encontrar la posición del header del statement correspondiente
    target_header = f"[{target_role_id}]"
    header_pos = None
    
    for i, cuenta in enumerate(presentation_list):
        if target_header in str(cuenta):
            header_pos = i
            break
    
    if header_pos is None:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontró header {target_header}, agregando al final")
        # Si no encontramos el header, agregar al final
        for new_account in sorted(new_accounts):
            presentation_list.append(new_account)
    else:
        # Buscar la posición correcta para cada cuenta nueva basándose en el orden en facts
        facts_order = {}  # mapear cuenta → posición en facts
        section_accounts = []  # cuentas de facts en orden de aparición
        
        # Obtener orden de aparición en facts
        for idx, (_, row) in enumerate(facts_filtered.iterrows()):
            label = str(row.get('Label', '')).strip()
            if label and not re.match(r'^\s*\[(\d{6})\]', label) and '[sinopsis]' not in label.lower() and '[abstract]' not in label.lower():
                clean_label = re.sub(r'\s+', ' ', label).strip()
                if clean_label and clean_label not in ['', 'nan']:
                    facts_order[clean_label] = idx
                    section_accounts.append(clean_label)
        
        # Para cada cuenta nueva, encontrar la mejor posición de inserción
        for new_account in new_accounts:
            if new_account in facts_order:
                new_account_facts_pos = facts_order[new_account]
                best_insert_pos = header_pos + 1  # posición por defecto después del header
                
                # Buscar la cuenta en presentation que aparece inmediatamente antes en facts
                prev_account_in_facts = None
                for i in range(len(section_accounts)):
                    if section_accounts[i] == new_account:
                        # Encontrar la cuenta anterior que existe en presentation
                        for j in range(i - 1, -1, -1):
                            candidate = section_accounts[j]
                            # Buscar esta cuenta en presentation_list
                            for k in range(header_pos + 1, len(presentation_list)):
                                if re.match(r'^\s*\[(\d{6})\]', str(presentation_list[k])):
                                    break  # llegamos al próximo header
                                if str(presentation_list[k]).strip() == candidate:
                                    prev_account_in_facts = candidate
                                    best_insert_pos = k + 1  # insertar después de esta cuenta
                                    break
                            if prev_account_in_facts:
                                break
                        break
                
                if os.getenv('X2E_DEBUG') == '1':
                    if prev_account_in_facts:
                        print(f"DEBUG: Insertando '{new_account}' después de '{prev_account_in_facts}' en posición {best_insert_pos}")
                    else:
                        print(f"DEBUG: Insertando '{new_account}' en posición por defecto {best_insert_pos}")
                
                presentation_list.insert(best_insert_pos, new_account)
                
                # Ajustar posiciones para próximas inserciones
                for i in range(len(presentation_list)):
                    if i > best_insert_pos:
                        continue
            else:
                # Si no está en facts_order, agregar al final de la sección
                section_end = len(presentation_list)
                for i in range(header_pos + 1, len(presentation_list)):
                    if re.match(r'^\s*\[(\d{6})\]', str(presentation_list[i])):
                        section_end = i
                        break
                presentation_list.insert(section_end, new_account)
    
    # Crear nuevo DataFrame con las cuentas agregadas
    updated_presentation = pd.DataFrame({'Cuenta': presentation_list})
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Presentation actualizado de {len(presentation_tree)} a {len(updated_presentation)} cuentas")
    
    return updated_presentation


def ensure_missing_accounts_from_presentation(presentation_data: pd.DataFrame, base_mapping: dict, statement_kind: str, facts_df: pd.DataFrame = None, lang: str = "es") -> dict:
    """
    Reconstruye el mapeo completo usando el orden de presentation.csv y evitando duplicados.
    Incluye solo cuentas con valores en facts.csv, PERO conserva filas de categoría
    marcadas como "[sinopsis]" aunque no tengan valores (para mantener la estructura).
    """
    if presentation_data is None or presentation_data.empty:
        return base_mapping
    
    # Mapear statement_kind a role_id
    role_mapping = {
        "BALANCE": "210000",
        "RESULTADOS": "310000", 
        "FLUJO": "510000"
    }
    
    target_role_id = role_mapping.get(statement_kind, "210000")
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Reconstruyendo mapeo con orden de presentation para {statement_kind} (role {target_role_id})")
    
    # Inicializar role si no existe
    if target_role_id not in base_mapping:
        base_mapping[target_role_id] = []
    
    # Crear diccionario de taxonomía base para lookup rápido
    taxonomy_dict = {item[1]: item[0] for item in base_mapping[target_role_id]}
    
    # Obtener cuentas que tienen valores en facts.csv
    facts_labels = set()
    if facts_df is not None:
        for _, row in facts_df.iterrows():
            label = str(row.get('Label', ''))
            clean_label = re.sub(r'\[.*?\]', '', label).strip()
            clean_label = re.sub(r'\s+', ' ', clean_label).strip()
            if clean_label and clean_label not in ['', 'nan']:
                facts_labels.add(clean_label)
    
    # Usar aplanamiento para extraer todas las cuentas organizadas por role EN ORDEN
    flattened_accounts = flatten_presentation_accounts(presentation_data)
    
    # Procesar solo las cuentas del role objetivo
    target_accounts = flattened_accounts.get(target_role_id, [])
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Reconstruyendo con {len(target_accounts)} cuentas de presentation en orden")
    
    # RECONSTRUIR el mapeo completo manteniendo el orden de presentation
    new_mapping = []
    added_count = 0
    taxonomy_count = 0
    
    for label in target_accounts:
        # Incluir categorías [sinopsis] aunque no tengan valores (visualmente importantes)
        lower_label = str(label).lower()
        is_sinopsis_label = (
            ('[sinopsis]' in lower_label) or lower_label.endswith('sinopsis') or
            ('[abstract]' in lower_label) or lower_label.endswith('abstract') or
            ('[resumen]' in lower_label) or lower_label.endswith('resumen')
        )
        # Solo incluir cuentas que tengan valores en facts, excepto si son [sinopsis]
        if (label not in facts_labels) and (not is_sinopsis_label):
            continue
            
        # Debug para cuentas específicas
        is_target_account = any(x in label.lower() for x in ['ingreso neto por intereses', 'resultado financiero neto', 'servicios bancarios'])
        
        # Si la cuenta está en taxonomía, usar su qname original
        if label in taxonomy_dict:
            qname = taxonomy_dict[label]
            new_mapping.append((qname, label))
            taxonomy_count += 1
            if is_target_account and os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Usando cuenta de taxonomía en orden: {label}")
        else:
            # Si no está en taxonomía, crear qname sintético
            qname_part = re.sub(r'[^a-zA-Z0-9]', '', label.replace(' ', ''))
            if len(qname_part) > 50:
                qname_part = qname_part[:50]
            qname = f"presentation:{qname_part}" if qname_part else f"presentation:{len(new_mapping)}"
            
            new_mapping.append((qname, label))
            added_count += 1
            
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Agregando cuenta de presentation en orden: {label}")
            if is_target_account and os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: *** CUENTA BANCARIA agregada en orden: {label}")
    
    # Reemplazar el mapeo completo con el nuevo orden
    base_mapping[target_role_id] = new_mapping
    
    if os.getenv('X2E_DEBUG') == '1':
        total_items = len(new_mapping)
        print(f"DEBUG: Mapeo reconstruido para {statement_kind}. Total: {total_items} (taxonomía: {taxonomy_count}, presentation: {added_count})")
    
    return base_mapping


def build_hybrid_mapping(presentation_data: pd.DataFrame, lang: str = "es", company_rut: str = None) -> dict[str, list[tuple[str, str]]]:
    """
    Construye mapeo híbrido combinando taxonomia_ilustrada.json con estrategia facts-first.
    NUEVA ESTRATEGIA: Si tenemos presentation restructured, lo usamos como base.
    AHORA: Siempre prioriza estructura específica de empresa cuando está disponible.
    """
    # PRIMERO: Intentar cargar estructura específica por empresa
    company_mapping = None
    if company_rut:
        company_mapping = load_company_specific_structure(company_rut, lang)
        if company_mapping:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Estructura específica encontrada para empresa {company_rut}")
                total_items = sum(len(items) for items in company_mapping.values())
                print(f"DEBUG: Usando estructura específica. Total elementos: {total_items}")
                for role_id, items in company_mapping.items():
                    print(f"DEBUG: Role {role_id}: {len(items)} elementos")
            return company_mapping
    
    if presentation_data is not None and not presentation_data.empty:
        # Detectar si es presentation restructured (solo tiene columna 'Cuenta')
        is_restructured = len(presentation_data.columns) == 1 and 'Cuenta' in presentation_data.columns
        
        if is_restructured:
            if os.getenv('X2E_DEBUG') == '1':
                print("DEBUG: Construyendo mapeo desde presentation restructured...")
            
            # Construir mapeo directamente desde el presentation restructured
            mapping = {}
            current_role = None
            current_accounts = []
            
            for _, row in presentation_data.iterrows():
                cuenta = str(row['Cuenta']).strip()
                
                # Detectar headers de role
                role_match = re.match(r'^\s*\[(\d{6})\]', cuenta)
                if role_match:
                    # Guardar role anterior si existe
                    if current_role is not None and current_accounts:
                        mapping[current_role] = current_accounts
                    
                    # Iniciar nuevo role
                    current_role = role_match.group(1)
                    current_accounts = []
                    continue
                
                # Agregar cuenta al role actual
                if current_role is not None and cuenta and cuenta != '':
                    # Crear qname sintético
                    qname_part = re.sub(r'[^a-zA-Z0-9]', '', cuenta.replace(' ', ''))
                    if len(qname_part) > 50:
                        qname_part = qname_part[:50]
                    qname = f"restructured:{qname_part}" if qname_part else f"restructured:{len(current_accounts)}"
                    
                    current_accounts.append((qname, cuenta))
            
            # Guardar el último role
            if current_role is not None and current_accounts:
                mapping[current_role] = current_accounts
            
            if os.getenv('X2E_DEBUG') == '1':
                total_items = sum(len(items) for items in mapping.values())
                print(f"DEBUG: Mapeo desde restructured completado. Total elementos: {total_items}")
                for role_id, items in mapping.items():
                    print(f"DEBUG: Role {role_id}: {len(items)} elementos")
            
            return mapping
    
    # Fallback a taxonomía estándar
    base_mapping = build_complete_mapping(lang, company_rut)
    
    if os.getenv('X2E_DEBUG') == '1':
        print("DEBUG: Usando mapeo desde taxonomía estándar...")
        total_items = sum(len(items) for items in base_mapping.values())
        print(f"DEBUG: Mapeo base completado. Total elementos: {total_items}")
        for role_id, items in base_mapping.items():
            print(f"DEBUG: Role {role_id}: {len(items)} elementos")
    
    return base_mapping


def write_unmapped_accounts_report(unmapped_accounts: list[str], statement_kind: str, output_dir: Path) -> None:
    """
    Escribe reporte de cuentas no mapeadas para análisis.
    """
    if not unmapped_accounts:
        return
        
    report_path = output_dir / f"unmapped_accounts_{statement_kind.lower()}.txt"
    try:
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"REPORTE DE CUENTAS NO MAPEADAS - {statement_kind}\n")
            f.write("=" * 50 + "\n\n")
            f.write(f"Total cuentas sin mapear: {len(unmapped_accounts)}\n\n")
            f.write("Lista de cuentas:\n")
            for i, account in enumerate(unmapped_accounts, 1):
                f.write(f"{i:3d}. {account}\n")
                
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Reporte de cuentas no mapeadas guardado: {report_path}")
            
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Error escribiendo reporte: {e}")


def get_account_mapping(lang: str = "es", presentation_data: pd.DataFrame = None, company_rut: str = None) -> dict[str, dict[str, str]]:
    """
    Obtiene mapeo de cuentas usando estrategia híbrida: taxonomía ilustrada + datos reales CMF.
    """
    # Usar mapeo híbrido si tenemos datos de presentation
    if presentation_data is not None and not presentation_data.empty:
        complete_mapping = build_hybrid_mapping(presentation_data, lang, company_rut)
        if os.getenv('X2E_DEBUG') == '1':
            total_items = sum(len(role_map) for role_map in complete_mapping.values())
            print(f"DEBUG: Usando mapeo híbrido (taxonomía + CMF): {total_items} elementos")
    else:
        # Fallback a taxonomía pura
        complete_mapping = build_complete_mapping(lang, company_rut)
        if os.getenv('X2E_DEBUG') == '1':
            total_items = sum(len(role_map) for role_map in complete_mapping.values())
            print(f"DEBUG: Usando SOLO taxonomía ilustrada: {total_items} elementos")
    
    if not complete_mapping:
        if os.getenv('X2E_DEBUG') == '1':
            print("ERROR: No se pudo cargar mapeo de cuentas")
        return {}
    
    return complete_mapping


def guess_role_kind(role_uri: str) -> str | None:
    """Mapea roleUri a tipo de estado."""
    if role_uri is None or pd.isna(role_uri):
        return None
    txt = str(role_uri)

    # NUEVO: detectar código [XXXXXX] directamente
    m = re.match(r'^\[(\d{6})\]', txt)
    if m:
        code = m.group(1)
        if code == '210000':
            return "BALANCE"
        if code == '310000':
            return "RESULTADOS"
        if code == '510000':
            return "FLUJO"

    # Compatibilidad previa (URIs con 'role-210000', etc.)
    if re.search(r"role[-_/]?210000", txt):
        return "BALANCE"
    if re.search(r"role[-_/]?310000", txt):
        return "RESULTADOS"
    if re.search(r"role[-_/]?510000", txt):
        return "FLUJO"

    # Fallback textual
    if re.search(r"Statement of financial position|Estado de situación financiera|Estado de Situación|Balance", txt, re.I):
        return "BALANCE"
    if re.search(r"Statement of profit|Statement of comprehensive income|Estado del resultado|Resultados", txt, re.I):
        return "RESULTADOS"
    if re.search(r"Cash flow|Flujo[s]? de efectivo|Flujo[s]? de caja", txt, re.I):
        return "FLUJO"
    return None


def load_inputs(out_dir: Path, stem: str, lang: str = "es"):
    # ✨ PRIORIZAR OUTPUT DE GENERATE_PRIMARY_ROLES_CSV ✨
    # Primero buscar primary_roles_{stem}_{lang}.csv (ya procesado perfectamente)
    primary_roles_path = out_dir / f"primary_roles_{stem}_{lang}.csv"
    # Compatibilidad: algunos generadores usan nombre sin RUT → primary_roles_<YYYYMM-YYYYMM>_<lang>.csv
    ym_range = None
    try:
        m = re.match(r"^.+_(\d{6}-\d{6})$", str(stem))
        if m:
            ym_range = m.group(1)
    except Exception:
        ym_range = None
    alt_primary_roles_path = (out_dir / f"primary_roles_{ym_range}_{lang}.csv") if ym_range else None
    facts_path = out_dir / f"facts_{stem}_{lang}.csv"
    pres_path  = out_dir / f"presentation_{stem}_{lang}.csv"
    
    #Aumentar límite de tamaño de campo CSV para manejar text blocks extensos
    try:
        csv.field_size_limit(2 ** 31 - 1)
    except Exception:
        pass
    
    # Usar EXCLUSIVAMENTE los primary_roles generados por el script oficial.
    # Si hay varios, elegir el de rango más amplio (inicio más antiguo, fin más reciente).
    selected: Path | None = None
    range_candidates: list[tuple[str, str, Path]] = []
    try:
        # Buscar en este out_consolidated y en TODOS los out_consolidated_* de la empresa
        search_dirs: list[Path] = [out_dir]
        try:
            if out_dir.name.startswith('out_consolidated_'):
                company_dir_root = out_dir.parent
                # Agregar otros out_consolidated_* hermanos
                search_dirs.extend([p for p in company_dir_root.glob('out_consolidated_*') if p.is_dir()])
        except Exception:
            pass
        # De-duplicar
        seen = set()
        uniq_dirs: list[Path] = []
        for d0 in search_dirs:
            key = str(d0.resolve())
            if key in seen:
                continue
            seen.add(key)
            uniq_dirs.append(d0)
        for base in uniq_dirs:
            if os.getenv('X2E_DEBUG') == '1':
                primary_files = list(base.glob(f"primary_roles_*_{lang}.csv"))
                print(f"      ║ Archivos primary_roles encontrados en {base.name}: {[p.name for p in primary_files]}")
            for p in base.glob(f"primary_roles_*_{lang}.csv"):
                pattern = rf"^primary_roles_(\d{{6}})-(\d{{6}})_{re.escape(lang)}\.csv$"
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"      ║ Evaluando {p.name} con patrón {pattern}")
                m = re.match(pattern, p.name)
                if m:
                    if os.getenv('X2E_DEBUG') == '1':
                        print(f"      ║ ✅ MATCH: {p.name} → grupos: {m.groups()}")
                    range_candidates.append((m.group(1), m.group(2), p))
                elif os.getenv('X2E_DEBUG') == '1':
                    print(f"      ║ ❌ NO MATCH: {p.name}")
    except Exception:
        pass

    if range_candidates:
        # Elegir por (start ascendente, end descendente) → rango más amplio
        def _cmp_key(t: tuple[str, str, Path]):
            start, end, _ = t
            return (int(start), -int(end))
        best = sorted(range_candidates, key=_cmp_key)[0]
        selected = best[2]
    else:
        # Fallback: usar el del stem o el alterno detectado
        if alt_primary_roles_path and alt_primary_roles_path.exists():
            selected = alt_primary_roles_path
        elif primary_roles_path.exists():
            selected = primary_roles_path

    if selected is None:
        raise SystemExit("No se encontró ningún primary_roles_* CSV. Ejecuta generate_primary_roles_csv.py y reintenta.")

    if os.getenv('X2E_DEBUG') == '1':
        print(f"      ║ ✨ Usando primary_roles CSV: {selected.name}")
    try:
        facts = pd.read_csv(selected, engine="pyarrow")
    except Exception:
        facts = pd.read_csv(selected, engine="python")
    try:
        facts.attrs = getattr(facts, 'attrs', {})
        facts.attrs['from_primary_csv'] = True
    except Exception:
        pass
    
    # DEBUG: Verificar que los datos del primary_roles CSV son correctos
    if os.getenv('X2E_DEBUG') == '1':
        print(f"      ║ 📊 PRIMARY_ROLES CSV cargado: {len(facts)} filas, {len(facts.columns)} columnas")
        # Mostrar primeras cuentas con valores numéricos
        sample_rows = facts[facts['RoleCode'].isin(['210000', '310000', '510000'])].head(15)
        for _, row in sample_rows.iterrows():
            label = row['Label'][:50]
            role = row['RoleCode']
            # Buscar primer valor no nulo en las columnas de fecha
            first_value = None
            date_col = None
            for col in facts.columns:
                if re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(col)) and pd.notna(row[col]) and str(row[col]).strip():
                    first_value = str(row[col]).strip()
                    date_col = col
                    break
            print(f"      ║   {role} | {label:<50} | {date_col}={first_value}")
    
    # CRÍTICO: El facts ya viene procesado por generate_primary_roles_csv.py
    # NO aplicar ningún procesamiento adicional que pueda alterar los datos
    
    # DEBUG: Verificar que el atributo se mantiene
    if os.getenv('X2E_DEBUG') == '1':
        try:
            from_primary = bool(getattr(facts, 'attrs', {}).get('from_primary_csv'))
            print(f"      ║ 🏷️ ATRIBUTO from_primary_csv = {from_primary}")
            print(f"      ║ 🏷️ facts.attrs = {dict(getattr(facts, 'attrs', {}))}")
        except Exception as e:
            print(f"      ║ ⚠️ Error verificando atributo: {e}")
    
    # NUEVA LÓGICA: Reestructurar presentation.csv automáticamente
    print(f"      ║ Procesando presentation.csv...")
    
    # 1. Verificar si ya existe la versión reestructurada
    pres_restructured_path = out_dir / f"presentation_{stem}_{lang}_restructured.csv"
    
    if pres_restructured_path.exists():
        print(f"      ║ Usando presentation reestructurado existente")
        try:
            pres = pd.read_csv(pres_restructured_path, engine="pyarrow")
        except Exception:
            pres = pd.read_csv(pres_restructured_path, engine="python")
    else:
        # 2. Crear versión reestructurada del presentation original
        if pres_path.exists():
            restructured_path = restructure_presentation_to_single_column(str(pres_path))
            try:
                pres = pd.read_csv(restructured_path, engine="pyarrow")
            except Exception:
                pres = pd.read_csv(restructured_path, engine="python")
        else:
            print(f"      ║ ADVERTENCIA: No se encontró {pres_path}")
            pres = pd.DataFrame()
    
    return facts, pres


def normalize_facts(facts_raw: pd.DataFrame, lang: str | None = None) -> pd.DataFrame:
    facts = facts_raw.copy()

    # === NUEVO: detectar solo fechas "puras" ===
    full_date_re     = re.compile(r'^\d{4}[-/]\d{2}[-/]\d{2}$')                    # solo fecha
    prefixed_date_re = re.compile(r'^(\d{4}[-/]\d{2}[-/]\d{2})\s*(?:-|—|–)\s*(.+)$')  # fecha + sufijo

    rename_map: dict[str, str] = {}
    pure_date_cols: list[str] = []   # solo YYYY-MM-DD (sin sufijo)

    for col in facts.columns:
        s = str(col).strip()
        if not s:
            continue

        m_full = full_date_re.match(s)
        if m_full:
            # Fecha pura → renombrar a ISO exacto
            dt = pd.to_datetime(s, errors='coerce')
            if not pd.isna(dt):
                iso = dt.strftime('%Y-%m-%d')
                rename_map[col] = iso
                pure_date_cols.append(iso)
            continue

        m_pref = prefixed_date_re.match(s)
        if m_pref:
            # Fecha + sufijo → conservar sufijo, NO colapsar en la fecha pura
            d_raw, suffix = m_pref.group(1), m_pref.group(2)
            dt = pd.to_datetime(d_raw, errors='coerce')
            if pd.isna(dt):
                continue
            iso = dt.strftime('%Y-%m-%d')
            # normaliza un poco el sufijo para que sea estable como nombre de columna
            suffix_norm = re.sub(r'\s+', ' ', suffix).strip()
            suffix_norm = re.sub(r'[^\w\-\[\]\(\) ]+', '', suffix_norm)  # opcional
            new_name = f"{iso} - {suffix_norm}" if suffix_norm else iso
            rename_map[col] = new_name
            # OJO: NO lo añadimos a pure_date_cols (no es fecha "pura")
            continue

        # cualquier otro encabezado queda tal cual

    if rename_map:
        facts.rename(columns=rename_map, inplace=True)

    # Coalescer SOLO columnas verdaderamente duplicadas de fecha pura
    date_columns = list(dict.fromkeys(pure_date_cols))
    try:
        for dc in list(date_columns):
            _coalesce_duplicate_named_columns(facts, dc)
    except Exception:
        pass

    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG normalize_facts: PURE date columns: {date_columns}")
        leaked_like = [c for c in facts.columns if re.match(r'^\d{4}-\d{2}-\d{2}\s*-\s*', str(c))]
        if leaked_like:
            print(f"DEBUG normalize_facts: NON-PURE date-like columns preserved (won't be used to fill): {leaked_like[:6]}{' …' if len(leaked_like)>6 else ''}")

    # … (lo demás igual) …

    # Columnas base a conservar: Label/qname + SOLO fechas puras (+ columnas auxiliares si existen)
    keep_columns = ['Label']
    if 'qname' in facts.columns:
        keep_columns.append('qname')
    if 'contextRef' in facts.columns:
        keep_columns.append('contextRef')
    # Mantener columnas auxiliares si vienen desde out_consolidated
    for aux_col in ('LabelKeyId', 'LabelKeyIdExt', 'SectionKey', 'RoleCode'):
        if aux_col in facts.columns and aux_col not in keep_columns:
            keep_columns.append(aux_col)
    keep_columns += date_columns

    facts = facts[keep_columns]

    # (resto del cuerpo de normalize_facts igual…)

    
    # EXTRAER EL QNAME / LABEL
    # En el factTable, el elemento puede estar en cualquier columna según su nivel de jerarquía.
    # Preferimos 'qname' si existe; si no, caemos a 'Label'.
    def extract_element_name(row):
        # Preferir el Label legible del idioma actual para que case con el árbol de presentación
        if pd.notna(row.get('Label')) and str(row.get('Label', '')).strip():
            return str(row['Label']).strip()
        # Fallback a qname si el Label viene vacío
        qn = row.get('qname') if 'qname' in facts.columns else None
        if pd.notna(qn) and str(qn).strip():
            return str(qn).strip()
        # Último recurso: buscar en columnas originales no fecha/metadata
        for col in facts_raw.columns:
            val = row.get(col) if col in row.index else facts_raw.loc[row.name, col] if row.name in facts_raw.index else None
            if pd.notna(val) and str(val).strip():
                val_str = str(val).strip()
                if (not re.match(r'^\d{4}-\d{2}-\d{2}', val_str)
                    and val_str not in ['Label','localName','contextRef','unitRef','Dec','Prec','Lang','Value','qname']
                    and len(val_str) > 3):
                    return val_str
        return ""
    
    # Aplicar la extracción de nombres de elementos
    facts['Label'] = facts.apply(extract_element_name, axis=1)
    
    # Agregar campos que espera el resto del código
    facts['label'] = facts['Label']  # Usar el mismo valor para label y Label
    facts['contextref'] = facts.get('contextRef', '')
    facts['unitref'] = facts.get('unitRef', '')
    facts['dec'] = facts.get('Dec', '')
    facts['prec'] = facts.get('Prec', '')
    facts['lang'] = facts.get('Lang', '')
    facts['value'] = facts.get('Value', '')
    facts['unit'] = facts.get('unitRef', '')
    facts['decimals'] = facts.get('Dec', '')
    facts['periodStart'] = facts.get('periodStart', '')
    facts['periodEnd'] = facts.get('periodEnd', '')
    facts['instant'] = facts.get('instant', '')
    facts['endInstant'] = facts.get('endInstant', '')
    facts['contextId'] = facts.get('contextRef', '')
    
    # Para value_num, usar la primera columna de fecha disponible como valor principal
    if date_columns:
        # Si hay columnas duplicadas con el mismo nombre, la selección puede devolver un DataFrame
        s0 = facts[date_columns[0]]
        try:
            import pandas as _pd
            if isinstance(s0, _pd.DataFrame):
                # Tomar primer valor no vacío (izquierda→derecha)
                s0 = s0.bfill(axis=1).iloc[:, 0].infer_objects(copy=False)
        except Exception:
            pass
        facts['value_num'] = pd.to_numeric(s0, errors='coerce')
        facts['period_display'] = date_columns[0]  # Usar la primera fecha como período principal
    else:
        facts['value_num'] = pd.to_numeric(facts.get('Value', 0), errors='coerce')
        facts['period_display'] = facts.get('contextRef', 'unknown')
    
    # Filtrar filas que tienen Label válido (no vacío)
    facts = facts[facts['Label'].str.strip().str.len() > 0]
    
    # Filtrar elementos que no sean notas: mantener líneas de roles principales y todos los elementos (no empiezan con '[')
    # Esto conserva los encabezados de rol [210000|310000|510000] y todas las filas de cuentas reales
    facts = facts[facts['Label'].str.match(r'^\[\d{6}\]|^[^\[]', na=False)]   
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG normalize_facts: After filtering notes, kept {len(facts)} rows")
    
    # Mantener solo Label y columnas de fechas (matching por idioma)
    base_cols = ['Label'] + (['qname'] if 'qname' in facts.columns else [])
    # Propagar columnas auxiliares si existen
    for aux_col in ('LabelKeyId', 'LabelKeyIdExt', 'SectionKey', 'RoleCode'):
        if aux_col in facts.columns:
            base_cols.append(aux_col)
    facts = facts[base_cols + date_columns].copy()

    # Normalizar Label a string limpio
    facts['Label'] = facts['Label'].astype(str).str.strip()
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG normalize_facts: Columns kept: {list(facts.columns)}")
        print(f"DEBUG normalize_facts: Final shape: {facts.shape}")
        print(f"DEBUG normalize_facts: Sample labels: {facts['Label'].dropna().head().tolist()}")
    
    # Guardar debug
    if os.getenv('X2E_DEBUG') == '1':
        debug_path = Path(__file__).parent / "debug_facts_normalized.csv"
        facts.to_csv(debug_path, index=False)
        print(f"DEBUG: Facts normalizado guardado en {debug_path}")
    
    return facts

def fill_values_from_facts_strict(
    complete_structure: pd.DataFrame,
    facts: pd.DataFrame,
    date_columns: list[str],
    statement_kind: str | None = None,
    debug: bool = False
) -> pd.DataFrame:
    """
    Pega valores de facts a la estructura con coincidencia EXACTA:
      - Clave 1: qname (si existe en facts y podemos inferirlo para la cuenta)
      - Clave 2: etiqueta con ESPACIOS normalizados (sin fuzzy).
    No sobreescribe celdas ya pobladas y nunca llena categorías/headers.
    """

    import re
    import pandas as pd

    if complete_structure.empty or facts.empty:
        return complete_structure.copy()

    def _canon_spaces(s: str) -> str:
        # normaliza espacios y NBSP, pero NO toca mayúsculas, acentos ni signos
        s = (s or "").replace("\xa0", " ")
        return re.sub(r"\s+", " ", s.strip())

    def _is_category(lbl: str) -> bool:
        if not lbl:
            return False
        l = lbl.lower()
        if re.match(r"^\[\d{6}\]\s", lbl):
            return True
        if "[sinopsis]" in l or "[abstract]" in l or "[resumen]" in l:
            return True
        return False

    result = complete_structure.copy()

    # Intersección de columnas de fecha entre facts y estructura (fechas crudas YYYY-MM-DD)
    facts_dates = [c for c in facts.columns if re.match(r"^\d{4}-\d{2}-\d{2}$", str(c))]
    dates_in_common = [d for d in date_columns if d in facts_dates and d in result.columns]
    if not dates_in_common:
        if debug:
            print("DEBUG fill_values_from_facts_strict: no hay fechas en común; nada que copiar.")
        return result

    # Índices para empates exactos
    facts = facts.copy()
    facts["__key_label"] = facts["Label"].astype(str).map(_canon_spaces)

    by_label = {}
    for _, r in facts.iterrows():
        kl = r["__key_label"]
        if kl and kl not in by_label:
            by_label[kl] = r

    # Prioridad máxima: LabelKeyIdExt (incluye contexto), luego LabelKeyId
    by_lkid = {}
    by_lkid_ext = {}
    
    # Preferir LabelKeyIdExt si está disponible (más específico con contexto)
    if 'LabelKeyIdExt' in facts.columns:
        for _, r in facts.iterrows():
            lke = str(r.get('LabelKeyIdExt') or '').strip()
            if lke:
                # Permitir múltiples registros con el mismo LabelKeyIdExt
                # para preservar cuentas duplicadas con diferentes valores
                if lke not in by_lkid_ext:
                    by_lkid_ext[lke] = []
                by_lkid_ext[lke].append(r)
    
    # LabelKeyId básico como fallback
    if 'LabelKeyId' in facts.columns:
        for _, r in facts.iterrows():
            lk = str(r.get('LabelKeyId') or '').strip()
            if lk:
                if lk not in by_lkid:
                    by_lkid[lk] = []
                by_lkid[lk].append(r)

    by_qname = {}
    if "qname" in facts.columns:
        for _, r in facts.iterrows():
            qn = str(r.get("qname") or "").strip()
            if qn and qn not in by_qname:
                by_qname[qn] = r

    # Si ya guardas un mapeo label→qname desde tu taxonomía, úsalo aquí (opcional):
    # label_to_qname = {...}  # si lo tienes preparado
    label_to_qname = None  # dejar None si no tienes el diccionario listo

    applied = 0
    total_candidates = 0

    for idx, row in result.iterrows():
        raw_lbl = str(row.get("Cuenta", "") or row.get("Label", ""))
        if not raw_lbl:
            continue
        if _is_category(raw_lbl):
            continue

        total_candidates += 1

        # 0) intentar por LabelKeyIdExt primero (más específico), luego LabelKeyId
        fact_row = None
        
        # Función auxiliar para consolidar múltiples filas duplicadas
        def _consolidate_duplicate_rows(duplicate_rows, debug_key="", current_context=""):
            """
            Consolida múltiples filas duplicadas considerando el contexto de sección.
            Prioriza filas que coincidan con el contexto actual de la estructura.
            """
            if not duplicate_rows:
                return None
                
            if len(duplicate_rows) == 1:
                return duplicate_rows[0]
                
            # Si hay múltiples filas, crear una fila consolidada con lógica inteligente
            base_row = duplicate_rows[0].copy()
            
            # Intentar determinar el contexto de la cuenta actual desde la estructura
            account_label = str(row.get("Cuenta", "") or row.get("Label", "")).lower()
            
            # Función para obtener prioridad de fila basada en contexto
            def _get_row_priority(dup_row):
                section_key = str(dup_row.get('SectionKey', '')).lower()
                label_ext = str(dup_row.get('LabelKeyIdExt', '')).lower()
                
                priority = 0
                
                # Priorizar según el contexto de la cuenta
                if 'servicios bancarios' in account_label or 'bancarios' in account_label:
                    if 'servicios bancarios' in section_key or 'bancarios' in section_key:
                        priority += 100
                elif 'negocios no bancarios' in account_label or 'no bancarios' in account_label:
                    if 'negocios no bancarios' in section_key or 'no bancarios' in section_key:
                        priority += 100
                elif 'inversión' in account_label or 'inversion' in account_label:
                    if 'inversión' in section_key or 'inversion' in section_key:
                        priority += 100
                elif 'financiación' in account_label or 'financiacion' in account_label:
                    if 'financiación' in section_key or 'financiacion' in section_key:
                        priority += 100
                
                # Priorizar filas que realmente tienen datos
                has_data = False
                for dc in dates_in_common:
                    val = dup_row.get(dc)
                    if not pd.isna(val) and str(val).strip() != "" and str(val).strip() != "0":
                        has_data = True
                        break
                if has_data:
                    priority += 50
                    
                return priority
            
            # Ordenar filas por prioridad (mayor prioridad primero)
            prioritized_rows = sorted(duplicate_rows, key=_get_row_priority, reverse=True)
            
            # Para cada columna de fecha, usar el valor de la fila con mayor prioridad que tenga datos
            for dc in dates_in_common:
                consolidated_value = None
                source_section = None
                
                for dup_row in prioritized_rows:
                    val = dup_row.get(dc)
                    if not pd.isna(val) and str(val).strip() != "":
                        # Evitar valores cero a menos que sea la única opción
                        val_str = str(val).replace(',', '').replace('.', '').replace('-', '').strip()
                        if val_str != "0" or consolidated_value is None:
                            consolidated_value = val
                            source_section = str(dup_row.get('SectionKey', ''))
                            break
                            
                if consolidated_value is not None:
                    base_row[dc] = consolidated_value
            
            if debug and len(duplicate_rows) > 1:
                sections_found = []
                values_by_section = {}
                
                for dup_row in duplicate_rows:
                    section = str(dup_row.get('SectionKey', 'No section'))
                    if section not in sections_found:
                        sections_found.append(section)
                    
                    for dc in dates_in_common:
                        val = dup_row.get(dc)
                        if not pd.isna(val) and str(val).strip() != "":
                            if section not in values_by_section:
                                values_by_section[section] = {}
                            values_by_section[section][dc] = str(val)[:15]
                
                if values_by_section:
                    print(f"DEBUG: Consolidando {len(duplicate_rows)} duplicados para {debug_key}")
                    print(f"DEBUG: Secciones encontradas: {sections_found[:3]}")  # Solo primeras 3
                    for section, vals in list(values_by_section.items())[:2]:  # Solo primeras 2 secciones
                        if vals:
                            first_date_val = list(vals.items())[0] if vals else ("", "")
                            print(f"DEBUG:   {section}: {first_date_val[0]}={first_date_val[1]}")
                    
            return base_row
        
        # Probar LabelKeyIdExt primero si está disponible
        if 'LabelKeyIdExt' in result.columns and by_lkid_ext:
            lke = str(row.get('LabelKeyIdExt') or '').strip()
            if lke and lke in by_lkid_ext:
                fact_rows = by_lkid_ext[lke]
                if fact_rows:
                    current_account = str(row.get("Cuenta", "") or row.get("Label", ""))
                    fact_row = _consolidate_duplicate_rows(fact_rows, f"LabelKeyIdExt:{lke}", current_account)
        
        # Si no encontró con LabelKeyIdExt, intentar con LabelKeyId básico
        if fact_row is None and 'LabelKeyId' in result.columns and by_lkid:
            lkid = str(row.get('LabelKeyId') or '').strip()
            if lkid and lkid in by_lkid:
                fact_rows = by_lkid[lkid]
                if fact_rows:
                    current_account = str(row.get("Cuenta", "") or row.get("Label", ""))
                    fact_row = _consolidate_duplicate_rows(fact_rows, f"LabelKeyId:{lkid}", current_account)

        # 1) intentar por qname si podemos derivarlo
        if label_to_qname:
            qn = label_to_qname.get(raw_lbl)
            if qn:
                fact_row = by_qname.get(qn)

        # 2) si no hay qname o no encontró, intentar por etiqueta con espacios normalizados
        if fact_row is None:
            k = _canon_spaces(raw_lbl)
            fact_row = by_label.get(k)

        if fact_row is None:
            continue

        # Copiar solo celdas vacías
        for dc in dates_in_common:
            v = fact_row.get(dc)
            if pd.isna(v) or str(v).strip() == "":
                continue
            cur = result.at[idx, dc]
            if (cur is None) or (pd.isna(cur)) or (str(cur).strip() == ""):
                result.at[idx, dc] = v
                applied += 1

    if debug:
        print(f"DEBUG fill_values_from_facts_strict: {applied} celdas rellenadas de {total_candidates} cuentas candidatas.")

    return result

def build_tree_and_order(pres: pd.DataFrame) -> pd.DataFrame:
    """
    Soporta AMBOS formatos:
      - Nuevo (RESTRUCTURADO): una sola columna 'Cuenta'
      - Antiguo (Arelle): 'Presentation Relationships' + 'Unnamed:n'
    Devuelve filas con: roleUri, Label, presLabel, depth, order
    """
    
    import re
    import pandas as pd

    _ROLE_CODE = re.compile(r'^\[(\d{6})\]')
    pres = pres.copy()
    pres.columns = pres.columns.str.strip()

    # ----- CAMINO NUEVO: CSV reestructurado (1 columna) -----
    if 'Cuenta' in pres.columns and len(pres.columns) == 1:
        s = pres['Cuenta'].astype(str).str.strip()
        rows, current_role = [], None
        for idx, val in s.items():
            if not val:
                continue
            m = _ROLE_CODE.match(val)
            if m:
                current_role = val  # p.ej. "[310000] Estado del resultado..."
                rows.append({
                    'roleUri': current_role,
                    'Label':  current_role,
                    'presLabel': current_role,
                    'depth': 0,
                    'order': int(idx),
                })
                continue
            if not current_role:
                # si aún no apareció un rol, ignoramos líneas sueltas
                continue
            rows.append({
                'roleUri': current_role,
                'Label':  val,
                'presLabel': val,
                'depth': 1,
                'order': int(idx),
            })
        if not rows:
            return pd.DataFrame({'roleUri':[None],'order':[1],'depth':[0],'Label':['dummy'],'presLabel':['dummy']})
        df = pd.DataFrame(rows)
        df['order'] = df['order'].astype(int)
        df['depth'] = df['depth'].astype(int)
        return df

    # ----- RESPALDO: Formato jerárquico original (Unnamed:n) -----
    result_rows = []
    current_role = None
    # columnas jerárquicas
    hierarchy_cols = [col for col in pres.columns if str(col).startswith('Unnamed:')]
    for idx, row in pres.iterrows():
        first_col_val = row.iloc[0] if not pd.isna(row.iloc[0]) else None
        if first_col_val and str(first_col_val).strip().startswith('['):
            current_role = str(first_col_val).strip()
            result_rows.append({
                'roleUri': current_role,
                'Label': current_role,
                'presLabel': current_role,
                'depth': 0,
                'order': idx
            })
            continue
        if not current_role:
            continue
        element_name, depth = None, 0
        for i, col in enumerate(hierarchy_cols):
            val = row[col] if col in row.index else None
            if not pd.isna(val) and str(val).strip():
                element_name = str(val).strip()
                depth = i + 1
        if not element_name:
            continue
        result_rows.append({
            'roleUri': current_role,
            'Label': element_name,
            'presLabel': element_name,
            'depth': depth,
            'order': idx
        })
    if not result_rows:
        return pd.DataFrame({'roleUri':[None],'order':[1],'depth':[0],'Label':['dummy'],'presLabel':['dummy']})
    return pd.DataFrame(result_rows)





def select_role_tree(p_tree: pd.DataFrame, kind: str) -> pd.DataFrame:
    # Detectar si es presentation restructured
    if len(p_tree.columns) == 1 and 'Cuenta' in p_tree.columns:
        # Para presentation restructured, extraer la sección correspondiente al kind
        return extract_restructured_section(p_tree, kind)
    
    # Lógica original para árbol normal
    mask = p_tree["roleUri"].map(guess_role_kind).eq(kind)
    t = p_tree.loc[mask].copy()
    # Orden estable por order y depth
    t = t.sort_values(["order", "depth"], kind="mergesort").reset_index(drop=True)
    return t


def extract_restructured_section(p_tree: pd.DataFrame, kind: str) -> pd.DataFrame:
    """
    Extrae la sección correspondiente al statement_kind del presentation restructured.
    """
    # Mapear kind a role_id
    role_mapping = {
        "BALANCE": "210000",
        "RESULTADOS": "310000", 
        "FLUJO": "510000"
    }
    
    target_role_id = role_mapping.get(kind, "210000")
    
    # Detección especial para RESULTADOS - buscar [320000] primero
    if kind == "RESULTADOS":
        # Buscar [320000] primero
        for i, row in p_tree.iterrows():
            cuenta = str(row['Cuenta']).strip()
            if '[320000]' in cuenta:
                target_role_id = "320000"
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Detectado [320000] en restructured para RESULTADOS")
                break
    
    # Buscar el header correspondiente
    target_header = f"[{target_role_id}]"
    
    # Encontrar el inicio de la sección
    start_idx = None
    for i, row in p_tree.iterrows():
        cuenta = str(row['Cuenta']).strip()
        if target_header in cuenta:
            start_idx = i
            break
    
    if start_idx is None:
        # Si no encontramos el header, devolver DataFrame vacío
        return pd.DataFrame(columns=['Cuenta'])
    
    # Encontrar el final de la sección (próximo header de role)
    end_idx = len(p_tree)
    for i in range(start_idx + 1, len(p_tree)):
        cuenta = str(p_tree.iloc[i]['Cuenta']).strip()
        if re.match(r'^\s*\[(\d{6})\]', cuenta):
            end_idx = i
            break
    
    # Extraer la sección
    section = p_tree.iloc[start_idx:end_idx].copy().reset_index(drop=True)
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Extraída sección {kind} del restructured: {len(section)} filas")
    
    return section


def choose_label(group: pd.DataFrame) -> str:
    """Simplemente retorna el primer Label del grupo ya que solo tenemos Label y fechas."""
    if group.empty:
        return ""
    
    # Como ya solo tenemos Label y fechas, simplemente retornamos el Label
    return group.iloc[0]["Label"] if "Label" in group.columns else ""

def restructure_presentation_to_single_column(presentation_path: str) -> str:
    """
    Reestructura presentation.csv a una sola columna 'Cuenta':
    - SOLO árbol: 'Presentation Relationships' + columnas hasta ANTES de 'Pref. Label'
    - Ignora por completo 'Pref. Label', 'Type', 'References'
    - CONSERVA roles [xxxxx] y etiquetas con [sinopsis]
    - EXCLUYE valores propios de Type (TextBlock, Date, String, etc.) y References (IAS/IFRS/MC con fecha)
    - Evita duplicados, respeta orden
    """
    import pandas as pd
    import re
    from pathlib import Path
    p = Path(presentation_path)
    if not p.exists():
        print(f"      ║ ERROR: No se encontró {presentation_path}")
        return presentation_path

    print("      ║ Reestructurando árbol de presentación → 1 columna (sin Pref. Label/Type/References)…")

    # Cargar todo como texto
    df = pd.read_csv(presentation_path, dtype=str)

    # Detectar columna base del árbol
    cols = list(df.columns)
    try:
        start_idx = next(i for i, c in enumerate(cols)
                         if "presentation" in str(c).lower() and "relationship" in str(c).lower())
    except StopIteration:
        start_idx = 0
        print(f"      ║ ADVERTENCIA: no se encontró 'Presentation Relationships', usando {cols[start_idx]}")

    # Encontrar límite (la primera aparición de 'Pref. Label' si existe)
    cut_names = ["Pref. Label", "Pref.Label", "Pref Label"]
    end_idx = None
    for name in cut_names:
        if name in cols:
            end_idx = cols.index(name)
            break
    if end_idx is None:
        # Si no hay 'Pref. Label', usamos todas las columnas restantes (caso raro)
        end_idx = len(cols)

    # Tomar SOLO las columnas del árbol (desde start hasta ANTES de 'Pref. Label')
    tree_cols = cols[start_idx:end_idx]
    tree = df[tree_cols].map(lambda x: x.strip() if isinstance(x, str) else x)

    # --- Filtros ---
    # 1) Valores típicos de Type (no son cuentas)
    type_literals = {"TextBlock", "Date", "String", "Boolean", "Monetary", "Instant", "Duration"}
    # 2) Patrón típico de References (MC/IAS/IFRS/NIC/NIIF + fecha)
    refs_re = re.compile(r"^(MC|IAS|IFRS|NIC|NIIF)\b.*\d{4}-\d{2}-\d{2}", re.IGNORECASE)

    def keep_item(txt: str) -> bool:
        """
        Mantener:
          - Todo (incluye [sinopsis] y roles [xxxxx])
        Excluir:
          - Cadenas de Type (TextBlock, Date, String, …)
          - Líneas que lucen como References (MC/IAS/IFRS/NIC/NIIF + fecha)
        """
        if not txt or not txt.strip():
            return False
        if txt in type_literals:
            return False
        if refs_re.match(txt):
            return False
        return True  # NO filtramos [sinopsis] ni [xxxxx]

    # Colapsar: tomar el valor más profundo (última celda no vacía por fila, dentro del árbol)
    cuentas = []
    for _, row in tree.iterrows():
        last_val = None
        for val in reversed(row.tolist()):
            if isinstance(val, str) and val.strip():
                last_val = val.strip()
                break
        if last_val and keep_item(last_val):
            cuentas.append(last_val)

    # Lista final sin duplicados (preserva el primer encuentro)
    out = pd.DataFrame({"Cuenta": pd.Index(cuentas).drop_duplicates(keep="first")})

    output_path = presentation_path.replace(".csv", "_restructured.csv")
    out.to_csv(output_path, index=False)

    print(f"      ║ Presentation reestructurado: {len(out)} cuentas (roles y [sinopsis] incluidos; sin Type/References)")
    print(f"      ║ Guardado en: {Path(output_path).name}")
    return output_path


def extract_all_accounts_from_presentation(presentation_df: pd.DataFrame, statement_kind: str) -> list[str]:
    if presentation_df.empty or 'Cuenta' not in presentation_df.columns:
        return []

    # Usar autodetección para RESULTADOS
    if statement_kind == "RESULTADOS":
        income_role = detect_income_statement_role(presentation_df)
        role_codes = {"BALANCE": "210000", "RESULTADOS": income_role, "FLUJO": "510000"}
    else:
        role_codes = {"BALANCE": "210000", "RESULTADOS": "310000", "FLUJO": "510000"}
    
    target_role = role_codes.get(statement_kind)
    if not target_role:
        return []

    header_target = re.compile(rf'^\s*["\']?\[{target_role}\]', re.I)
    any_header    = re.compile(r'^\s*["\']?\[(\d{6})\]', re.I)

    accounts = []
    in_target = False

    for account in presentation_df['Cuenta']:
        s = str(account or '').strip()
        if header_target.match(s):
            in_target = True
            accounts.append(s)
            continue

        m_any = any_header.match(s)
        if m_any:
            # nuevo header: solo seguimos si es el mismo rol; si no, salimos
            code = m_any.group(1)
            if in_target and code != target_role:
                break
            in_target = (code == target_role)
            if in_target:
                accounts.append(s)
            continue

        if in_target and s and s not in accounts:
            accounts.append(s)

    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Extraidas {len(accounts)} cuentas para {statement_kind} (presentation, corte por headers).")
    return accounts




def build_complete_statement_structure(
    statement_kind: str,
    lang: str = "es",
    date_columns: list[str] = None,
    presentation_tree: pd.DataFrame = None,
    facts_df: pd.DataFrame = None,
    is_consolidated_facts: bool = False,  # NUEVO parámetro
    company_rut: str = None  # NUEVO: RUT de la empresa para estructura específica
) -> pd.DataFrame:
    """
    Construye estructura completa de estados financieros desde taxonomía,
    independiente de si hay valores en facts o no.
    """
    if date_columns is None:
        date_columns = []
    
    # Obtener mapeo híbrido para el tipo de estado
    complete_mapping = build_hybrid_mapping(presentation_tree, lang, company_rut) if presentation_tree is not None else build_complete_mapping(lang, company_rut)
    
    # Verificar si tenemos estructura específica de empresa
    has_company_structure = False
    if company_rut:
        company_mapping = load_company_specific_structure(company_rut, lang)
        has_company_structure = bool(company_mapping)
        if has_company_structure and os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Estructura específica detectada para {company_rut} - NO agregando cuentas adicionales de facts")
    
    # NUEVA ESTRATEGIA: Si tenemos presentation restructured, agregamos cuentas faltantes de facts
    # PERO SOLO si NO tenemos estructura específica de empresa
    if facts_df is not None and presentation_tree is not None and not has_company_structure:
        # Detectar si el presentation es restructured (tiene solo columna 'Cuenta')
        is_restructured = len(presentation_tree.columns) == 1 and 'Cuenta' in presentation_tree.columns
        
        if is_restructured:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Detectado presentation restructured, agregando cuentas faltantes de facts")
            
            # Usar la nueva función para agregar cuentas faltantes de facts
            # Para facts consolidados, usar lógica especial que respete el orden original
            if is_consolidated_facts:
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Usando add_missing_facts_accounts especial para facts consolidados")
                presentation_tree = _add_missing_facts_preserve_order(presentation_tree, facts_df, statement_kind, lang)
            else:
                presentation_tree = add_missing_facts_accounts(presentation_tree, facts_df, statement_kind, lang)
            
            # Ahora construir el mapeo desde el presentation actualizado
            complete_mapping = build_hybrid_mapping(presentation_tree, lang)
        else:
            # Lógica original para presentations normales
            try:
                complete_mapping = ensure_missing_accounts_from_presentation(
                    presentation_tree, complete_mapping, statement_kind, facts_df, lang
                )
            except Exception as e:
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Error reforzando mapeo desde presentation actual: {e}")
    elif has_company_structure and os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Saltando agregado de cuentas faltantes - usando estructura específica de empresa")
    # Sistema de fallback: usar role primario, si no hay datos usar alternativo
    role_fallbacks = {
        "BALANCE": ["210000", "220000"],      # Primero corriente/no corriente, luego orden liquidez
        "RESULTADOS": ["310000", "320000"],   # Primero función, luego naturaleza
        "FLUJO": ["510000", "520000"],        # Primero directo, luego indirecto
        "PATRIMONIO": ["610000"]              # Solo uno disponible
    }
    
    # Buscar el primer role que tenga datos EN LA REALIDAD (en presentation/facts)
    role_candidates = role_fallbacks.get(statement_kind, ["210000"])
    role_items = []
    used_role_id = None
    
    # FALLBACK SÚPER SIMPLE: buscar [320000] en presentation, si existe usar ese
    if statement_kind == "RESULTADOS" and presentation_tree is not None:
        # Buscar específicamente [320000] en el presentation tree
        has_320000 = presentation_tree.astype(str).apply(lambda x: x.str.contains(r'\[320000\]', na=False)).any().any()
        if has_320000:
            # FORZAR uso de 320000
            items_320000 = complete_mapping.get("320000", [])
            if items_320000:
                role_items = items_320000
                used_role_id = "320000"
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"🎯 DETECTADO [320000] en presentation - FORZANDO uso de role 320000")
                    print(f"✅ USANDO ROLE 320000 para {statement_kind} ({len(items_320000)} cuentas)")
    
    # Si no se forzó 320000, usar orden normal
    if not role_items:
        for role_id in role_candidates:
            items = complete_mapping.get(role_id, [])
            if items:
                role_items = items
                used_role_id = role_id
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"✅ USANDO ROLE: {role_id} para {statement_kind} ({len(items)} cuentas)")
                break
    
    if not role_items and role_candidates:
        # Si ningún role tiene datos, usar el primero como fallback
        used_role_id = role_candidates[0]
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontraron datos, usando role por defecto {used_role_id}")
    
    if not role_items:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontraron items para role {used_role_id}")
        return pd.DataFrame()
    
    # Crear estructura base con todas las cuentas de la taxonomía
    accounts_data = []
    
    # Usar el role_id seleccionado
    final_role_id = used_role_id or "210000"
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"🎯 FORZANDO HEADER DE TAXONOMÍA: {final_role_id} para {statement_kind}")
    role_headers = {
        "210000": "[210000] Estado de situación financiera, corriente/no corriente",
        "220000": "[220000] Estado de situación financiera, orden de liquidez",
        "310000": "[310000] Estado del resultado, por función de gasto", 
        "320000": "[320000] Estado del resultado, por naturaleza de gasto",
        "420000": "[420000] Estado de Resultados Integral",
        "510000": "[510000] Estado de flujos de efectivo, método directo",
        "520000": "[520000] Estado de flujos de efectivo, método indirecto",
        "610000": "[610000] Estado de Cambio en el Patrimonio"
    }
    
    header_label = role_headers.get(final_role_id, f"[{final_role_id}] Estado financiero")
    
    # Header del estado
    header_row = {
        'roleUri': f'[{final_role_id}]',
        'Label': header_label,
        'presLabel': header_label,
        'Cuenta': header_label,
        'RoleCode': final_role_id,
        'LabelKeyId': f"{final_role_id}||{header_label}",
        'depth': 0,
        'order': 0
    }
    
    # Agregar columnas de fechas vacías para el header
    for col in date_columns:
        header_row[col] = None
        
    accounts_data.append(header_row)
    
    # Agregar TODAS las cuentas de la taxonomía para este rol EN EL ORDEN ORIGINAL
    order = 1
    for qname, label in role_items:
        # Los elementos ya están filtrados para tener prefijo
        account_row = {
            'roleUri': f'[{final_role_id}]',
            'Label': label,
            'presLabel': label,
            'Cuenta': label,
            'qname': qname,
            'RoleCode': final_role_id,
            'LabelKeyId': f"{final_role_id}||{label}",
            'depth': 1,
            'order': order
        }
        
        # Agregar columnas de fechas vacías
        for col in date_columns:
            account_row[col] = None
            
        accounts_data.append(account_row)
        
        # Debug para la cuenta problemática
        if os.getenv('X2E_DEBUG') == '1':
            if 'primas' in label.lower() and 'pagos' in label.lower():
                print(f"🔍 CUENTA PROBLEMÁTICA AGREGADA A ESTRUCTURA:")
                print(f"   Order: {order}")
                print(f"   QName: {qname}")
                print(f"   Label: {label}")
            
        order += 1
    
    # Crear DataFrame
    df = pd.DataFrame(accounts_data)
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Estructura completa creada para {statement_kind}: {len(df)} cuentas")
        
    return df

def fill_values_from_facts(
    complete_structure: pd.DataFrame,
    facts: pd.DataFrame,
    date_columns: list[str],
    statement_kind: str = None
) -> pd.DataFrame:
    """
    Relleno ESTRICTO por coincidencia exacta de etiqueta:
    - Se matchea 'Cuenta' (structure) == 'Label' (facts), con .strip() en ambos lados (case-sensitive).
    - Se usa SOLO el facts que llega por parámetro (ya filtrado por rol en compose_statement).
    - Si hay múltiples contextos para la misma cuenta/fecha:
        * si hay 0 o >1 valores no nulos distintos => deja NaN (evita mezclar)
        * si hay exactamente 1 valor no nulo => usa ese
    - Corrige el bug de índices usando un _rid estable para escribir de vuelta.
    - NO escala por miles acá (la escala se aplica al escribir el Excel).
    """
    import pandas as _pd

    if facts is None or facts.empty or complete_structure is None or complete_structure.empty:
        return complete_structure

    print(f"      ║ Ejecutando mapeo estricto para {len(complete_structure)} cuentas...")

    # Copia base + índice estable para re-asignar por fila
    result = complete_structure.copy()
    result['_rid'] = range(len(result))
    result['_cuenta_key'] = result['Cuenta'].astype(str).str.strip()

    # Limpiar facts y preparar claves de unión exacta
    facts_clean = facts.copy()
    if 'Label' not in facts_clean.columns:
        return result.drop(columns=['_rid', '_cuenta_key'], errors='ignore')

    facts_clean = facts_clean[facts_clean['Label'].notna() & (facts_clean['Label'].astype(str).str.strip() != '')].copy()
    facts_clean['_label_key'] = facts_clean['Label'].astype(str).str.strip()

    # Columnas a conservar del facts (Label + qname/contextRef si existen + fechas presentes)
    keep = ['_label_key', 'Label']
    if 'qname' in facts_clean.columns:
        keep.append('qname')
    if 'contextRef' in facts_clean.columns:
        keep.append('contextRef')
    keep_dates = [c for c in date_columns if c in facts_clean.columns]
    keep += keep_dates
    facts_used = facts_clean[keep].copy()

    # Merge 1:N (porque puede haber múltiples contextRef por misma etiqueta)
    merged = result.merge(
        facts_used,
        left_on='_cuenta_key',
        right_on='_label_key',
        how='left',
        suffixes=('', '_f')
    )

    # Para cada columna de fecha, agregamos por _rid:
    # - si un _rid tiene >1 valores no nulos distintos => NaN (ambiguo)
    # - si tiene exactamente 1 valor no nulo => ese
    for col in date_columns:
        if col not in keep_dates:
            # Si la fecha no existe en facts_used, garantizamos la columna en result como vacía
            if col not in result.columns:
                result[col] = _pd.NA
            continue

        # Convertir a numérico sin escalar aquí (la escala se aplica al escribir en Excel)
        s = _pd.to_numeric(merged[col], errors='coerce')

        # Conteo de valores no nulos por cuenta
        nonnull_count = s.groupby(merged['_rid']).apply(lambda x: x.notna().sum())

        # Número de valores no nulos DISTINTOS por cuenta
        nunique_nonnull = s.groupby(merged['_rid']).nunique(dropna=True)

        # Primer valor no nulo (si existe)
        first_value = s.groupby(merged['_rid']).first()

        # Armamos la serie agregada respetando la regla de ambigüedad
        agg = first_value.copy()
        # donde haya 0 valores => NaN
        agg[nonnull_count.fillna(0) == 0] = _pd.NA
        # donde haya >1 distintos => NaN (ambiguo)
        agg[nunique_nonnull.fillna(0) > 1] = _pd.NA

        # Diagnóstico opcional
        if os.getenv('X2E_DEBUG') == '1':
            amb = int((nunique_nonnull.fillna(0) > 1).sum())
            zeros = int((nonnull_count.fillna(0) == 0).sum())
            print(f"DEBUG: {col}: grupos sin dato={zeros}, ambiguos={amb}")

        # Escribimos por _rid, evitando el bug de índices del merge 1:N
        if col not in result.columns:
            result[col] = _pd.NA
        result[col] = agg.reindex(result['_rid']).values

    # Limpiar valores en filas de categorías ([xxxxxx], [sinopsis], etc.)
    sinopsis_mask = result['Cuenta'].str.contains('\\[sinopsis\\]', case=False, na=False, regex=True)
    abstract_mask = result['Cuenta'].str.contains('\\[abstract\\]', case=False, na=False, regex=True)
    resumen_mask  = result['Cuenta'].str.contains('\\[resumen\\]',  case=False, na=False, regex=True)
    role_header_mask = result['Cuenta'].str.match(r'^\[\d{6}\]\s+', na=False)
    category_mask = sinopsis_mask | abstract_mask | resumen_mask | role_header_mask

    for col in date_columns:
        if col in result.columns:
            result.loc[category_mask, col] = _pd.NA

    # Limpieza de columnas temporales
    result = result.drop(columns=['_rid', '_cuenta_key'], errors='ignore')

    # Resumen
    accounts_with_data = 0
    for _, row in result.iterrows():
        if any((col in result.columns) and _pd.notna(row.get(col)) for col in date_columns):
            accounts_with_data += 1
    print(f"      ║ Mapeo completado (estricto): {accounts_with_data}/{len(result)} cuentas con valores")

    return result


def enhance_account_mapping(
    merged: pd.DataFrame,
    statement_kind: str,
    lang: str = "es",
    output_dir: Path | None = None,
    presentation_data: pd.DataFrame | None = None,
    facts_data: pd.DataFrame | None = None
) -> pd.DataFrame:
    """
    Mejora el mapeo de cuentas usando estrategia facts-first: todas las cuentas con valores deben aparecer.
    """
    # Obtener mapeo híbrido para el tipo de estado actual
    account_mapping = get_account_mapping(lang, presentation_data)
    
    # NUEVA ESTRATEGIA: Asegurar que las cuentas faltantes de presentation aparezcan
    if facts_data is not None and presentation_data is not None:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: facts_data disponible para {statement_kind}, shape: {facts_data.shape}")
        account_mapping = ensure_missing_accounts_from_presentation(
            presentation_data, account_mapping, statement_kind, facts_data, lang
        )
    else:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: facts_data NO disponible para {statement_kind}")
    role_mapping = {}
    
    # Determinar role_id según statement_kind
    role_id_map = {
        "BALANCE": "210000",
        "RESULTADOS": "310000", 
        "FLUJO": "510000"
    }
    
    role_id = role_id_map.get(statement_kind, "210000")
    role_items = account_mapping.get(role_id, [])
    
    # Convertir lista de tuplas a dict para compatibilidad
    role_mapping = {qname: label for qname, label in role_items}
    
    if not role_mapping:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontró mapeo para role {role_id}")
        return merged
    
    unmapped_accounts = []
    mapped_count = 0
    
    # Mejorar mapeo usando taxonomía completa
    for idx, row in merged.iterrows():
        original_label = row.get('Label', '')
        
        # Intentar mapeo por qname exacto
        qname = row.get('qname', '')
        if qname and qname in role_mapping:
            new_label = role_mapping[qname]
            merged.at[idx, 'Cuenta'] = new_label
            merged.at[idx, 'Label'] = new_label
            mapped_count += 1
            continue
            
        # Intentar mapeo por nombre sin prefijo
        if qname and ':' in qname:
            name_only = qname.split(':', 1)[1]
            if name_only in role_mapping:
                new_label = role_mapping[name_only]
                merged.at[idx, 'Cuenta'] = new_label
                merged.at[idx, 'Label'] = new_label
                mapped_count += 1
                continue
        
        # Intentar mapeo por Label exacto
        if original_label in role_mapping:
            new_label = role_mapping[original_label]
            merged.at[idx, 'Cuenta'] = new_label
            mapped_count += 1
            continue
            
        # SOLO mapeo exacto (case-insensitive)
        if original_label:
            original_lower = original_label.lower()
            exact_match = None
            
            # Buscar coincidencia exacta case-insensitive
            for key, value in role_mapping.items():
                if original_lower == key.lower():
                    exact_match = value
                    break
            
            if exact_match:
                merged.at[idx, 'Cuenta'] = exact_match
                mapped_count += 1
                continue
        
        # No se pudo mapear
        if original_label and not original_label.startswith('['):
            unmapped_accounts.append(original_label)
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG enhance_account_mapping {statement_kind}:")
        print(f"  - Cuentas mapeadas: {mapped_count}")
        print(f"  - Cuentas sin mapear: {len(unmapped_accounts)}")
        if unmapped_accounts:
            print(f"  - Ejemplos sin mapear: {unmapped_accounts[:5]}")
    
    # Escribir reporte de cuentas no mapeadas si hay directorio de salida
    if output_dir and unmapped_accounts:
        write_unmapped_accounts_report(unmapped_accounts, statement_kind, output_dir)
    
    return merged


def create_legacy_merged_structure(
    facts_main: pd.DataFrame,
    tree: pd.DataFrame,
    all_dates: list[str],
    statement_kind: str,
    lang: str,
    presentation_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """
    Crea estructura merged usando el método original basado en tree + facts.
    """
    def date_cols_of(df: pd.DataFrame) -> list[str]:
        if df is None:
            return []
        return [c for c in df.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(c))]
    
    dates_main = set(date_cols_of(facts_main))
    
    # Preparar dataset principal con Label y qname si existe
    facts_for_merge_cols = ['Label'] + (['qname'] if 'qname' in facts_main.columns else []) + list(dates_main)
    facts_for_merge = facts_main[facts_for_merge_cols].copy()

    # Unir árbol con facts principal por Label; si queda vacío, intentar por qname
    merged = tree.merge(facts_for_merge, on="Label", how="left")
    if merged[date_cols_of(facts_main)].isna().all().all() and 'qname' in facts_for_merge.columns:
        # Intentar unir por qname
        try:
            merged_q = tree.merge(facts_for_merge.rename(columns={'qname': 'Label'}), on='Label', how='left')
            # Si trajo más datos, usarlo
            if not merged_q[date_cols_of(facts_main)].isna().all().all():
                merged = merged_q
        except Exception:
            pass
    
    merged["Cuenta"] = merged.get("presLabel", merged["Label"]).fillna(merged["Label"]).infer_objects(copy=False)
    
    # Aplicar mapeo mejorado usando taxonomía completa
    if statement_kind:
        output_dir = None
        try:
            if hasattr(facts_main, 'attrs') and 'source_path' in facts_main.attrs:
                output_dir = Path(facts_main.attrs['source_path']).parent
        except Exception:
            pass
        # Ya no necesitamos mapeo externo - todo viene de facts
    
    return merged


def add_cash_beginning_period(df: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega fila 'Efectivo y equivalentes al efectivo al principio del periodo'
    antes de 'Efectivo y equivalentes al efectivo al final del periodo'.
    
    Los valores son el 'Efectivo al final del periodo' del período anterior.
    Solo agrega si no existe ya una cuenta de "al principio del periodo".
    """
    if df.empty:
        return df
    
    # NUEVA VALIDACIÓN: Verificar si ya existe "Efectivo al principio del periodo"
    efectivo_principio_mask = df['Cuenta'].str.contains(
        'Efectivo y equivalentes al efectivo al principio del periodo', 
        na=False, 
        case=False
    )
    
    if efectivo_principio_mask.any():
        if os.getenv('X2E_DEBUG') == '1':
            existing_count = efectivo_principio_mask.sum()
            print(f"DEBUG: Ya existe(n) {existing_count} cuenta(s) de 'Efectivo al principio del periodo'")
            
            # Verificar si tiene datos
            principio_rows = df[efectivo_principio_mask]
            date_columns = [col for col in df.columns if col != 'Cuenta']
            has_data = False
            for _, row in principio_rows.iterrows():
                for col in date_columns:
                    if pd.notna(row[col]) and row[col] is not None and str(row[col]) not in ['', 'nan', '0', '0.0']:
                        has_data = True
                        break
                if has_data:
                    break
            
            if has_data:
                print(f"DEBUG: La cuenta existente ya tiene datos - no se modificará")
                return df
            else:
                print(f"DEBUG: La cuenta existente está vacía - se calculará automáticamente")
                # Continuar con el cálculo pero actualizar la fila existente en lugar de agregar nueva
        
        # Si llegamos aquí, existe pero está vacía - necesitamos calcularla
    
    # Buscar la fila de "Efectivo al final del periodo"
    efectivo_final_mask = df['Cuenta'].str.contains(
        'Efectivo y equivalentes al efectivo al final del periodo', 
        na=False, 
        case=False
    )
    
    if not efectivo_final_mask.any():
        if os.getenv('X2E_DEBUG') == '1':
            print("DEBUG: No se encontró 'Efectivo al final del periodo' - no se agregará fila al principio")
        return df
    
    efectivo_final_row = df[efectivo_final_mask].iloc[0]
    efectivo_final_index = df[efectivo_final_mask].index[0]
    
    # Determinar si vamos a crear nueva fila o actualizar existente
    create_new_row = not efectivo_principio_mask.any()
    efectivo_principio_index = None
    
    if create_new_row:
        # Crear nueva fila de "Efectivo al principio del periodo"
        efectivo_principio_row = efectivo_final_row.copy()
        efectivo_principio_row['Cuenta'] = 'Efectivo y equivalentes al efectivo al principio del periodo'
    else:
        # Usar la fila existente pero copiar la estructura de la final
        efectivo_principio_index = efectivo_principio_mask.idxmax()
        efectivo_principio_row = df.loc[efectivo_principio_index].copy()
        # Mantener el nombre original de la cuenta
    
    # Obtener columnas de fechas (excluyendo 'Cuenta')
    date_columns = [col for col in df.columns if col != 'Cuenta']
    
    # Desplazar valores: inicio de Q2 = final de Q1, inicio de Q1 = final de Q4_prev, etc.
    if len(date_columns) > 1:
        # Procesar desde el segundo período hasta el final
        for i in range(len(date_columns)):
            current_col = date_columns[i]
            if i == len(date_columns) - 1:
                # La última columna (período más antiguo) queda vacía
                efectivo_principio_row[current_col] = pd.NA
            else:
                # Valor del principio del período actual = Valor del final del período siguiente (más antiguo)
                prev_col = date_columns[i + 1]
                raw_value = efectivo_final_row[prev_col]
                
                # Convertir string con formato a número puro para el validador
                if pd.notna(raw_value) and raw_value is not None:
                    try:
                        if isinstance(raw_value, str):
                            # Limpiar formato: quitar comas y convertir a float
                            clean_val = raw_value.replace(',', '').replace('"', '').strip()
                            if clean_val and clean_val != 'nan':
                                numeric_val = float(clean_val)
                                efectivo_principio_row[current_col] = numeric_val
                            else:
                                efectivo_principio_row[current_col] = pd.NA
                        else:
                            # Ya es numérico, usar directamente
                            efectivo_principio_row[current_col] = raw_value
                    except (ValueError, TypeError):
                        efectivo_principio_row[current_col] = pd.NA
                else:
                    efectivo_principio_row[current_col] = pd.NA
    
    if os.getenv('X2E_DEBUG') == '1':
        action = "Agregando" if create_new_row else "Actualizando"
        print(f"DEBUG: {action} 'Efectivo al principio del periodo' - índice {efectivo_final_index if create_new_row else efectivo_principio_index}")
        print(f"DEBUG: Columnas procesadas: {date_columns}")
    
    if create_new_row:
        # Insertar la nueva fila justo antes de "Efectivo al final del periodo"
        # Crear DataFrame con la nueva fila
        new_row_df = pd.DataFrame([efectivo_principio_row])
        
        # Dividir el DataFrame original en dos partes
        before_final = df.iloc[:efectivo_final_index]
        from_final = df.iloc[efectivo_final_index:]
        
        # Concatenar: antes + nueva fila + desde final
        result_df = pd.concat([before_final, new_row_df, from_final], ignore_index=True)
        
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Nueva fila agregada. DataFrame final tiene {len(result_df)} filas (original: {len(df)})")
    else:
        # Actualizar la fila existente
        result_df = df.copy()
        result_df.loc[efectivo_principio_index] = efectivo_principio_row
        
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: Fila existente actualizada. DataFrame mantiene {len(result_df)} filas")
    
    return result_df


def _reorder_balance_accounts(df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    Reordena las cuentas del balance según la jerarquía conceptual típica:
    1. Header [210000]
    2. Activos (corrientes, no corrientes) 
    3. Pasivos (corrientes, no corrientes)
    4. Patrimonio
    5. Total patrimonio y pasivos
    """
    if df.empty:
        return df
    
    # Definir patrones de orden para balance
    order_patterns = [
        # 1. Header
        (r'\[210000\]', 0),
        # 2. Estado de situación financiera [sinopsis]  
        (r'Estado de situación financiera \[sinopsis\]', 1),
        
        # 3. ACTIVOS
        (r'^Activos \[sinopsis\]$', 10),
        (r'Negocios no bancarios \[sinopsis\]', 11),
        (r'Activos corrientes \[sinopsis\]', 12),
        (r'Efectivo y equivalentes al efectivo', 13),
        (r'Otros activos financieros corrientes', 14),
        (r'Otros activos no financieros corrientes', 15),
        (r'Deudores comerciales y otras cuentas por cobrar corrientes', 16),
        (r'Cuentas por cobrar a entidades relacionadas, corrientes', 17),
        (r'Inventarios corrientes', 18),
        (r'Activos por impuestos corrientes, corrientes', 19),
        (r'Total de activos corrientes distintos de los activos', 20),
        (r'Activos no corrientes o grupos de activos para su disposición', 21),
        (r'Activos corrientes totales', 22),
        
        # Activos no corrientes
        (r'Activos no corrientes \[sinopsis\]', 30),
        (r'Otros activos financieros no corrientes', 31),
        (r'Otros activos no financieros no corrientes', 32),
        (r'Cuentas por cobrar no corrientes', 33),
        (r'Inversiones contabilizadas utilizando el método de la participación', 34),
        (r'Activos intangibles distintos de la plusvalía', 35),
        (r'Plusvalía', 36),
        (r'Propiedades, planta y equipo', 37),
        (r'Activos por derecho de uso', 38),
        (r'Activos por impuestos diferidos', 39),
        (r'Total de activos no corrientes', 40),
        
        # Totales activos
        (r'Total activos de negocios no bancarios', 50),
        (r'Activos Bancarios \[sinopsis\]', 51),
        (r'Instrumentos para negociación', 52),
        (r'Contratos de retrocompra y préstamos de valores', 53),
        (r'Créditos y cuentas por cobrar a clientes', 54),
        (r'Instrumentos de inversión disponibles para la venta', 55),
        (r'Instrumentos de inversión hasta el vencimiento', 56),
        (r'Intangibles', 57),
        (r'Activo fijo', 58),
        (r'Total activos servicios bancarios', 59),
        (r'Total de activos', 60),
        
        # 4. PASIVOS
        (r'^Pasivos \[sinopsis\]$', 100),
        (r'Pasivos corrientes \[sinopsis\]', 101),
        (r'Otros pasivos financieros corrientes', 102),
        (r'Cuentas por pagar comerciales y otras cuentas por pagar', 103),
        (r'Cuentas por pagar a entidades relacionadas, corrientes', 104),
        (r'Otras provisiones a corto plazo', 105),
        (r'Pasivos por impuestos corrientes, corrientes', 106),
        (r'Provisiones corrientes por beneficios a los empleados', 107),
        (r'Otros pasivos no financieros corrientes', 108),
        (r'Pasivos por arrendamientos corrientes', 109),
        (r'Total de pasivos corrientes distintos de los pasivos', 110),
        (r'Pasivos corrientes totales', 111),
        
        # Pasivos no corrientes  
        (r'Pasivos no corrientes \[sinopsis\]', 120),
        (r'Otros pasivos financieros no corrientes', 121),
        (r'Cuentas por pagar no corrientes', 122),
        (r'Otras provisiones a largo plazo', 123),
        (r'Pasivo por impuestos diferidos', 124),
        (r'Provisiones no corrientes por beneficios a los empleados', 125),
        (r'Otros pasivos no financieros no corrientes', 126),
        (r'Pasivos por arrendamientos no corrientes', 127),
        (r'Total de pasivos no corrientes', 128),
        
        # Totales pasivos
        (r'Total pasivos de negocios no bancarios', 140),
        (r'Pasivos Servicios Bancarios \[sinopsis\]', 141),
        (r'Depósitos y otras obligaciones a la vista', 142),
        (r'Contratos de retrocompra y préstamos de valores', 143),
        (r'Depósitos y otras captaciones a plazo', 144),
        (r'Otras obligaciones financieras', 145),
        (r'Instrumentos de deuda emitidos', 146),
        (r'Obligación Subordinada al Banco Central de Chile', 147),
        (r'Provisiones', 148),
        (r'Total pasivos Servicios Bancarios', 149),
        (r'Total de pasivos', 150),
        
        # 5. PATRIMONIO
        (r'Patrimonio \[sinopsis\]$', 200),
        (r'Capital emitido y pagado$', 201),
        (r'^Capital emitido$', 201),  # Variación del anterior
        (r'Ganancias \(pérdidas\) acumuladas', 202),
        (r'Prima de emisión', 203),
        (r'Otras reservas', 204),
        (r'Patrimonio atribuible a los propietarios de la controladora', 205),
        (r'Participaciones no controladoras', 206),
        (r'Patrimonio total', 207),
        
        # 6. TOTAL FINAL
        (r'Total de patrimonio y pasivos', 300),
    ]
    
    # Asignar órdenes a cada fila
    df_with_order = df.copy()
    df_with_order['_sort_order'] = 9999  # Valor por defecto para cuentas no clasificadas
    
    for pattern, order_value in order_patterns:
        mask = df_with_order['Label'].str.contains(pattern, case=False, regex=True, na=False)
        df_with_order.loc[mask, '_sort_order'] = order_value
        
        if debug and mask.any():
            matched_count = mask.sum()
            print(f"DEBUG: Patrón '{pattern}' -> orden {order_value}, {matched_count} cuentas")
    
    # Ordenar por orden asignado, manteniendo orden original para empates
    df_with_order['_original_order'] = range(len(df_with_order))
    df_sorted = df_with_order.sort_values(['_sort_order', '_original_order']).drop(['_sort_order', '_original_order'], axis=1)
    
    if debug:
        print(f"DEBUG: Balance reordenado - Primeras 5: {df_sorted['Label'].head(5).tolist()}")
        print(f"DEBUG: Balance reordenado - Últimas 5: {df_sorted['Label'].tail(5).tolist()}")
    
    return df_sorted.reset_index(drop=True)


def clean_duplicate_values_by_context(facts_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    Limpia valores duplicados incorrectos en facts consolidados.
    En lugar de eliminar filas, limpia los valores que están en el contexto incorrecto.
    Mantiene todas las filas pero solo deja valores donde corresponden según su SectionKey.
    """
    if facts_df.empty:
        return facts_df
    
    # Pre-calcular columnas de fechas
    date_columns = [col for col in facts_df.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(col))]
    
    # Agrupar por Label (cuenta conceptual) para encontrar duplicados
    grouped = facts_df.groupby('Label', sort=False)
    
    result_df = facts_df.copy()
    cleaned_count = 0
    processed_labels = 0
    
    for label, group in grouped:
        if len(group) <= 1:
            continue  # No hay duplicados
            
        processed_labels += 1
        group_list = group.to_dict('records')
        group_indices = group.index.tolist()
        
        # Encontrar cuál fila tiene el valor más relevante para cada fecha
        for dc in date_columns:
            values_by_section = {}
            non_empty_rows = []
            
            # Recopilar valores por sección
            for idx, (row_idx, row) in enumerate(zip(group_indices, group_list)):
                val = row.get(dc)
                section_key = str(row.get('SectionKey', '')).lower()
                
                if val is not None and not pd.isna(val):
                    val_str = str(val).replace(',', '').replace('-', '').strip()
                    if val_str and val_str != "0":  # Tiene un valor real
                        values_by_section[section_key] = {
                            'value': val,
                            'row_idx': row_idx,
                            'priority': _calculate_section_priority(section_key, label)
                        }
                        non_empty_rows.append((row_idx, section_key, val))
            
            # Si hay múltiples valores no vacíos para la misma cuenta conceptual
            if len(non_empty_rows) > 1:
                # Determinar cuál sección debería tener el valor
                best_section = max(values_by_section.keys(), 
                                 key=lambda s: values_by_section[s]['priority'])
                best_row_idx = values_by_section[best_section]['row_idx']
                best_value = values_by_section[best_section]['value']
                
                # Limpiar valores en filas que NO deberían tener este valor
                for row_idx, section_key, val in non_empty_rows:
                    if row_idx != best_row_idx:
                        result_df.at[row_idx, dc] = None  # Limpiar valor incorrecto
                        cleaned_count += 1
                        
                        if debug and processed_labels <= 3:  # Limitar debug output
                            print(f"DEBUG: Limpiando '{label}' en {section_key[:20]} para {dc}")
                            print(f"DEBUG:   Removiendo valor {val} -> mejor en {best_section[:20]}")
    
    if debug:
        print(f"DEBUG: Limpieza completada - {cleaned_count} valores limpiados en {processed_labels} cuentas duplicadas")
    
    return result_df


def _calculate_section_priority(section_key_lower: str, account_label: str) -> int:
    """
    Calcula prioridad para determinar qué sección debería tener el valor
    basado en el tipo de cuenta y su contexto natural
    """
    priority = 0
    account_lower = account_label.lower()
    
    # Lógica específica por tipo de cuenta
    if 'dividendos pagados' in account_lower:
        # Los dividendos pagados suelen estar en actividades de financiación
        if 'financiación' in section_key_lower or 'servicios bancarios' in section_key_lower:
            priority += 30
        elif 'negocios no bancarios' in section_key_lower:
            priority += 10  # Menor prioridad para operación
            
    elif 'dividendos recibidos' in account_lower:
        # Los dividendos recibidos suelen estar en actividades de operación o inversión
        if 'inversion' in section_key_lower or 'inversión' in section_key_lower:
            priority += 30
        elif 'negocios no bancarios' in section_key_lower and ('operación' in section_key_lower or 'operacion' in section_key_lower):
            priority += 25
        elif 'negocios no bancarios' in section_key_lower:
            priority += 20  # Prioridad media para negocios no bancarios
        elif 'servicios bancarios' in section_key_lower:
            priority += 15  # Menor prioridad
            
    elif 'intereses pagados' in account_lower:
        # Los intereses pagados suelen estar en actividades de financiación
        if 'financiación' in section_key_lower or 'financiacion' in section_key_lower:
            priority += 30
        elif 'operación' in section_key_lower or 'operacion' in section_key_lower:
            priority += 20
            
    elif 'intereses recibidos' in account_lower:
        # Los intereses recibidos suelen estar en actividades de operación
        if 'operación' in section_key_lower or 'operacion' in section_key_lower:
            priority += 30
        elif 'inversión' in section_key_lower or 'inversion' in section_key_lower:
            priority += 25
            
    else:
        # Para cuentas genéricas, usar lógica general
        if 'servicios bancarios' in section_key_lower:
            priority += 25
        elif 'negocios no bancarios' in section_key_lower:
            priority += 20
        elif 'inversión' in section_key_lower or 'inversion' in section_key_lower:
            priority += 22
        elif 'financiación' in section_key_lower or 'financiacion' in section_key_lower:
            priority += 22
        elif 'operación' in section_key_lower or 'operacion' in section_key_lower:
            priority += 18
    
    return priority


def deduplicate_facts_by_context(facts_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    Deduplica facts consolidados manteniendo solo una entrada por cuenta conceptual,
    priorizando la fila que está en el contexto más específico y tiene datos reales.
    OPTIMIZADO para better performance en datasets grandes.
    """
    if facts_df.empty:
        return facts_df
    
    # Optimización: pre-calcular columnas de fechas una sola vez
    date_columns = [col for col in facts_df.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(col))]
    
    # Función optimizada para calcular score
    def _fast_score_row(row):
        """Versión optimizada de scoring"""
        score = 0
        section_key_lower = str(row.get('SectionKey', '')).lower()
        
        # Puntuación por sección (más eficiente)
        if 'bancarios' in section_key_lower:
            if 'servicios' in section_key_lower:
                score += 20
            elif 'no bancarios' in section_key_lower or 'negocios' in section_key_lower:
                score += 15
        elif 'inversión' in section_key_lower or 'inversion' in section_key_lower:
            score += 10
        elif 'financiación' in section_key_lower or 'financiacion' in section_key_lower:
            score += 10
        
        # Optimización: evaluar datos solo si es necesario
        has_meaningful_data = False
        data_count = 0
        
        for dc in date_columns[:3]:  # Limitar a primeras 3 fechas para speed
            val = row.get(dc)
            if val is not None and not pd.isna(val):
                val_str = str(val).replace(',', '').replace('-', '').strip()
                if val_str and val_str != "0" and val_str != "":
                    has_meaningful_data = True
                    data_count += 1
                    if data_count >= 2:  # Early exit si ya tiene suficientes datos
                        break
        
        if has_meaningful_data:
            score += 30 + min(data_count * 3, 15)  # Max 45 points for data
                
        return score
    
    # Agrupar por Label y procesar
    grouped = facts_df.groupby('Label', sort=False)  # sort=False para better performance
    
    result_rows = []
    duplicates_count = 0
    processed_labels = 0
    
    for label, group in grouped:
        processed_labels += 1
        if len(group) == 1:
            # No hay duplicados para esta cuenta
            result_rows.append(group.iloc[0].to_dict())
            continue
        
        # Hay duplicados - elegir el mejor usando scoring optimizado
        group_dicts = group.to_dict('records')
        
        # Calcular scores y encontrar el mejor en una sola pasada
        best_row = max(group_dicts, key=_fast_score_row)
        result_rows.append(best_row)
        
        duplicates_count += len(group_dicts) - 1
        
        # Debug limitado para evitar spam
        if debug and len(group_dicts) > 1 and processed_labels <= 5:  # Solo primeros 5
            sections = [str(row.get('SectionKey', ''))[:20] for row in group_dicts]
            scores = [_fast_score_row(row) for row in group_dicts]
            best_idx = scores.index(max(scores))
            print(f"DEBUG: '{label}' - {len(group_dicts)} dupes, scores: {scores}, chose: {best_idx}")
            print(f"DEBUG:   Sections: {sections}")
    
    # Crear DataFrame resultado de manera eficiente
    result_df = pd.DataFrame(result_rows)
    
    if debug:
        print(f"DEBUG: Deduplicación completada - {duplicates_count} duplicados removidos ({len(facts_df)} → {len(result_df)} filas)")
    
    return result_df


def filter_facts_by_statement(facts: pd.DataFrame, statement_kind: str) -> pd.DataFrame:
    """
    Filtra facts para tomar solo la sección correspondiente al statement.
    Corta justo antes del próximo encabezado [XXXXXX] (incluye casos con espacios/comillas).
    """
    if facts.empty:
        return facts

    role_pref = {
        "BALANCE": ["210000", "220000"],
        "RESULTADOS": ["310000", "320000"],
        "FLUJO": ["510000", "520000"],
    }
    desired_roles = role_pref.get(statement_kind, ["210000"])

    # Si existe RoleCode (out_consolidated), filtrar por ese campo primero
    if 'RoleCode' in facts.columns:
        for code in desired_roles:
            # Encontrar bloques continuos del RoleCode y elegir el principal
            role_mask = facts['RoleCode'].astype(str) == code
            if not role_mask.any():
                continue
            
            # Encontrar todos los bloques continuos con este RoleCode
            role_indices = facts[role_mask].index.tolist()
            blocks = []
            current_block = [role_indices[0]]
            
            for i in range(1, len(role_indices)):
                if role_indices[i] == role_indices[i-1] + 1:
                    # Índice consecutivo, parte del mismo bloque
                    current_block.append(role_indices[i])
                else:
                    # Salto en índices, nuevo bloque
                    blocks.append(current_block)
                    current_block = [role_indices[i]]
            blocks.append(current_block)  # Agregar último bloque
            
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Encontrados {len(blocks)} bloques para {statement_kind} (RoleCode={code})")
                for i, block in enumerate(blocks):
                    print(f"  Bloque {i+1}: {len(block)} filas, rango {block[0]}-{block[-1]}")
            
            # Estrategia mejorada: combinar bloques en orden lógico
            # 1. Bloque con header va primero
            # 2. Luego bloques por orden de aparición, priorizando los que tienen datos
            
            header_block = None
            data_blocks = []
            
            for block in blocks:
                block_facts = facts.loc[block]
                has_header = block_facts['Label'].astype(str).str.contains(rf'\[{code}\]', na=False, regex=True).any()
                
                if has_header:
                    header_block = block
                else:
                    # Verificar si el bloque tiene datos significativos
                    date_cols = [c for c in block_facts.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(c))]
                    if date_cols:
                        has_data = block_facts[date_cols].notna().any().any()
                        if has_data:
                            data_blocks.append(block)
            
            # Construir subset combinando bloques relevantes
            # MEJORAR: Ordenar bloques según posición lógica en el statement
            all_indices = []
            if header_block:
                all_indices.extend(header_block)
            
            # Ordenar bloques de datos por su posición de inicio (orden natural del facts)
            data_blocks_sorted = sorted(data_blocks, key=lambda block: block[0])
            
            # Agregar bloques con datos en orden natural
            for block in data_blocks_sorted:
                all_indices.extend(block)
                
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Bloques ordenados por posición: {[f'{block[0]}-{block[-1]}' for block in data_blocks_sorted]}")
            
            # Si no hay header ni datos, usar el bloque más largo
            if not all_indices:
                main_block = max(blocks, key=len)
                all_indices = main_block
                
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Combinando bloques - Header: {'Sí' if header_block else 'No'}, Datos: {len(data_blocks)} bloques")
                print(f"DEBUG: Total filas combinadas: {len(all_indices)}")
            
            subset = facts.loc[all_indices].copy()
            
            # Asegurar que header esté primero (orden básico)
            if not subset.empty:
                header_mask = subset['Label'].astype(str).str.contains(rf'\[{code}\]', na=False, regex=True)
                if header_mask.any():
                    header_rows = subset[header_mask]
                    non_header_rows = subset[~header_mask]
                    subset = pd.concat([header_rows, non_header_rows], ignore_index=True)
                    
                    if os.getenv('X2E_DEBUG') == '1':
                        print(f"DEBUG: Reordenado para colocar header al principio ({len(header_rows)} headers encontrados)")
            
            if not subset.empty:
                # Mantener filas con datos en fechas o categorías especiales
                date_columns = [c for c in subset.columns
                                if c not in ('Label', 'RoleCode', 'LabelKeyId', 'LabelKeyIdExt', 'SectionKey') and isinstance(c, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', c)]
                if date_columns:
                    has_data_mask = subset[date_columns].notna().any(axis=1)
                    is_pseudo_cat = subset['Label'].astype(str).str.contains(r'\[(?:sinopsis|abstract|resumen)\]',
                                                                            flags=re.I, na=False, regex=True)
                    # Incluir siempre el header si viene como fila
                    is_header = subset['Label'].astype(str).str.match(rf'^\s*["\']?\[{code}\]', na=False)
                    keep_mask = has_data_mask | is_pseudo_cat | is_header
                    subset = subset[keep_mask].copy()
                    
                    # LIMPIEZA ADICIONAL: Si hay cuentas duplicadas (mismo Label), 
                    # conservar solo las que tienen datos, eliminando duplicados vacíos
                    # IMPORTANTE: Mantener el orden original del subset
                    if 'LabelKeyId' in subset.columns:
                        # Crear un mapeo para mantener el orden original
                        cleaned_indices = []
                        seen_labels = set()
                        
                        for idx in subset.index:
                            row = subset.loc[idx]
                            label = row['Label']
                            
                            if label not in seen_labels:
                                # Primera vez que vemos esta etiqueta
                                cleaned_indices.append(idx)
                                seen_labels.add(label)
                            else:
                                # Etiqueta duplicada - verificar si esta tiene más datos que la anterior
                                prev_idx = None
                                for prev_i in cleaned_indices:
                                    if subset.loc[prev_i, 'Label'] == label:
                                        prev_idx = prev_i
                                        break
                                
                                if prev_idx is not None:
                                    # Comparar cantidad de datos
                                    current_data = row[date_columns].notna().sum()
                                    prev_data = subset.loc[prev_idx, date_columns].notna().sum()
                                    
                                    if current_data > prev_data:
                                        # Reemplazar la anterior con la actual
                                        cleaned_indices.remove(prev_idx)
                                        cleaned_indices.append(idx)
                                        
                                        if os.getenv('X2E_DEBUG') == '1':
                                            print(f"DEBUG: Reemplazado duplicado para '{label[:50]}...' - nueva fila con {current_data} valores (vs {prev_data})")
                        
                        # Reconstruir subset manteniendo el orden
                        subset = subset.loc[cleaned_indices].copy().reset_index(drop=True)
                
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Filtrado {statement_kind} por RoleCode={code}: {len(subset)} filas (bloques combinados, limpiado)")
                    # Debug del orden final
                    print(f"DEBUG: Orden final después de filtrar - Primeras 3: {subset['Label'].head(3).tolist()}")
                    print(f"DEBUG: Orden final después de filtrar - Últimas 3: {subset['Label'].tail(3).tolist()}")
                return subset

        # Si no encontramos ningún RoleCode deseado, retornar vacío para este kind
        return pd.DataFrame(columns=facts.columns)

    # Fallback: no hay RoleCode, usar corte por headers [XXXXXX]
    target_role = desired_roles[0]
    header_target_re = rf'^\s*["\']?\[{target_role}\]'
    any_header_re    = r'^\s*["\']?\[(\d{6})\]'

    header_mask = facts['Label'].astype(str).str.match(header_target_re, na=False)
    if not header_mask.any():
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: No se encontró header [{target_role}] en facts")
        return pd.DataFrame(columns=facts.columns)

    start_idx = header_mask.idxmax()
    next_header_mask = facts['Label'].astype(str).str.match(any_header_re, na=False) & (facts.index > start_idx)
    if next_header_mask.any():
        end_idx = next_header_mask.idxmax()
        filtered_facts = facts.loc[start_idx:end_idx - 1].copy()
    else:
        filtered_facts = facts.loc[start_idx:].copy()

    date_columns = [c for c in filtered_facts.columns if c != 'Label' and isinstance(c, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', c)]
    if date_columns:
        has_data_mask   = filtered_facts[date_columns].notna().any(axis=1)
        is_target_header = filtered_facts['Label'].astype(str).str.match(header_target_re, na=False)
        is_pseudo_cat    = filtered_facts['Label'].astype(str).str.contains(r'\[(?:sinopsis|abstract|resumen)\]', flags=re.I, na=False, regex=True)
        keep_mask = has_data_mask | is_target_header | is_pseudo_cat
        filtered_facts = filtered_facts[keep_mask].copy()

    if os.getenv('X2E_DEBUG') == '1':
        data_rows = len(filtered_facts) - filtered_facts['Label'].astype(str).str.match(any_header_re, na=False).sum()
        print(f"DEBUG: Filtrado {statement_kind} (headers): {len(filtered_facts)} filas ({data_rows} con datos)")
    return filtered_facts


def compose_statement(
    facts_raw: pd.DataFrame,
    tree: pd.DataFrame,
    lang: str | None = None,
    max_dates: int | None = None,
    statement_kind: str | None = None,
    allowed_months: tuple[str, str] | None = None,
    presentation_data: pd.DataFrame | None = None,
    output_dir: Path | None = None,
    company_rut: str | None = None,  # NUEVO: RUT de la empresa para estructura específica
) -> pd.DataFrame:
    """
    Une facts con el árbol y crea estructura completa basada en taxonomía.
    
    NUEVO ENFOQUE V2.0:
    - Crea estructura completa desde taxonomía independiente de facts
    - Rellena valores desde facts donde existan
    - Mantiene todas las cuentas disponibles para fórmulas futuras
    """
    
    # NUEVA LÓGICA: Detectar si facts viene de out_consolidated
    is_consolidated = ('LabelKeyId' in facts_raw.columns and 'RoleCode' in facts_raw.columns)
    
    if is_consolidated and os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: Detectado facts from out_consolidated - preservando estructura completa")
        print(f"DEBUG: Facts shape: {facts_raw.shape}, columnas: {list(facts_raw.columns[:5])}...")
    
    # Si los facts provienen del CSV perfecto de primary_roles, usar un flujo directo
    try:
        from_primary_csv = bool(getattr(facts_raw, 'attrs', {}).get('from_primary_csv'))
    except Exception:
        from_primary_csv = False
    
    if os.getenv('X2E_DEBUG') == '1':
        print(f"DEBUG: from_primary_csv = {from_primary_csv}")
        if hasattr(facts_raw, 'attrs'):
            print(f"DEBUG: facts_raw.attrs = {dict(getattr(facts_raw, 'attrs', {}))}")
        else:
            print(f"DEBUG: facts_raw no tiene attrs")

    if from_primary_csv and statement_kind:
        # Determinar RoleCode objetivo para esta hoja
        role_map = {"BALANCE": "210000", "RESULTADOS": "310000", "FLUJO": "510000"}
        target_role = role_map.get(statement_kind)
        df_src = facts_raw.copy()
        # Filtrar por RoleCode exacto y preservar ORDEN ORIGINAL del CSV
        if 'RoleCode' in df_src.columns and target_role is not None:
            df_src = df_src[df_src['RoleCode'].astype(str) == target_role].copy()
        else:
            # Si no está RoleCode (caso raro), devolver vacío para este statement
            return pd.DataFrame(columns=['Cuenta'])

        # Determinar columnas de fecha reales presentes en el CSV
        # Aceptar formatos YYYY-MM-DD y MM/DD/YYYY (con o sin cero inicial)
        def _is_date_header(lbl: object) -> bool:
            if not isinstance(lbl, str):
                return False
            s = lbl.strip()
            if re.fullmatch(r'\d{4}-\d{2}-\d{2}', s):
                return True
            if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}', s):
                return True
            return False
        date_cols = [c for c in df_src.columns if _is_date_header(c)]

        # Preparar filas: copiar filas del CSV tal cual, columna Cuenta = Label
        rows = []
        # Agregar filas del CSV tal cual (preservando [sinopsis], etc.)
        label_col = 'Label' if 'Label' in df_src.columns else None
        for _, r in df_src.iterrows():
            cuenta = str(r.get(label_col, '')).strip() if label_col else ''
            if not cuenta:
                continue
            row = {"Cuenta": cuenta}
            for d in date_cols:
                row[d] = r.get(d)
            rows.append(row)

        result = pd.DataFrame(rows)

        # CRÍTICO: NO RENOMBRAR columnas de fecha para evitar pérdida/mezcla de datos
        # El primary_roles CSV ya viene con las columnas de fecha exactas que necesitamos
        # Renombrar puede causar que múltiples fechas mapeen al mismo nombre y se pierdan datos
        
        if os.getenv('X2E_DEBUG') == '1':
            print(f"[PRIMARY CSV] ⚠ CONSERVANDO nombres originales de columnas de fecha: {date_cols[:5]}")
        
        # En lugar de transformar, mantener los nombres originales de fecha
        # Solo reorganizar el orden de las columnas: Cuenta primero, luego fechas en orden descendente
        date_cols_sorted = sorted(date_cols, reverse=True)  # Más reciente primero
        column_order = ['Cuenta'] + date_cols_sorted
        
        # Asegurar que tenemos todas las columnas que queremos
        available_cols = [col for col in column_order if col in result.columns]
        result = result[available_cols]
        
        if os.getenv('X2E_DEBUG') == '1':
            print(f"[PRIMARY CSV] ✅ Orden final de columnas: {list(result.columns)[:8]}...")
            
        # Los datos ya están correctos, NO aplicar transformaciones que puedan alterar valores
        # Debug: verificar presencia y valores de líneas clave desde primary CSV
        if os.getenv('X2E_DEBUG') == '1':
            try:
                sample_labels = ['Dividendos pagados', 'Intereses pagados', 'Cobros procedentes de las ventas de bienes y prestación de servicios']
                for lbl in sample_labels:
                    sub = df_src[df_src.get('Label', '').astype(str).str.contains(lbl, na=False)]
                    if not sub.empty:
                        print(f"[PRIMARY CSV] {statement_kind} → '{lbl}': {len(sub)} fila(s) en CSV")
                        # Mostrar valores de las primeras filas para las fechas detectadas
                        for i, (_, rr) in enumerate(sub.iterrows()):
                            vals = {d: rr.get(d) for d in date_cols}
                            print(f"   • CSV row {i+1}: {vals}")
                # Verificar en el DataFrame resultante
                for lbl in sample_labels:
                    sub2 = result[result['Cuenta'].astype(str).str.contains(lbl, na=False)]
                    if not sub2.empty:
                        print(f"[PRIMARY → DF] {statement_kind} → '{lbl}': {len(sub2)} fila(s) en DF final")
                        vals2 = sub2.iloc[0].to_dict()
                        print(f"   • DF first row: {{k: vals2[k] for k in ['Cuenta'] + date_cols[:1]}}")
            except Exception as _e:
                print(f"[PRIMARY CSV] debug falló: {_e}")
        # Asegurar tipos adecuados y devolver directamente (saltando todo el pipeline complejo)
        return result

    # Flujo normal (facts no provienen de primary_roles CSV): normalizar y seguir
    facts_main = normalize_facts(facts_raw, lang=lang)

    # Determinar columnas de fechas
    def date_cols_of(df: pd.DataFrame) -> list[str]:
        if df is None:
            return []
        return [c for c in df.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(c))]

    dates_main = set(date_cols_of(facts_main))
    all_dates = sorted(dates_main, reverse=True)
    # Filtrar por rango permitido (solo consolidado), usando prefijo YYYY-MM
    if allowed_months:
        lo, hi = allowed_months
        def _in_range(d: str) -> bool:
            try:
                ym = str(d)[:7]
                return (ym >= lo) and (ym <= hi)
            except Exception:
                return True
        all_dates = [d for d in all_dates if _in_range(d)]

    # Filtro opcional por año mínimo/máximo (para limpiar residuales muy antiguos)
    try:
        import os as _os
        min_year_env = _os.getenv('X2E_MIN_YEAR')
        max_year_env = _os.getenv('X2E_MAX_YEAR')
        if min_year_env:
            min_y = int(min_year_env)
            all_dates = [d for d in all_dates if int(str(d)[:4]) >= min_y]
        if max_year_env:
            max_y = int(max_year_env)
            all_dates = [d for d in all_dates if int(str(d)[:4]) <= max_y]
    except Exception:
        pass

    # NUEVA ESTRATEGIA: Usar presentation restructured si está disponible, sino taxonomía
    if statement_kind:
        # Detectar si el tree es presentation restructured
        is_restructured = tree is not None and len(tree.columns) == 1 and 'Cuenta' in tree.columns
        
        if os.getenv('X2E_DEBUG') == '1':
            if is_restructured:
                print(f"      ║ Construyendo {statement_kind} desde PRESENTATION RESTRUCTURED")
                print(f"DEBUG: Detectado presentation restructured para {statement_kind} - USANDO presentation tree")
            else:
                print(f"      ║ Construyendo {statement_kind} desde taxonomía completa")
                print(f"DEBUG: Construyendo desde taxonomía completa para {statement_kind} - presentation no restructured")
        
        # NUEVO ENFOQUE: Filtrar facts por statement ANTES de crear estructura
        facts_for_statement = filter_facts_by_statement(facts_main, statement_kind)
        
        # NUEVO: Limpiar values duplicados incorrectos en facts consolidados
        if is_consolidated and not facts_for_statement.empty and 'SectionKey' in facts_for_statement.columns:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Aplicando limpieza de valores duplicados incorrectos en facts consolidados...")
            facts_for_statement = clean_duplicate_values_by_context(facts_for_statement, debug=(os.getenv('X2E_DEBUG')=='1'))
        
        if os.getenv('X2E_DEBUG') == '1':
            final_count = len(facts_for_statement)
            original_count = len(facts_main)
            print(f"DEBUG: Facts procesados para {statement_kind}: {final_count} de {original_count} total")
        
        # SI ES CONSOLIDADO Y HAY FACTS FILTRADOS, COMBINAR CON PRESENTATION PARA ORDEN CORRECTO
        if is_consolidated and not facts_for_statement.empty:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"DEBUG: Combinando facts consolidados con presentation para orden correcto en {statement_kind}")
            
            # Crear estructura desde presentation (orden correcto) + datos desde facts consolidados
            complete_structure = build_complete_statement_structure(
                statement_kind, 
                lang or "es", 
                all_dates,
                tree,                    
                facts_for_statement,    # Usar facts consolidados como fuente de datos
                is_consolidated_facts=True,  # NUEVO: Evitar agregar cuentas adicionales al final
                company_rut=company_rut  # NUEVO: RUT de la empresa para estructura específica
            )
            
            if os.getenv('X2E_DEBUG') == '1':
                # Debug: contar cuentas duplicadas en facts consolidados
                if 'Label' in complete_structure.columns:
                    label_counts = complete_structure['Label'].value_counts()
                    duplicated_labels = label_counts[label_counts > 1]
                    if len(duplicated_labels) > 0:
                        print(f"DEBUG: {len(duplicated_labels)} cuentas con duplicados en facts consolidados:")
                        for label, count in duplicated_labels.head(5).items():
                            print(f"  {label}: {count} veces")
                        
                        # Verificar específicamente cuentas problemáticas
                        target_labels = ['Pagos por primas', 'Efectivo y equivalentes']
                        for target in target_labels:
                            matches = complete_structure[complete_structure['Label'].str.contains(target, na=False)]
                            if len(matches) > 0:
                                print(f"DEBUG: Cuentas con '{target}': {len(matches)} filas")
            
            # Asegurar que tenemos las columnas de fecha
            date_columns = [c for c in complete_structure.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', str(c))]
            if date_columns:
                # Reordenar columnas: primero metadatos, luego fechas en orden descendente
                meta_cols = []
                for col in ['Cuenta', 'Label', 'LabelKeyId', 'RoleCode']:
                    if col in complete_structure.columns:
                        meta_cols.append(col)
                
                date_columns = sorted(date_columns, reverse=True)
                complete_structure = complete_structure[meta_cols + date_columns]
                
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"DEBUG: Facts consolidados procesados: {len(complete_structure)} filas, {len(date_columns)} fechas")
                    print(f"DEBUG: Orden facts consolidados - Primeras 3: {complete_structure['Cuenta'].head(3).tolist()}")
                    print(f"DEBUG: Orden facts consolidados - Últimas 3: {complete_structure['Cuenta'].tail(3).tolist()}")
                    
                    # Verificar si hay header al principio
                    first_account = complete_structure['Cuenta'].iloc[0] if len(complete_structure) > 0 else ''
                    is_header = '[' in str(first_account) and ']' in str(first_account)
                    print(f"DEBUG: Primera cuenta es header: {is_header} - {first_account}")
        else:
            # Crear estructura completa desde facts filtrados (lógica original)
            complete_structure = build_complete_statement_structure(
                statement_kind, 
                lang or "es", 
                all_dates,
                tree,                    # Pasar tree 
                facts_for_statement,    # Pasar SOLO facts del statement actual
                is_consolidated_facts=False,  # Facts normales, pueden necesitar cuentas adicionales
                company_rut=company_rut  # NUEVO: RUT de la empresa para estructura específica
            )
        # --- FILTRO DURO: eliminar filas cuyo encabezado [XXXXXX] no sea el del rol REAL detectado ---
        # SALTAR para facts consolidados ya filtrados
        if not (is_consolidated and not facts_for_statement.empty):
            def _detect_role_in_df(df: pd.DataFrame) -> str | None:
                try:
                    for _, r in df.iterrows():
                        s = str(r.get('Cuenta') or r.get('Label') or '')
                        m = re.match(r'^\s*["\']?\[(\d{6})\]', s)
                        if m:
                            return m.group(1)
                except Exception:
                    return None
                return None

            detected_role = _detect_role_in_df(complete_structure)
            if not detected_role:
                # Usar autodetección para RESULTADOS
                if statement_kind == "RESULTADOS":
                    income_role = detect_income_statement_role(tree, facts_for_statement)
                    role_id_map = {"BALANCE": "210000", "RESULTADOS": income_role, "FLUJO": "510000"}
                else:
                    role_id_map = {"BALANCE": "210000", "RESULTADOS": "310000", "FLUJO": "510000"}
                detected_role = role_id_map.get(statement_kind, "210000")
            complete_structure = strip_foreign_role_segments(complete_structure, detected_role)
        if isinstance(complete_structure, pd.DataFrame) and 'Cuenta' in complete_structure.columns:
            _before = len(complete_structure)
            # Preservar todas las filas después del header coincidente; strip_foreign_role_segments ya hizo el corte
            if os.getenv('X2E_DEBUG') == '1' and _before != len(complete_structure):
                print(f"DEBUG: purgadas {_before - len(complete_structure)} filas de roles ajenos (≠ [{detected_role}]).")

        if not complete_structure.empty:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"      ║ Estructura de taxonomía creada: {len(complete_structure)} cuentas para {statement_kind}")
                # Verificar si la cuenta problemática está en la estructura
                target_count = len(complete_structure[complete_structure['Cuenta'].str.contains('Pagos por primas', na=False)])
                if target_count > 0:
                    print(f"✅ Cuenta problemática INCLUIDA en estructura ({target_count} cuentas con 'Pagos por primas')")
                else:
                    print(f"❌ Cuenta problemática NO encontrada en estructura")
                print(f"DEBUG: Estructura de taxonomía creada con {len(complete_structure)} cuentas")
            
            # Rellenar valores desde facts filtrados (solo español)
            # AHORA SIEMPRE usamos fill_values_from_facts_strict para mapear correctamente
            merged = fill_values_from_facts_strict(complete_structure, facts_for_statement, all_dates, statement_kind, debug=(os.getenv('X2E_DEBUG')=='1'))
            
            if os.getenv('X2E_DEBUG') == '1' and is_consolidated:
                print(f"DEBUG: Merged con facts consolidados - Últimas 5: {merged['Cuenta'].tail(5).tolist()}")
                
                # Debug: verificar que se mantienen cuentas importantes
                target_labels = ['Pagos por primas', 'Total de patrimonio y pasivos']
                for target in target_labels:
                    matches = merged[merged['Cuenta'].str.contains(target, na=False)]
                    if len(matches) > 0:
                        print(f"DEBUG: Merged - Cuentas con '{target}': {len(matches)} filas")
            
            # IMPORTANTE: Aplicar limpieza de duplicados después del merge para Excel
            if is_consolidated:
                if os.getenv('X2E_DEBUG') == '1':
                    print("DEBUG: Aplicando limpieza final de duplicados en Excel merged...")
                # Preparar los datos en formato facts para la función de limpieza
                temp_facts = merged.copy()
                temp_facts['Label'] = temp_facts['Cuenta']
                temp_facts['LabelKeyId'] = temp_facts['Cuenta'] + '||' + statement_kind
                temp_facts['LabelKeyIdExt'] = temp_facts['LabelKeyId']
                temp_facts['SectionKey'] = ''  # No tenemos contexto aquí, usar lógica por nombre
                temp_facts['RoleCode'] = '000000'  # Placeholder
                
                # Aplicar limpieza 
                cleaned_temp = clean_duplicate_values_by_context(temp_facts, debug=(os.getenv('X2E_DEBUG')=='1'))
                
                # Restaurar los datos limpios al merged
                for col in all_dates:
                    if col in cleaned_temp.columns:
                        merged[col] = cleaned_temp[col]
                        
                if os.getenv('X2E_DEBUG') == '1':
                    print("DEBUG: Limpieza final de duplicados completada")

            if FACTS_ENHANCER_AVAILABLE:
                debug_enhancer = os.getenv('X2E_DEBUG') == '1'
                merged = apply_facts_enhancements(merged, facts_main, debug_enhancer, output_dir)
            else:
                print("🔒 Facts Enhancer: MODO ESTRICTO (no-op) activado")
            
            # Ya todas las cuentas están desde facts - no necesitamos agregar más
                
        else:
            # Solo si falla completamente la taxonomía, usar fallback
            if os.getenv('X2E_DEBUG') == '1':
                print("ERROR: Estructura de taxonomía vacía - usando fallback")
            merged = create_legacy_merged_structure(
                facts_main,
                tree,
                all_dates,
                statement_kind,
                lang,
                presentation_data=presentation_data,
            )
    else:
        # Si no hay statement_kind, usar método original
        merged = create_legacy_merged_structure(
            facts_main,
            tree,
            all_dates,
            statement_kind,
            lang,
            presentation_data=presentation_data,
        )

    # Asegurar todas las columnas de fechas presentes
    for dc in all_dates:
        if dc not in merged.columns:
            merged[dc] = pd.NA

    # Renombrar columnas de fecha a etiquetas normalizadas por periodo (YYYY o YYYYQn)
    kind_eff = statement_kind or "RESULTADOS"
    period_map = _period_labels_from_dates(all_dates, kind_eff)
    if period_map:
        merged.rename(columns=period_map, inplace=True)

    # Recalcular columnas de período después del rename
    period_cols = [period_map.get(dc, dc) for dc in all_dates]
    # Dedup and sort: all period labels are now YYYYQ[1-4] (Q4 always explicit).
    # In Anual mode (dec_as_year), keep only Q4 columns (remove Q1-Q3).
    # In combined/quarterly mode, keep all.
    dec_as_year = os.getenv('X2E_DECEMBER_AS_YEAR', '0') == '1'
    combined_mode = os.getenv('X2E_COMBINED', '0') == '1'
    base_list = list(dict.fromkeys(period_cols))

    if dec_as_year and not combined_mode:
        # Anual mode: keep only Q4 columns, remove Q1/Q2/Q3
        base_list = [p for p in base_list if not (len(p) == 6 and p[4] == 'Q' and p[5] in '123')]

    period_cols = sorted(base_list, key=_period_sort_key, reverse=True)

    # Eliminar columnas de período completamente vacías (sin valores reales)
    def _has_data(series: pd.Series) -> bool:
        try:
            def _nonempty(v):
                if v is None:
                    return False
                if pd.isna(v):
                    return False
                if isinstance(v, str):
                    s = v.strip().lower()
                    return s not in ("", "none", "nan")
                return True
            return series.apply(_nonempty).any()
        except Exception:
            return series.notna().any()

    # Debug: verificar si la columna de la cuenta problemática se elimina aquí
    original_period_cols = period_cols.copy()
    period_cols = [c for c in period_cols if c in merged.columns and _has_data(merged[c])]
    
    if statement_kind == "FLUJO":
        removed_cols = [c for c in original_period_cols if c not in period_cols]
        if removed_cols:
            print(f"⚠️  COLUMNAS ELIMINADAS POR _has_data: {removed_cols}")
            # Verificar si alguna contiene datos de la cuenta problemática
            target_rows = merged[merged['Cuenta'].str.contains('Pagos por primas', na=False)]
            if not target_rows.empty:
                for col in removed_cols:
                    if col in merged.columns:
                        vals = target_rows[col].tolist()
                        print(f"   {col}: valores cuenta problemática = {vals}")
        else:
            print(f"      ║ Todas las columnas de períodos conservadas")

    # VERIFICAR QUE LA CUENTA PROBLEMÁTICA ESTÉ EN EL DATAFRAME FINAL ANTES DE ESCRIBIR AL EXCEL
    if statement_kind == "FLUJO":
        target_rows = merged[merged['Cuenta'].str.contains('Pagos por primas', na=False)]
        if not target_rows.empty:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"🎯 CUENTA PROBLEMÁTICA EN DATAFRAME FINAL: {len(target_rows)} filas")
                print(f"   Columnas disponibles: {list(merged.columns)}")
                print(f"   Period_cols finales: {period_cols}")
                for idx, row in target_rows.iterrows():
                    print(f"   Fila {idx}: {row['Cuenta']}")
                    # Usar period_cols en lugar de fechas hardcodeadas
                    for col in period_cols:
                        if col in merged.columns:
                            val = row.get(col, 'N/A')
                            print(f"   {col}: {val}")
        else:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"❌ CUENTA PROBLEMÁTICA NO ESTÁ EN DATAFRAME FINAL")
                print(f"   Total filas en merged: {len(merged)}")
                print(f"   Primeras 10 cuentas: {merged['Cuenta'].head(10).tolist()}")
    
    # Construir índice del otro idioma por qname
    other_index = None
    # facts_other no se usa en el nuevo sistema simplificado
    # if facts_other is not None and 'qname' in facts_other.columns and facts_other.shape[0] > 0:
    #     other_index = facts_other.set_index('qname', drop=False)

    # Completar faltantes usando qname
    if other_index is not None and 'qname' in merged.columns:
        for i, row in merged.iterrows():
            q = row.get('qname')
            if pd.isna(q) or q not in other_index.index:
                continue
            other_row = other_index.loc[q]
            if isinstance(other_row, pd.DataFrame):
                other_row = other_row.iloc[0]
            for dc in all_dates:
                if pd.isna(row.get(dc)) or row.get(dc) == '':
                    val = other_row.get(dc)
                    if not pd.isna(val) and val != '':
                        merged.at[i, dc] = val


    # ✨ APLICAR ORDENAMIENTO PERFECTO BASADO EN JSON ✨
    # No usar el ordenamiento antiguo - aplicar nuestro algoritmo perfecto siempre
    try:
        # Construir company_dir desde output_dir o usando company_rut
        company_dir = None
        if output_dir:
            # Intentar inferir del path: .../data/XBRL/.../RUT_EMPRESA/...
            parts = output_dir.parts
            for i, part in enumerate(parts):
                if part.startswith('91705000') or (company_rut and part.startswith(company_rut.split('-')[0])):
                    company_dir = Path(*parts[:i+1]) / part
                    break
        
        if company_dir and company_dir.exists():
            # Verificar que tenemos las columnas necesarias para el ordenamiento
            required_cols = ['RoleCode', 'Label']
            missing_cols = [col for col in required_cols if col not in merged.columns]
            
            if not missing_cols:
                # Asegurar que tenemos SectionKey y LabelKeyIdExt
                if 'SectionKey' not in merged.columns:
                    merged['SectionKey'] = merged.get('Label', '')
                if 'LabelKeyIdExt' not in merged.columns:
                    merged['LabelKeyIdExt'] = merged.get('LabelKeyId', '') 
                
                merged = apply_perfect_json_ordering(merged, company_dir, lang=lang or 'es', 
                                                    enable_log=os.getenv('X2E_DEBUG') == '1')
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"      ║ ✨ Ordenamiento JSON perfecto aplicado en compose_statement: {len(merged)} filas")
            else:
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"      ║ ⚠ Ordenamiento JSON no aplicado - columnas faltantes: {missing_cols}")
                # Fallback: ordenamiento antiguo
                if 'order' in merged.columns and not is_consolidated:
                    merged = merged.sort_values('order', kind='mergesort').reset_index(drop=True)
        else:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"      ║ ⚠ Company_dir no encontrado, usando ordenamiento básico")
            # Fallback: ordenamiento antiguo
            if 'order' in merged.columns and not is_consolidated:
                merged = merged.sort_values('order', kind='mergesort').reset_index(drop=True)
                
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"      ║ ⚠ Error en ordenamiento JSON perfecto: {e}")
        # Fallback: ordenamiento antiguo
        if 'order' in merged.columns and not is_consolidated:
            merged = merged.sort_values('order', kind='mergesort').reset_index(drop=True)

    # --- luego sigues como ya tienes ---
    final_dates = list(period_cols)
    if isinstance(max_dates, int) and max_dates > 0:
        final_dates = final_dates[:max_dates]
    result_cols = ["Cuenta"] + final_dates

    available_cols = [col for col in result_cols if col in merged.columns]
    table = merged[available_cols].copy()
    
    # Columnas finales: aplicar tope si corresponde (p. ej., datasets simples → 2 años)
    final_dates = list(period_cols)
    if isinstance(max_dates, int) and max_dates > 0:
        final_dates = final_dates[:max_dates]
    result_cols = ["Cuenta"] + final_dates
    
    # Verificar que las columnas existan antes de acceder
    available_cols = [col for col in result_cols if col in merged.columns]
    table = merged[available_cols].copy()
    
 
    table = table.reset_index(drop=True)
    try:
        # Detectar rol real de la tabla (header presente) o caer al esperado por tipo
        def _detect_role_in_table(df: pd.DataFrame) -> str | None:
            try:
                for _, r in df.iterrows():
                    s = str(r.get('Cuenta') or '')
                    m = re.match(r'^\s*["\']?\[(\d{6})\]', s)
                    if m:
                        return m.group(1)
            except Exception:
                return None
            return None

        expected_role = _detect_role_in_table(table) or {"BALANCE": "210000", "RESULTADOS": "310000", "FLUJO": "510000"}.get(statement_kind, "210000")
        # No hacer strip para facts consolidados (ya están filtrados correctamente)
        if 'Cuenta' in table.columns and expected_role and not is_consolidated:
            table = strip_foreign_role_segments(table, expected_role).reset_index(drop=True)
    except Exception as _e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"DEBUG: strip_foreign_role_segments skipped: {_e}")

    if os.getenv('X2E_DEBUG') == '1' and is_consolidated:
        print(f"DEBUG: compose_statement FINAL - Últimas 5 cuentas: {table['Cuenta'].tail(5).tolist()}")
    
    return table



def _coalesce_duplicate_named_columns(df: pd.DataFrame, name: str) -> None:
    cols = [c for c in df.columns if c == name]
    if len(cols) <= 1:
        return
    
    # Realizar bfill y luego manejar explícitamente la inferencia de tipos
    filled = df[cols].bfill(axis=1)
    # Tomar la primera columna después del bfill
    s = filled.iloc[:, 0]
    # Manejar explícitamente la conversión de tipos si es necesario
    if s.dtype == object:
        s = s.infer_objects(copy=False)
    
    df.drop(columns=cols, inplace=True)
    df[name] = s


def main():
    if len(sys.argv) < 3:
        print("Uso: python xbrl_to_excel.py <out_dir> <stem> [lang]")
        sys.exit(1)

    out_dir = Path(sys.argv[1])
    stem = sys.argv[2]
    lang = sys.argv[3] if len(sys.argv) > 3 else "es"

    # Extraer RUT de la empresa del stem para usar estructura específica
    company_rut = extract_company_rut(stem)
    if os.getenv('X2E_DEBUG') == '1' and company_rut:
        print(f"DEBUG: RUT extraído del stem: {company_rut}")

    facts, pres = load_inputs(out_dir, stem, lang)
    using_primary_csv = False
    try:
        using_primary_csv = bool(getattr(facts, 'attrs', {}).get('from_primary_csv'))
    except Exception:
        using_primary_csv = False
    
    # Marcar source_path para identificar Watts después
    try:
        facts.attrs = {'source_path': str(out_dir)}
    except Exception:
        pass
    
    # Solo trabajamos con español
    # NUEVA LÓGICA: Si es restructured, usar pres directamente. Sino, construir árbol.
    is_restructured = len(pres.columns) == 1 and 'Cuenta' in pres.columns
    if is_restructured:
        tree = pres  # Usar presentation restructured directamente
        if os.getenv('X2E_DEBUG') == '1':
            print(f"      ║ Detectado presentation RESTRUCTURED - usando directamente")
    else:
        tree = build_tree_and_order(pres)  # Lógica original
        if os.getenv('X2E_DEBUG') == '1':
            print(f"      ║ Presentation normal - construyendo árbol")

    # Solo nombres de hojas en español
    sheet_names = [
        ("BALANCE", "Balance General"),
        ("RESULTADOS", "Estado de Resultados"), 
        ("FLUJO", "Flujo Efectivo")
    ]
    suffix = "_es"

    # Detectar modo trimestral y límite de periodos (por defecto 12)
    quarterly_mode = os.getenv('X2E_KEEP_ONLY_QUARTERS', '0') == '1'
    try:
        max_quarters = int(os.getenv('X2E_MAX_QUARTERS', '12'))
    except Exception:
        max_quarters = 12

    hojas, nombres = [], []
    for kind, nombre in sheet_names:
        if using_primary_csv:
            # Con primary_roles, no dependas del árbol de presentación para incluir la hoja
            t = pd.DataFrame({'_': [1]})
        else:
            t = select_role_tree(tree, kind)
            if t.empty:
                continue
        # Limitar períodos visibles por rango de consolidado si aplica
        allowed = None
        m_rng = re.match(r"^\d{7,8}(?:-[0-9Kk])?_([0-9]{6})-([0-9]{6})$", stem)
        if m_rng:
            lo = f"{m_rng.group(1)[:4]}-{m_rng.group(1)[4:]}"
            hi = f"{m_rng.group(2)[:4]}-{m_rng.group(2)[4:]}"
            allowed = (lo, hi)
        # Agregar información de directorio a facts para debug
        try:
            facts.attrs = {'source_path': str(out_dir)}
        except Exception:
            pass
            
        df = compose_statement(
            facts,
            t,
            lang=lang,
            max_dates=(max_quarters if quarterly_mode else None),
            statement_kind=kind,
            allowed_months=allowed,
            presentation_data=pres,  # Pasar presentation raw para mapeo híbrido
            output_dir=out_dir,  # 🆕 Pasar output_dir al Facts Enhancer
            company_rut=company_rut,  # NUEVO: RUT de la empresa para estructura específica
        )
        
        # AGREGAR FILA DE EFECTIVO AL PRINCIPIO DEL PERIODO PARA FLUJO DE EFECTIVO
        if kind == "FLUJO" and not using_primary_csv:
            df = add_cash_beginning_period(df)
            
        # VERIFICAR CONTENIDO FINAL ANTES DE AGREGAR A HOJAS
        if kind == "FLUJO":
            target_in_final = df[df['Cuenta'].str.contains('Pagos por primas', na=False)]
            if not target_in_final.empty:
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"🎯 CUENTA PROBLEMÁTICA EN HOJA FINAL {nombre}: {len(target_in_final)} filas")
                print(f"   Columnas en hoja final: {list(df.columns)}")
                for idx, row in target_in_final.iterrows():
                    print(f"   {row['Cuenta']}")
                    # Mostrar TODOS los valores (incluso None/vacíos)
                    has_any_value = False
                    for col in df.columns[1:]:  # Skip 'Cuenta' column
                        val = row.get(col, 'N/A')
                        print(f"   {col}: {val}")
                        # Verificar si hay valor válido, evitando boolean ambiguity con pandas NA
                        if not pd.isna(val) and val is not None and val != 'N/A' and str(val).strip():
                            has_any_value = True
                    print(f"   ✓ Tiene valores: {has_any_value}")
                    if not has_any_value:
                        print(f"   ⚠️  CUENTA SIN VALORES - PODRÍA SER FILTRADA")
            else:
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"❌ CUENTA PROBLEMÁTICA NO ESTÁ EN HOJA FINAL {nombre}")
                print(f"   Primeras 5 cuentas en hoja: {df['Cuenta'].head(5).tolist()}")
                print(f"   Total filas en hoja: {len(df)}")
                print(f"   Columnas: {list(df.columns)}")
                if len(df) > 0:
                    print(f"   Primeras 5 cuentas: {df['Cuenta'].head(5).tolist()}")
        
        hojas.append(df)
        nombres.append(nombre)

    if not hojas:
        raise SystemExit("No se encontraron roles Balance/Resultados/Flujo en el CSV de presentación.")

    # Normalizar periodos entre hojas SOLO si no venimos de primary_roles CSV
    try:
        if using_primary_csv:
            raise RuntimeError('skip-period-normalization')
        all_periods = set()
        for df in hojas:
            periods = [str(c) for c in df.columns[1:]]
            all_periods |= set(periods)
        if all_periods:
            # Mostrar primero los más recientes
            ordered_all = sorted(list(all_periods), key=_period_sort_key, reverse=True)
            # En modo trimestral, limitar a los últimos N (por defecto 12)
            if quarterly_mode:
                ordered_all = ordered_all[:max_quarters]
            for i in range(len(hojas)):
                df = hojas[i]
                
                # Debug para FLUJO: verificar cuenta problemática antes de reorganizar
                if nombres[i] == "Flujo Efectivo":
                    target_before_reorg = df[df['Cuenta'].str.contains('Pagos por primas', na=False)]
                    if not target_before_reorg.empty:
                        print(f"🔄 ANTES DE REORGANIZAR {nombres[i]}:")
                        print(f"   Cuenta problemática presente")
                        print(f"   Columnas originales: {list(df.columns)}")
                        print(f"   Ordered_all: {ordered_all}")
                    
                    # NUEVO DEBUG: Verificar si existe la fila de efectivo al principio
                    cash_beginning = df[df['Cuenta'].str.contains('Efectivo y equivalentes al efectivo al principio', na=False)]
                    if not cash_beginning.empty:
                        print(f"✅ EFECTIVO AL PRINCIPIO: presente antes de reorganizar ({len(cash_beginning)} filas)")
                    else:
                        print(f"❌ EFECTIVO AL PRINCIPIO: NO encontrado antes de reorganizar")
                        
                # Asegurar columnas faltantes con NA
                for p in ordered_all:
                    if p not in df.columns:
                        df[p] = pd.NA
                hojas[i] = df[["Cuenta"] + ordered_all]
                
                # Debug para FLUJO: verificar cuenta problemática después de reorganizar
                if os.getenv('X2E_DEBUG') == '1' and nombres[i] == "Flujo Efectivo":
                    target_after_reorg = hojas[i][hojas[i]['Cuenta'].str.contains('Pagos por primas', na=False)]
                    if target_after_reorg.empty:
                        print(f"❌ DESPUÉS DE REORGANIZAR {nombres[i]}: cuenta problemática PERDIDA")
                        
                    # NUEVO DEBUG: Verificar si existe la fila de efectivo al principio después de reorganizar
                    cash_beginning_after = hojas[i][hojas[i]['Cuenta'].str.contains('Efectivo y equivalentes al efectivo al principio', na=False)]
                    if not cash_beginning_after.empty:
                        print(f"✅ EFECTIVO AL PRINCIPIO: presente después de reorganizar ({len(cash_beginning_after)} filas)")
                        print(f"   Muestra valores: {cash_beginning_after.iloc[0].to_dict()}")
                    else:
                        print(f"❌ EFECTIVO AL PRINCIPIO: NO encontrado después de reorganizar")
                        print(f"   Columnas finales: {list(hojas[i].columns)}")
                        print(f"   Total filas: {len(hojas[i])}")
                else:
                    if os.getenv('X2E_DEBUG') == '1' and nombres[i] == "Flujo Efectivo":
                        print(f"✅ DESPUÉS DE REORGANIZAR {nombres[i]}: cuenta problemática AÚN presente")

            # Recorte automático de cola de años prácticamente vacíos (p. ej., 2012)
            try:
                import os as _os
                # Permitir desactivar con X2E_AUTO_TRIM_EMPTY_TAIL=0
                if _os.getenv('X2E_AUTO_TRIM_EMPTY_TAIL', '1') == '1':
                    # Umbral mínimo de celdas no vacías por año (suma de todas las hojas)
                    min_nonempty = int(_os.getenv('X2E_MIN_NONEMPTY_PER_YEAR', '5'))
                    # Recorremos desde el más antiguo hacia el reciente (final de ordered_all → inicio)
                    drop_upto_idx = None
                    for idx_from_end, lbl in enumerate(reversed(ordered_all)):
                        # contar no vacíos sumados en todas las hojas
                        total_nonempty = 0
                        for df in hojas:
                            if lbl in df.columns:
                                s = df[lbl]
                                cnt = int(s.apply(lambda v: (v not in (None, "")) and not pd.isna(v)).sum())
                                total_nonempty += cnt
                        if total_nonempty < min_nonempty:
                            # marcar para cortar esta etiqueta
                            drop_upto_idx = idx_from_end
                        else:
                            break
                    if drop_upto_idx is not None and drop_upto_idx >= 0:
                        # Mantener etiquetas desde inicio hasta antes de la cola a recortar
                        keep_labels = ordered_all[: len(ordered_all) - (drop_upto_idx + 1)]
                        if keep_labels:
                            # Debug para FLUJO: verificar si se pierde la cuenta problemática
                            for i in range(len(hojas)):
                                if os.getenv('X2E_DEBUG') == '1' and nombres[i] == "Flujo Efectivo":
                                    target_before = hojas[i][hojas[i]['Cuenta'].str.contains('Pagos por primas', na=False)]
                                    if not target_before.empty:
                                        print(f"🔍 ANTES DE TRIM: cuenta problemática presente en {nombres[i]}")
                                        cols_before = list(hojas[i].columns)
                                        print(f"   Columnas antes: {cols_before}")
                                        print(f"   Keep_labels: {keep_labels}")
                                        dropped_labels = [c for c in cols_before[1:] if c not in keep_labels]
                                        if dropped_labels:
                                            print(f"   ⚠️  Labels que se van a eliminar: {dropped_labels}")
                                
                                hojas[i] = hojas[i][["Cuenta"] + keep_labels]
                                
                                if os.getenv('X2E_DEBUG') == '1' and nombres[i] == "Flujo Efectivo":
                                    target_after = hojas[i][hojas[i]['Cuenta'].str.contains('Pagos por primas', na=False)]
                                    if target_after.empty:
                                        print(f"❌ DESPUÉS DE TRIM: cuenta problemática ELIMINADA de {nombres[i]}")
                                    else:
                                        print(f"✅ DESPUÉS DE TRIM: cuenta problemática AÚN presente en {nombres[i]}")
            except Exception:
                pass
    except Exception:
        pass

    out_xlsx = out_dir / f"estados_{stem}{suffix}.xlsx"
    # Fallback a openpyxl si xlsxwriter no está disponible
    try:
        excel_writer = pd.ExcelWriter(out_xlsx, engine="xlsxwriter")
    except ImportError:
        print("      ║ xlsxwriter no disponible, utilizando openpyxl...")
        excel_writer = pd.ExcelWriter(out_xlsx, engine="openpyxl")
    
    with excel_writer as writer:
        workbook = writer.book

        # Paleta corporativa y tipografía
        brand_primary = '#0F172A'   # Navy oscuro
        brand_secondary = '#1F2937' # Gris azulado oscuro
        brand_accent = '#2563EB'    # Azul acento sobrio
        brand_gray_100 = '#F7F7F7'
        brand_gray_150 = '#F0F0F0'
        brand_gray_200 = '#E5E7EB'
        base_font = 'Calibri'

        # Propiedades del documento (compatibilidad openpyxl)
        try:
            if hasattr(workbook, 'set_properties'):
                workbook.set_properties({
                    'title': f"Estados financieros {stem}",
                    'subject': 'Reporte financiero generado automáticamente',
                    'company': 'CMF Extract',
                    'category': 'Financial Statements',
                    'comments': 'Generado por xbrl_to_excel.py'
                })
            else:
                # openpyxl method
                workbook.properties.title = f"Estados financieros {stem}"
                workbook.properties.subject = 'Reporte financiero generado automáticamente'
                workbook.properties.category = 'Financial Statements'
                workbook.properties.comments = 'Generado por xbrl_to_excel.py'
        except AttributeError:
            pass

        # Formatos corporativos
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

        # Celda vacía para categorías (celdas numéricas)
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

        # Localización unidad
        unit_header_note = 'Miles CLP' if lang == 'es' else 'Thousands CLP'

        # Intentar identificar nombre de la empresa desde la ruta del dataset (preferido)
        def _guess_company_name_from_path(p: Path) -> str | None:
            try:
                d = p
                company_dir = None
                for _ in range(6):
                    if d is None:
                        break
                    if d.name.startswith('Estados_financieros_(XBRL)') or d.name.startswith('out_consolidated_'):
                        company_dir = d.parent
                        break
                    d = d.parent
                if company_dir is None:
                    company_dir = p.parent
                raw = company_dir.name  # p.ej. 91041000-8_VIÑA_SAN_PEDRO_TARAPACA_SA
                name_part = raw.split('_', 1)[1] if '_' in raw else raw
                human = name_part.replace('_', ' ').strip()
                return human or None
            except Exception:
                return None

        entity_name = _guess_company_name_from_path(out_dir) or stem
        if entity_name == stem:
            # Fallback a entityIdentifier si existe en facts
            try:
                entity_candidates = facts.get('entityIdentifier') if isinstance(facts, pd.DataFrame) else None
                entity_name = str(entity_candidates.dropna().iloc[0]) if entity_candidates is not None and not entity_candidates.dropna().empty else stem
            except Exception:
                entity_name = stem

        # Generar timestamp para pie de página
        ts_str = datetime.now().strftime('%Y-%m-%d %H:%M')

        for idx_sheet, (df, name) in enumerate(zip(hojas, nombres)):
            worksheet = workbook.add_worksheet(name)
            worksheet.set_tab_color(brand_accent)

            # Configuración de impresión y visualización
            worksheet.hide_gridlines(2)
            worksheet.set_landscape()
            worksheet.set_paper(9)  # A4
            worksheet.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
            worksheet.set_zoom(110)
            worksheet.set_default_row(15)

            # Configurar anchos de columnas (asegurar que la columna B sea visible)
            for i, col in enumerate(df.columns):
                if i == 0:
                    max_len = min(max(12, df[col].astype(str).str.len().max() + 5), 65)
                    worksheet.set_column(i, i, max_len)
                else:
                    # Asegurar al menos 12 de ancho para evitar "columna casi oculta"
                    worksheet.set_column(i, i, 18 if i > 0 else 12)

            # Filas: título, subtítulo, encabezados
            ncols = len(df.columns)
            header_row = 2
            title_text = f"{name} — {entity_name}"

            # Construir subtítulo con unidad y periodos
            date_cols = [str(c) for c in df.columns[1:]]
            if lang == 'es':
                periods_label = 'Períodos'
                unit_label = 'Unidad'
            else:
                periods_label = 'Periods'
                unit_label = 'Unit'
            # Rango estético AAAA - AAAA (si solo hay 2-3 fechas, respetar las más recientes)
            if date_cols:
                try:
                    years = sorted({str(c)[:4] for c in date_cols})
                    periods_text = f"{years[0]} - {years[-1]}" if years else '-'
                except Exception:
                    periods_text = ', '.join(date_cols[:4])
            else:
                periods_text = '-'
            subtitle_text = f"{unit_label}: {unit_header_note}    •    {periods_label}: {periods_text}"

            worksheet.merge_range(0, 0, 0, ncols - 1, title_text, title_format)
            worksheet.merge_range(1, 0, 1, ncols - 1, subtitle_text, subtitle_format)
            worksheet.set_row(0, 26)
            worksheet.set_row(1, 18)

            # Encabezados (siempre escribir todos con el mismo formato visual)
            for col_num, value in enumerate(df.columns.values):
                header_text = value
                worksheet.write(header_row, col_num, header_text, header_format)
            worksheet.set_row(header_row, 22)

            # Agrupar columnas trimestrales bajo cada año (modo combinado)
            # Q4 is the "annual summary" column (always visible).
            # Q1-Q3 are grouped under Q4 and hidden for non-latest years.
            if os.getenv('X2E_COMBINED', '0') == '1':
                try:
                    import re as _re
                    # Map year → {quarter_num: col_index}
                    year_quarter_cols: dict[str, dict[int, int]] = {}

                    for c_idx, lbl in enumerate(df.columns):
                        if c_idx == 0:
                            continue  # 'Cuenta'
                        s = str(lbl).strip().split("\n", 1)[0]
                        m_q = _re.match(r"^(\d{4})Q([1-4])$", s)
                        if m_q:
                            y = m_q.group(1)
                            q = int(m_q.group(2))
                            year_quarter_cols.setdefault(y, {})[q] = c_idx

                    # Latest year with quarterly data → all quarters visible
                    latest_year = None
                    try:
                        latest_year = max(int(y) for y in year_quarter_cols.keys()) if year_quarter_cols else None
                    except Exception:
                        latest_year = None

                    for y, qmap in year_quarter_cols.items():
                        is_latest_year = (latest_year is not None and int(y) == int(latest_year))
                        # Q1-Q3 columns (not Q4) for this year
                        inner_quarters = sorted([ci for q, ci in qmap.items() if q != 4])
                        q4_col = qmap.get(4)

                        if not inner_quarters:
                            continue  # only Q4 exists, nothing to group

                        # Group Q1-Q3 with outline level 1
                        start_ci = min(inner_quarters)
                        end_ci = max(inner_quarters)
                        worksheet.set_column(start_ci, end_ci, None, None, {
                            'level': 1,
                            'hidden': (not is_latest_year)
                        })

                        # Q4 is the summary column (to the RIGHT of Q1-Q3, never hidden)
                        if q4_col is not None:
                            worksheet.set_column(q4_col, q4_col, None, None, {
                                'collapsed': (not is_latest_year)
                            })

                    # Enable outline/grouping with summary to the RIGHT of grouped columns
                    try:
                        worksheet.outline_settings(visible=True, symbols_below=False, symbols_right=True, show_outline_symbols=True)
                    except Exception:
                        pass
                except Exception:
                    pass

            # Repetir filas de encabezado en impresión y pie de página
            worksheet.repeat_rows(0, header_row)
            worksheet.set_footer(f"&L{name}  |  {entity_name}&RGenerado: {ts_str}   Página &P de &N")

            # Escribir datos con alternancia (normalizada por bloque y por hoja)
            data_start_row = header_row + 1
            for r_index, (index, row) in enumerate(df.iterrows()):
                row_num = data_start_row + r_index
                cuenta = str(row['Cuenta'])
                
                # Debug para cuenta problemática Y VERIFICACIÓN ADICIONAL
                if 'primas' in cuenta.lower() and 'pagos' in cuenta.lower():
                    if os.getenv('X2E_DEBUG') == '1':
                        print(f"📝 ESCRIBIENDO CUENTA PROBLEMÁTICA AL EXCEL:")
                        print(f"   r_index: {r_index}, row_num: {row_num}")
                        print(f"   cuenta: {cuenta}")
                        print(f"   valores: {[row.get(col) for col in df.columns[1:]]}")
                        
                        # FORZAR que la cuenta aparezca - agregar al final si no está
                        # Esto es un safety net para asegurar que siempre aparezca (solo en modo debug)
                        try:
                            # Escribir la cuenta con formato destacado para fácil identificación
                            worksheet.write(row_num, 0, f">>> {cuenta} <<<", concept_cell_format)
                            print(f"   ✅ FORZADO: Cuenta escrita en fila {row_num} con formato destacado")
                        except Exception as e:
                            print(f"   ❌ Error forzando escritura: {e}")
                
                # Alternancia: usar índice de datos r_index (no row_num absoluto)
                is_alternate = (r_index % 2 == 1)

                cuentas_total_es = [
                    'Ganancia bruta',
                    'Ganancias (pérdidas) de actividades operacionales',
                    'Ganancia (pérdida), antes de impuestos',
                    'Ganancia (pérdida)',
                    'Flujos de efectivo netos procedentes de (utilizados en) operaciones',
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
                # Use same logic as validator for consistency
                is_category = (cuenta_lower.startswith('[') and ']' in cuenta_lower)
                # Tratar etiquetas [sinopsis]/[abstract]/[resumen] como categorías visuales
                is_sinopsis_cat = any(tag in cuenta_lower for tag in ('[sinopsis]', '[abstract]', '[resumen]'))
                if is_sinopsis_cat:
                    is_category = True
                is_total = (
                    any(word in cuenta_lower for word in totales)
                    or cuenta.strip() in cuentas_total_es
                    or cuenta.strip() in cuentas_total_en
                    or cuenta.strip() in cuentas_total_ifrs
                )
                is_subcategory = not is_category and not is_total

                if is_category:
                    concept_cell_format = category_format
                elif is_total:
                    concept_cell_format = total_format
                elif is_alternate:
                    concept_cell_format = subcategory_format_alt
                else:
                    concept_cell_format = subcategory_format

                worksheet.write(row_num, 0, cuenta, concept_cell_format)

                # Helper: robust numeric parser for CSV strings like "539,132,202,000"
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
                    # Trailing minus (e.g., 123-) → negative
                    if s.endswith('-') and not s.startswith('-'):
                        neg = True
                        s = s[:-1].strip()
                    # Remove thousands separators and spaces; keep possible decimal point if present
                    # For CLP values we expect integers; remove commas and dots safely
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

            # Congelar paneles y filtros con nuevas filas de encabezado
            worksheet.freeze_panes(data_start_row, 1)
            worksheet.autofilter(header_row, 0, header_row + len(df), len(df.columns) - 1)


    print(f"      ╔═══════════════════════════════════════════════════════════════════════════════════")
    print(f"      ║ Excel generado exitosamente: {out_xlsx.name}")
    print(f"      ╚═══════════════════════════════════════════════════════════════════════════════════")
    


if __name__ == "__main__":
    main()