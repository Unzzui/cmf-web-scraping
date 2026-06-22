#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facts Enhancer - Parche para mejorar matching de datos en facts.csv

PROBLEMAS QUE RESUELVE:
1. Fechas con contexto/miembro: "2023-12-31 - Vehículos [miembro]" 
2. Cuentas con nombres muy largos que fallan en matching
3. Datos importantes que se pierden por contextos específicos

ESTRATEGIA:
- Buscar valores faltantes en fechas exactas pero con contextos diferentes
- Matching fuzzy para cuentas muy largas
- Fallback inteligente preservando integridad de datos
"""

import pandas as pd
import re
import os
from pathlib import Path
from typing import Dict, Set, Optional, List, Tuple

# --- helpers y flags al inicio del archivo (debajo de imports) ---
X2E_ENABLE_CONTEXT_PROMOTION = os.getenv('X2E_ENABLE_CONTEXT_PROMOTION', '0') == '1'

def _is_pure_date_col(col: str) -> bool:
    return bool(re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(col).strip()))

def _is_ifrs9_sensitive(label: str) -> bool:
    if not label:
        return False
    s = label.lower()
    keys = [
        'para negociar',
        'no destinados a negociación',
        'obligatoriamente',
        'valorados obligatoriamente',
        'valor razonable con cambios en resultados'
    ]
    return any(k in s for k in keys)

def _allowed_context_header(h: str) -> bool:
    """
    Solo permitir (si se activa por env) contextos que NO tengan '[...]' y que, si traen sufijo,
    sea algo tipo ' - Consolidado'/' - Consolidated'. Nada de miembros/dimensiones.
    """
    h = str(h)
    if '[' in h:
        return False
    low = h.lower()
    # Permitir únicamente sufijos planos sin miembros (muy conservador)
    return (' - consolidado' in low or ' - consolidated' in low)

# --- reemplaza COMPLETO enhance_facts_with_context_data por este ---
def enhance_facts_with_context_data(facts_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    MODO SEGURO (por defecto): NO promociona datos desde columnas con contexto.
    Si X2E_ENABLE_CONTEXT_PROMOTION=1, solo copiará desde columnas sin '[miembro]'
    y jamás para etiquetas IFRS9 sensibles.
    """
    if facts_df is None or facts_df.empty:
        return facts_df

    if not X2E_ENABLE_CONTEXT_PROMOTION:
        if debug:
            print("DEBUG Facts Enhancer: promoción de contextos DESACTIVADA (modo estricto).")
        return facts_df

    enhanced_df = facts_df.copy()
    # Columnas que "empiezan por" fecha
    date_columns = [c for c in enhanced_df.columns if re.match(r'^\d{4}-\d{2}-\d{2}', str(c))]
    clean_dates   = [c for c in date_columns if _is_pure_date_col(c)]
    context_dates = [c for c in date_columns if not _is_pure_date_col(c)]

    if debug:
        print(f"DEBUG Facts Enhancer (context on): {len(clean_dates)} limpias, {len(context_dates)} con contexto")

    enhanced_count = 0
    for ridx, row in enhanced_df.iterrows():
        label = str(row.get('Label', '') or '').strip()
        # Nunca copiar para etiquetas IFRS9 delicadas
        if _is_ifrs9_sensitive(label):
            continue

        # Fechas limpias vacías
        empty_clean = [d for d in clean_dates if (pd.isna(row.get(d)) or str(row.get(d)).strip() == '')]
        if not empty_clean:
            continue

        for empty_date in empty_clean:
            base = empty_date  # ya es YYYY-MM-DD exacto
            # Buscar contextos DEL MISMO día permitidos (sin [miembro], solo ' - Consolidado' opcional)
            candidates = [cd for cd in context_dates if str(cd).startswith(base) and _allowed_context_header(cd)]
            best_value = None
            for cd in candidates:
                val = row.get(cd)
                if pd.notna(val) and str(val).strip() != '':
                    best_value = val
                    break  # primera permitida gana (no hay prioridad por miembro)

            if best_value is not None:
                enhanced_df.at[ridx, empty_date] = best_value
                enhanced_count += 1
                if debug:
                    print(f"DEBUG: {label[:60]} → {empty_date} <- {cd}")

    if debug:
        print(f"DEBUG Facts Enhancer: {enhanced_count} celdas rellenadas desde contextos PERMITIDOS")
    return enhanced_df



