#!/usr/bin/env python3
"""Debug del manejo de períodos"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper

def test_period_validation():
    print("=== DEBUG VALIDACIÓN DE PERÍODOS ===")
    
    # Test sin período configurado
    scraper1 = CMFBankScraper()
    print(f"\nSin período configurado:")
    print(f"  last_month: {scraper1.last_month}")
    print(f"  last_year: {scraper1.last_year}")
    print(f"  is_period_available(9, 2025): {scraper1.is_period_available(9, 2025)}")
    
    # Test con período válido
    scraper2 = CMFBankScraper(last_available_period="07/2025")
    print(f"\nCon período '07/2025':")
    print(f"  last_month: {scraper2.last_month}")
    print(f"  last_year: {scraper2.last_year}")
    print(f"  is_period_available(6, 2025): {scraper2.is_period_available(6, 2025)}")  # Debería ser True
    print(f"  is_period_available(7, 2025): {scraper2.is_period_available(7, 2025)}")  # Debería ser True
    print(f"  is_period_available(8, 2025): {scraper2.is_period_available(8, 2025)}")  # Debería ser False
    print(f"  is_period_available(9, 2025): {scraper2.is_period_available(9, 2025)}")  # Debería ser False
    
    # Test con formato inválido
    scraper3 = CMFBankScraper(last_available_period="07/2025")  # Mismo formato que usaste
    print(f"\nCon período '07/2025' (mismo formato del error):")
    print(f"  last_month: {scraper3.last_month}")
    print(f"  last_year: {scraper3.last_year}")

if __name__ == "__main__":
    test_period_validation()