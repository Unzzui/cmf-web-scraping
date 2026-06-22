#!/usr/bin/env python3
"""
Script para identificar empresas faltantes en productos finales
Compara XBRL con Product_v1 para mostrar qué empresas te faltan agregar
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


def extract_company_info_from_xbrl(xbrl_path: Path) -> Dict[str, str]:
    """Extrae información de empresas desde archivos XBRL"""
    companies = {}
    
    if not xbrl_path.exists():
        print(f"❌ Error: La ruta XBRL no existe: {xbrl_path}")
        return {}
    
    print(f"🔍 Escaneando archivos XBRL en: {xbrl_path}")
    
    for company_dir in xbrl_path.iterdir():
        if company_dir.is_dir():
            # Extraer RUT y nombre de la empresa del nombre del directorio
            dir_name = company_dir.name
            match = re.match(r'(\d{8}-\d)_(.+)', dir_name)
            
            if match:
                rut = match.group(1)
                company_name = match.group(2)
                companies[rut] = company_name
    
    return companies

def extract_company_info_from_products(products_path: Path) -> Dict[str, str]:
    """Extrae información de empresas desde productos finales"""
    companies = {}
    
    if not products_path.exists():
        print(f"❌ Error: La ruta de productos no existe: {products_path}")
        return {}
    
    print(f"🔍 Escaneando productos finales en: {products_path}")
    
    for excel_file in products_path.glob("*.xlsx"):
        filename = excel_file.stem
        
        # Patrón: "NOMBRE EMPRESA - RUT - Análisis Financiero PERIODO [IDIOMA].xlsx"
        # Ejemplo: "AGUAS ANDINAS SA - 61808000-5 - Análisis Financiero 2014-2025Q1 [ES].xlsx"
        pattern = r'(.+?)\s*-\s*(\d{8}-\d)\s*-\s*Análisis Financiero\s*(.+?)\s*\[(ES|EN)\]'
        match = re.match(pattern, filename)
        
        if match:
            company_name = match.group(1).strip()
            rut = match.group(2)
            companies[rut] = company_name
    
    return companies



def compare_companies(xbrl_companies: Dict[str, str], 
                     product_companies: Dict[str, str]) -> Tuple[Dict, Dict, Dict]:
    """Compara empresas entre XBRL y productos"""
    
    # Empresas que están en XBRL pero no en productos
    missing_in_products = {}
    
    # Empresas que están en productos pero no en XBRL
    missing_in_xbrl = {}
    
    # Empresas en común con períodos faltantes (no usado en versión simple)
    common_with_missing_periods = {}
    
    # Solo identificar empresas que faltan en productos
    for rut, company_name in xbrl_companies.items():
        if rut not in product_companies:
            # Empresa solo en XBRL - FALTA EN PRODUCTOS
            missing_in_products[rut] = company_name
    
    # Procesar empresas solo en productos (para estadísticas)
    for rut, company_name in product_companies.items():
        if rut not in xbrl_companies:
            missing_in_xbrl[rut] = company_name
    
    return missing_in_products, missing_in_xbrl, common_with_missing_periods

def generate_report(missing_in_products: Dict, 
                   xbrl_companies: Dict,
                   product_companies: Dict) -> None:
    """Genera un reporte simple de empresas faltantes"""
    
    print("\n" + "="*60)
    print("🔍 REPORTE DE EMPRESAS FALTANTES")
    print("="*60)
    
    # Estadísticas básicas
    print(f"\n📊 RESUMEN:")
    print(f"   Empresas en XBRL: {len(xbrl_companies)}")
    print(f"   Empresas en Productos: {len(product_companies)}")
    print(f"   Empresas faltantes: {len(missing_in_products)}")
    
    # Empresas que faltan en productos
    if missing_in_products:
        print(f"\n❌ ESTAS EMPRESAS TE FALTAN AGREGAR ({len(missing_in_products)}):")
        print("-" * 50)
        
        for rut, company_name in sorted(missing_in_products.items()):
            print(f"   📁 {rut} - {company_name}")
            print()
        
        print(f"🎯 ACCIÓN: Necesitas generar análisis financiero para {len(missing_in_products)} empresas")
    else:
        print(f"\n✅ TODAS LAS EMPRESAS ESTÁN COMPLETAS")
        print("   No hay empresas faltantes en productos")
    
    print("\n" + "="*60)


def main():
    """Función principal"""
    print("🔍 Iniciando verificación de empresas faltantes...")
    print("=" * 60)
    
    # Definir rutas
    xbrl_path = Path("/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total")
    products_path = Path("/home/unzzui/Documents/coding/CMF_extract/Product_v1/Total")
    
    # Verificar que existan las rutas
    if not xbrl_path.exists():
        print(f"❌ Error: La ruta XBRL no existe: {xbrl_path}")
        return
    
    if not products_path.exists():
        print(f"❌ Error: La ruta de productos no existe: {products_path}")
        return
    
    try:
        # Extraer información de ambos directorios
        xbrl_companies = extract_company_info_from_xbrl(xbrl_path)
        product_companies = extract_company_info_from_products(products_path)
        
        if not xbrl_companies:
            print("❌ No se encontraron empresas en XBRL")
            return
        
        if not product_companies:
            print("❌ No se encontraron productos finales")
            return
        
        # Comparar empresas
        missing_in_products, missing_in_xbrl, common_with_missing_periods = compare_companies(
            xbrl_companies, product_companies
        )
        
        # Generar reporte simple en consola
        generate_report(
            missing_in_products, xbrl_companies, product_companies
        )
        

        
    except Exception as e:
        print(f"\n❌ Error durante la comparación: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
