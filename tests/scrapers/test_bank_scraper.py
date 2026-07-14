#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script para el CMF Bank Scraper
Prueba diferentes escenarios de descarga de datos bancarios
"""

import sys
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_single_bank_download():
    """Prueba descarga de un solo banco"""
    print("\n" + "="*60)
    print("TEST 1: Descarga de un solo banco")
    print("="*60)
    
    scraper = CMFBankScraper(output_dir="output/banks/test")
    
    bank_code = "001"
    report_type = "MB1"
    month = 7
    year = 2025
    
    print(f"\nDescargando: {scraper.BANK_CODES[bank_code]}")
    print(f"Reporte: {scraper.REPORT_TYPES[report_type]}")
    print(f"Período: {month:02d}/{year}")
    
    filepath = scraper.download_bank_data(bank_code, report_type, month, year)
    
    if filepath:
        print(f"✓ Descarga exitosa: {filepath}")
        
        df = scraper.process_csv_to_dataframe(filepath)
        if df is not None:
            print(f"✓ CSV procesado correctamente")
            print(f"  - Filas: {len(df)}")
            print(f"  - Columnas: {len(df.columns)}")
            print(f"\nPrimeras columnas: {list(df.columns[:5])}")
            return True
    else:
        print("✗ Error en la descarga")
        return False


def test_multiple_banks_download():
    """Prueba descarga de múltiples bancos"""
    print("\n" + "="*60)
    print("TEST 2: Descarga de múltiples bancos")
    print("="*60)
    
    scraper = CMFBankScraper(output_dir="output/banks/test")
    
    test_banks = ["001", "012", "037", "016", "014"]
    report_type = "MB1"
    month = 7
    year = 2025
    
    print(f"\nBancos a descargar:")
    for code in test_banks:
        print(f"  - {code}: {scraper.BANK_CODES[code]}")
    
    print(f"\nReporte: {scraper.REPORT_TYPES[report_type]}")
    print(f"Período: {month:02d}/{year}")
    
    results = scraper.download_multiple_banks(test_banks, report_type, month, year)
    
    print(f"\nResultados:")
    success_count = 0
    for bank_code, filepath in results.items():
        bank_name = scraper.BANK_CODES[bank_code]
        if filepath:
            print(f"  ✓ {bank_name}: {Path(filepath).name}")
            success_count += 1
        else:
            print(f"  ✗ {bank_name}: Error")
    
    print(f"\n{success_count}/{len(test_banks)} bancos descargados exitosamente")
    return success_count == len(test_banks)


def test_different_report_types():
    """Prueba diferentes tipos de reportes para un banco"""
    print("\n" + "="*60)
    print("TEST 3: Diferentes tipos de reportes")
    print("="*60)
    
    scraper = CMFBankScraper(output_dir="output/banks/test")
    
    bank_code = "037"
    report_types = ["MB1", "MR1", "ADC"]
    month = 7
    year = 2025
    
    print(f"\nBanco: {scraper.BANK_CODES[bank_code]}")
    print(f"Período: {month:02d}/{year}")
    print(f"\nReportes a descargar:")
    
    success_count = 0
    for report_type in report_types:
        print(f"\n  Descargando: {scraper.REPORT_TYPES[report_type]}...")
        
        filepath = scraper.download_bank_data(
            bank_code, report_type, month, year,
            save_as=f"{bank_code}_{report_type}_{year}{month:02d}"
        )
        
        if filepath:
            print(f"    ✓ Guardado como: {Path(filepath).name}")
            success_count += 1
        else:
            print(f"    ✗ Error en descarga")
    
    print(f"\n{success_count}/{len(report_types)} reportes descargados exitosamente")
    return success_count == len(report_types)


def test_period_range():
    """Prueba descarga con rango de períodos"""
    print("\n" + "="*60)
    print("TEST 4: Descarga con rango de períodos")
    print("="*60)
    
    scraper = CMFBankScraper(output_dir="output/banks/test")
    
    bank_code = "016"
    report_type = "MR1"
    start_month = 1
    start_year = 2025
    end_month = 7
    end_year = 2025
    
    print(f"\nBanco: {scraper.BANK_CODES[bank_code]}")
    print(f"Reporte: {scraper.REPORT_TYPES[report_type]}")
    print(f"Período: {start_month:02d}/{start_year} a {end_month:02d}/{end_year}")
    
    filepath = scraper.download_bank_data(
        bank_code, report_type,
        start_month, start_year,
        end_month, end_year,
        save_as=f"{bank_code}_rango_{start_year}{start_month:02d}_{end_year}{end_month:02d}"
    )
    
    if filepath:
        print(f"✓ Descarga exitosa: {filepath}")
        
        df = scraper.process_csv_to_dataframe(filepath)
        if df is not None:
            print(f"✓ CSV procesado")
            print(f"  - Filas: {len(df)}")
            print(f"  - Columnas: {len(df.columns)}")
            return True
    else:
        print("✗ Error en la descarga")
        return False


def test_url_generation():
    """Prueba la generación de URLs"""
    print("\n" + "="*60)
    print("TEST 5: Generación de URLs")
    print("="*60)
    
    scraper = CMFBankScraper()
    
    bank_code = "001"
    report_type = "MB1"
    month = 7
    year = 2025
    
    print(f"\nParámetros:")
    print(f"  - Banco: {scraper.BANK_CODES[bank_code]}")
    print(f"  - Reporte: {scraper.REPORT_TYPES[report_type]}")
    print(f"  - Período: {month:02d}/{year}")
    
    view_url = scraper.build_view_url(bank_code, report_type, month, year, month, year)
    download_url = scraper.build_download_csv_url(bank_code, report_type, month, year, month, year)
    
    print(f"\nURL Vista Web:")
    print(f"  {view_url[:100]}...")
    
    print(f"\nURL Descarga CSV:")
    print(f"  {download_url[:100]}...")
    
    return True


def run_all_tests():
    """Ejecuta todas las pruebas"""
    print("\n" + "#"*60)
    print("# CMF BANK SCRAPER - SUITE DE PRUEBAS")
    print("#"*60)
    print(f"\nFecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    tests = [
        ("Descarga de un banco", test_single_bank_download),
        ("Descarga múltiples bancos", test_multiple_banks_download),
        ("Diferentes tipos de reportes", test_different_report_types),
        ("Rango de períodos", test_period_range),
        ("Generación de URLs", test_url_generation)
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, result))
        except Exception as e:
            print(f"\n✗ ERROR en {test_name}: {e}")
            results.append((test_name, False))
    
    print("\n" + "#"*60)
    print("# RESUMEN DE RESULTADOS")
    print("#"*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASSED" if result else "✗ FAILED"
        print(f"  {status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} pruebas exitosas")
    
    if passed == total:
        print("\n🎉 ¡Todas las pruebas pasaron exitosamente!")
    else:
        print(f"\n⚠️  {total - passed} pruebas fallaron")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test suite para CMF Bank Scraper")
    parser.add_argument("--test", type=int, help="Ejecutar test específico (1-5)")
    parser.add_argument("--all", action="store_true", help="Ejecutar todos los tests")
    
    args = parser.parse_args()
    
    if args.test:
        tests = {
            1: test_single_bank_download,
            2: test_multiple_banks_download,
            3: test_different_report_types,
            4: test_period_range,
            5: test_url_generation
        }
        
        if args.test in tests:
            tests[args.test]()
        else:
            print(f"Test {args.test} no existe. Usa 1-5")
    else:
        run_all_tests()