#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI para CMF Bank Scraper
Interfaz de línea de comandos para descargar datos bancarios de la CMF
"""

import sys
import os
from pathlib import Path
from datetime import datetime
import argparse
from typing import List, Dict
import time

sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper


class BankScraperCLI:
    """CLI para el scraper de bancos"""
    
    def __init__(self, last_period: str = None):
        try:
            self.scraper = CMFBankScraper(output_dir="output/banks/cli", last_available_period=last_period)
        except ValueError as e:
            print(f"❌ Error: {e}")
            print("Use el formato correcto: MM/YYYY (ejemplo: 07/2025)")
            sys.exit(1)
        self.current_year = datetime.now().year
        
    def display_banks(self):
        """Muestra lista de bancos disponibles"""
        print("\n" + "="*60)
        print("BANCOS DISPONIBLES")
        print("="*60)
        for code, name in self.scraper.BANK_CODES.items():
            if code != "999":  # Excluir SISTEMA FINANCIERO
                print(f"  {code}: {name}")
        print("="*60)
    
    def display_reports(self):
        """Muestra tipos de reportes disponibles"""
        print("\nTIPOS DE REPORTES:")
        for code, name in self.scraper.REPORT_TYPES.items():
            print(f"  {code}: {name}")
    
    def get_quarterly_months(self) -> List[int]:
        """Retorna los meses trimestrales (3, 6, 9, 12)"""
        return [3, 6, 9, 12]
    
    def get_monthly_months(self) -> List[int]:
        """Retorna todos los meses (1-12)"""
        return list(range(1, 13))
    
    def download_bank_periods(self, bank_code: str, report_types: List[str], 
                            years: List[int], months: List[int],
                            mode: str) -> Dict[str, str]:
        """
        Descarga datos para múltiples períodos y reportes
        
        Args:
            bank_code: Código del banco
            report_types: Lista de tipos de reportes
            years: Lista de años a descargar
            months: Lista de meses a descargar
            mode: Modo de descarga ('trimestral' o 'mensual')
            
        Returns:
            Diccionario con resultados
        """
        results = {}
        bank_name = self.scraper.BANK_CODES.get(bank_code, f"banco_{bank_code}")
        
        print(f"\n{'='*60}")
        print(f"DESCARGANDO: {bank_name}")
        report_names = [self.scraper.REPORT_TYPES.get(rt, rt) for rt in report_types]
        print(f"Reportes: {' + '.join(report_names)}")
        print(f"Modo: {mode.upper()}")
        print(f"Años: {min(years)} - {max(years)}")
        print(f"{'='*60}")
        
        total_downloads = len(years) * len(months) * len(report_types)
        current_download = 0
        successful_downloads = 0
        skipped_future = 0
        
        for year in years:
            for month in months:
                # Verificar si el período está disponible
                if not self.scraper.is_period_available(month, year):
                    current_download += len(report_types)  # Contar todos los reportes omitidos
                    period_str = f"{year}-{month:02d}"
                    print(f"\n[{current_download-len(report_types)+1}-{current_download}/{total_downloads}] Período {period_str}: ⏭️ NO DISPONIBLE (omitidos {len(report_types)} reportes)")
                    skipped_future += len(report_types)
                    continue
                
                # Descargar cada tipo de reporte para este período
                for report_type in report_types:
                    current_download += 1
                    period_str = f"{year}-{month:02d}"
                    result_key = f"{period_str}_{report_type}"
                    
                    print(f"\n[{current_download}/{total_downloads}] {period_str} - {report_type}...", end=" ")
                    
                    # Descargar con nombre específico que incluya el tipo de reporte
                    filepath = self.scraper.download_bank_data(
                        bank_code, report_type, month, year, 
                        month, year, organize_by_bank=True
                    )
                    
                    if filepath:
                        print("✓ OK")
                        results[result_key] = filepath
                        successful_downloads += 1
                    else:
                        print("✗ NO DISPONIBLE")
                        results[result_key] = None
                    
                    # Pausa entre descargas para no sobrecargar el servidor
                    if current_download < total_downloads:
                        time.sleep(1)
        
        print(f"\n{'='*60}")
        print(f"Resumen: {successful_downloads} descargados, {skipped_future} no disponibles omitidos")
        print(f"{'='*60}")
        
        return results
    
    def ask_last_period(self) -> str:
        """Pregunta al usuario sobre el último período disponible"""
        print("\n" + "="*60)
        print("CONFIGURACIÓN DEL ÚLTIMO PERÍODO DISPONIBLE")
        print("="*60)
        print("\nPara obtener el último período disponible:")
        print("1. Ve a: https://datosbanco.cmfchile.cl/sbifweb/servlet/BaseDato?indice=30.0")
        print("2. Selecciona cualquier banco")
        print("3. Selecciona cualquier reporte (ej: MB1)")
        print("4. Verás un mensaje como 'Ultimo Periodo Cargado: 07/2025'")
        
        while True:
            last_period = input("\nIngresa el último período disponible (formato MM/YYYY, ej: 07/2025): ").strip()
            
            if not last_period:
                print("❌ Debes ingresar un período")
                continue
                
            try:
                month, year = last_period.split('/')
                month = int(month)
                year = int(year)
                
                if not (1 <= month <= 12):
                    print("❌ El mes debe estar entre 01 y 12")
                    continue
                    
                if year < 2000 or year > 2030:
                    print("❌ El año parece inválido")
                    continue
                    
                return last_period
                
            except ValueError:
                print("❌ Formato inválido. Use MM/YYYY (ej: 07/2025)")
                continue
    
    def interactive_mode(self):
        """Modo interactivo de la CLI"""
        print("\n" + "="*60)
        print("CMF BANK SCRAPER CLI - MODO INTERACTIVO")
        print("="*60)
        
        # Preguntar por el último período disponible
        if self.scraper.last_available_period is None:
            last_period = self.ask_last_period()
            self.scraper = CMFBankScraper(output_dir="output/banks/cli", last_available_period=last_period)
        
        # Mostrar bancos disponibles
        self.display_banks()
        
        # Selección de banco
        while True:
            bank_input = input("\nIngrese código de banco (o 'all' para todos): ").strip()
            
            if bank_input.lower() == 'all':
                bank_codes = [code for code in self.scraper.BANK_CODES.keys() if code != "999"]
                break
            elif bank_input in self.scraper.BANK_CODES:
                bank_codes = [bank_input]
                break
            else:
                print("❌ Código de banco no válido. Intente nuevamente.")
        
        # Siempre descargar MB1 y MR1
        report_types = ["MB1", "MR1"]
        print(f"\n📊 Descargando automáticamente:")
        for rt in report_types:
            print(f"  - {rt}: {self.scraper.REPORT_TYPES[rt]}")
        
        # Selección de modo
        print("\nMODOS DE DESCARGA:")
        print("  1. Trimestral (meses 3, 6, 9, 12)")
        print("  2. Mensual (todos los meses 1-12)")
        
        while True:
            mode_input = input("\nSeleccione modo (1 o 2): ").strip()
            if mode_input == "1":
                mode = "trimestral"
                months = self.get_quarterly_months()
                break
            elif mode_input == "2":
                mode = "mensual"
                months = self.get_monthly_months()
                break
            else:
                print("❌ Opción no válida. Ingrese 1 o 2.")
        
        # Selección de años
        default_years = 5
        years_input = input(f"\n¿Cuántos años hacia atrás? (default={default_years}): ").strip()
        
        try:
            num_years = int(years_input) if years_input else default_years
            num_years = max(1, min(num_years, 10))  # Entre 1 y 10 años
        except ValueError:
            num_years = default_years
        
        years = list(range(self.current_year - num_years + 1, self.current_year + 1))
        
        # Confirmación
        print("\n" + "="*60)
        print("RESUMEN DE DESCARGA:")
        print(f"  Bancos: {', '.join([self.scraper.BANK_CODES[c] for c in bank_codes[:3]])}" + 
              (f" y {len(bank_codes)-3} más" if len(bank_codes) > 3 else ""))
        print(f"  Reportes: {' + '.join([self.scraper.REPORT_TYPES[rt] for rt in report_types])}")
        print(f"  Modo: {mode.capitalize()}")
        print(f"  Años: {min(years)} - {max(years)} ({num_years} años)")
        print(f"  Total descargas: {len(bank_codes) * len(years) * len(months) * len(report_types)} archivos")
        print("="*60)
        
        confirm = input("\n¿Proceder con la descarga? (s/n): ").strip().lower()
        
        if confirm != 's':
            print("Descarga cancelada.")
            return
        
        # Ejecutar descargas
        all_results = {}
        for bank_code in bank_codes:
            results = self.download_bank_periods(
                bank_code, report_types, years, months, mode
            )
            all_results[bank_code] = results
        
        # Mostrar resumen
        self.show_summary(all_results)
    
    def show_summary(self, all_results: Dict[str, Dict[str, str]]):
        """Muestra resumen de descargas"""
        print("\n" + "="*60)
        print("RESUMEN DE DESCARGAS")
        print("="*60)
        
        total_files = 0
        successful_files = 0
        
        for bank_code, results in all_results.items():
            bank_name = self.scraper.BANK_CODES.get(bank_code, bank_code)
            bank_success = sum(1 for v in results.values() if v is not None)
            bank_total = len(results)
            
            total_files += bank_total
            successful_files += bank_success
            
            print(f"\n{bank_name}:")
            print(f"  ✓ Exitosas: {bank_success}/{bank_total}")
            
            if bank_success < bank_total:
                failed_periods = [k for k, v in results.items() if v is None]
                print(f"  ✗ Fallidas: {', '.join(failed_periods[:5])}" + 
                      (f" y {len(failed_periods)-5} más" if len(failed_periods) > 5 else ""))
        
        print("\n" + "="*60)
        print(f"TOTAL: {successful_files}/{total_files} archivos descargados")
        print(f"Directorio de salida: {self.scraper.output_dir}")
        print("="*60)


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description="CLI para descargar datos bancarios de la CMF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  
  # Modo interactivo (recomendado para comenzar)
  python cli_bank_scraper.py
  
  # Descarga rápida - Un banco, modo trimestral, últimos 5 años (MB1 + MR1)
  python cli_bank_scraper.py --bank 001 --mode trimestral --years 5 --last-period "07/2025"
  
  # Descarga mensual completa - Banco Santander, últimos 3 años (MB1 + MR1)
  python cli_bank_scraper.py --bank 037 --mode mensual --years 3 --last-period "07/2025"
  
  # Múltiples bancos (siempre MB1 + MR1)
  python cli_bank_scraper.py --bank 001,012,037 --mode trimestral --last-period "07/2025"
  
  # Todos los bancos, modo trimestral (siempre MB1 + MR1)
  python cli_bank_scraper.py --bank all --mode trimestral --years 2 --last-period "07/2025"
        """
    )
    
    parser.add_argument("--bank", type=str, 
                       help="Código(s) de banco(s) separados por coma, o 'all' para todos")
    parser.add_argument("--report", type=str, 
                       help="[IGNORADO] Siempre descarga MB1 y MR1")
    parser.add_argument("--mode", type=str, choices=['trimestral', 'mensual'],
                       help="Modo de descarga: trimestral (3,6,9,12) o mensual (1-12)")
    parser.add_argument("--years", type=int, default=5,
                       help="Número de años hacia atrás (default: 5)")
    parser.add_argument("--list-banks", action="store_true",
                       help="Mostrar lista de bancos disponibles")
    parser.add_argument("--list-reports", action="store_true",
                       help="Mostrar tipos de reportes disponibles")
    parser.add_argument("--last-period", type=str,
                       help="Último período disponible en formato MM/YYYY (ej: 07/2025)")
    
    args = parser.parse_args()
    
    cli = BankScraperCLI(last_period=args.last_period)
    
    # Mostrar listas informativas
    if args.list_banks:
        cli.display_banks()
        return
    
    if args.list_reports:
        cli.display_reports()
        return
    
    # Si se proporcionan argumentos mínimos, ejecutar modo batch
    if args.bank and args.mode:
        # Si no se proporcionó --last-period, preguntarlo
        if not args.last_period:
            print("⚠️  Falta el parámetro --last-period")
            last_period = cli.ask_last_period()
            cli.scraper = CMFBankScraper(output_dir="output/banks/cli", last_available_period=last_period)
        
        # Procesar códigos de banco
        if args.bank.lower() == 'all':
            bank_codes = [code for code in cli.scraper.BANK_CODES.keys() if code != "999"]
        else:
            bank_codes = [code.strip() for code in args.bank.split(',')]
            # Validar códigos
            invalid_codes = [c for c in bank_codes if c not in cli.scraper.BANK_CODES]
            if invalid_codes:
                print(f"❌ Códigos de banco no válidos: {', '.join(invalid_codes)}")
                cli.display_banks()
                return
        
        # Siempre usar MB1 y MR1 (ignorar el parámetro --report)
        report_types = ["MB1", "MR1"]
        print(f"📊 Descargando siempre: {' + '.join([cli.scraper.REPORT_TYPES[rt] for rt in report_types])}")
        
        # Configurar períodos
        current_year = datetime.now().year
        years = list(range(current_year - args.years + 1, current_year + 1))
        
        if args.mode == 'trimestral':
            months = cli.get_quarterly_months()
        else:
            months = cli.get_monthly_months()
        
        # Ejecutar descargas
        print(f"\nModo batch: {len(bank_codes)} banco(s), {len(years)} año(s), {len(months)} mes(es) por año")
        
        all_results = {}
        for bank_code in bank_codes:
            results = cli.download_bank_periods(
                bank_code, report_types, years, months, args.mode
            )
            all_results[bank_code] = results
        
        cli.show_summary(all_results)
    
    else:
        # Modo interactivo
        cli.interactive_mode()


if __name__ == "__main__":
    main()