#!/usr/bin/env python3
"""
Script de validación completa del sistema CMF Web Scraping
Valida todos los componentes: GUI modular, extractor, archivos y dependencias
"""

import os
import sys
import importlib
import subprocess
from datetime import datetime

class SystemValidator:
    def __init__(self):
        self.tests_passed = 0
        self.tests_failed = 0
        self.errors = []
    
    def log_test(self, test_name, passed, message=""):
        """Registrar resultado de una prueba"""
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
        if message:
            print(f"     {message}")
        
        if passed:
            self.tests_passed += 1
        else:
            self.tests_failed += 1
            self.errors.append(f"{test_name}: {message}")
    
    def check_dependencies(self):
        """Verificar dependencias de Python"""
        print("\n🔍 Verificando dependencias...")
        
        required_packages = [
            'tkinter', 'pandas', 'selenium', 'bs4', 'xlsxwriter', 'threading'
        ]
        
        for package in required_packages:
            try:
                if package == 'bs4':
                    importlib.import_module('bs4')
                elif package == 'threading':
                    import threading
                else:
                    importlib.import_module(package)
                self.log_test(f"Dependencia {package}", True)
            except ImportError as e:
                self.log_test(f"Dependencia {package}", False, str(e))
    
    def check_project_structure(self):
        """Verificar estructura del proyecto"""
        print("\n📁 Verificando estructura del proyecto...")
        
        required_files = [
            'cmf_gui_modular.py',
            'cmf_gui.py',
            'cmf_annual_reports_scraper.py',
            'rut_chilean_companies.py',
            'test_extractor.py',
            'setup_selenium.py',
            'requirements.txt'
        ]
        
        required_dirs = [
            'gui',
            'gui/components',
            'gui/styles',
            'gui/utils',
            'data',
            'data/RUT_Chilean_Companies'
        ]
        
        # Verificar archivos
        for file in required_files:
            exists = os.path.exists(file)
            self.log_test(f"Archivo {file}", exists)
        
        # Verificar directorios
        for directory in required_dirs:
            exists = os.path.isdir(directory)
            self.log_test(f"Directorio {directory}", exists)
    
    def check_gui_modules(self):
        """Verificar módulos de la GUI"""
        print("\n🖥️ Verificando módulos GUI...")
        
        gui_modules = [
            'gui.main_window',
            'gui.components.company_table',
            'gui.components.control_panel',
            'gui.components.log_viewer',
            'gui.styles.professional_theme',
            'gui.utils.csv_manager',
            'gui.utils.system_utils'
        ]
        
        for module in gui_modules:
            try:
                importlib.import_module(module)
                self.log_test(f"Módulo {module}", True)
            except ImportError as e:
                self.log_test(f"Módulo {module}", False, str(e))
    
    def check_extractor(self):
        """Verificar el extractor de empresas"""
        print("\n🏢 Verificando extractor de empresas...")
        
        try:
            from rut_chilean_companies import CMFCompanyExtractor
            
            # Verificar que la clase se puede instanciar
            extractor = CMFCompanyExtractor(year=2023)
            self.log_test("Instanciar CMFCompanyExtractor", True)
            
            # Verificar métodos principales
            methods = ['extract_companies', 'setup_driver', 'navigate_to_cmf', 'save_data']
            for method in methods:
                has_method = hasattr(extractor, method)
                self.log_test(f"Método {method}", has_method)
                
        except Exception as e:
            self.log_test("Extractor de empresas", False, str(e))
    
    def check_data_files(self):
        """Verificar archivos de datos existentes"""
        print("\n📊 Verificando archivos de datos...")
        
        csv_file = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
        excel_file = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx"
        
        csv_exists = os.path.exists(csv_file)
        excel_exists = os.path.exists(excel_file)
        
        self.log_test("Archivo CSV de empresas", csv_exists)
        self.log_test("Archivo Excel de empresas", excel_exists)
        
        if csv_exists:
            try:
                import pandas as pd
                df = pd.read_csv(csv_file)
                companies_count = len(df)
                has_data = companies_count > 0
                self.log_test("Datos en CSV", has_data, f"{companies_count} empresas")
                
                # Verificar columnas requeridas
                required_columns = ['Razón Social', 'RUT', 'RUT_Sin_Guión']
                for col in required_columns:
                    has_column = col in df.columns
                    self.log_test(f"Columna {col}", has_column)
                    
            except Exception as e:
                self.log_test("Lectura de CSV", False, str(e))
    
    def run_quick_test(self):
        """Ejecutar prueba rápida del extractor"""
        print("\n🚀 Ejecutando prueba rápida...")
        
        try:
            # Verificar que podemos importar sin errores
            from rut_chilean_companies import CMFCompanyExtractor
            extractor = CMFCompanyExtractor(year=2023)
            
            # Solo verificar que el setup funciona (sin extraer datos)
            driver = extractor.setup_driver()
            if driver:
                driver.quit()
                self.log_test("Configuración de WebDriver", True)
            else:
                self.log_test("Configuración de WebDriver", False, "No se pudo crear el driver")
                
        except Exception as e:
            self.log_test("Prueba rápida", False, str(e))
    
    def generate_report(self):
        """Generar reporte final"""
        print("\n" + "="*60)
        print("📋 REPORTE DE VALIDACIÓN DEL SISTEMA")
        print("="*60)
        print(f"🕐 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"✅ Pruebas exitosas: {self.tests_passed}")
        print(f"❌ Pruebas fallidas: {self.tests_failed}")
        print(f"📊 Total de pruebas: {self.tests_passed + self.tests_failed}")
        
        if self.tests_failed == 0:
            print("\n🎉 ¡SISTEMA COMPLETAMENTE FUNCIONAL!")
            print("Todos los componentes están funcionando correctamente.")
        else:
            print(f"\n⚠️  ENCONTRADOS {self.tests_failed} PROBLEMAS:")
            for error in self.errors:
                print(f"   • {error}")
        
        print("\n📖 Para usar el sistema:")
        print("   GUI Modular: python cmf_gui_modular.py")
        print("   GUI Original: python cmf_gui.py")
        print("   Extractor: python rut_chilean_companies.py")
        print("   Pruebas: python test_extractor.py")
        
        return self.tests_failed == 0

def main():
    print("🔍 VALIDADOR DEL SISTEMA CMF WEB SCRAPING")
    print("="*50)
    
    validator = SystemValidator()
    
    # Ejecutar todas las validaciones
    validator.check_dependencies()
    validator.check_project_structure()
    validator.check_gui_modules()
    validator.check_extractor()
    validator.check_data_files()
    validator.run_quick_test()
    
    # Generar reporte final
    success = validator.generate_report()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
