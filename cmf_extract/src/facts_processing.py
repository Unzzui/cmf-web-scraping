#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Procesamiento y normalización de datos facts XBRL.
"""

from __future__ import annotations
import os
import re
import pandas as pd
from .data_utils import _period_labels_from_dates

# Importar Facts Enhancer para mejorar matching de datos
try:
    from facts_enhancer import apply_facts_enhancements
    FACTS_ENHANCER_AVAILABLE = True
except ImportError:
    FACTS_ENHANCER_AVAILABLE = False
    if os.getenv('X2E_DEBUG') == '1':
        print("WARNING: facts_enhancer.py no disponible, funcionalidades limitadas")


def normalize_facts(facts_raw: pd.DataFrame, lang: str | None = None) -> pd.DataFrame:
    """Normaliza el DataFrame de facts aplicando varias transformaciones."""
    if facts_raw.empty:
        return facts_raw
    
    facts = facts_raw.copy()
    
    # Debug inicial
    if os.getenv('X2E_DEBUG') == '1':
        print(f"🔍 normalize_facts: Iniciando con {len(facts)} filas")
        print(f"   Columnas disponibles: {list(facts.columns)}")
    
    # 1. Convertir valores a numérico donde sea posible
    if 'value' in facts.columns:
        # Limpiar valores antes de conversión
        facts['value'] = facts['value'].astype(str).str.replace(',', '').str.replace(' ', '').str.strip()
        facts['value'] = pd.to_numeric(facts['value'], errors='coerce')
    
    # 2. Normalizar fechas
    date_columns = [col for col in facts.columns if 'date' in col.lower() or col in ['period', 'endDate', 'startDate']]
    for date_col in date_columns:
        if date_col in facts.columns:
            facts[date_col] = pd.to_datetime(facts[date_col], errors='coerce')
    
    # 3. Limpiar conceptos duplicados (mantener el más reciente por fecha)
    if 'concept' in facts.columns and 'endDate' in facts.columns:
        # Ordenar por fecha descendente y eliminar duplicados
        facts = facts.sort_values('endDate', ascending=False)
        facts = facts.drop_duplicates(subset=['concept', 'endDate'], keep='first')
    
    # 4. Filtrar por idioma si se especifica
    if lang and 'lang' in facts.columns:
        facts = facts[facts['lang'] == lang]
    
    # 5. Eliminar filas con valores nulos en columnas críticas
    critical_columns = ['concept', 'value']
    for col in critical_columns:
        if col in facts.columns:
            facts = facts.dropna(subset=[col])
    
    # 6. Aplicar Facts Enhancer si está disponible
    if FACTS_ENHANCER_AVAILABLE:
        try:
            source_path = getattr(facts, 'attrs', {}).get('source_path', '')
            if source_path:
                facts = apply_facts_enhancements(facts, source_path)
                if os.getenv('X2E_DEBUG') == '1':
                    print(f"✅ Facts Enhancer aplicado exitosamente")
        except Exception as e:
            if os.getenv('X2E_DEBUG') == '1':
                print(f"⚠️  Error aplicando Facts Enhancer: {e}")
    
    # Debug final
    if os.getenv('X2E_DEBUG') == '1':
        print(f"✅ normalize_facts: Finalizado con {len(facts)} filas")
    
    return facts


def calculate_keyword_similarity(original: str, key: str, value: str) -> float:
    """Calcula similitud entre etiquetas para mapeo fuzzy."""
    original_lower = original.lower()
    key_lower = key.lower()
    value_lower = value.lower()
    
    # Puntuación base por coincidencias de palabras clave
    score = 0.0
    
    # Palabras del original
    original_words = set(re.findall(r'\w+', original_lower))
    key_words = set(re.findall(r'\w+', key_lower))
    value_words = set(re.findall(r'\w+', value_lower))
    
    # Coincidencias exactas dan más puntos
    key_matches = len(original_words & key_words)
    value_matches = len(original_words & value_words)
    
    if key_matches > 0:
        score += (key_matches / len(original_words)) * 0.6
    
    if value_matches > 0:
        score += (value_matches / len(original_words)) * 0.4
    
    # Bonificación por subcadenas importantes
    important_terms = ['efectivo', 'cash', 'activo', 'asset', 'pasivo', 'liability', 
                      'patrimonio', 'equity', 'ingreso', 'income', 'gasto', 'expense',
                      'flujo', 'flow', 'operaci', 'operat', 'inversión', 'invest',
                      'financiaci', 'financ']
    
    for term in important_terms:
        if term in original_lower:
            if term in key_lower:
                score += 0.1
            if term in value_lower:
                score += 0.1
    
    return min(score, 1.0)  # Limitar a 1.0


def find_conceptual_mapping(original_label: str, statement_kind: str) -> str | None:
    """Encuentra mapeo conceptual para etiquetas no mapeadas directamente."""
    original_lower = original_label.lower()
    
    # Mapeos conceptuales específicos por tipo de estado
    conceptual_mappings = {
        'BALANCE': {
            'efectivo': 'Efectivo y equivalentes al efectivo',
            'cash': 'Cash and cash equivalents',
            'deudores comerciales': 'Deudores comerciales y otras cuentas por cobrar',
            'trade receivables': 'Trade and other current receivables',
            'inventarios': 'Inventarios',
            'inventories': 'Inventories',
            'propiedades': 'Propiedades, planta y equipo',
            'property': 'Property, plant and equipment',
            'cuentas por pagar': 'Cuentas por pagar comerciales y otras cuentas por pagar',
            'trade payables': 'Trade and other current payables',
            'patrimonio': 'Patrimonio',
            'equity': 'Equity',
        },
        'RESULTADOS': {
            'ingresos ordinarios': 'Ingresos de actividades ordinarias',
            'revenue': 'Revenue',
            'ventas': 'Ingresos de actividades ordinarias',
            'sales': 'Revenue',
            'costo de ventas': 'Costo de ventas',
            'cost of sales': 'Cost of sales',
            'gastos administración': 'Gastos de administración',
            'administrative expenses': 'Administrative expenses',
            'resultado operacional': 'Ganancias (pérdidas) de actividades operacionales',
            'operating profit': 'Profit (loss) from operating activities',
        },
        'FLUJO': {
            'actividades operación': 'Flujos de efectivo procedentes de (utilizados en) actividades de operación',
            'operating activities': 'Cash flows from (used in) operating activities',
            'actividades inversión': 'Flujos de efectivo procedentes de (utilizados en) actividades de inversión',
            'investing activities': 'Cash flows from (used in) investing activities',
            'actividades financiación': 'Flujos de efectivo procedentes de (utilizados en) actividades de financiación',
            'financing activities': 'Cash flows from (used in) financing activities',
            'cobros ventas': 'Cobros procedentes de las ventas de bienes y prestación de servicios',
            'cash receipts from sales': 'Cash receipts from sales of goods and rendering of services',
        }
    }
    
    mappings = conceptual_mappings.get(statement_kind, {})
    
    # Buscar coincidencia conceptual
    best_match = None
    best_score = 0.0
    
    for key_phrase, standard_label in mappings.items():
        if key_phrase in original_lower:
            score = len(key_phrase) / len(original_lower)  # Puntuación por longitud de coincidencia
            if score > best_score:
                best_score = score
                best_match = standard_label
    
    return best_match if best_score > 0.3 else None