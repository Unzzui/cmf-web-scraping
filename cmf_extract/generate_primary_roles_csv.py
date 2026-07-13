#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Genera un CSV primario por empresa con SOLO los 3 roles principales:
  - [210000] Balance general
  - [310000] Estado de resultados
  - [510000] Flujo efectivo (método directo)

Se conecta al pipeline existente reutilizando las funciones de xbrl_to_excel
para normalización y corte por statement, y a batch_xbrl_to_excel para
descubrir datasets de la empresa. El CSV resultante contiene una fila por
(RoleCode, SectionKey, Label) y columnas de fecha YYYY-MM-DD.

Uso:
  python generate_primary_roles_csv.py --company-dir data/XBRL/Total/<RUT_EMPRESA> [--lang es]

Salida:
  <company_dir>/out_consolidated_<RUT_MINMAX>/primary_roles_<RUT_MINMAX>_<lang>.csv
"""

from __future__ import annotations

import argparse
import os
import re
import json
from pathlib import Path
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass
import pandas as pd
import calendar


def _normalize_synopsis_name(name: str) -> str:
    """
    Normalize synopsis marker names to ensure consistent capitalization
    ESTA ES LA ÚNICA FUNCIÓN QUE DEBE HACER NORMALIZACIONES DE SYNOPSIS
    """
    if not name or '[sinopsis]' not in name.lower():
        return name
    
    # Common normalizations for synopsis markers - EXHAUSTIVE LIST
    normalizations = {
        # Principales categorías bancarias
        'negocios no bancarios': 'Negocios no bancarios',
        'servicios bancarios': 'Servicios bancarios',
        'activos bancarios': 'Activos bancarios', 
        'pasivos servicios bancarios': 'Pasivos servicios bancarios',
        
        # Estados financieros principales
        'estado de situación financiera': 'Estado de situación financiera',
        'estado de resultados': 'Estado de resultados',
        'estado de flujos de efectivo': 'Estado de flujos de efectivo',
        
        # Categorías principales
        'activos': 'Activos',
        'pasivos': 'Pasivos',
        'patrimonio': 'Patrimonio',
        'patrimonio y pasivos': 'Patrimonio y pasivos',
        'ganancia (pérdida)': 'Ganancia (pérdida)',
        
        # Subcategorías activos/pasivos
        'activos corrientes': 'Activos corrientes',
        'activos no corrientes': 'Activos no corrientes',
        'pasivos corrientes': 'Pasivos corrientes',
        'pasivos no corrientes': 'Pasivos no corrientes',
        
        # Flujos de efectivo - categorías principales
        'flujos de efectivo procedentes de (utilizados en) actividades de operación': 'Flujos de efectivo procedentes de (utilizados en) actividades de operación',
        'flujos de efectivo procedentes de (utilizados en) actividades de inversión': 'Flujos de efectivo procedentes de (utilizados en) actividades de inversión', 
        'flujos de efectivo procedentes de (utilizados en) actividades de financiación': 'Flujos de efectivo procedentes de (utilizados en) actividades de financiación',
        
        # Flujos de efectivo - subcategorías
        'cambios en activos y pasivos que afectan al flujo operacional': 'Cambios en activos y pasivos que afectan al flujo operacional',
        'cargos (abonos) a resultados que no significan movimientos de efectivo': 'Cargos (abonos) a resultados que no significan movimientos de efectivo',
        'clases de cobros por actividades de operación': 'Clases de cobros por actividades de operación',
        'clases de pagos': 'Clases de pagos',
    }
    
    # Extract the main part without [sinopsis]
    main_part = name.replace('[sinopsis]', '').strip()
    main_lower = main_part.lower()
    
    # Apply normalizations
    for key, normalized in normalizations.items():
        if main_lower == key:
            return f"{normalized} [sinopsis]"
    
    # For other cases, apply title case to first letter only
    if main_part:
        normalized_main = main_part[0].upper() + main_part[1:]
        return f"{normalized_main} [sinopsis]"
    
    return name


def _load_hierarchical_structure(company_rut: str) -> Dict[str, any]:
    """
    Carga la estructura jerárquica desde new_eeff_estructura.json para una empresa específica
    Retorna un diccionario con la estructura por rol
    """
    try:
        estructura_file = Path(__file__).parent / "new_eeff_estructura.json"
        if not estructura_file.exists():
            print(f"⚠️ No se encontró new_eeff_estructura.json en {estructura_file}")
            return {}
        
        with open(estructura_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Buscar empresa por RUT
        for empresa in data.get('empresas', []):
            if empresa.get('empresa', {}).get('rut') == company_rut:
                print(f"📖 Encontrada estructura para {empresa['empresa']['nombre']} ({company_rut})")
                
                # Crear mapa por rol
                structure_by_role = {}
                for rol in empresa.get('roles', []):
                    role_id = rol.get('id')
                    if role_id in ['210000', '310000', '510000']:
                        lineas = rol.get('lineas', [])
                        tree = rol.get('tree', [])
                        
                        # Crear mapeo cuenta -> path jerárquico
                        account_paths = {}
                        
                        def _build_paths(node, path=[]):
                            """Recursivamente construir paths jerárquicos"""
                            current_path = path + [node['label']]
                            
                            # Para cuentas que aparecen en múltiples contextos, crear múltiples entradas
                            label = node['label']
                            if label in account_paths:
                                # Si ya existe, agregar este path como alternativo
                                # Priorizar paths más específicos (más largos)
                                if len(current_path) > len(account_paths[label]):
                                    account_paths[label] = current_path
                            else:
                                account_paths[label] = current_path
                            
                            for child in node.get('children', []):
                                _build_paths(child, current_path)
                        
                        # Construir paths para todo el tree
                        for root in tree:
                            _build_paths(root)
                        
                        structure_by_role[role_id] = {
                            'lineas': lineas,
                            'tree': tree,
                            'account_paths': account_paths
                        }
                        
                        print(f"  📋 Rol {role_id}: {len(lineas)} líneas, {len(account_paths)} paths jerárquicos")
                
                return structure_by_role
        
        print(f"⚠️ No se encontró estructura para empresa {company_rut}")
        return {}
        
    except Exception as e:
        print(f"❌ Error cargando estructura jerárquica: {e}")
        return {}


def _build_hierarchical_label_key(account_label: str, structure: Dict[str, any], role_id: str) -> str:
    """
    Construye el LabelKeyId jerárquico basado en la estructura del JSON
    Formato: role_id||path_jerarquico||cuenta
    """
    if not structure or role_id not in structure:
        return f"{role_id}||{account_label}"
    
    role_structure = structure[role_id]
    account_paths = role_structure.get('account_paths', {})
    
    if account_label in account_paths:
        path = account_paths[account_label]
        # Construir key jerárquico: role_id||categoria_principal||subcategoria||cuenta
        if len(path) > 1:
            # Usar el path completo como jerarquía
            hierarchy_path = "||".join(path[:-1])  # Todos excepto el último (que es la cuenta misma)
            return f"{role_id}||{hierarchy_path}||{account_label}"
        else:
            # Cuenta de nivel raíz
            return f"{role_id}||{account_label}"
    else:
        # Cuenta no encontrada en estructura, usar formato básico
        return f"{role_id}||{account_label}"


# Map a statement kind to role code and a human super-section label
STATEMENTS = [
    ("BALANCE",   "210000", "Balance"),
    ("RESULTADOS","310000", "Resultados"),
    ("FLUJO",     "510000", "Operación"),  # super-section used as prefix for SectionKey in flujo
]


def clean_insufficient_date_columns(df: pd.DataFrame, min_threshold_pct: float = 0.1, enable_log: bool = False) -> pd.DataFrame:
    """
    Elimina columnas de fechas que no tengan suficientes datos en los roles principales.
    
    Utiliza un umbral dinámico basado en la mediana de datos por columna para ser más estricto.
    Preserva el orden original de las columnas de fecha.
    
    Args:
        df: DataFrame filtrado por roles principales (210000, 310000/320000, 510000)
        min_threshold_pct: Porcentaje mínimo base, pero se ajusta dinámicamente (default: 10%)
        enable_log: Si mostrar logs informativos
    
    Returns:
        DataFrame con columnas de fechas limpias en orden original
    """
    if df is None or df.empty:
        return df
    
    # Identificar columnas de fecha puras YYYY-MM-DD EN ORDEN ORIGINAL
    date_cols = [c for c in df.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]
    
    if not date_cols:
        return df  # No hay columnas de fecha para limpiar
    
    meta_cols = [c for c in df.columns if c not in date_cols]  # Columnas que no son fechas
    
    # PASO 1: Calcular estadísticas por columna
    roles = df['RoleCode'].astype(str).unique() if 'RoleCode' in df.columns else []
    col_stats = {}
    
    for date_col in date_cols:  # MANTENER ORDEN ORIGINAL
        total_non_empty = 0
        role_stats = []
        
        for role in sorted(roles):
            role_data = df[df['RoleCode'].astype(str) == role]
            if len(role_data) == 0:
                continue
                
            non_empty = role_data[date_col].notna().sum()
            total_role_rows = len(role_data)
            non_empty_pct = (non_empty / total_role_rows) * 100 if total_role_rows > 0 else 0
            
            role_stats.append(f"R{role}: {non_empty}/{total_role_rows} ({non_empty_pct:.1f}%)")
            total_non_empty += non_empty
        
        col_stats[date_col] = {
            'total_non_empty': total_non_empty,
            'role_stats': role_stats
        }
    
    # PASO 2: Umbral dinámico más estricto basado en múltiples métricas
    non_empty_counts = [col_stats[col]['total_non_empty'] for col in date_cols]
    if non_empty_counts:
        median_count = sorted(non_empty_counts)[len(non_empty_counts) // 2]
        max_count = max(non_empty_counts)
        
        # Parámetros configurables
        median_pct = float(os.getenv('CMF_DATE_MEDIAN_PCT', '0.35'))  # Default: 35% de mediana
        min_absolute = int(os.getenv('CMF_DATE_MIN_ABSOLUTE', '50'))   # Default: mínimo 50 filas

        # El piso absoluto asume una empresa con muchas líneas por período. En empresas
        # pequeñas (inmobiliarias, securitizadoras, clubes) ni la columna más completa
        # llega a 50 valores, así que el piso descarta TODAS las columnas y el CSV queda
        # sin períodos: el Excel sale como esqueleto vacío y la empresa cae en cuarentena
        # con "CSV sin filas o sin períodos válidos". Se acota el piso a la mitad de la
        # columna más rica para que nunca pueda barrer el set completo.
        min_absolute_effective = min(min_absolute, max_count * 0.5)

        # Usar el más estricto de: 35% mediana, 15% del máximo, o el piso acotado
        threshold_median = median_count * median_pct
        threshold_max = max_count * 0.15  # 15% del máximo
        threshold_base = len(df) * min_threshold_pct

        dynamic_threshold = max(threshold_median, threshold_max, threshold_base,
                                min_absolute_effective)
    else:
        dynamic_threshold = len(df) * min_threshold_pct
    
    if enable_log:
        print(f"[primary-csv] 📊 Estadísticas por columna: mediana={median_count if non_empty_counts else 0}, máx={max_count if non_empty_counts else 0}")
        print(f"[primary-csv] 🎯 Umbral dinámico: {dynamic_threshold:.1f} filas mínimas (mediana×{median_pct}, máx×0.15, absoluto≥{min_absolute})")
    
    # PASO 3: Filtrar columnas con múltiples criterios
    cols_to_keep = []
    cols_removed = []
    
    # Detectar años huérfanos (columnas muy separadas del grupo principal)
    orphan_detection = os.getenv('CMF_DATE_ORPHAN_DETECTION', '1') == '1'
    main_years = set()
    
    if orphan_detection and non_empty_counts:
        # Encontrar años con datos significativos (> 50% de la mediana)
        for date_col in date_cols:
            if col_stats[date_col]['total_non_empty'] >= median_count * 0.5:
                year = int(date_col[:4])
                main_years.add(year)
        
        if enable_log and main_years:
            print(f"[primary-csv] 📅 Años principales detectados: {sorted(main_years)}")
    
    for date_col in date_cols:  # MANTENER ORDEN ORIGINAL
        stats = col_stats[date_col]
        year = int(date_col[:4])
        
        # Criterio 1: Umbral dinámico
        meets_threshold = stats['total_non_empty'] >= dynamic_threshold
        
        # Criterio 2: Detección de huérfanos (años muy separados)
        is_orphan = False
        if orphan_detection and main_years:
            # Un año es huérfano si está a >2 años del grupo principal Y tiene pocos datos
            min_main_year = min(main_years)
            max_main_year = max(main_years)
            is_separated = (year < min_main_year - 2) or (year > max_main_year + 2)
            has_few_data = stats['total_non_empty'] < median_count * 0.3  # <30% de la mediana
            is_orphan = is_separated and has_few_data
        
        should_keep = meets_threshold and not is_orphan
        
        if should_keep:
            cols_to_keep.append(date_col)
            if enable_log:
                reason = f"({stats['total_non_empty']} total)"
                if is_orphan:
                    reason += f" [año separado: {year} vs {sorted(main_years)}]"
                print(f"  ✅ {date_col}: {' | '.join(stats['role_stats'])} - CONSERVADA {reason}")
        else:
            cols_removed.append(date_col)
            if enable_log:
                reason = f"({stats['total_non_empty']} total)"
                if is_orphan:
                    reason += f" [año huérfano: {year} separado de {sorted(main_years)}]"
                elif not meets_threshold:
                    reason += f" [< umbral {dynamic_threshold:.0f}]"
                print(f"  ❌ {date_col}: {' | '.join(stats['role_stats'])} - ELIMINADA {reason}")
    
    if enable_log:
        if cols_removed:
            print(f"[primary-csv] 🧹 Limpieza: {len(cols_removed)} columnas con datos insuficientes eliminadas")
        print(f"[primary-csv] 📊 Conservadas: {len(cols_to_keep)} de {len(date_cols)} columnas de fechas")
    
    # Ordenar fechas conservadas de más reciente a más antigua (como el resto del sistema)
    cols_to_keep_sorted = sorted(cols_to_keep, reverse=True)
    
    # Retornar DataFrame con columnas ordenadas correctamente
    final_cols = meta_cols + cols_to_keep_sorted
    return df[final_cols].copy()


def detect_income_statement_role_from_facts(df_facts: pd.DataFrame, company_rut: str = None) -> str:
    """
    Detecta automáticamente si usar rol 310000 (función) o 320000 (naturaleza)
    para el estado de resultados basado en estructura JSON específica por empresa.
    
    Prioridad de detección:
    1. Estructura específica en new_eeff_estructura.json por RUT
    2. RoleCode en facts DataFrame
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
                                enable_log = os.getenv('CMF_PRIMARY_LOG', '0') == '1'
                                if enable_log:
                                    titulo = rol.get('titulo', '')
                                    print(f"[primary-csv] 📋 Estructura JSON empresa {company_rut}: usando rol {role_id}")
                                    if 'naturaleza' in titulo.lower():
                                        print(f"[primary-csv] 🎯 Confirmado rol naturaleza: {titulo[:60]}...")
                                return role_id
                        break
        except Exception as e:
            enable_log = os.getenv('CMF_PRIMARY_LOG', '0') == '1'
            if enable_log:
                print(f"[primary-csv] ⚠ Error leyendo estructura JSON: {e}")
    
    # PRIORIDAD 2: Buscar códigos de rol únicos en facts
    if df_facts is not None and not df_facts.empty and 'RoleCode' in df_facts.columns:
        role_codes = df_facts['RoleCode'].astype(str).unique()
        if '320000' in role_codes:
            return "320000"
        elif '310000' in role_codes:
            return "310000"
    
    # Default fallback: función (310000)
    return "310000"


