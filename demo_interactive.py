#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Demo de la CLI Interactiva
Muestra las características principales sin descargar archivos
"""

import os
import time
from cli_interactive import InteractiveCLI, Colors


def demo_visual_elements():
    """Demo de elementos visuales"""
    cli = InteractiveCLI()
    
    cli.clear_screen()
    cli.print_header("DEMO - CLI INTERACTIVA")
    
    print(f"\n{Colors.OKCYAN}Este es un demo de los elementos visuales de la nueva CLI:{Colors.ENDC}")
    
    # Demo de mensajes
    time.sleep(1)
    cli.print_success("Mensaje de éxito - para confirmaciones")
    time.sleep(1)
    cli.print_warning("Mensaje de advertencia - para recordatorios")
    time.sleep(1)
    cli.print_error("Mensaje de error - para problemas")
    time.sleep(1)
    cli.print_info("Mensaje informativo - para ayuda")
    
    # Demo de barra de progreso
    print(f"\n{Colors.BOLD}Demo de barra de progreso:{Colors.ENDC}")
    for i in range(0, 101, 10):
        cli.show_progress(i, 100, f"Procesando archivo {i//10 + 1}")
        time.sleep(0.3)
    
    print(f"\n\n{Colors.OKGREEN}✨ Características de la CLI interactiva:{Colors.ENDC}")
    
    features = [
        "🎨 Interfaz colorida y amigable",
        "📋 Menús paso a paso",
        "🏦 Selección visual de bancos",
        "📊 Barra de progreso en tiempo real",
        "✅ Validación de entrada",
        "📁 Organización automática de archivos",
        "🔄 Opciones para repetir descargas",
        "🎯 Resumen claro antes de ejecutar"
    ]
    
    for feature in features:
        print(f"  {feature}")
        time.sleep(0.5)
    
    input(f"\n{Colors.BOLD}Presiona Enter para ver el menú principal...{Colors.ENDC}")


def demo_menu_flow():
    """Demo del flujo de menús"""
    cli = InteractiveCLI()
    
    cli.clear_screen()
    cli.print_header("FLUJO DE MENÚS - DEMO")
    
    print(f"\n{Colors.OKCYAN}Flujo típico de la aplicación:{Colors.ENDC}")
    
    steps = [
        "1. 🚀 Pantalla de bienvenida",
        "2. ⚙️  Configuración del período",
        "3. 🏦 Selección de bancos",
        "4. 📅 Selección de modo (trimestral/mensual)",
        "5. 📆 Selección de años",
        "6. 📋 Resumen de configuración",
        "7. 🔄 Descarga con progreso",
        "8. 🎉 Resultados y próximos pasos"
    ]
    
    for step in steps:
        print(f"\n  {Colors.OKBLUE}{step}{Colors.ENDC}")
        time.sleep(1)
    
    print(f"\n{Colors.WARNING}💡 En cada paso puedes:{Colors.ENDC}")
    print("  • Ver opciones numeradas")
    print("  • Obtener ayuda contextual")
    print("  • Validación automática de entrada")
    print("  • Cancelar con Ctrl+C")
    
    input(f"\n{Colors.BOLD}Presiona Enter para continuar...{Colors.ENDC}")


def show_usage_examples():
    """Mostrar ejemplos de uso"""
    cli = InteractiveCLI()
    
    cli.clear_screen()
    cli.print_header("EJEMPLOS DE USO")
    
    print(f"\n{Colors.BOLD}Cómo ejecutar la CLI interactiva:{Colors.ENDC}")
    
    examples = [
        ("🚀 CLI Interactiva Completa", "python cli_interactive.py"),
        ("⚡ CLI Simple (original)", "python cli_bank_scraper.py"),
        ("🛠️ Modo Batch", "python cli_bank_scraper.py --bank 001 --mode trimestral --last-period '07/2025'")
    ]
    
    for title, command in examples:
        print(f"\n{Colors.OKGREEN}{title}:{Colors.ENDC}")
        print(f"  {Colors.OKCYAN}$ {command}{Colors.ENDC}")
    
    print(f"\n{Colors.WARNING}📋 La CLI interactiva es ideal para:{Colors.ENDC}")
    print("  • Usuarios nuevos que necesitan guía")
    print("  • Configuración exploratoria")
    print("  • Descargas ocasionales")
    print("  • Ver todas las opciones disponibles")
    
    print(f"\n{Colors.WARNING}⚡ La CLI simple es mejor para:{Colors.ENDC}")
    print("  • Automatización y scripts")
    print("  • Usuarios experimentados")
    print("  • Descargas repetitivas")
    print("  • Integración con otros sistemas")
    
    input(f"\n{Colors.BOLD}Presiona Enter para terminar el demo...{Colors.ENDC}")


def main():
    """Ejecutar demo completo"""
    print(f"{Colors.HEADER}")
    print("=" * 60)
    print("🎬 DEMO - CLI INTERACTIVA PARA CMF BANK SCRAPER")  
    print("=" * 60)
    print(f"{Colors.ENDC}")
    
    print(f"\n{Colors.OKCYAN}Este demo muestra las nuevas características interactivas.{Colors.ENDC}")
    
    options = [
        "🎨 Ver elementos visuales",
        "📋 Ver flujo de menús", 
        "📖 Ver ejemplos de uso",
        "🚀 Ejecutar CLI interactiva real",
        "🚪 Salir"
    ]
    
    while True:
        print(f"\n{Colors.BOLD}¿Qué quieres ver?{Colors.ENDC}")
        for i, option in enumerate(options, 1):
            print(f"  {Colors.OKCYAN}{i}.{Colors.ENDC} {option}")
        
        try:
            choice = int(input(f"\n{Colors.BOLD}Selecciona (1-{len(options)}): {Colors.ENDC}").strip())
            
            if choice == 1:
                demo_visual_elements()
            elif choice == 2:
                demo_menu_flow()
            elif choice == 3:
                show_usage_examples()
            elif choice == 4:
                print(f"\n{Colors.OKGREEN}🚀 Ejecutando CLI interactiva real...{Colors.ENDC}")
                time.sleep(2)
                cli = InteractiveCLI()
                cli.run()
                break
            elif choice == 5:
                print(f"\n{Colors.OKCYAN}👋 ¡Gracias por probar la CLI interactiva!{Colors.ENDC}")
                break
            else:
                print(f"{Colors.FAIL}❌ Opción no válida{Colors.ENDC}")
                
        except (ValueError, KeyboardInterrupt):
            print(f"\n{Colors.WARNING}👋 Saliendo del demo...{Colors.ENDC}")
            break


if __name__ == "__main__":
    main()