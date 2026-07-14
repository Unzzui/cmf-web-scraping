#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar que se generen las URLs correctas para cada tipo de reporte
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_report_urls():
    """Verifica que las URLs se generen con los índices correctos"""
    print("\n" + "="*60)
    print("TEST: URLs POR TIPO DE REPORTE")
    print("="*60)
    
    scraper = CMFBankScraper()
    
    bank_code = "001"
    month = 7
    year = 2025
    
    print(f"Banco: {scraper.BANK_CODES[bank_code]}")
    print(f"Período: {month:02d}/{year}")
    print()
    
    # Probar diferentes tipos de reporte
    report_types = ["MB1", "MR1"]
    
    for report_type in report_types:
        url = scraper.build_download_csv_url(bank_code, report_type, month, year, month, year)
        
        print(f"{report_type} ({scraper.REPORT_TYPES[report_type]}):")
        print(f"  Índice esperado: {scraper.REPORT_INDICES[report_type]}")
        
        # Extraer el índice de la URL
        if 'indice=' in url:
            start = url.find('indice=') + 7
            end = url.find('&', start)
            if end == -1:
                end = len(url)
            actual_index = url[start:end]
            
            if actual_index == scraper.REPORT_INDICES[report_type]:
                print(f"  ✅ Índice correcto: {actual_index}")
            else:
                print(f"  ❌ Índice incorrecto: {actual_index} (esperado: {scraper.REPORT_INDICES[report_type]})")
        
        print(f"  🔗 URL: {url[:100]}...")
        print()


def test_actual_download():
    """Prueba descarga real para verificar que funciona"""
    print("\n" + "="*60)
    print("TEST: DESCARGA REAL CON NUEVOS ÍNDICES")
    print("="*60)
    
    scraper = CMFBankScraper(
        output_dir="output/banks/test_indices",
        last_available_period="07/2025"
    )
    
    bank_code = "001"
    month = 6
    year = 2025
    
    print(f"Probando descarga real de MB1 y MR1 para {month:02d}/{year}")
    
    # Probar MB1
    print(f"\n1. Descargando MB1 (índice {scraper.REPORT_INDICES['MB1']})...")
    result_mb1 = scraper.download_bank_data(bank_code, "MB1", month, year)
    
    if result_mb1:
        print(f"   ✅ MB1 descargado: {Path(result_mb1).name}")
    else:
        print(f"   ❌ MB1 falló")
    
    # Probar MR1  
    print(f"\n2. Descargando MR1 (índice {scraper.REPORT_INDICES['MR1']})...")
    result_mr1 = scraper.download_bank_data(bank_code, "MR1", month, year)
    
    if result_mr1:
        print(f"   ✅ MR1 descargado: {Path(result_mr1).name}")
    else:
        print(f"   ❌ MR1 falló")
    
    # Comparar tamaños de archivo
    if result_mb1 and result_mr1:
        size_mb1 = Path(result_mb1).stat().st_size
        size_mr1 = Path(result_mr1).stat().st_size
        
        print(f"\n📊 Comparación de archivos:")
        print(f"   MB1: {size_mb1:,} bytes")
        print(f"   MR1: {size_mr1:,} bytes")
        
        if size_mb1 > 1000 and size_mr1 > 1000:
            print(f"   ✅ Ambos archivos tienen datos significativos")
        else:
            print(f"   ⚠️  Uno o ambos archivos parecen pequeños")


if __name__ == "__main__":
    test_report_urls()
    test_actual_download()