@dataclass
class DatasetInfo:
    stem: str
    yyyy: int
    mm: int
    dataset_dir: Path


def _quarter_end_for_month(yyyy: int, mm: int) -> str:
    # Map CMF quarters to typical end dates; otherwise last day of month
    if mm in (3, 6, 9, 12):
        day = {3: 31, 6: 30, 9: 30, 12: 31}[mm]
        return f"{yyyy:04d}-{mm:02d}-{day:02d}"
    # For unusual months, take last day
    last_day = calendar.monthrange(yyyy, mm)[1]
    return f"{yyyy:04d}-{mm:02d}-{last_day:02d}"


def _compute_target_date_col(df_cols: List[str], yyyy: int, mm: int) -> str | None:
    # Choose the exact date column matching the period end if present; else best match by year-month prefix
    want = _quarter_end_for_month(yyyy, mm)
    if want in df_cols:
        return want
    prefix = f"{yyyy:04d}-{mm:02d}"
    cands = [c for c in df_cols if isinstance(c, str) and c.startswith(prefix)]
    if cands:
        # pick the max date on that month
        return sorted(cands)[-1]
    # fallback: pick the max date for that year
    yp = f"{yyyy:04d}-"
    cands = [c for c in df_cols if isinstance(c, str) and c.startswith(yp)]
    if cands:
        return sorted(cands)[-1]
    return None


