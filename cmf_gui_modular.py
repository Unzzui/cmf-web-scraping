#!/usr/bin/env python3
"""
CMF Financial Data Scraper - Aplicación Principal
Lanzador para la interfaz gráfica modularizada
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox

# Agregar el directorio actual al path para importaciones
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from gui import CMFScraperGUI
except ImportError as e:
    print(f"Error importando la GUI: {e}")
    print("Asegúrate de que todos los módulos estén en su lugar.")
    sys.exit(1)


def check_dependencies():
    """Verificar dependencias requeridas"""
    required_modules = {
        'pandas': 'pandas',
        'selenium': 'selenium', 
        'beautifulsoup4': 'bs4',  # beautifulsoup4 se importa como bs4
        'xlsxwriter': 'xlsxwriter'
    }
    
    missing_modules = []
    
    for package_name, import_name in required_modules.items():
        try:
            __import__(import_name)
        except ImportError:
            missing_modules.append(package_name)
    
    if missing_modules:
        error_msg = (
            "Módulos faltantes detectados:\n\n" +
            "\n".join(f"• {module}" for module in missing_modules) +
            "\n\nInstale los módulos faltantes usando:\n" +
            f"pip install {' '.join(missing_modules)}"
        )
        
        # Intentar mostrar en GUI si está disponible
        try:
            root = tk.Tk()
            root.withdraw()  # Ocultar ventana principal
            messagebox.showerror("Dependencias faltantes", error_msg)
            root.destroy()
        except:
            # Fallback a consola
            print("ERROR: " + error_msg.replace('\n\n', '\n'))
        
        return False
    
    return True


def check_scraper_module():
    """Verificar que el módulo scraper esté disponible"""
    try:
        import cmf_annual_reports_scraper
        return True
    except ImportError:
        error_msg = (
            "No se encontró el módulo 'cmf_annual_reports_scraper.py'\n\n"
            "Asegúrese de que el archivo esté en el mismo directorio que esta aplicación."
        )
        
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Módulo scraper faltante", error_msg)
            root.destroy()
        except:
            print("ERROR: " + error_msg)
        
        return False


def main():
    """Función principal de la aplicación"""
    # Verificar dependencias
    if not check_dependencies():
        sys.exit(1)
    
    if not check_scraper_module():
        sys.exit(1)
    
    try:
        # Crear y ejecutar la aplicación
        root = tk.Tk()
        
        # Configurar ícono de la aplicación si existe
        icon_path = os.path.join(current_dir, 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
            except:
                pass  # Ignorar si no se puede cargar el ícono
        
        # Crear la aplicación
        app = CMFScraperGUI(root)
        
        # Centrar ventana en la pantalla
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        # Iniciar aplicación
        root.mainloop()
        
    except KeyboardInterrupt:
        print("\nAplicación interrumpida por el usuario.")
        sys.exit(0)
    except Exception as e:
        error_msg = f"Error inesperado al iniciar la aplicación:\n{str(e)}"
        
        try:
            messagebox.showerror("Error crítico", error_msg)
        except:
            print(f"ERROR CRÍTICO: {error_msg}")
        
        sys.exit(1)


if __name__ == "__main__":
    main()
