#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Interactiva para CMF Bank Scraper
Interfaz amigable con menús visuales y experiencia paso a paso
"""

import sys
import os
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, str(Path(__file__).parent))

from src.scrapers.cmf_bank_scraper import CMFBankScraper


class Colors:
    """Colores para la terminal"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class InteractiveCLI:
    """CLI interactiva mejorada para el scraper de bancos"""
    
    def __init__(self):
        self.scraper = None
        self.last_period = None
        self.clear_screen()
    
    def clear_screen(self):
        """Limpia la pantalla"""
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def print_header(self, title: str):
        """Imprime un header estilizado"""
        width = 70
        print(f"\n{Colors.HEADER}{'=' * width}")
        print(f"🏦 {title.center(width-4)} 🏦")
        print(f"{'=' * width}{Colors.ENDC}")
    
    def print_section(self, title: str):
        """Imprime una sección"""
        print(f"\n{Colors.OKBLUE}📋 {title}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}{'-' * (len(title) + 4)}{Colors.ENDC}")
    
    def print_success(self, message: str):
        """Imprime mensaje de éxito"""
        print(f"{Colors.OKGREEN}✅ {message}{Colors.ENDC}")
    
    def print_warning(self, message: str):
        """Imprime mensaje de advertencia"""
        print(f"{Colors.WARNING}⚠️  {message}{Colors.ENDC}")
    
    def print_error(self, message: str):
        """Imprime mensaje de error"""
        print(f"{Colors.FAIL}❌ {message}{Colors.ENDC}")
    
    def print_info(self, message: str):
        """Imprime mensaje informativo"""
        print(f"{Colors.OKCYAN}ℹ️  {message}{Colors.ENDC}")
    
    def show_progress(self, current: int, total: int, description: str):
        """Muestra barra de progreso"""
        percent = (current / total) * 100
        filled = int(percent // 4)
        bar = "█" * filled + "░" * (25 - filled)
        print(f"\r{Colors.OKCYAN}[{bar}] {percent:.1f}% - {description}{Colors.ENDC}", end="", flush=True)
    
    def get_user_input(self, prompt: str, options: List[str] = None) -> str:
        """Obtiene input del usuario con validación"""
        while True:
            if options:
                print(f"\n{Colors.BOLD}{prompt}{Colors.ENDC}")
                for i, option in enumerate(options, 1):
                    print(f"  {Colors.OKCYAN}{i}.{Colors.ENDC} {option}")
                
                choice = input(f"\n{Colors.BOLD}Seleccione una opción (1-{len(options)}): {Colors.ENDC}").strip()
                
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(options):
                        return str(idx + 1)
                    else:
                        self.print_error("Opción no válida. Intente nuevamente.")
                except ValueError:
                    self.print_error("Ingrese un número válido.")
            else:
                response = input(f"{Colors.BOLD}{prompt}{Colors.ENDC}").strip()
                if response:
                    return response
                self.print_error("Este campo es obligatorio.")
    
    def welcome_screen(self):
        """Pantalla de bienvenida"""
        self.clear_screen()
        self.print_header("CMF BANK SCRAPER - VERSIÓN INTERACTIVA")
        
        print(f"\n{Colors.OKCYAN}¡Bienvenido al descargador de datos bancarios de la CMF!{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Esta herramienta te ayudará a descargar estados financieros de bancos chilenos.{Colors.ENDC}")
        
        print(f"\n{Colors.OKGREEN}✨ Características:{Colors.ENDC}")
        print(f"  🏦 Todos los bancos chilenos disponibles")
        print(f"  📊 Estados de Situación (MB1) y Resultados (MR1)")
        print(f"  📁 Organización automática por RUT y tipo de reporte") 
        print(f"  ⏰ Validación de períodos disponibles")
        print(f"  🔄 Modo trimestral y mensual")
        
        input(f"\n{Colors.BOLD}Presiona Enter para continuar...{Colors.ENDC}")
    
    def setup_period(self):
        """Configurar el último período disponible"""
        self.clear_screen()
        self.print_header("CONFIGURACIÓN DEL PERÍODO")
        
        self.print_info("Para obtener datos precisos, necesitamos saber el último período disponible en la CMF.")
        
        print(f"\n{Colors.WARNING}📍 Pasos para obtener el período:{Colors.ENDC}")
        print("  1. Abre: https://datosbanco.cmfchile.cl/sbifweb/servlet/BaseDato?indice=30.0")
        print("  2. Selecciona cualquier banco")
        print("  3. Selecciona cualquier reporte (ej: MB1)")
        print("  4. Verás algo como 'Ultimo Periodo Cargado: 07/2025'")
        
        while True:
            period = input(f"\n{Colors.BOLD}Ingresa el último período (MM/YYYY, ej: 07/2025): {Colors.ENDC}").strip()
            
            try:
                month, year = period.split('/')
                month = int(month)
                year = int(year)
                
                if not (1 <= month <= 12):
                    self.print_error("El mes debe estar entre 01 y 12")
                    continue
                    
                if year < 2000 or year > 2030:
                    self.print_error("El año parece inválido")
                    continue
                    
                self.last_period = period
                self.scraper = CMFBankScraper(
                    output_dir="output/banks/interactive",
                    last_available_period=period
                )
                
                self.print_success(f"Período configurado: {period}")
                time.sleep(1)
                break
                
            except ValueError:
                self.print_error("Formato inválido. Use MM/YYYY (ej: 07/2025)")
            except Exception as e:
                self.print_error(f"Error: {e}")
    
    def select_banks(self) -> List[str]:
        """Seleccionar bancos para descargar"""
        self.clear_screen()
        self.print_header("SELECCIÓN DE BANCOS")
        
        options = [
            "🏦 Un banco específico",
            "💼 Múltiples bancos",
            "🏛️ Bancos principales (Top 5)",
            "🌟 Todos los bancos"
        ]
        
        choice = self.get_user_input("¿Qué bancos quieres descargar?", options)
        
        if choice == "1":  # Un banco específico
            return self.select_single_bank()
        elif choice == "2":  # Múltiples bancos
            return self.select_multiple_banks()
        elif choice == "3":  # Bancos principales
            return ["001", "037", "016", "012", "014"]  # Top 5 bancos
        else:  # Todos los bancos
            return [code for code in self.scraper.BANK_CODES.keys() if code != "999"]
    
    def select_single_bank(self) -> List[str]:
        """Seleccionar un solo banco"""
        self.print_section("Bancos Disponibles")
        
        banks = list(self.scraper.BANK_CODES.items())
        banks = [(k, v) for k, v in banks if k != "999"]  # Excluir sistema financiero
        
        # Mostrar en columnas
        for i in range(0, len(banks), 2):
            left = banks[i]
            right = banks[i+1] if i+1 < len(banks) else None
            
            left_text = f"{left[0]}: {left[1]}"
            if right:
                right_text = f"{right[0]}: {right[1]}"
                print(f"  {left_text:<35} {right_text}")
            else:
                print(f"  {left_text}")
        
        while True:
            code = input(f"\n{Colors.BOLD}Ingresa el código del banco: {Colors.ENDC}").strip()
            
            if code in self.scraper.BANK_CODES and code != "999":
                bank_name = self.scraper.BANK_CODES[code]
                self.print_success(f"Seleccionado: {bank_name}")
                time.sleep(1)
                return [code]
            else:
                self.print_error("Código de banco no válido")
    
    def select_multiple_banks(self) -> List[str]:
        """Seleccionar múltiples bancos"""
        self.print_info("Ingresa los códigos de banco separados por comas (ej: 001,037,016)")
        
        self.print_section("Bancos Principales")
        main_banks = [
            ("001", "BANCO DE CHILE"),
            ("037", "BANCO SANTANDER-CHILE"),
            ("016", "BANCO DE CREDITO E INVERSIONES"),
            ("012", "BANCO DEL ESTADO DE CHILE"),
            ("014", "SCOTIABANK CHILE"),
            ("051", "BANCO FALABELLA"),
            ("049", "BANCO SECURITY")
        ]
        
        for code, name in main_banks:
            print(f"  {code}: {name}")
        
        while True:
            codes = input(f"\n{Colors.BOLD}Códigos (separados por coma): {Colors.ENDC}").strip()
            
            try:
                bank_codes = [code.strip() for code in codes.split(',')]
                invalid_codes = [c for c in bank_codes if c not in self.scraper.BANK_CODES or c == "999"]
                
                if invalid_codes:
                    self.print_error(f"Códigos no válidos: {', '.join(invalid_codes)}")
                    continue
                
                self.print_success(f"Seleccionados {len(bank_codes)} bancos")
                time.sleep(1)
                return bank_codes
                
            except Exception as e:
                self.print_error(f"Error: {e}")
    
    def select_mode(self) -> tuple:
        """Seleccionar modo de descarga"""
        self.clear_screen()
        self.print_header("MODO DE DESCARGA")
        
        options = [
            "📈 Trimestral (meses 3, 6, 9, 12) - Recomendado",
            "📅 Mensual (todos los meses 1-12) - Completo"
        ]
        
        choice = self.get_user_input("Selecciona el modo de descarga:", options)
        
        if choice == "1":
            return "trimestral", [3, 6, 9, 12]
        else:
            return "mensual", list(range(1, 13))
    
    def select_years(self) -> List[int]:
        """Seleccionar años a descargar"""
        self.print_section("Rango de Años")
        
        current_year = datetime.now().year
        
        options = [
            f"📅 Último año ({current_year})",
            f"📅 Últimos 2 años ({current_year-1} - {current_year})",
            f"📅 Últimos 3 años ({current_year-2} - {current_year})",
            f"📅 Últimos 5 años ({current_year-4} - {current_year})",
            "⚙️  Personalizado"
        ]
        
        choice = self.get_user_input("¿Cuántos años descargar?", options)
        
        if choice == "1":
            return [current_year]
        elif choice == "2":
            return [current_year-1, current_year]
        elif choice == "3":
            return list(range(current_year-2, current_year+1))
        elif choice == "4":
            return list(range(current_year-4, current_year+1))
        else:
            while True:
                try:
                    years_input = input(f"\n{Colors.BOLD}¿Cuántos años hacia atrás? (1-10): {Colors.ENDC}").strip()
                    num_years = int(years_input)
                    
                    if 1 <= num_years <= 10:
                        return list(range(current_year - num_years + 1, current_year + 1))
                    else:
                        self.print_error("Ingresa un número entre 1 y 10")
                except ValueError:
                    self.print_error("Ingresa un número válido")
    
    def show_summary(self, bank_codes: List[str], mode: str, months: List[int], years: List[int]):
        """Mostrar resumen antes de la descarga"""
        self.clear_screen()
        self.print_header("RESUMEN DE DESCARGA")
        
        print(f"\n{Colors.BOLD}📊 Configuración:{Colors.ENDC}")
        print(f"  🏦 Bancos: {len(bank_codes)} banco(s)")
        
        if len(bank_codes) <= 5:
            for code in bank_codes:
                bank_name = self.scraper.BANK_CODES[code]
                rut = self.scraper.BANKS_RUTS.get(code, "N/A")
                print(f"     • {bank_name} ({rut})")
        else:
            print(f"     • {self.scraper.BANK_CODES[bank_codes[0]]} y {len(bank_codes)-1} más...")
        
        print(f"\n  📋 Reportes: Estado de Situación (MB1) + Estado de Resultados (MR1)")
        print(f"  📅 Modo: {mode.capitalize()}")
        print(f"  📆 Años: {min(years)} - {max(years)} ({len(years)} año(s))")
        print(f"  ⏰ Período válido hasta: {self.last_period}")
        
        total_files = len(bank_codes) * len(years) * len(months) * 2  # 2 reportes por período
        print(f"\n  📈 Total estimado: {total_files} archivos")
        
        print(f"\n{Colors.WARNING}📁 Los archivos se guardarán en:{Colors.ENDC}")
        print(f"     output/banks/interactive/{{RUT}}_{{BANCO}}/{{REPORTE}}/")
        
        confirm = input(f"\n{Colors.BOLD}¿Proceder con la descarga? (s/n): {Colors.ENDC}").strip().lower()
        return confirm == 's'
    
    def download_with_progress(self, bank_codes: List[str], mode: str, months: List[int], years: List[int]):
        """Ejecutar descarga con barra de progreso"""
        self.clear_screen()
        self.print_header("DESCARGA EN PROGRESO")
        
        total_operations = len(bank_codes) * len(years) * len(months) * 2
        current_operation = 0
        successful_downloads = 0
        
        print(f"\n{Colors.OKCYAN}🚀 Iniciando descarga de {total_operations} archivos...{Colors.ENDC}\n")
        
        start_time = time.time()
        
        for bank_code in bank_codes:
            bank_name = self.scraper.BANK_CODES[bank_code]
            rut = self.scraper.BANKS_RUTS.get(bank_code, "N/A")
            
            print(f"\n{Colors.OKBLUE}🏦 Procesando: {bank_name} ({rut}){Colors.ENDC}")
            
            for year in years:
                for month in months:
                    # Verificar disponibilidad del período
                    if not self.scraper.is_period_available(month, year):
                        current_operation += 2  # Saltar ambos reportes
                        self.show_progress(current_operation, total_operations, f"Período {year}-{month:02d} no disponible")
                        continue
                    
                    # Descargar MB1
                    current_operation += 1
                    self.show_progress(current_operation, total_operations, f"MB1 {year}-{month:02d}")
                    
                    result_mb1 = self.scraper.download_bank_data(
                        bank_code, "MB1", month, year, organize_by_bank=True
                    )
                    if result_mb1:
                        successful_downloads += 1
                    
                    time.sleep(1)
                    
                    # Descargar MR1
                    current_operation += 1
                    self.show_progress(current_operation, total_operations, f"MR1 {year}-{month:02d}")
                    
                    result_mr1 = self.scraper.download_bank_data(
                        bank_code, "MR1", month, year, organize_by_bank=True
                    )
                    if result_mr1:
                        successful_downloads += 1
                    
                    time.sleep(1)
        
        elapsed_time = time.time() - start_time
        
        print(f"\n\n{Colors.OKGREEN}🎉 ¡Descarga completada!{Colors.ENDC}")
        print(f"  ✅ Archivos descargados: {successful_downloads}/{total_operations}")
        print(f"  ⏱️  Tiempo total: {elapsed_time:.1f} segundos")
        print(f"  📁 Ubicación: output/banks/interactive/")
        
        input(f"\n{Colors.BOLD}Presiona Enter para continuar...{Colors.ENDC}")
    
    def show_results(self):
        """Mostrar resultados finales"""
        self.clear_screen()
        self.print_header("DESCARGA COMPLETADA")
        
        output_dir = Path("output/banks/interactive")
        
        if output_dir.exists():
            folders = list(output_dir.iterdir())
            
            print(f"\n{Colors.OKGREEN}📁 Se crearon {len(folders)} carpetas de bancos:{Colors.ENDC}")
            
            for folder in sorted(folders):
                if folder.is_dir():
                    report_folders = list(folder.iterdir())
                    total_files = sum(len(list(rf.glob("*.csv"))) for rf in report_folders if rf.is_dir())
                    print(f"  🏦 {folder.name} ({total_files} archivos)")
        
        print(f"\n{Colors.OKCYAN}💡 Próximos pasos:{Colors.ENDC}")
        print("  1. Los archivos están listos para análisis")
        print("  2. Puedes importar los CSVs a Excel, Python, R, etc.")
        print("  3. Cada carpeta contiene MB1 (Situación) y MR1 (Resultados)")
        
        options = [
            "🔄 Nueva descarga",
            "📂 Abrir directorio de salida",
            "🚪 Salir"
        ]
        
        choice = self.get_user_input("¿Qué quieres hacer ahora?", options)
        
        if choice == "1":
            self.run()
        elif choice == "2":
            print(f"{Colors.OKCYAN}📂 Abriendo: {output_dir.absolute()}{Colors.ENDC}")
            os.system(f"xdg-open '{output_dir.absolute()}'" if os.name == 'posix' else f"explorer '{output_dir.absolute()}'")
            time.sleep(2)
            self.show_results()
    
    def run(self):
        """Ejecutar la CLI interactiva"""
        try:
            self.welcome_screen()
            self.setup_period()
            
            bank_codes = self.select_banks()
            mode, months = self.select_mode()
            years = self.select_years()
            
            if self.show_summary(bank_codes, mode, months, years):
                self.download_with_progress(bank_codes, mode, months, years)
                self.show_results()
            else:
                self.print_warning("Descarga cancelada")
                
        except KeyboardInterrupt:
            print(f"\n\n{Colors.WARNING}🛑 Descarga interrumpida por el usuario{Colors.ENDC}")
        except Exception as e:
            print(f"\n\n{Colors.FAIL}💥 Error inesperado: {e}{Colors.ENDC}")


if __name__ == "__main__":
    cli = InteractiveCLI()
    cli.run()