def _detect_context_section(label: str) -> Tuple[str|None, str|None]:
    """Return (main_block, sub_block) from a label line if it looks like a [sinopsis] category.
    main_block recognizes 'Negocios no bancarios' / 'Servicios bancarios'.
    sub_block captures any other [sinopsis] line.
    """
    s = (label or '').strip()
    if not s:
        return None, None
    low = s.lower()
    if '[sinopsis]' in low or '[abstract]' in low or '[resumen]' in low:
        # Normalizaciones removidas - deben venir ya normalizadas desde batch_xbrl_to_excel.py
        # if 'negocios no bancarios' in low:
        #     return 'Negocios no bancarios [sinopsis]', None
        # if 'servicios bancarios' in low:
        #     return 'Servicios bancarios [sinopsis]', None
        
        # Aplicar normalización para consistencia
        normalized_s = _normalize_synopsis_name(s)
        if 'negocios no bancarios' in low:
            return normalized_s, None
        if 'servicios bancarios' in low:
            return normalized_s, None
        # other sinopsis -> treat as sub block
        return None, normalized_s
    return None, None


def _detect_super_section(label: str) -> Optional[str]:
    """Detecta super-sección para Flujo: Operación / Inversión / Financiación."""
    s = (label or '').lower()
    if 'actividades de operación' in s or 'actividades de la operación' in s:
        return 'Operación'
    if 'actividades de inversión' in s or 'actividades de inversion' in s:
        return 'Inversión'
    if 'actividades de financiación' in s or 'actividades de financiacion' in s or 'actividades de financiamiento' in s:
        return 'Financiación'
    return None


