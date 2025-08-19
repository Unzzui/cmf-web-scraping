#!/usr/bin/env python3
"""
Lanzador rápido para CMF GUI Modular
Ejecuta la interfaz gráfica del scraper CMF de forma simple
"""

import os
import sys
import subprocess

def main():
    """Lanzar la GUI del CMF Scraper"""
    print("🚀 Lanzando CMF GUI Modular...")
    
    # Ruta al archivo principal
    gui_path = "src/gui/cmf_gui_modular.py"
    
    # Verificar que el archivo existe
    if not os.path.exists(gui_path):
        print(f"❌ Error: No se encontró {gui_path}")
        print("Asegúrate de estar en el directorio raíz del proyecto")
        return 1
    
    try:
        # Ejecutar el archivo
        print(f"📁 Ejecutando: {gui_path}")
        result = subprocess.run([sys.executable, gui_path], check=True)
        return result.returncode
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al ejecutar la GUI: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⏹️ Ejecución interrumpida por el usuario")
        return 0
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
