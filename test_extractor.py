#!/usr/bin/env python3
"""
Script de prueba para el extractor mejorado de empresas CMF
"""

import sys
import os
from datetime import datetime

# Verificar que estamos en el directorio correcto
if not os.path.exists('rut_chilean_companies.py'):
    print("Error: Ejecute este script desde el directorio del proyecto")
    sys.exit(1)

def test_extractor():
    """Probar el extractor de empresas"""
    try:
        from rut_chilean_companies import CMFCompanyExtractor
        
        print("🚀 Iniciando prueba del extractor de empresas CMF")
        print("=" * 60)
        
        # Crear extractor para el año 2023
        extractor = CMFCompanyExtractor(year=2023)
        
        # Ejecutar extracción
        success = extractor.extract_companies()
        
        if success:
            print("\n✅ Prueba completada exitosamente!")
            
            # Verificar archivos creados
            csv_path = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
            excel_path = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx"
            
            if os.path.exists(csv_path):
                import pandas as pd
                df = pd.read_csv(csv_path)
                print(f"📊 Archivo CSV: {len(df)} empresas")
                print(f"📁 Ubicación: {csv_path}")
                
                # Mostrar primeras empresas
                print("\n📋 Primeras 5 empresas:")
                print(df[['Razón Social', 'RUT', 'RUT_Sin_Guión']].head())
            
            if os.path.exists(excel_path):
                print(f"📊 Archivo Excel creado: {excel_path}")
        else:
            print("\n❌ Error en la prueba")
            return False
            
        return True
        
    except ImportError as e:
        print(f"❌ Error de importación: {e}")
        print("Asegúrese de tener todas las dependencias instaladas:")
        print("pip install selenium beautifulsoup4 pandas xlsxwriter")
        return False
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return False

def show_usage():
    """Mostrar instrucciones de uso"""
    print("📖 Uso del Extractor de Empresas CMF")
    print("=" * 40)
    print()
    print("1. Ejecutar extracción (año actual-1):")
    print("   python rut_chilean_companies.py")
    print()
    print("2. Ejecutar extracción para año específico:")
    print("   python rut_chilean_companies.py 2022")
    print()
    print("3. Ejecutar prueba:")
    print("   python test_extractor.py")
    print()
    print("📁 Archivos generados:")
    print("   ./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv")
    print("   ./data/RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx")
    print()
    print("📋 Dependencias requeridas:")
    print("   pip install selenium beautifulsoup4 pandas xlsxwriter")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        show_usage()
    else:
        print(f"🕐 Iniciando prueba: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        success = test_extractor()
        sys.exit(0 if success else 1)
