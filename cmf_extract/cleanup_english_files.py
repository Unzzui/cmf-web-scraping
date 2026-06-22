#!/usr/bin/env python3
"""
Script para eliminar archivos en inglés del directorio Product_v1/Total.
Solo mantiene los archivos en español.
"""

import os
import glob
import re
from pathlib import Path

def cleanup_english_files():
    """
    Elimina archivos en inglés del directorio Product_v1/Total.
    Mantiene solo los archivos en español.
    """
    
    # Directorio objetivo
    target_dir = "Product_v1/Total"
    
    # Verificar que el directorio existe
    if not os.path.exists(target_dir):
        print(f"❌ El directorio {target_dir} no existe.")
        return
    
    print(f"🧹 Limpiando archivos en inglés del directorio: {target_dir}")
    print("=" * 60)
    
    # Patrones para identificar archivos en inglés
    english_patterns = [
        r".*\[EN\]\.xlsx$",  # Archivos que terminan en [EN].xlsx
        r".*Financial Analysis.*\.xlsx$",  # Archivos con "Financial Analysis"
        r".*_en\.xlsx$",  # Archivos que terminan en _en.xlsx
    ]
    
    # Contadores
    total_files = 0
    english_files = 0
    spanish_files = 0
    deleted_files = 0
    
    # Obtener todos los archivos Excel en el directorio
    excel_files = glob.glob(os.path.join(target_dir, "*.xlsx"))
    
    if not excel_files:
        print("ℹ️  No se encontraron archivos Excel en el directorio.")
        return
    
    print(f"📊 Total de archivos Excel encontrados: {len(excel_files)}")
    print()
    
    # Clasificar archivos
    for file_path in excel_files:
        filename = os.path.basename(file_path)
        total_files += 1
        
        # Verificar si es archivo en inglés
        is_english = False
        for pattern in english_patterns:
            if re.match(pattern, filename, re.IGNORECASE):
                is_english = True
                break
        
        if is_english:
            english_files += 1
            print(f"🇬🇧 Archivo en inglés: {filename}")
        else:
            spanish_files += 1
            print(f"🇪🇸 Archivo en español: {filename}")
    
    print()
    print(f"📈 Resumen de clasificación:")
    print(f"   - Archivos en inglés: {english_files}")
    print(f"   - Archivos en español: {spanish_files}")
    print(f"   - Total: {total_files}")
    
    if english_files == 0:
        print("\n✅ No hay archivos en inglés para eliminar.")
        return
    
    print()
    print("⚠️  ADVERTENCIA: Los archivos en inglés serán ELIMINADOS permanentemente.")
    
    # Confirmar antes de eliminar
    while True:
        response = input("\n¿Deseas continuar? (sí/no): ").lower().strip()
        if response in ['sí', 'si', 's', 'yes', 'y']:
            break
        elif response in ['no', 'n']:
            print("❌ Operación cancelada. No se eliminaron archivos.")
            return
        else:
            print("Por favor, responde 'sí' o 'no'.")
    
    print()
    print("🗑️  Eliminando archivos en inglés...")
    print("-" * 40)
    
    # Eliminar archivos en inglés
    for file_path in excel_files:
        filename = os.path.basename(file_path)
        
        # Verificar si es archivo en inglés
        is_english = False
        for pattern in english_patterns:
            if re.match(pattern, filename, re.IGNORECASE):
                is_english = True
                break
        
        if is_english:
            try:
                os.remove(file_path)
                deleted_files += 1
                print(f"✅ Eliminado: {filename}")
            except Exception as e:
                print(f"❌ Error al eliminar {filename}: {e}")
    
    print()
    print("🎉 Limpieza completada!")
    print(f"📊 Archivos eliminados: {deleted_files}")
    print(f"📁 Archivos restantes: {spanish_files}")
    
    # Mostrar archivos restantes
    remaining_files = glob.glob(os.path.join(target_dir, "*.xlsx"))
    if remaining_files:
        print("\n📋 Archivos restantes en español:")
        for file_path in remaining_files:
            filename = os.path.basename(file_path)
            print(f"   - {filename}")

def preview_cleanup():
    """
    Vista previa de la limpieza sin eliminar archivos.
    """
    
    target_dir = "Product_v1/Total"
    
    if not os.path.exists(target_dir):
        print(f"❌ El directorio {target_dir} no existe.")
        return
    
    print(f"👀 Vista previa de limpieza en: {target_dir}")
    print("=" * 60)
    
    # Patrones para identificar archivos en inglés
    english_patterns = [
        r".*\[EN\]\.xlsx$",
        r".*Financial Analysis.*\.xlsx$",
        r".*_en\.xlsx$",
    ]
    
    excel_files = glob.glob(os.path.join(target_dir, "*.xlsx"))
    
    if not excel_files:
        print("ℹ️  No se encontraron archivos Excel en el directorio.")
        return
    
    print(f"📊 Total de archivos Excel: {len(excel_files)}")
    print()
    
    english_files = []
    spanish_files = []
    
    for file_path in excel_files:
        filename = os.path.basename(file_path)
        
        # Verificar si es archivo en inglés
        is_english = False
        for pattern in english_patterns:
            if re.match(pattern, filename, re.IGNORECASE):
                is_english = True
                break
        
        if is_english:
            english_files.append(filename)
        else:
            spanish_files.append(filename)
    
    print("🇬🇧 Archivos en inglés (serán ELIMINADOS):")
    if english_files:
        for filename in english_files:
            print(f"   ❌ {filename}")
    else:
        print("   ✅ No hay archivos en inglés")
    
    print()
    print("🇪🇸 Archivos en español (se MANTENDRÁN):")
    if spanish_files:
        for filename in spanish_files:
            print(f"   ✅ {filename}")
    else:
        print("   ❌ No hay archivos en español")
    
    print()
    print(f"📈 Resumen:")
    print(f"   - Archivos a eliminar: {len(english_files)}")
    print(f"   - Archivos a mantener: {len(spanish_files)}")
    print(f"   - Total: {len(excel_files)}")

def main():
    """
    Función principal del script.
    """
    
    print("🧹 LIMPIADOR DE ARCHIVOS EN INGLÉS")
    print("=" * 50)
    print("Este script elimina archivos en inglés del directorio Product_v1/Total")
    print("Solo mantiene los archivos en español.")
    print()
    
    while True:
        print("Opciones:")
        print("1. Vista previa (sin eliminar)")
        print("2. Ejecutar limpieza")
        print("3. Salir")
        print()
        
        choice = input("Selecciona una opción (1-3): ").strip()
        
        if choice == "1":
            print()
            preview_cleanup()
        elif choice == "2":
            print()
            cleanup_english_files()
        elif choice == "3":
            print("👋 ¡Hasta luego!")
            break
        else:
            print("❌ Opción inválida. Por favor selecciona 1, 2 o 3.")
        
        print()
        input("Presiona Enter para continuar...")
        print()

if __name__ == "__main__":
    main()
