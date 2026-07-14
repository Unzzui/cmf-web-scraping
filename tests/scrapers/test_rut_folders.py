#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar la nueva estructura de carpetas con RUTs
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_rut_folder_structure():
    """Prueba la nueva estructura de carpetas con RUTs"""
    print("\n" + "="*60)
    print("TEST: ESTRUCTURA DE CARPETAS CON RUTs")
    print("="*60)
    
    scraper = CMFBankScraper(
        output_dir="output/banks/test_ruts",
        last_available_period="07/2025"
    )
    
    # Probar con diferentes bancos
    test_banks = [
        ("001", "BANCO_DE_CHILE"),
        ("037", "BANCO_SANTANDER-CHILE"),
        ("051", "BANCO_FALABELLA")
    ]
    
    for bank_code, expected_name in test_banks:
        bank_name = scraper.BANK_CODES[bank_code]
        bank_rut = scraper.BANKS_RUTS[bank_code]
        
        print(f"\n📦 {bank_name}")
        print(f"   Código: {bank_code}")
        print(f"   RUT: {bank_rut}")
        
        # Descargar MB1
        result = scraper.download_bank_data(
            bank_code, "MB1", 6, 2025, organize_by_bank=True
        )
        
        if result:
            print(f"   ✅ Descarga exitosa")
            
            # Verificar estructura de carpetas
            result_path = Path(result)
            print(f"   📁 Carpeta: {result_path.parent.parent.name}")
            
            expected_folder = f"{bank_rut}_{expected_name}"
            if expected_folder in result_path.parent.parent.name:
                print(f"   ✅ Nombre correcto: {expected_folder}")
            else:
                print(f"   ❌ Nombre incorrecto")
                print(f"      Esperado: {expected_folder}")
                print(f"      Actual: {result_path.parent.parent.name}")
        else:
            print(f"   ❌ Error en descarga")
    
    print(f"\n" + "="*60)
    print("ESTRUCTURA RESULTANTE:")
    print("="*60)
    
    base_path = Path("output/banks/test_ruts")
    if base_path.exists():
        for bank_folder in base_path.iterdir():
            if bank_folder.is_dir():
                print(f"\n📁 {bank_folder.name}/")
                for report_folder in bank_folder.iterdir():
                    if report_folder.is_dir():
                        print(f"  📁 {report_folder.name}/")
                        for csv_file in report_folder.glob("*.csv"):
                            print(f"    📄 {csv_file.name}")


def show_expected_structure():
    """Muestra la estructura esperada"""
    print(f"\n" + "="*60)
    print("ESTRUCTURA ESPERADA:")
    print("="*60)
    
    expected = """
📁 97004000-5_BANCO_DE_CHILE/
  📁 MB1/
    📄 2025_06.csv
  📁 MR1/
    📄 2025_06.csv

📁 97036000-K_BANCO_SANTANDER-CHILE/
  📁 MB1/
    📄 2025_06.csv
  📁 MR1/
    📄 2025_06.csv

📁 96509660-4_BANCO_FALABELLA/
  📁 MB1/
    📄 2025_06.csv
  📁 MR1/
    📄 2025_06.csv
"""
    print(expected)


if __name__ == "__main__":
    test_rut_folder_structure()
    show_expected_structure()