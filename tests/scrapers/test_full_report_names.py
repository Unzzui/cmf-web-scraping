#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar carpetas con nombres completos de reportes
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_full_report_names():
    """Prueba carpetas con nombres completos de reportes"""
    print("\n" + "="*60)
    print("TEST: CARPETAS CON NOMBRES COMPLETOS DE REPORTES")
    print("="*60)
    
    scraper = CMFBankScraper(
        output_dir="output/banks/test_full_names",
        last_available_period="07/2025"
    )
    
    bank_code = "001"
    bank_name = scraper.BANK_CODES[bank_code]
    bank_rut = scraper.BANKS_RUTS[bank_code]
    
    print(f"Banco: {bank_name}")
    print(f"RUT: {bank_rut}")
    print(f"Descargando período: 06/2025")
    
    # Descargar MB1
    print(f"\n1. Descargando MB1 (Estado de Situación)...")
    result_mb1 = scraper.download_bank_data(
        bank_code, "MB1", 6, 2025, organize_by_bank=True
    )
    
    # Descargar MR1
    print(f"\n2. Descargando MR1 (Estado de Resultados)...")
    result_mr1 = scraper.download_bank_data(
        bank_code, "MR1", 6, 2025, organize_by_bank=True
    )
    
    print(f"\n" + "="*60)
    print("ESTRUCTURA RESULTANTE:")
    print("="*60)
    
    base_path = Path("output/banks/test_full_names")
    bank_folder = base_path / f"{bank_rut}_{bank_name.replace(' ', '_').replace(',', '').replace('.', '')}"
    
    if bank_folder.exists():
        print(f"\n📁 {bank_folder.name}/")
        
        for report_folder in sorted(bank_folder.iterdir()):
            if report_folder.is_dir():
                print(f"  📁 {report_folder.name}/")
                for csv_file in report_folder.glob("*.csv"):
                    print(f"    📄 {csv_file.name}")
    
    print(f"\n" + "="*60)
    print("VERIFICACIÓN DE NOMBRES:")
    print("="*60)
    
    expected_folders = [
        "MB1_ESTADO_DE_SITUACION",
        "MR1_ESTADO_DE_RESULTADOS"
    ]
    
    for expected in expected_folders:
        folder_path = bank_folder / expected
        if folder_path.exists():
            print(f"  ✅ {expected}")
        else:
            print(f"  ❌ {expected} (no encontrada)")
    
    print(f"\n" + "="*60)
    print("PATHS COMPLETOS:")
    print("="*60)
    
    if result_mb1:
        print(f"📄 MB1: {result_mb1}")
    if result_mr1:
        print(f"📄 MR1: {result_mr1}")


def show_expected_structure():
    """Muestra la estructura esperada"""
    print(f"\n" + "="*60)
    print("ESTRUCTURA ESPERADA:")
    print("="*60)
    
    expected = """
📁 97004000-5_BANCO_DE_CHILE/
  📁 MB1_ESTADO_DE_SITUACION/
    📄 2025_06.csv
  📁 MR1_ESTADO_DE_RESULTADOS/
    📄 2025_06.csv
"""
    print(expected)


if __name__ == "__main__":
    test_full_report_names()
    show_expected_structure()