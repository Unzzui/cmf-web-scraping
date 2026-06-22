#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar la nueva estructura de carpetas por reporte
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_folder_structure():
    """Prueba la nueva estructura de carpetas"""
    print("\n" + "="*60)
    print("TEST: ESTRUCTURA DE CARPETAS POR REPORTE")
    print("="*60)
    
    scraper = CMFBankScraper(
        output_dir="output/banks/test_structure",
        last_available_period="07/2025"
    )
    
    bank_code = "001"
    bank_name = scraper.BANK_CODES[bank_code]
    
    print(f"Banco: {bank_name}")
    print(f"Testing descarga para junio 2025...")
    
    # Descargar MB1
    print(f"\n1. Descargando MB1...")
    filepath_mb1 = scraper.download_bank_data(
        bank_code, "MB1", 6, 2025, organize_by_bank=True
    )
    
    # Descargar MR1  
    print(f"\n2. Descargando MR1...")
    filepath_mr1 = scraper.download_bank_data(
        bank_code, "MR1", 6, 2025, organize_by_bank=True
    )
    
    print(f"\n" + "="*60)
    print("ESTRUCTURA RESULTANTE:")
    print("="*60)
    
    base_path = Path("output/banks/test_structure")
    bank_folder = base_path / f"{bank_code}_BANCO_DE_CHILE"
    
    if bank_folder.exists():
        print(f"\n📁 {bank_folder.name}/")
        
        # Mostrar carpetas MB1
        mb1_folder = bank_folder / "MB1"
        if mb1_folder.exists():
            print(f"  📁 MB1/")
            for file in mb1_folder.glob("*.csv"):
                print(f"    📄 {file.name}")
        
        # Mostrar carpetas MR1
        mr1_folder = bank_folder / "MR1" 
        if mr1_folder.exists():
            print(f"  📁 MR1/")
            for file in mr1_folder.glob("*.csv"):
                print(f"    📄 {file.name}")
    
    print(f"\n" + "="*60)
    print("PATHS RESULTANTES:")
    print("="*60)
    
    if filepath_mb1:
        print(f"✅ MB1: {filepath_mb1}")
    else:
        print(f"❌ MB1: Error en descarga")
        
    if filepath_mr1:
        print(f"✅ MR1: {filepath_mr1}")
    else:
        print(f"❌ MR1: Error en descarga")
    
    expected_structure = """
📁 001_BANCO_DE_CHILE/
  📁 MB1/
    📄 2025_06.csv
  📁 MR1/
    📄 2025_06.csv
"""
    print(f"\nESTRUCTURA ESPERADA:{expected_structure}")


if __name__ == "__main__":
    test_folder_structure()