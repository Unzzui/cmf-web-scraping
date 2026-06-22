#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para verificar la estructura del Excel generado
"""

import pandas as pd
from pathlib import Path

def verificar_excel():
    # Buscar el archivo Excel más reciente
    output_dir = Path("output")
    excel_files = list(output_dir.glob("estados_financieros_*.xlsx"))
    
    if not excel_files:
        print("❌ No se encontraron archivos Excel en el directorio output/")
        return
    
    # Tomar el más reciente
    latest_file = max(excel_files, key=lambda x: x.stat().st_mtime)
    print(f"📁 Verificando archivo: {latest_file.name}")
    print()
    
    try:
        # Leer cada hoja
        for sheet_name in ["Balance", "Estado_Resultados", "Flujo_Efectivo"]:
            print(f"📊 HOJA: {sheet_name}")
            print("=" * 50)
            
            df = pd.read_excel(latest_file, sheet_name=sheet_name)
            
            # Mostrar información de columnas
            print(f"Columnas: {list(df.columns)}")
            print(f"Total de filas: {len(df)}")
            print()
            
            # Mostrar primeras 5 filas
            print("Primeras 5 filas:")
            print(df.head().to_string(index=False))
            print()
            
            # Mostrar tipos de datos
            print("Tipos de datos:")
            print(df.dtypes)
            print()
            
            # Contar valores no nulos en cada columna
            print("Valores no nulos por columna:")
            for col in df.columns:
                non_null = df[col].notna().sum()
                print(f"  {col}: {non_null}/{len(df)}")
            print()
            
            print("-" * 80)
            print()
    
    except Exception as e:
        print(f"❌ Error al leer el archivo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verificar_excel()
