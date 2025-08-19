#!/usr/bin/env python3
"""
Script de prueba para demostrar el funcionamiento del verificador XBRL
Este script simula el proceso sin necesidad de conexión a internet
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Tuple

def parse_company_folder(company_folder: str, xbrl_base_path: str = "/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total") -> Dict[str, any]:
    """
    Parsear carpeta de empresa para extraer RUT y último período
    (Versión de prueba sin dependencias externas)
    """
    company_path = Path(xbrl_base_path) / company_folder
    
    if not company_path.exists():
        print(f"⚠️ Carpeta de empresa no encontrada: {company_path}")
        return {}
    
    # Extraer RUT del nombre de la carpeta
    rut_match = re.match(r'(\d{7,8}-\d)', company_folder)
    if not rut_match:
        print(f"⚠️ No se pudo extraer RUT de: {company_folder}")
        return {}
    
    rut = rut_match.group(1)
    rut_numero = rut.split('-')[0]
    
    # Buscar períodos disponibles en subcarpetas
    periods_found = []
    for item in company_path.iterdir():
        if item.is_dir():
            # Patrón: Estados_financieros_(XBRL)99589230_202503_extracted
            match = re.search(r'Estados_financieros_\(XBRL\)(\d+)_(\d{6})_extracted', item.name)
            if match:
                rut_in_folder = match.group(1)
                period = match.group(2)
                
                # Verificar que el RUT en la carpeta coincida
                if rut_in_folder == rut_numero:
                    periods_found.append(period)
                    print(f"      📅 Período encontrado: {period} en {item.name}")
    
    if not periods_found:
        print(f"⚠️ No se encontraron períodos para {company_folder}")
        return {
            "rut": rut,
            "rut_numero": rut_numero,
            "last_period": None,
            "last_year": None,
            "last_month": None,
            "next_period": None,
            "next_year": None,
            "next_month": None
        }
    
    # Encontrar el período más reciente
    periods_found.sort(reverse=True)  # Ordenar de más reciente a más antiguo
    last_period = periods_found[0]
    
    # Parsear el último período
    last_year = int(last_period[:4])
    last_month = int(last_period[4:6])
    
    # Calcular el siguiente período a buscar
    next_year, next_month = get_next_period(last_year, last_month)
    next_period = format_period(next_year, next_month)
    
    print(f"📁 Empresa: {company_folder}")
    print(f"   🆔 RUT: {rut}")
    print(f"   📅 Último período disponible: {last_year}-{last_month:02d} ({last_period})")
    print(f"   🔍 Siguiente período a buscar: {next_year}-{next_month:02d} ({next_period})")
    
    return {
        "rut": rut,
        "rut_numero": rut_numero,
        "last_period": last_period,
        "last_year": last_year,
        "last_month": last_month,
        "next_period": next_period,
        "next_year": next_year,
        "next_month": next_month,
        "all_periods": periods_found
    }

def format_period(year: int, month: int) -> str:
    """Convertir (año, mes) a formato YYYYMM"""
    return f"{year}{month:02d}"

def get_next_period(year: int, month: int) -> Tuple[int, int]:
    """
    Obtener el siguiente período (trimestral)
    
    Args:
        year: Año actual
        month: Mes actual
        
    Returns:
        Tupla (año_siguiente, mes_siguiente)
    """
    if month == 3:
        return year, 6
    elif month == 6:
        return year, 9
    elif month == 9:
        return year, 12
    elif month == 12:
        return year + 1, 3
    else:
        # Si no es un mes trimestral, ir al siguiente trimestre
        if month < 3:
            return year, 3
        elif month < 6:
            return year, 6
        elif month < 9:
            return year, 9
        else:
            return year, 12

def simulate_xbrl_check(company_info: Dict[str, any]) -> Dict[str, List[str]]:
    """
    Simular verificación de disponibilidad XBRL
    (En la versión real, esto iría a la CMF)
    """
    print(f"   🔍 Simulando verificación desde: {company_info['next_year']}-{company_info['next_month']:02d}")
    
    # Simular algunos períodos disponibles y otros no
    available_periods = []
    unavailable_periods = []
    
    year = company_info['next_year']
    month = company_info['next_month']
    
    # Simular verificación de 3 períodos
    for i in range(3):
        period_str = format_period(year, month)
        
        # Simular que algunos períodos están disponibles
        if i == 0:  # Primer período (siguiente al último local)
            available_periods.append(period_str)
            print(f"      ✅ XBRL disponible para {year}-{month:02d}")
        else:
            unavailable_periods.append(period_str)
            print(f"      ❌ XBRL no disponible para {year}-{month:02d}")
        
        # Ir al siguiente período
        year, month = get_next_period(year, month)
    
    return {
        "available": available_periods,
        "unavailable": unavailable_periods
    }

def main():
    """Función principal de prueba"""
    print("🧪 PRUEBA DEL VERIFICADOR XBRL")
    print("=" * 60)
    
    # Ruta base (ajustar según tu sistema)
    xbrl_base_path = "/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total"
    
    if not Path(xbrl_base_path).exists():
        print(f"❌ La carpeta base no existe: {xbrl_base_path}")
        print("Por favor, ajusta la ruta en el script o crea la carpeta")
        return
    
    print(f"📁 Verificando carpeta: {xbrl_base_path}")
    
    # Listar empresas disponibles
    company_folders = [f for f in Path(xbrl_base_path).iterdir() if f.is_dir()]
    
    if not company_folders:
        print("❌ No se encontraron carpetas de empresas")
        return
    
    print(f"🏢 Encontradas {len(company_folders)} empresas")
    
    # Procesar cada empresa
    for company_folder in company_folders:
        company_name = company_folder.name
        print(f"\n{'='*60}")
        print(f"🔍 Procesando empresa: {company_name}")
        print(f"{'='*60}")
        
        # Parsear carpeta de empresa
        company_info = parse_company_folder(company_name, xbrl_base_path)
        if not company_info:
            print(f"⚠️ No se pudo procesar: {company_name}")
            continue
        
        # Si no hay períodos, saltar
        if not company_info.get("last_period"):
            print(f"   ⏭️ Saltando {company_name} - No hay períodos disponibles")
            continue
        
        # Simular verificación de disponibilidad
        availability = simulate_xbrl_check(company_info)
        
        # Mostrar resultados
        print(f"\n   📊 RESULTADOS:")
        print(f"      ✅ Períodos disponibles: {len(availability['available'])}")
        print(f"      ❌ Períodos no disponibles: {len(availability['unavailable'])}")
        
        if availability['available']:
            print(f"      📥 Disponibles: {', '.join(availability['available'])}")
        
        if availability['unavailable']:
            print(f"      ⏳ No disponibles: {', '.join(availability['unavailable'])}")
    
    print(f"\n{'='*60}")
    print("🎉 PRUEBA COMPLETADA")
    print("=" * 60)
    print("Este script demuestra cómo el verificador:")
    print("1. 📁 Lee las carpetas de empresas")
    print("2. 🆔 Extrae el RUT automáticamente")
    print("3. 📅 Encuentra el último período disponible")
    print("4. 🔍 Calcula el siguiente período a buscar")
    print("5. 🌐 (En la versión real) Verifica en la CMF")
    print("\nPara usar la versión real:")
    print("   python check_xbrl_availability.py")

if __name__ == "__main__":
    main()
