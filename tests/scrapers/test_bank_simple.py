#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script simple de prueba para el Bank Scraper
Descarga datos de un banco para verificar funcionamiento
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper
from datetime import datetime

def test_single_download():
    """Prueba simple de descarga"""
    print("\n" + "="*60)
    print("TEST SIMPLE - CMF BANK SCRAPER")
    print("="*60)
    
    scraper = CMFBankScraper(output_dir="output/banks/test")
    
    # Configuración de prueba
    bank_code = "001"  # Banco de Chile
    report_type = "MB1"  # Estado de Situación
    month = 6  # Junio (sabemos que debería existir)
    year = 2024  # Año pasado para asegurar que hay datos
    
    print(f"\nPrueba 1: Descarga simple")
    print(f"  Banco: {scraper.BANK_CODES[bank_code]}")
    print(f"  Reporte: {scraper.REPORT_TYPES[report_type]}")
    print(f"  Período: {month:02d}/{year}")
    
    # Descargar con organización por banco
    result = scraper.download_bank_data(
        bank_code, report_type, month, year,
        organize_by_bank=True
    )
    
    if result:
        print(f"  ✓ Descarga exitosa: {result}")
    else:
        print(f"  ✗ Descarga falló")
    
    # Prueba 2: Intentar descargar período futuro
    print(f"\nPrueba 2: Validación de período futuro")
    future_month = 12
    future_year = 2025
    print(f"  Intentando descargar: {future_month:02d}/{future_year}")
    
    result = scraper.download_bank_data(
        bank_code, report_type, future_month, future_year,
        organize_by_bank=True
    )
    
    if result:
        print(f"  ✗ ERROR: Se descargó un período futuro (no debería)")
    else:
        print(f"  ✓ Correcto: Período futuro fue rechazado")
    
    # Prueba 3: Descarga trimestral
    print(f"\nPrueba 3: Descarga trimestral (Q2 2024)")
    quarters = [3, 6, 9, 12]
    year = 2024
    current_month = datetime.now().month
    
    for month in quarters:
        if year == 2024 or (year == datetime.now().year and month <= current_month):
            print(f"\n  Descargando Q{quarters.index(month)+1} ({month:02d}/{year})...", end=" ")
            result = scraper.download_bank_data(
                bank_code, report_type, month, year,
                organize_by_bank=True
            )
            if result:
                print("✓")
            else:
                print("✗")
        else:
            print(f"\n  Omitiendo {month:02d}/{year} (futuro)")
    
    print(f"\n{'='*60}")
    print("Archivos se guardan en carpetas organizadas por banco:")
    print(f"  output/banks/test/{bank_code}_{scraper.BANK_CODES[bank_code].replace(' ', '_')}/")
    print("="*60)


if __name__ == "__main__":
    test_single_download()