def _build_primary_roles_csv(company_dir: Path, lang: str = 'es') -> Path | None:
    """Genera el CSV primario desde los facts consolidados en out_consolidated.

    Estrategia:
      1) Cargar facts consolidados del out_consolidated (facts_*_es.csv)
      2) Quedarnos únicamente con los roles principales 210000/310000/510000
      3) Filtrar filas válidas: Label no vacío, no '[sinopsis]' ni headers, sin 'bloque de texto'
      4) Conservar solo cuentas con algún valor numérico en al menos una fecha
      5) Ordenar por estructura_eeff_empresas.json dentro de cada role
      6) Escribir primary_roles_<rango>_es.csv en out_consolidated
    """
    import importlib, sys, json
    if str(company_dir.parent.parent.parent) not in sys.path:
        sys.path.insert(0, str(company_dir.parent.parent.parent))
    bmod = importlib.import_module('batch_xbrl_to_excel')

    enable_log = os.getenv('CMF_PRIMARY_LOG', '0') == '1'

    # 🆕 CARGAR ESTRUCTURA JERÁRQUICA DESDE new_eeff_estructura.json
    # Extraer RUT del nombre de la carpeta de la empresa. La empresa es
    # `company_dir` mismo (ej. "93007000-9_SOCIEDAD_QUIMICA..."), no su parent
    # (que sería "Total"/"Anual"/etc).
    company_name = company_dir.name  # e.g., "91705000-7_QUIÑENCO_SA"
    rut_with_dv = company_name.split('_', 1)[0]  # Extraer RUT: "91705000-7"
    hierarchical_structure = _load_hierarchical_structure(rut_with_dv)
    if enable_log:
        print(f"[primary-csv] 📖 Estructura jerárquica cargada: {len(hierarchical_structure)} roles")

    # Detectar out_consolidated con el rango de fechas más amplio (end-period más reciente)
    import re as _re_oc
    ocands = [p for p in company_dir.glob('out_consolidated_*') if p.is_dir()]
    if ocands:
        def _end_period(p: Path) -> str:
            m = _re_oc.search(r'(\d{6})(?=[/\\]|$)', p.name)
            return m.group(1) if m else ""
        ocands.sort(key=_end_period, reverse=True)
    out_dir = ocands[0] if ocands else (company_dir / "out_consolidated_memory")
    out_dir.mkdir(exist_ok=True)  # por si no existía

    # LÓGICA ESPECIAL PARA WATTS SA: usar facts CSV mejorado si existe
    is_watts = '76455830-8' in str(company_dir)
    
    df_facts = None
    if is_watts:
        # Para WATTS SA, intentar cargar el facts CSV mejorado primero
        facts_files = list(out_dir.glob('facts_*_es.csv'))
        if facts_files:
            facts_file = facts_files[0]
            try:
                import pandas as pd
                df_facts = pd.read_csv(facts_file)
                if enable_log:
                    print(f"[primary-csv] 🔧 WATTS SA: usando facts CSV mejorado ({len(df_facts.columns)} columnas)")
            except Exception as e:
                if enable_log:
                    print(f"[primary-csv] ⚠ Error leyendo facts mejorado: {e}")
                df_facts = None
    
    # Si no se cargó facts mejorado, usar método estándar
    if df_facts is None:
        if enable_log:
            action = "agregación estándar" if not is_watts else "fallback a agregación estándar"
            print(f"[primary-csv] ▶ {action} (ignorando facts_*_es.csv)")
        try:
            ds_all = [d for d in bmod.find_datasets(company_dir) if getattr(d, 'company_dir', None) == company_dir]
            if not ds_all:
                if enable_log:
                    print(f"[primary-csv] ⚠ No se encontraron datasets para {company_dir}")
                return None
            df_facts = bmod._aggregate_facts_for_company(ds_all, lang, company_dir.parent.parent.parent)
        except Exception as e:
            if enable_log:
                print(f"[primary-csv] ❌ Agregación en memoria falló: {e}")
            return None



    if df_facts is None or df_facts.empty:
        if enable_log:
            print(f"[primary-csv] ⚠ Facts consolidados vacíos para {company_dir.name}")
        return None

    import pandas as pd
    # Identificar columnas de fecha puras YYYY-MM-DD
    date_cols = [c for c in df_facts.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]
    if not date_cols:
        if enable_log:
            print(f"[primary-csv] ⚠ Sin columnas de fecha puras en consolidado: {list(df_facts.columns)[:8]}")
        return None

    # Filtrar solo roles principales - detectar automáticamente 310000 vs 320000
    if 'RoleCode' not in df_facts.columns:
        if enable_log:
            print(f"[primary-csv] ⚠ Facts consolidado sin RoleCode; no es compatible")
        return None
    
    # Detectar automáticamente el rol de estado de resultados (310000 o 320000)
    income_role = detect_income_statement_role_from_facts(df_facts, rut_with_dv)
    primary_roles = ['210000', income_role, '510000']

    if enable_log and income_role == '320000':
        print(f"[primary-csv] 🎯 Detectado rol 320000 (naturaleza) para estado de resultados")

    df = df_facts[df_facts['RoleCode'].astype(str).isin(primary_roles)].copy()

    # ─────────────────────────────────────────────────────────────────────
    # Fallback Balance desde Notes [800100]/[610000].
    # Algunas empresas/períodos no publican [210000] en el XBRL; el módulo
    # `balance_fallback` rescata items de notes y deriva subtotales por
    # identidades IFRS.
    # ─────────────────────────────────────────────────────────────────────
    try:
        from cmf.pipeline.balance_fallback import apply_balance_fallback
        df = apply_balance_fallback(
            df, df_facts, rut_with_dv,
            estructura_dir=Path(__file__).parent,
            enable_log=enable_log,
        )
    except Exception as _exc:
        if enable_log:
            print(f"[primary-csv] ⚠ Fallback Balance falló: {_exc}")

    # Cash Flow: rellenar "Efectivo al final del periodo" desde Balance cuando falte.
    try:
        from cmf.pipeline.cash_flow_fallback import apply_cash_flow_fallback
        df = apply_cash_flow_fallback(df, enable_log=enable_log)
    except Exception as _exc:
        if enable_log:
            print(f"[primary-csv] ⚠ Fallback Cash Flow falló: {_exc}")

    # Estado de Resultados: inyectar D&A y acciones emitidas desde notas
    # ([800200]/[822100]/[823180] para D&A, [861200] para acciones).
    try:
        from cmf.pipeline.income_statement_fallback import apply_income_statement_fallback
        df = apply_income_statement_fallback(df, df_facts, income_role,
                                             enable_log=enable_log)
    except Exception as _exc:
        if enable_log:
            print(f"[primary-csv] ⚠ Fallback Estado de Resultados falló: {_exc}")

    # Manual overrides: valores llenados a mano por el usuario en
    # cmf_extract/manual_overrides.json (o ruta por env CMF_MANUAL_OVERRIDES).
    # Solo rellena celdas que aún están vacías después de los fallbacks.
    try:
        from cmf.pipeline.manual_overrides import apply_manual_overrides
        overrides_path = Path(os.environ.get(
            "CMF_MANUAL_OVERRIDES",
            str(Path(__file__).parent / "manual_overrides.json"),
        ))
        df = apply_manual_overrides(df, rut_with_dv, overrides_path,
                                    enable_log=enable_log)
    except Exception as _exc:
        if enable_log:
            print(f"[primary-csv] ⚠ Manual overrides fallaron: {_exc}")

    # 🧹 LIMPIEZA: Eliminar columnas de fechas con datos insuficientes
    cleanup_threshold = float(os.getenv('CMF_DATE_CLEANUP_THRESHOLD', '0.1'))  # Default: 10%
    if enable_log:
        print(f"[primary-csv] 🧹 Iniciando limpieza de columnas con datos insuficientes (umbral: {cleanup_threshold*100:.1f}%)...")
    df = clean_insufficient_date_columns(df, min_threshold_pct=cleanup_threshold, enable_log=enable_log)
    
    # 🔄 ACTUALIZAR date_cols después de la limpieza
    date_cols = [c for c in df.columns if isinstance(c, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}', c)]
    if enable_log:
        print(f"[primary-csv] 📅 Columnas de fechas post-limpieza: {len(date_cols)} columnas")

    # Paso nuevo: Consolidar valores cuando existen columnas duplicadas del mismo día
    # en df_facts (p.ej., '2019-12-31' y '2019-12-31#2'). Llenar los huecos de las
    # columnas puras YYYY-MM-DD en 'df' usando cualquier columna alternativa no vacía.
    try:
        # Construir grupos de columnas por fecha base - usar solo columnas que existen después de limpieza
        base_to_cols: Dict[str, List[str]] = {}
        # Usar df.columns (post-limpieza) como base, pero buscar alternativas en df_facts
        cleaned_dates = set(date_cols)
        
        for c in df_facts.columns:
            if not isinstance(c, str):
                continue
            m = re.match(r'^(\d{4}-\d{2}-\d{2})', c)
            if m:
                base = m.group(1)
                # Solo incluir si la fecha base existe en df post-limpieza
                if base in cleaned_dates:
                    base_to_cols.setdefault(base, []).append(c)

        # Indexar df_facts por clave estable para cruzar filas
        key_cols = ['RoleCode','SectionKey','Label']
        def _key_from_row(r):
            return (str(r.get('RoleCode','')), str(r.get('SectionKey','')), str(r.get('Label','')))
        facts_index = { _key_from_row(r): i for i, r in df_facts.iterrows() }

        # Asegurar que 'df' contiene solo columnas de fecha puras + metadatos
        # Rellenar vacíos en cada fila
        for i, r in df.iterrows():
            k = _key_from_row(r)
            if k not in facts_index:
                continue
            src_i = facts_index[k]
            src_row = df_facts.loc[src_i]
            for d in date_cols:
                # Verificación adicional de seguridad
                if d not in df.columns:
                    if enable_log:
                        print(f"[primary-csv] ⚠ Columna {d} no existe en df post-limpieza, saltando...")
                    continue
                val = r.get(d)
                # si está vacío, buscar entre candidatas de ese mismo día
                if val is None or (isinstance(val, float) and pd.isna(val)) or (isinstance(val, str) and val.strip() in ('','-')):
                    for cand in base_to_cols.get(d, []):
                        try:
                            v2 = src_row.get(cand)
                        except Exception:
                            v2 = None
                        if v2 is None or (isinstance(v2, float) and pd.isna(v2)):
                            continue
                        s2 = str(v2).strip()
                        if s2 == '' or s2 == '-':
                            continue
              
                        df.at[i, d] = v2
                        break
    except Exception as _e:
        if enable_log:
            print(f"[primary-csv] Aviso: consolidación de columnas duplicadas falló: {_e}")

    # Cargar estructura JSON PRIMERO
    struct_by_role: Dict[str, List[str]] = {}
    try:
        struct_path = Path(__file__).resolve().parent / 'analisis_excel' / 'estructura_eeff_empresas.json'
        if struct_path.exists():
            j = json.loads(struct_path.read_text(encoding='utf-8'))
            rut_with_dv = company_dir.name.split('_', 1)[0]
            emp = None
            for e in j.get('empresas', []):
                erut = str(e.get('empresa',{}).get('rut',''))
                if erut == rut_with_dv and e.get('lang','es') == lang:
                    emp = e; break
            if emp is None:
                for e in j.get('empresas', []):
                    if e.get('lang','es') == lang:
                        emp = e; break
            if emp:
                if os.getenv('CMF_ORDER_DEBUG'):
                    company_name = emp.get('empresa', {}).get('nombre', 'Unknown')
                    company_rut = emp.get('empresa', {}).get('rut', 'Unknown')
                    print(f"[JSON DEBUG] Loading structure for: {company_name} (RUT: {company_rut})")
                    print(f"[JSON DEBUG] Requested RUT was: {rut_with_dv}")
                for r in emp.get('roles', []):
                    rid = str(r.get('id'))
                    struct_by_role[rid] = [str(x) for x in (r.get('lineas') or [])]
                    if os.getenv('CMF_ORDER_DEBUG') and rid == '510000':
                        cash_flow_lines = struct_by_role[rid]
                        print(f"[JSON DEBUG] Role 510000 loaded with {len(cash_flow_lines)} lines")
                        # Show positions of key lines
                        key_lines = [
                            'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
                            'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]',
                            'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]'
                        ]
                        for key_line in key_lines:
                            try:
                                pos = cash_flow_lines.index(key_line)
                                print(f"[JSON DEBUG]   '{key_line}' at position {pos}")
                            except ValueError:
                                print(f"[JSON DEBUG]   '{key_line}' NOT FOUND!")
    except Exception as e:
        if enable_log:
            print(f"[primary-csv] ⚠ No se pudo cargar/parsear estructura JSON: {e}")

    # Determinar qué cuentas [sinopsis] incluir - normalizar para comparación correcta
    json_synopsis_accounts = set()
    try:
        for role_code, seq in struct_by_role.items():
            for label in seq:
                if '[sinopsis]' in str(label).lower():
                    # Normalizar la etiqueta del JSON antes de guardarla para comparación consistente
                    normalized_json_label = _normalize_synopsis_name(str(label).strip())
                    json_synopsis_accounts.add((role_code, normalized_json_label))
        if enable_log:
            print(f"[primary-csv] Cuentas [sinopsis] definidas en JSON: {len(json_synopsis_accounts)}")
    except Exception as e:
        if enable_log:
            print(f"[primary-csv] Error cargando cuentas [sinopsis] del JSON: {e}")
    
    def _is_json_synopsis(row) -> bool:
        """Check if this row is a [sinopsis] account (any synopsis, not just from JSON)"""
        label = str(row.get('Label', '')).strip()
        # Mantener TODAS las cuentas [sinopsis] para preservar la estructura jerárquica
        return '[sinopsis]' in label.lower() or '[abstract]' in label.lower()

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
    
    # 🔧 NORMALIZACIÓN CRÍTICA: Aplicar antes de cualquier procesamiento
    print(f"[primary-csv] 🔧 Normalizando {len(df)} labels antes de procesamiento...")
    df['Label'] = df['Label'].apply(lambda x: _normalize_synopsis_name(str(x)) if pd.notna(x) else x)
    # También normalizar SectionKey que puede contener etiquetas [sinopsis]
    if 'SectionKey' in df.columns:
        df['SectionKey'] = df['SectionKey'].apply(lambda x: _normalize_synopsis_name(str(x)) if pd.notna(x) else x)
    # Normalizar claves compuestas que pueden contener etiquetas [sinopsis]
    for key_col in ['LabelKeyId', 'LabelKeyIdExt']:
        if key_col in df.columns:
            def _normalize_compound_key(key_str):
                if not key_str or pd.isna(key_str):
                    return key_str
                # Las claves tienen formato "210000||section||label", normalizar cada parte
                parts = str(key_str).split('||')
                normalized_parts = []
                for part in parts:
                    normalized_parts.append(_normalize_synopsis_name(part))
                return '||'.join(normalized_parts)
            df[key_col] = df[key_col].apply(_normalize_compound_key)
    
    # 🆕 RECONSTRUIR LabelKeyIdExt usando la estructura jerárquica desde new_eeff_estructura.json
    if hierarchical_structure:
        if enable_log:
            print(f"[primary-csv] 🔨 Reconstruyendo LabelKeyIdExt con estructura jerárquica...")
        
        def _rebuild_label_key_id_ext(row):
            role_code = str(row.get('RoleCode', ''))
            label = str(row.get('Label', ''))
            current_key = str(row.get('LabelKeyIdExt', ''))
            
            if role_code in hierarchical_structure:
                # Construir nuevo LabelKeyIdExt jerárquico
                new_key = _build_hierarchical_label_key(label, hierarchical_structure, role_code)
                if enable_log and new_key != current_key:
                    print(f"[hierarchy] {label[:40]}: {current_key} → {new_key}")
                return new_key
            else:
                return current_key
        
        # Aplicar reconstrucción a LabelKeyIdExt
        if 'LabelKeyIdExt' in df.columns:
            df['LabelKeyIdExt'] = df.apply(_rebuild_label_key_id_ext, axis=1)
            if enable_log:
                print(f"[primary-csv] ✅ LabelKeyIdExt reconstruido para {len(df)} filas")
    
    # Filtrar labels inválidos pero conservar [sinopsis] que están en la estructura JSON
    def _is_valid_or_json_synopsis(row) -> bool:
        label = str(row.get('Label', ''))
        if _is_valid_label(label):
            return True
        # Si no es válido normalmente, verificar si es [sinopsis] del JSON
        return _is_json_synopsis(row)
    
    df = df[df.apply(_is_valid_or_json_synopsis, axis=1)].copy()

    # NUEVA FUNCIONALIDAD: Generar cuentas [sinopsis] faltantes del JSON
    # Esto asegura que todas las cuentas estructurales definidas en estructura_eeff_empresas.json
    # aparezcan en el CSV aunque no tengan datos, manteniendo la jerarquía correcta
    # NO generar cuentas faltantes - solo ordenar las cuentas existentes
    # Esto permite que funcione con las +40 empresas diferentes que tienen estructuras distintas

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
    # Antes de filtrar por numéricos, aplicar relleno especial para flujo (fin <- inicio) si faltan valores
    try:
        # Mapa rápido label normalizado -> índice
        def _norm(s: str) -> str:
            return (s or '').replace('\xa0',' ').strip().lower()
        idx_by_key = {}
        for i, r in df.iterrows():
            rc = str(r.get('RoleCode',''))
            lbl = _norm(str(r.get('Label','')))
            sec = str(r.get('SectionKey',''))
            idx_by_key[(rc, sec, lbl)] = i

        end_patterns = [
            'efectivo y equivalentes al efectivo al final del periodo',
            'cash and cash equivalents at end of period',
            'cash and cash equivalents at the end of the period',
        ]
        begin_patterns = [
            'efectivo y equivalentes al efectivo al principio del periodo',
            'cash and cash equivalents at beginning of period',
            'cash and cash equivalents at the beginning of the period',
        ]

        # Para cada fila de FIN buscar fila de INICIO en el mismo SectionKey (si existe) y rellenar vacíos
        for (rc, sec, lbl_norm), i in list(idx_by_key.items()):
            if rc != '510000':
                continue
            if not any(p in lbl_norm for p in end_patterns):
                continue
            # buscar inicio mismo sec; si no, buscar cualquiera
            beg_idx = None
            for key2, j in idx_by_key.items():
                rc2, sec2, lbl2 = key2
                if rc2 != '510000':
                    continue
                if any(p in lbl2 for p in begin_patterns) and sec2 == sec:
                    beg_idx = j; break
            if beg_idx is None:
                for key2, j in idx_by_key.items():
                    rc2, sec2, lbl2 = key2
                    if rc2 != '510000':
                        continue
                    if any(p in lbl2 for p in begin_patterns):
                        beg_idx = j; break
            if beg_idx is None:
                continue
            # rellenar
            for d in date_cols:
                v = df.at[i, d] if d in df.columns else None
                if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and v.strip() in ('','-')):
                    vb = df.at[beg_idx, d] if d in df.columns else None
                    if vb is None or (isinstance(vb, float) and pd.isna(vb)) or (isinstance(vb, str) and vb.strip() in ('','-')):
                        continue
                 
    except Exception as _e:
        if enable_log:
            print(f"[primary-csv] Aviso: relleno fin<-inicio falló: {_e}")

    # Incluir filas con valores numéricos O [sinopsis] definidas en JSON O categorías principales de flujo
    # Esto preserva la estructura jerárquica completa
    def _is_main_cash_flow_category(row) -> bool:
        """Preservar categorías principales de flujo de efectivo aunque no tengan valores"""
        label = str(row.get('Label', '')).strip()
        role_code = str(row.get('RoleCode', '')).strip()
        
        if role_code != '510000':  # Solo para flujo de efectivo
            return False
        
        # Excluir cuentas intermedias con || que contaminan el orden  
        if '||' in label:
            return False
        
        # Categorías principales que DEBEN aparecer como encabezados
        main_categories = [
            'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
            'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]', 
            'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]',
            'Negocios no bancarios [sinopsis]',
            'Servicios bancarios [sinopsis]'
        ]
        
        return any(main_cat in label for main_cat in main_categories)
    
    def _is_intermediate_account(row) -> bool:
        """Filtrar cuentas intermedias que no deben aparecer en el output final"""
        label = str(row.get('Label', '')).strip()
        return '||' in label  # Cuentas con || son intermedias del procesamiento jerárquico
    
    df = df[df.apply(lambda r: (_row_has_numeric(r) or _is_json_synopsis(r) or _is_main_cash_flow_category(r)) 
                              and not _is_intermediate_account(r), axis=1)].copy()

   

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



    # Ordenamiento DIRECTO basado en claves jerárquicas LabelKeyId, LabelKeyIdExt, SectionKey
    df['__role_ord'] = df['RoleCode'].map({'210000':1,'310000':2,'510000':3}).fillna(9).astype(int)
    
    if struct_by_role:
        # Ordenamiento simple y directo usando las claves jerárquicas tal como están
        def _create_hierarchical_sort_key(row):
            role_ord = row['__role_ord']
            label = str(row.get('Label', ''))
            label_key_id = str(row.get('LabelKeyId', ''))
            label_key_id_ext = str(row.get('LabelKeyIdExt', ''))
            section_key = str(row.get('SectionKey', ''))
            
            # Buscar posición JSON si existe
            seq = struct_by_role.get(str(row['RoleCode'])) or []
            normalized_label = _normalize_synopsis_name(label)
            json_position = 999999
            for idx, json_item in enumerate(seq):
                if _normalize_synopsis_name(str(json_item)) == normalized_label:
                    json_position = idx
                    break
            
            # Si existe en JSON, usar posición exacta como prioridad
            if json_position != 999999:
                is_synopsis = 0 if '[sinopsis]' in label.lower() else 1
                return (role_ord, json_position, is_synopsis, 0, label.lower())
            
            # Para cuentas no en JSON: ordenar por claves jerárquicas
            # Usar LabelKeyId como clave principal de ordenamiento + offset alto para ir después
            primary_key = label_key_id if label_key_id else label_key_id_ext
            is_synopsis = 0 if '[sinopsis]' in label.lower() else 1
            
            # Convertir primary_key a posición numérica basada en hash
            primary_order = 100000 + abs(hash(primary_key)) % 100000
            
            return (role_ord, primary_order, is_synopsis, hash(section_key) % 1000, label.lower())
        
        # Aplicar ordenamiento directo por claves jerárquicas
        sort_keys = df.apply(_create_hierarchical_sort_key, axis=1)
        df['__sort_key'] = sort_keys
        
        # Debug: mostrar claves de ordenamiento para cuentas problemáticas  
        if os.getenv('CMF_ORDER_DEBUG'):
            problem_accounts = ['Negocios no bancarios [sinopsis]', 'Clases de cobros por actividades de operación [sinopsis]', 'Cobros procedentes de las ventas de bienes y prestación de servicios']
            for idx, row in df.iterrows():
                label = str(row.get('Label', ''))
                if (any(problem in label for problem in problem_accounts) or 
                    'Cobros procedentes de las ventas' in label) and row.get('RoleCode') == 510000:
                    # Usar loc con el índice real del DataFrame
                    sort_key = sort_keys.loc[idx]
                    group_ord = row.get('__group_ord', 'N/A')
                    print(f"[SORT DEBUG] '{label}' -> sort_key: {sort_key}")
                    print(f"             group_ord: {group_ord}")
        
        df = df.sort_values('__sort_key', kind='stable')
        df.drop(columns=['__sort_key'], inplace=True, errors='ignore')
    else:
        # Sin estructura JSON, ordenar por RoleCode, SectionKey, Label
        df.sort_values(['__role_ord','SectionKey','Label'], inplace=True, kind='stable')
    
    df.drop(columns=['__role_ord'], inplace=True)

    # 🔥 FORZAR CREACIÓN DE SUBCATEGORÍAS OBLIGATORIAS EN CASH FLOW
    # Asegurar que existen las 3 entradas de cada subcategoría bajo cada categoría principal
    if enable_log:
        print("[primary-csv] 🔒 Forzando subcategorías obligatorias en Cash Flow...")
    
    main_categories_cash_flow = [
        'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
        'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]',
        'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]'
    ]
    subcategorias_obligatorias = [
        'Negocios no bancarios [sinopsis]',
        'Servicios bancarios [sinopsis]'
    ]
    
    # Obtener columnas de fecha del DataFrame existente
    existing_date_cols = [col for col in df.columns if col not in ['LabelKeyId', 'LabelKeyIdExt', 'SectionKey', 'Label', 'RoleCode']]
    
    for main_cat in main_categories_cash_flow:
        for subcat in subcategorias_obligatorias:
            # Verificar si ya existe esta combinación
            label_key_ext = f"510000||{main_cat}||{subcat}"
            exists = ((df['RoleCode'] == '510000') & 
                     (df['LabelKeyIdExt'] == label_key_ext) & 
                     (df['Label'] == subcat)).any()
            
            if not exists:
                # Crear nueva fila para la subcategoría
                new_row = {
                    'LabelKeyId': label_key_ext,
                    'LabelKeyIdExt': label_key_ext,
                    'SectionKey': f"{main_cat}||{subcat}",
                    'Label': subcat,
                    'RoleCode': '510000'
                }
                # Agregar columnas de fecha vacías
                for date_col in existing_date_cols:
                    new_row[date_col] = ''
                
                # Agregar al DataFrame
                df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
                if enable_log:
                    print(f"   ✅ CREADA: {main_cat[:30]}... → {subcat}")
    
    # Re-ordenar después de agregar las nuevas filas (incluir 320000 con mismo orden que 310000)
    df['__role_ord'] = df['RoleCode'].map(lambda x: {'210000':1,'310000':2,'320000':2,'510000':3}.get(x,9))
    df.sort_values(['__role_ord', 'LabelKeyIdExt', 'Label'], inplace=True, kind='stable')
    df.drop(columns=['__role_ord'], inplace=True)

    # Escribir CSV primario
    # Derivar rango ym del nombre de algún facts en out_consolidated o de fechas
    ym_guess = None
    for f in out_dir.glob('facts_*_es.csv'):
        m = re.match(r'^facts_(.+?)_(\d{6}-\d{6})_es\.csv$', f.name)
        if m:
            ym_guess = m.group(2)
            break
    if ym_guess is None:
        # fallback a min-max de columnas de fecha
        yms = sorted({c[:7] for c in date_cols})
        ym_guess = f"{yms[0].replace('-','')}-{yms[-1].replace('-','')}" if yms else 'range'

    out_path = out_dir / f"primary_roles_{ym_guess}_{lang}.csv"
    df.to_csv(out_path, index=False)
    if enable_log:
        print(f"[primary-csv] Escrito: {out_path} | filas={len(df)} | fechas={len(date_cols)}")
        for rc, title in [('210000','Balance'),('310000','Resultados'),('320000','Resultados'),('510000','Flujo')]:
            sub = df[df['RoleCode']==rc]
            if len(sub):
                print(f"  - {title} ({rc}): {len(sub)} filas | primeras: {sub['Label'].head(8).tolist()}")
    return out_path

 

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description='Genera CSV primario de 3 roles principales para una empresa')
    ap.add_argument('--company-dir', type=Path, required=True, help='Directorio de la empresa bajo data/XBRL/Total/...')
    ap.add_argument('--lang', default='es', choices=['es'], help='Idioma de labels (solo es)')
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    p = _build_primary_roles_csv(args.company_dir, args.lang)
    return 0 if p else 1


if __name__ == '__main__':
    raise SystemExit(main())