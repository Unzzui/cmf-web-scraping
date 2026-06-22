#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de ejemplo usando período específico
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_with_period():
    """Prueba con período específico configurado"""
    print("\n" + "="*60)
    print("TEST CON PERÍODO ESPECÍFICO")
    print("="*60)
    
    # Configurar con último período disponible (ejemplo)
    last_period = "07/2025"  # Cambiar por el período real que veas en la web
    
    scraper = CMFBankScraper(
        output_dir="output/banks/test_period", 
        last_available_period=last_period
    )
    
    bank_code = "001"  # Banco de Chile
    report_type = "MB1"
    
    print(f"Último período configurado: {last_period}")
    print(f"Banco: {scraper.BANK_CODES[bank_code]}")
    print(f"Reporte: {scraper.REPORT_TYPES[report_type]}")
    
    # Probar diferentes períodos
    test_periods = [
        (7, 2025),   # Debería funcionar si es el último
        (6, 2025),   # Debería funcionar
        (12, 2025),  # NO debería funcionar (futuro)
        (3, 2025),   # Debería funcionar
    ]
    
    for month, year in test_periods:
        print(f"\nProbando {month:02d}/{year}...", end=" ")
        
        if scraper.is_period_available(month, year):
            print("✓ DISPONIBLE - Descargando...", end=" ")
            result = scraper.download_bank_data(bank_code, report_type, month, year)
            if result:
                print("OK")
            else:
                print("ERROR")
        else:
            print("✗ NO DISPONIBLE (omitido)")
    
    print(f"\n{'='*60}")
    print("Verifica los archivos en: output/banks/test_period/")

if __name__ == "__main__":
    test_with_period()