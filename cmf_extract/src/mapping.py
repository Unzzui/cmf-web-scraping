#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones de mapeo de cuentas XBRL a estructura de estados financieros.
"""

from __future__ import annotations
import os
import json
import re
from pathlib import Path
from functools import lru_cache
import pandas as pd
from .translation import translate_label_to_english

# Cachés simples en memoria para acelerar corridas sin cambiar resultados
_TAXONOMY_CACHE: dict[str, dict[str, list[tuple[str, str]]]] = {}
_FLATTEN_CACHE: dict[int, dict] = {}


@lru_cache(maxsize=1)
def build_complete_mapping(lang: str = "es") -> dict[str, list[tuple[str, str]]]:
    """Construye el mapeo completo usando taxonomía IFRS oficial."""
    global _TAXONOMY_CACHE
    
    if lang in _TAXONOMY_CACHE:
        return _TAXONOMY_CACHE[lang]
    
    base_path = Path(__file__).parent.parent
    taxonomy_path = base_path / "taxonomia_ilustrada.json"
    
    try:
        with open(taxonomy_path, 'r', encoding='utf-8') as f:
            taxonomy_data = json.load(f)
    except FileNotFoundError:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  taxonomia_ilustrada.json no encontrado en {taxonomy_path}")
        return {}
    
    mapping = {}
    
    # Procesar cada sección del mapping
    for role_key, role_data in taxonomy_data.items():
        if not isinstance(role_data, dict):
            continue
            
        role_mapping = []
        
        # Determinar tipo de rol
        role_type = None
        if '210000' in role_key or 'balance' in role_key.lower():
            role_type = 'BALANCE'
        elif '310000' in role_key or 'income' in role_key.lower() or 'result' in role_key.lower():
            role_type = 'RESULTADOS'  
        elif '510000' in role_key or 'cash' in role_key.lower() or 'flow' in role_key.lower():
            role_type = 'FLUJO'
        
        if not role_type:
            continue
            
        # Procesar conceptos del rol
        for concept_key, concept_data in role_data.items():
            if not isinstance(concept_data, dict):
                continue
                
            # Obtener etiqueta en el idioma solicitado
            label_key = f"label_{lang}" if lang != "es" else "label"
            concept_label = concept_data.get(label_key, concept_data.get("label", ""))
            
            # Si no hay etiqueta en el idioma solicitado, intentar traducir
            if not concept_label and lang == "en":
                spanish_label = concept_data.get("label", "")
                if spanish_label:
                    concept_label = translate_label_to_english(spanish_label)
            
            if concept_label:
                role_mapping.append((concept_key, concept_label))
        
        if role_mapping:
            mapping[role_type] = role_mapping
    
    _TAXONOMY_CACHE[lang] = mapping
    return mapping


def load_legacy_mapping() -> dict[str, dict[str, str]]:
    """Carga el mapeo legacy desde cuentas.json como fallback."""
    base_path = Path(__file__).parent.parent
    legacy_path = base_path / "cuentas.json"
    
    try:
        with open(legacy_path, 'r', encoding='utf-8') as f:
            legacy_data = json.load(f)
        
        # Convertir formato legacy a nuevo formato
        converted = {}
        for role, accounts in legacy_data.items():
            if isinstance(accounts, dict):
                converted[role] = accounts
        
        return converted
    except FileNotFoundError:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  cuentas.json no encontrado en {legacy_path}")
        return {}


def flatten_presentation_accounts(presentation_data: pd.DataFrame) -> dict:
    """Extrae estructura plana de cuentas desde presentation CSV."""
    if presentation_data.empty:
        return {}
    
    # Usar hash simple para cache
    df_hash = hash(str(presentation_data.values.tobytes()))
    global _FLATTEN_CACHE
    
    if df_hash in _FLATTEN_CACHE:
        return _FLATTEN_CACHE[df_hash]
    
    flattened = {}
    
    for _, row in presentation_data.iterrows():
        concept = str(row.get('concept', ''))
        label = str(row.get('label', ''))
        role_uri = str(row.get('roleUri', ''))
        
        if concept and label:
            # Determinar tipo de statement
            statement_type = guess_role_kind(role_uri)
            if statement_type:
                if statement_type not in flattened:
                    flattened[statement_type] = {}
                flattened[statement_type][concept] = label
    
    _FLATTEN_CACHE[df_hash] = flattened
    return flattened


def ensure_missing_accounts_from_presentation(presentation_data: pd.DataFrame, base_mapping: dict, statement_kind: str, facts_df: pd.DataFrame = None, lang: str = "es") -> dict:
    """Asegura que cuentas importantes del presentation estén en el mapeo."""
    if presentation_data.empty:
        return base_mapping
    
    # Filtrar por tipo de statement
    relevant_presentation = presentation_data[
        presentation_data['roleUri'].apply(
            lambda x: guess_role_kind(str(x)) == statement_kind
        )
    ].copy() if 'roleUri' in presentation_data.columns else presentation_data.copy()
    
    if relevant_presentation.empty:
        return base_mapping
    
    enhanced_mapping = base_mapping.copy()
    added_count = 0
    
    for _, row in relevant_presentation.iterrows():
        concept = str(row.get('concept', ''))
        label = str(row.get('label', ''))
        
        if not concept or not label:
            continue
            
        # Verificar si ya existe en el mapping
        concept_exists = any(
            concept in [item[0] for item in accounts] 
            for accounts in enhanced_mapping.values()
        )
        
        if not concept_exists:
            # Determinar la sección apropiada basada en palabras clave
            section = _determine_section_for_account(label, statement_kind, lang)
            
            if section not in enhanced_mapping:
                enhanced_mapping[section] = []
            
            enhanced_mapping[section].append((concept, label))
            added_count += 1
    
    if added_count > 0 and os.getenv('X2E_DEBUG') == '1':
        print(f"✅ Agregadas {added_count} cuentas faltantes del presentation para {statement_kind}")
    
    return enhanced_mapping


def _determine_section_for_account(label: str, statement_kind: str, lang: str = "es") -> str:
    """Determina la sección apropiada para una cuenta basada en palabras clave."""
    label_lower = label.lower()
    
    if statement_kind == "BALANCE":
        if lang == "es":
            if any(word in label_lower for word in ['activo', 'deudor', 'efectivo', 'inventario', 'propiedad']):
                return "ACTIVOS"
            elif any(word in label_lower for word in ['pasivo', 'deuda', 'provisión', 'cuenta por pagar']):
                return "PASIVOS"
            elif any(word in label_lower for word in ['patrimonio', 'capital', 'reserva', 'ganancia acumulada']):
                return "PATRIMONIO"
        else:  # lang == "en"
            if any(word in label_lower for word in ['asset', 'receivable', 'cash', 'inventory', 'property']):
                return "ASSETS"
            elif any(word in label_lower for word in ['liability', 'debt', 'provision', 'payable']):
                return "LIABILITIES"
            elif any(word in label_lower for word in ['equity', 'capital', 'reserve', 'retained']):
                return "EQUITY"
        return "OTROS_ACTIVOS"
    
    elif statement_kind == "RESULTADOS":
        if lang == "es":
            if any(word in label_lower for word in ['ingreso', 'venta', 'revenue']):
                return "INGRESOS"
            elif any(word in label_lower for word in ['costo', 'gasto']):
                return "COSTOS_Y_GASTOS"
        else:  # lang == "en"
            if any(word in label_lower for word in ['income', 'revenue', 'sale']):
                return "INCOME"
            elif any(word in label_lower for word in ['cost', 'expense']):
                return "COSTS_AND_EXPENSES"
        return "OTROS_RESULTADOS"
    
    elif statement_kind == "FLUJO":
        if lang == "es":
            if any(word in label_lower for word in ['operaci', 'cobro', 'pago']):
                return "OPERACION"
            elif any(word in label_lower for word in ['inversión', 'compra', 'venta']):
                return "INVERSION"
            elif any(word in label_lower for word in ['financiaci', 'préstamo', 'dividendo']):
                return "FINANCIACION"
        else:  # lang == "en"
            if any(word in label_lower for word in ['operating', 'receipt', 'payment']):
                return "OPERATING"
            elif any(word in label_lower for word in ['investing', 'purchase', 'sale']):
                return "INVESTING"
            elif any(word in label_lower for word in ['financing', 'loan', 'dividend']):
                return "FINANCING"
        return "OTROS_FLUJOS"
    
    return "OTROS"


def build_hybrid_mapping(presentation_data: pd.DataFrame, lang: str = "es") -> dict[str, list[tuple[str, str]]]:
    """Construye un mapeo híbrido combinando taxonomía oficial y presentation."""
    # Comenzar con mapeo completo de taxonomía
    complete_mapping = build_complete_mapping(lang)
    
    # Enriquecer con cuentas del presentation
    for statement_kind in ['BALANCE', 'RESULTADOS', 'FLUJO']:
        if statement_kind in complete_mapping:
            complete_mapping[statement_kind] = ensure_missing_accounts_from_presentation(
                presentation_data, 
                {statement_kind: complete_mapping[statement_kind]}, 
                statement_kind, 
                lang=lang
            ).get(statement_kind, [])
    
    return complete_mapping


def write_unmapped_accounts_report(unmapped_accounts: list[str], statement_kind: str, output_dir: Path) -> None:
    """Escribe un reporte de cuentas no mapeadas para debug."""
    if not unmapped_accounts or os.getenv('X2E_DEBUG') != '1':
        return
    
    report_file = output_dir / f"unmapped_{statement_kind.lower()}_accounts.txt"
    
    try:
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(f"CUENTAS NO MAPEADAS - {statement_kind}\n")
            f.write("=" * 50 + "\n\n")
            
            for account in unmapped_accounts:
                f.write(f"- {account}\n")
            
            f.write(f"\nTotal: {len(unmapped_accounts)} cuentas no mapeadas\n")
        
        print(f"📝 Reporte de cuentas no mapeadas guardado: {report_file}")
    except Exception as e:
        if os.getenv('X2E_DEBUG') == '1':
            print(f"⚠️  No se pudo escribir reporte: {e}")


def get_account_mapping(lang: str = "es", presentation_data: pd.DataFrame = None) -> dict[str, dict[str, str]]:
    """Obtiene el mapeo de cuentas completo, combinando múltiples fuentes."""
    # Intentar cargar mapeo híbrido si hay presentation data
    if presentation_data is not None and not presentation_data.empty:
        hybrid_mapping = build_hybrid_mapping(presentation_data, lang)
        
        # Convertir a formato legacy para compatibilidad
        legacy_format = {}
        for statement_kind, accounts in hybrid_mapping.items():
            legacy_format[statement_kind] = {concept: label for concept, label in accounts}
        
        return legacy_format
    
    # Fallback a mapeo completo de taxonomía
    complete_mapping = build_complete_mapping(lang)
    legacy_format = {}
    for statement_kind, accounts in complete_mapping.items():
        legacy_format[statement_kind] = {concept: label for concept, label in accounts}
    
    # Si no hay mapeo completo, usar legacy
    if not legacy_format:
        legacy_format = load_legacy_mapping()
    
    return legacy_format


def guess_role_kind(role_uri: str) -> str | None:
    """Determina el tipo de estado financiero basado en el role URI."""
    u = str(role_uri).lower()
    if any(x in u for x in ['210000', 'balance', 'position']):
        return 'BALANCE'
    elif any(x in u for x in ['310000', 'income', 'profit', 'result']):
        return 'RESULTADOS'
    elif any(x in u for x in ['510000', 'cash', 'flow', 'flujo']):
        return 'FLUJO'
    return None