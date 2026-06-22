#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test para verificar descarga de ambos reportes (MB1 + MR1)
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper
from cli_bank_scraper import BankScraperCLI

def test_dual_reports():
    """Prueba descarga de MB1 y MR1 para un banco"""
    print("\n" + "="*60)
    print("TEST: DESCARGA DUAL - MB1 + MR1")
    print("="*60)
    
    cli = BankScraperCLI(last_period="07/2025")
    
    bank_code = "001"
    report_types = ["MB1", "MR1"]
    years = [2025]
    months = [6, 7]  # Solo dos meses para prueba rápida
    mode = "test"
    
    print(f"Banco: {cli.scraper.BANK_CODES[bank_code]}")
    print(f"Reportes: {[cli.scraper.REPORT_TYPES[rt] for rt in report_types]}")
    print(f"Períodos: {[f'{year}-{month:02d}' for year in years for month in months]}")
    
    results = cli.download_bank_periods(bank_code, report_types, years, months, mode)
    
    print(f"\nResultados esperados: {len(years) * len(months) * len(report_types)} archivos")
    print(f"Resultados obtenidos: {len([r for r in results.values() if r is not None])}")
    
    # Verificar estructura de archivos
    expected_files = []
    for year in years:
        for month in months:
            for report_type in report_types:
                expected_files.append(f"{year}-{month:02d}_{report_type}")
    
    print(f"\nArchivos esperados:")
    for ef in expected_files:
        status = "✓" if results.get(ef) else "✗"
        print(f"  {status} {ef}")
    
    # Verificar estructura de carpetas
    bank_dir = Path("output/banks/cli/001_BANCO_DE_CHILE")
    if bank_dir.exists():
        files = list(bank_dir.glob("*.csv"))
        print(f"\nArchivos en carpeta:")
        for f in sorted(files):
            print(f"  📄 {f.name}")


if __name__ == "__main__":
    test_dual_reports()