def _get_context_priority(context_date: str) -> int:
    """Asigna prioridad a contextos (mayor número = mayor prioridad)"""
    context = context_date.lower()
    
    # Prioridad alta: contextos generales o consolidados
    if 'consolidado' in context or 'consolidated' in context:
        return 100
    if 'total' in context:
        return 90
    if 'grupo' in context or 'group' in context:
        return 80
        
    # Prioridad media: contextos específicos pero relevantes
    if 'corriente' in context or 'current' in context:
        return 70
    if 'no corriente' in context or 'non current' in context:
        return 60
        
    # Prioridad baja: contextos muy específicos
    if 'miembro' in context or 'member' in context:
        return 30
    if 'vehículo' in context or 'vehicle' in context:
        return 20
        
    # Default: contexto desconocido
    return 50


def enhance_long_label_matching(complete_structure: pd.DataFrame, facts_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    Mejora el matching para cuentas con nombres muy largos usando fuzzy matching
    y búsqueda por palabras clave.
    """
    if complete_structure is None or complete_structure.empty or facts_df is None or facts_df.empty:
        return complete_structure
        
    enhanced_structure = complete_structure.copy()
    
    # Identificar cuentas sin datos
    date_cols = [c for c in enhanced_structure.columns if re.match(r'^\d{4}-\d{2}-\d{2}$', c)]
    empty_accounts = []
    
    for idx, row in enhanced_structure.iterrows():
        label = row.get('Cuenta', '') or row.get('Label', '')
        if not label:
            continue
            
        # Verificar si no tiene datos en ninguna fecha
        has_data = any(pd.notna(row[dc]) and str(row[dc]).strip() != '' for dc in date_cols)
        if not has_data:
            empty_accounts.append((idx, label))
    
    if debug:
        print(f"DEBUG Long Label Matcher: {len(empty_accounts)} cuentas sin datos para mejorar")
    
    matched_count = 0
    
    for idx, account_label in empty_accounts:
        # Buscar en facts usando diferentes estrategias
        best_match = _find_best_label_match(account_label, facts_df, debug)
        
        if best_match is not None:
            # Copiar valores del match encontrado
            for dc in date_cols:
                if dc in facts_df.columns:
                    value = best_match.get(dc)
                    if pd.notna(value) and str(value).strip() != '':
                        enhanced_structure.loc[idx, dc] = value
            
            matched_count += 1
            
            if debug:
                match_label = best_match.get('Label', 'Unknown')
                print(f"DEBUG: Matched '{account_label[:50]}...' -> '{match_label[:50]}...'")
    
    if debug:
        print(f"DEBUG Long Label Matcher: Mejorados {matched_count} matches")
    
    return enhanced_structure


def _find_best_label_match(target_label: str, facts_df: pd.DataFrame, debug: bool = False) -> Optional[pd.Series]:
    """
    Encuentra la mejor coincidencia para una cuenta usando múltiples estrategias.
    """
    if not target_label:
        return None
        
    target_lower = target_label.lower()
    target_words = set(re.findall(r'\b\w{4,}\b', target_lower))  # Palabras significativas
    
    best_match = None
    best_score = 0
    
    for _, row in facts_df.iterrows():
        fact_label = str(row.get('Label', '')).strip()
        if not fact_label:
            continue
            
        fact_lower = fact_label.lower()
        
        # Estrategia 1: Coincidencia exacta
        if target_lower == fact_lower:
            return row
            
        # Estrategia 2: Contención directa
        if target_lower in fact_lower or fact_lower in target_lower:
            score = min(len(target_lower), len(fact_lower)) / max(len(target_lower), len(fact_lower))
            if score > best_score:
                best_score = score
                best_match = row
                
        # Estrategia 3: Coincidencia de palabras clave
        fact_words = set(re.findall(r'\b\w{4,}\b', fact_lower))
        common_words = target_words.intersection(fact_words)
        
        if len(common_words) >= 3:  # Al menos 3 palabras en común
            word_score = len(common_words) / len(target_words.union(fact_words))
            if word_score > best_score:
                best_score = word_score
                best_match = row
    
    # Solo devolver si la puntuación es razonablemente buena
    if best_score > 0.6:  # 60% de similitud mínima
        return best_match
        
    return None


def _apply_facts_values_directly(structure: pd.DataFrame, facts_df: pd.DataFrame, debug: bool = False) -> pd.DataFrame:
    """
    Aplica valores de facts a la estructura con coincidencia EXACTA por etiqueta.
    - No usa fuzzy.
    - No copia contextos/dimensiones.
    - No sobreescribe celdas ya pobladas.
    - Ignora filas de categoría (headers y [sinopsis]/[abstract]/[resumen]).
    """
    if structure is None or facts_df is None or structure.empty or facts_df.empty:
        return structure

    import re
    import pandas as pd

    def _normalize_spaces(s: str) -> str:
        return re.sub(r"\s+", " ", s.strip()) if isinstance(s, str) else ""

    def _is_category(label: str) -> bool:
        if not label:
            return False
        l = label.lower()
        if re.match(r"^\[\d{6}\]\s", label):  # headers tipo [310000] ...
            return True
        if "[sinopsis]" in l or "[abstract]" in l or "[resumen]" in l:
            return True
        return False

    result = structure.copy()

    # Fechas "limpias" del facts (YYYY-MM-DD) y que además existan en la estructura
    facts_dates = [c for c in facts_df.columns if re.match(r"^\d{4}-\d{2}-\d{2}$", str(c))]
    date_columns = [d for d in facts_dates if d in result.columns]
    if not date_columns:
        if debug:
            print("DEBUG _apply_facts_values_directly: no hay columnas de fecha en común; no se aplica.")
        return result

    # Índice por Label con normalización de espacios (match exacto tras normalizar)
    facts_by_label = {}
    for _, row in facts_df.iterrows():
        raw = row.get("Label", "")
        lab = _normalize_spaces(str(raw))
        if lab and lab not in facts_by_label:
            facts_by_label[lab] = row  # si hay duplicados, conserva el primero

    applied_count = 0

    for idx, struct_row in result.iterrows():
        struct_label = _normalize_spaces(str(struct_row.get("Cuenta", "") or struct_row.get("Label", "")))
        if not struct_label:
            continue
        if _is_category(struct_label):
            # Nunca completar valores en categorías/headers
            continue

        # Coincidencia EXACTA tras normalizar espacios
        fact_row = facts_by_label.get(struct_label)
        if fact_row is None:
            continue

        # Copiar solo si la celda está vacía en la estructura
        for dc in date_columns:
            # valor en facts
            val = fact_row.get(dc)
            if pd.isna(val) or str(val).strip() == "":
                continue
            # celda actual en estructura
            cur = result.at[idx, dc] if dc in result.columns else None
            if (cur is None) or (pd.isna(cur)) or (str(cur).strip() == ""):
                result.at[idx, dc] = val
                applied_count += 1

    if debug and applied_count > 0:
        print(f"DEBUG _apply_facts_values_directly: {applied_count} celdas rellenadas (match exacto).")

    return result

def apply_facts_enhancements(complete_structure: pd.DataFrame, facts_df: pd.DataFrame, debug: bool = False, output_dir: Optional[Path] = None) -> pd.DataFrame:
    if debug:
        print("🔧 Aplicando Facts Enhancer...")

    # Paso 1: contextos -> OK (no mezcla etiquetas distintas)
    enhanced_facts = enhance_facts_with_context_data(facts_df, debug)

    # Paso 2: ⚠️ DESACTIVADO por defecto (solo si X2E_ENABLE_LONG_LABEL_MATCH=1)
    enable_long = os.getenv('X2E_ENABLE_LONG_LABEL_MATCH', '0') == '1'
    if enable_long:
        enhanced_structure = enhance_long_label_matching(complete_structure, enhanced_facts, debug)
    else:
        if debug:
            print("DEBUG: Long label matching DESACTIVADO (modo estricto)")
        enhanced_structure = complete_structure.copy()

    # Paso 3: reaplicar valores exactos
    final_structure = _apply_facts_values_directly(enhanced_structure, enhanced_facts, debug)

    # Paso 4: búsqueda en facts individuales (match exacto de etiqueta)
    if output_dir is not None:
        final_structure = enhance_with_individual_facts(final_structure, output_dir, debug)

    if debug:
        print("✅ Facts Enhancer completado")
    return final_structure




def enhance_with_individual_facts(structure: pd.DataFrame, output_dir: Path, debug: bool = False) -> pd.DataFrame:
    """
    Busca datos faltantes en facts individuales de cada período para cuentas que no tienen valores
    en el facts consolidado. Esto resuelve el problema de cuentas como:
    - "Efectivo y equivalentes al efectivo al principio del periodo"
    - Otras cuentas que se pierden en la consolidación
    
    LÓGICA ESPECIAL PARA EFECTIVO:
    - "Efectivo al principio" = "Efectivo al final" del periodo anterior
    """
    if structure.empty:
        return structure
        
    if debug:
        print("🔍 Buscando datos faltantes en facts individuales...")
    
    # Identificar cuentas completamente vacías
    # Buscar tanto fechas estándar como fechas con dimensiones en la estructura
    date_columns = [c for c in structure.columns if re.match(r'^\d{4}-\d{2}-\d{2}($|\s)', c)]
    empty_accounts = []
    
    for idx, row in structure.iterrows():
        label = row.get('Cuenta', '') or row.get('Label', '')
        if not label:
            continue
            
        # LÓGICA ESPECIAL: Para efectivo al principio del periodo, aplicar lógica de flujo
        if 'efectivo' in label.lower() and 'principio' in label.lower():
            structure = _fix_cash_flow_beginning_logic(structure, idx, label, date_columns, debug)
            continue
            
        # Para otras cuentas, verificar si no tiene datos
        has_data = any(
            pd.notna(row[dc]) and 
            str(row[dc]).strip() not in ['', 'nan', 'NaN', 'None'] 
            for dc in date_columns
        )
        if not has_data:
            empty_accounts.append((idx, label))
    
    if debug and len(empty_accounts) > 0:
        print(f"DEBUG: {len(empty_accounts)} cuentas sin datos buscando en facts individuales")
        for i, (_, label) in enumerate(empty_accounts[:5]):  # Mostrar primeras 5
            if any(x in label.lower() for x in ['efectivo', 'principio', 'corrientes']):
                print(f"  → Cuenta objetivo sin datos: {label[:60]}...")
    
    if len(empty_accounts) == 0:
        if debug:
            print("DEBUG: Todas las cuentas ya tienen datos, saltando búsqueda individual")
        return structure
    
    # Buscar facts individuales en el directorio padre
    individual_facts = _find_individual_facts_files(output_dir, debug)
    
    if len(individual_facts) == 0:
        if debug:
            print("DEBUG: No se encontraron facts individuales")
        return structure
    
    enhanced_structure = structure.copy()
    total_enhanced = 0
    
    # Procesar cada cuenta vacía
    for idx, account_label in empty_accounts:
        # Buscar en facts individuales
        found_values = _search_in_individual_facts(account_label, individual_facts, debug)
        
        if found_values:
            # Aplicar valores encontrados
            for date_col, value in found_values.items():
                if date_col in enhanced_structure.columns:
                    enhanced_structure.loc[idx, date_col] = value
                    total_enhanced += 1
                    
            if debug and any(x in account_label.lower() for x in ['efectivo', 'principio']):
                print(f"✅ Enhanced '{account_label[:50]}...' con {len(found_values)} valores")
    
    if debug:
        print(f"DEBUG: Enhanced {total_enhanced} valores desde facts individuales")
    
    return enhanced_structure


def _find_individual_facts_files(output_dir: Path, debug: bool = False) -> List[Path]:
    """
    Encuentra todos los archivos facts individuales en el directorio de la empresa
    OPTIMIZADO: Solo busca los archivos más recientes para mejorar rendimiento
    """
    facts_files = []
    
    try:
        # El output_dir es algo como: data/XBRL/Total/91705000-7_QUIÑENCO_SA/out_consolidated_2025-2014
        # Necesitamos buscar en el directorio padre para encontrar los facts individuales
        company_dir = output_dir.parent
        
        if debug:
            print(f"DEBUG: Buscando facts individuales en {company_dir}")
        
        # OPTIMIZACIÓN: Limitar búsqueda a los archivos más recientes (últimos 2 años)
        # para evitar procesar demasiados archivos
        current_year = 2025
        min_year = current_year - 2  # Solo archivos de 2023 en adelante
        
        # Buscar patrones como: Estados_financieros_(XBRL)91705000_*/out_*/facts_*_es.csv
        for item in company_dir.rglob("facts_*_es.csv"):
            if "out_" in str(item) and "consolidated" not in str(item):
                # Extraer año del nombre del archivo para filtrar
                year_match = re.search(r'(\d{4})', item.stem)
                if year_match:
                    file_year = int(year_match.group(1))
                    if file_year >= min_year:  # Solo archivos recientes
                        facts_files.append(item)
                else:
                    # Si no podemos extraer el año, incluirlo por seguridad
                    facts_files.append(item)
                
        # Ordenar por fecha más reciente primero para priorizar datos nuevos
        facts_files.sort(reverse=True)
        
        # LÍMITE DE SEGURIDAD: Máximo 10 archivos para evitar sobrecarga
        if len(facts_files) > 10:
            facts_files = facts_files[:10]
            if debug:
                print(f"DEBUG: Limitado a los 10 archivos más recientes por rendimiento")
                
        if debug:
            print(f"DEBUG: Encontrados {len(facts_files)} archivos de facts individuales (filtrados)")
            for i, f in enumerate(facts_files[:3]):  # Mostrar primeros 3
                print(f"  → {f.name}")
                
    except Exception as e:
        if debug:
            print(f"DEBUG: Error buscando facts individuales: {e}")
    
    return facts_files


def _fix_cash_flow_beginning_logic(structure: pd.DataFrame, cash_beginning_idx: int, 
                                 cash_beginning_label: str, date_columns: List[str], 
                                 debug: bool = False) -> pd.DataFrame:
    """
    Aplica lógica de flujo de efectivo: efectivo al principio = efectivo al final del periodo anterior.
    """
    if debug:
        print(f"DEBUG: Aplicando lógica de flujo de efectivo para '{cash_beginning_label[:50]}...'")
    
    # Buscar la cuenta correspondiente de "efectivo al final del periodo"
    cash_ending_idx = None
    cash_ending_label = ""
    
    for idx, row in structure.iterrows():
        label = row.get('Cuenta', '') or row.get('Label', '')
        if (label and 'efectivo' in label.lower() and 
            ('final' in label.lower() or 'fin' in label.lower()) and 
            'periodo' in label.lower()):
            cash_ending_idx = idx
            cash_ending_label = label
            break
    
    if cash_ending_idx is None:
        if debug:
            print("DEBUG: No se encontró cuenta de efectivo al final del periodo")
        return structure
    
    if debug:
        print(f"DEBUG: Cuenta efectivo final encontrada: '{cash_ending_label[:50]}...'")
    
    # Ordenar columnas de fecha cronológicamente
    date_cols_sorted = sorted([col for col in date_columns], 
                             key=lambda x: x.split()[0])  # Usar solo la parte de fecha para ordenar
    
    applied_values = 0
    
    # Para cada fecha, copiar el efectivo final del periodo anterior al principio del actual
    for i, current_date_col in enumerate(date_cols_sorted):
        # Buscar el periodo anterior
        if i == 0:
            continue  # No hay periodo anterior para el primero
            
        previous_date_col = date_cols_sorted[i-1]
        
        # Obtener efectivo al final del periodo anterior
        previous_ending_cash = structure.loc[cash_ending_idx, previous_date_col]
        
        if (pd.notna(previous_ending_cash) and 
            str(previous_ending_cash).strip() not in ['', 'nan', 'NaN', 'None']):
            
            # Copiar al efectivo al principio del periodo actual
            structure.loc[cash_beginning_idx, current_date_col] = previous_ending_cash
            applied_values += 1
            
            if debug:
                print(f"DEBUG: {previous_date_col} final → {current_date_col} principio: {previous_ending_cash}")
    
    if debug:
        print(f"DEBUG: Aplicados {applied_values} valores de flujo de efectivo")
    
    return structure


def _search_in_individual_facts(account_label: str, facts_files: List[Path], debug: bool = False) -> Dict[str, str]:
    """
    Busca una cuenta específica en facts individuales.
    MODO ESTRICTO: solo acepta columnas de fecha PURAS 'YYYY-MM-DD'.
    Nunca convierte columnas 'YYYY-MM-DD - ...[miembro]' a la fecha limpia.
    Además, para IFRS9 sensibles no copia aunque existan.
    """
    found_values: Dict[str, str] = {}
    target_lower = (account_label or '').lower()

    # No copiar nada para etiquetas IFRS9 delicadas
    if _is_ifrs9_sensitive(target_lower):
        if debug:
            print(f"DEBUG: IFRS9 sensible, sin lectura de facts individuales para '{account_label[:60]}'")
        return found_values

    for facts_file in facts_files:
        if len(found_values) >= 5:
            break

        try:
            df = pd.read_csv(facts_file, engine='python', nrows=5000)
        except Exception as e:
            if debug:
                print(f"DEBUG: Error leyendo {facts_file.name}: {e}")
            continue

        # Buscar fila con match EXACTO de etiqueta
        match_idx = None
        if 'Label' in df.columns:
            for i, v in enumerate(df['Label'].astype(str)):
                if v.strip().lower() == target_lower:
                    match_idx = i
                    break
        if match_idx is None:
            continue

        row = df.iloc[match_idx]
        file_values: Dict[str, str] = {}

        for col in df.columns:
            if col == 'Label':
                continue
            col_str = str(col).strip()
            # SOLO columnas puras YYYY-MM-DD
            if not _is_pure_date_col(col_str):
                continue

            val = row.get(col)
            if pd.notna(val) and str(val).strip() != '':
                file_values[col_str] = str(val).strip()

        # Combinar sin sobreescribir fechas ya halladas
        for date_key, value in file_values.items():
            if date_key not in found_values:
                found_values[date_key] = value

        if debug and file_values:
            print(f"DEBUG: {facts_file.name} → {len(file_values)} fechas puras para '{account_label[:40]}...'")

    return found_values



def debug_missing_account(account_name: str, facts_df: pd.DataFrame) -> None:
    """
    Función de debug para investigar por qué una cuenta específica no tiene datos.
    """
    print(f"\n🔍 DEBUG: Investigando cuenta '{account_name}'")
    
    # Buscar coincidencias parciales
    matches = []
    for _, row in facts_df.iterrows():
        label = str(row.get('Label', '')).lower()
        if account_name.lower() in label or any(word in label for word in account_name.lower().split() if len(word) > 3):
            matches.append(label)
    
    print(f"Coincidencias parciales encontradas: {len(matches)}")
    for i, match in enumerate(matches[:10]):  # Mostrar solo las primeras 10
        print(f"  {i+1}. {match}")
    
    # Buscar fechas contextuales
    date_columns = [c for c in facts_df.columns if re.match(r'^\d{4}-\d{2}-\d{2}', c)]
    context_dates = [c for c in date_columns if ' - ' in c or '[' in c]
    
    print(f"\nFechas contextuales disponibles: {len(context_dates)}")
    for cd in context_dates[:5]:  # Mostrar ejemplos
        print(f"  - {cd}")



def trace_promotions(original: pd.DataFrame, enhanced: pd.DataFrame) -> pd.DataFrame:
    """
    Devuelve un DataFrame con (Label, Fecha, Valor) donde enhanced tiene dato y original no.
    Útil para auditar de dónde aparecieron valores.
    """
    if original is None or enhanced is None or original.empty or enhanced.empty:
        return pd.DataFrame()
    date_cols = [c for c in enhanced.columns if _is_pure_date_col(c)]
    rows = []
    for _, er in enhanced.iterrows():
        lbl = er.get('Label', '')
        if not lbl:
            continue
        orow = original[original['Label'] == lbl]
        for dc in date_cols:
            ev = er.get(dc)
            if pd.notna(ev) and str(ev).strip() != '':
                # si en original no había valor, lo marcamos
                ov = None
                if not orow.empty:
                    ov = orow.iloc[0].get(dc)
                if ov is None or (pd.isna(ov)) or (str(ov).strip() == ''):
                    rows.append({'Label': lbl, 'Fecha': dc, 'Valor': ev})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    # Test básico del enhancer
    print("Facts Enhancer - Test Mode")
    
    # Aquí puedes agregar tests específicos
    test_data = {
        'Label': ['Efectivo y equivalentes al efectivo al principio del periodo', 'Ventas'],
        '2023-12-31': [None, '1000000'],
        '2023-12-31 - Consolidado [miembro]': ['500000', None]
    }
    
    df = pd.DataFrame(test_data)
    enhanced = enhance_facts_with_context_data(df, debug=True)
    
    print("\nTest completado:")
    print(enhanced)