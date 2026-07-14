#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba rápida para la CLI del Bank Scraper
"""

import subprocess
import sys

def test_list_commands():
    """Prueba los comandos de listado"""
    print("\n" + "="*60)
    print("TEST: Comandos de listado")
    print("="*60)
    
    # Listar bancos
    print("\n1. Listando bancos disponibles:")
    subprocess.run([sys.executable, "cli_bank_scraper.py", "--list-banks"])
    
    # Listar reportes
    print("\n2. Listando tipos de reportes:")
    subprocess.run([sys.executable, "cli_bank_scraper.py", "--list-reports"])


def test_single_bank_quarterly():
    """Prueba descarga de un banco en modo trimestral"""
    print("\n" + "="*60)
    print("TEST: Un banco, modo trimestral, 1 año")
    print("="*60)
    
    cmd = [
        sys.executable, 
        "cli_bank_scraper.py",
        "--bank", "001",
        "--report", "MB1",
        "--mode", "trimestral",
        "--years", "1"
    ]
    
    print(f"\nComando: {' '.join(cmd)}")
    print("\nEjecutando...")
    subprocess.run(cmd)


def show_usage_examples():
    """Muestra ejemplos de uso"""
    print("\n" + "="*60)
    print("EJEMPLOS DE USO DE LA CLI")
    print("="*60)
    
    examples = [
        ("Modo interactivo", "python cli_bank_scraper.py"),
        ("Un banco trimestral", "python cli_bank_scraper.py --bank 001 --report MB1 --mode trimestral --years 5"),
        ("Un banco mensual", "python cli_bank_scraper.py --bank 037 --report MR1 --mode mensual --years 3"),
        ("Múltiples bancos", "python cli_bank_scraper.py --bank 001,012,037 --report MB1 --mode trimestral"),
        ("Todos los bancos", "python cli_bank_scraper.py --bank all --report MB1 --mode trimestral --years 2"),
        ("Listar bancos", "python cli_bank_scraper.py --list-banks"),
        ("Listar reportes", "python cli_bank_scraper.py --list-reports"),
    ]
    
    for desc, cmd in examples:
        print(f"\n{desc}:")
        print(f"  $ {cmd}")


def main():
    print("\n" + "#"*60)
    print("# PRUEBA RÁPIDA - CMF BANK SCRAPER CLI")
    print("#"*60)
    
    print("""
Esta es una prueba rápida de la CLI. Opciones:

1. Ver ejemplos de uso
2. Listar bancos y reportes disponibles  
3. Prueba rápida (1 banco, trimestral, 1 año)
4. Ejecutar modo interactivo

""")
    
    option = input("Seleccione opción (1-4): ").strip()
    
    if option == "1":
        show_usage_examples()
    elif option == "2":
        test_list_commands()
    elif option == "3":
        test_single_bank_quarterly()
    elif option == "4":
        print("\nEjecutando modo interactivo...")
        subprocess.run([sys.executable, "cli_bank_scraper.py"])
    else:
        print("Opción no válida")


if __name__ == "__main__":
    main()