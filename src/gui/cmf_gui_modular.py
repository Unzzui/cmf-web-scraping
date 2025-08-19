#!/usr/bin/env python3
"""
CMF Financial Data Scraper - Aplicación Principal
Lanzador para la interfaz gráfica modularizada
"""

import sys
import os
import tkinter as tk
from tkinter import messagebox
import logging

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s'
)
logger = logging.getLogger(__name__)

# Agregar el directorio raíz del proyecto al path para importaciones
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

# Verificar y corregir imports
def fix_imports():
    """Corregir imports para la nueva estructura del proyecto"""
    try:
        # Importar la GUI principal
        from src.gui.main_window import CMFScraperGUI
        logger.info("✅ GUI principal importada correctamente")
        return CMFScraperGUI
    except ImportError as e:
        logger.error(f"❌ Error importando la GUI: {e}")
        
        # Intentar importación alternativa
        try:
            sys.path.insert(0, os.path.join(project_root, 'src'))
            from gui.main_window import CMFScraperGUI
            logger.info("✅ GUI importada con path alternativo")
            return CMFScraperGUI
        except ImportError as e2:
            logger.error(f"❌ Error en importación alternativa: {e2}")
            return None

def check_dependencies():
    """Verificar dependencias requeridas"""
    logger.info("🔍 Verificando dependencias...")
    
    required_modules = {
        'pandas': 'pandas',
        'selenium': 'selenium', 
        'beautifulsoup4': 'bs4',
        'xlsxwriter': 'xlsxwriter',
        'requests': 'requests',
        'urllib3': 'urllib3'
    }
    
    missing_modules = []
    
    for package_name, import_name in required_modules.items():
        try:
            __import__(import_name)
            logger.info(f"✅ {package_name} disponible")
        except ImportError:
            missing_modules.append(package_name)
            logger.warning(f"⚠️ {package_name} no disponible")
    
    if missing_modules:
        error_msg = (
            "Módulos faltantes detectados:\n\n" +
            "\n".join(f"• {module}" for module in missing_modules) +
            "\n\nInstale los módulos faltantes usando:\n" +
            f"pip install {' '.join(missing_modules)}"
        )
        
        logger.error(f"❌ Dependencias faltantes: {missing_modules}")
        
        # Intentar mostrar en GUI si está disponible
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Dependencias faltantes", error_msg)
            root.destroy()
        except:
            print("ERROR: " + error_msg.replace('\n\n', '\n'))
        
        return False
    
    logger.info("✅ Todas las dependencias están disponibles")
    return True

def check_scraper_modules():
    """Verificar que los módulos scraper estén disponibles"""
    logger.info("🔍 Verificando módulos scraper...")
    
    missing_modules = []
    
    # Verificar módulo XBRL
    try:
        from src.xbrl.cmf_xbrl_downloader import download_cmf_xbrl
        logger.info("✅ Módulo XBRL disponible")
        
        # Verificar que la función funciona
        if callable(download_cmf_xbrl):
            logger.info("✅ Función download_cmf_xbrl disponible y ejecutable")
        else:
            logger.warning("⚠️ download_cmf_xbrl no es una función ejecutable")
            missing_modules.append("download_cmf_xbrl (no es función)")
            
    except ImportError as e:
        missing_modules.append("cmf_xbrl_downloader.py")
        logger.error(f"❌ Error importando módulo XBRL: {e}")
    except Exception as e:
        missing_modules.append(f"cmf_xbrl_downloader.py (error: {e})")
        logger.error(f"❌ Error inesperado con módulo XBRL: {e}")
    
    # Verificar otros módulos importantes
    try:
        from src.scrapers.bolsa_santiago_scraper import scrape_bolsa_santiago
        logger.info("✅ Módulo Bolsa Santiago disponible")
    except ImportError:
        logger.warning("⚠️ Módulo Bolsa Santiago no disponible (opcional)")
    
    if missing_modules:
        logger.error(f"❌ Módulos scraper faltantes: {', '.join(missing_modules)}")
        return False
    
    logger.info("✅ Todos los módulos scraper están disponibles")
    return True

def check_gui_components():
    """Verificar que todos los componentes de la GUI estén disponibles"""
    logger.info("🔍 Verificando componentes de la GUI...")
    
    try:
        # Verificar componentes principales
        from src.gui.components.company_table import CompanyTable
        from src.gui.components.control_panel import ControlPanel
        from src.gui.components.log_viewer import LogViewer
        from src.gui.components.progress_dialog import ProgressDialog
        from src.gui.components.xbrl_status_panel import XBRLStatusPanel
        from src.gui.components.xbrl_confirmation_dialog import XBRLConfirmationDialog
        
        # Verificar utilidades
        from src.gui.utils.csv_manager import CSVManager
        from src.gui.utils.system_utils import open_folder
        from src.gui.utils.console_dashboard import ConsoleXBRLDashboard
        
        # Verificar estilos
        from src.gui.styles.professional_theme import ProfessionalStyles, get_font_config, get_color_config
        
        logger.info("✅ Todos los componentes de la GUI están disponibles")
        return True
        
    except ImportError as e:
        logger.error(f"❌ Error importando componentes de la GUI: {e}")
        return False

def main():
    """Función principal de la aplicación"""
    logger.info("🚀 Iniciando CMF GUI Modular...")
    
    # Verificar dependencias
    if not check_dependencies():
        logger.error("❌ Falló la verificación de dependencias")
        sys.exit(1)
    
    # Verificar módulos scraper
    if not check_scraper_modules():
        logger.error("❌ Falló la verificación de módulos scraper")
        sys.exit(1)
    
    # Verificar componentes de la GUI
    if not check_gui_components():
        logger.error("❌ Falló la verificación de componentes de la GUI")
        sys.exit(1)
    
    # Obtener la clase GUI
    CMFScraperGUI = fix_imports()
    if not CMFScraperGUI:
        logger.error("❌ No se pudo importar la GUI principal")
        sys.exit(1)
    
    try:
        logger.info("🎨 Creando ventana principal...")
        
        # Crear y ejecutar la aplicación
        root = tk.Tk()
        root.title("CMF Financial Data Scraper - Professional Edition")
        
        # Configurar ícono de la aplicación si existe
        icon_path = os.path.join(current_dir, 'assets', 'icon.ico')
        if os.path.exists(icon_path):
            try:
                root.iconbitmap(icon_path)
                logger.info("✅ Ícono de aplicación cargado")
            except Exception as e:
                logger.warning(f"⚠️ No se pudo cargar el ícono: {e}")
        
        # Crear la aplicación
        logger.info("🔧 Inicializando GUI...")
        app = CMFScraperGUI(root)
        
        # Centrar ventana en la pantalla
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')
        
        logger.info("✅ GUI inicializada correctamente")
        logger.info("🚀 Iniciando aplicación...")
        
        # Iniciar aplicación
        root.mainloop()
        
    except KeyboardInterrupt:
        logger.info("⏹️ Aplicación interrumpida por el usuario")
        sys.exit(0)
    except Exception as e:
        error_msg = f"Error inesperado al iniciar la aplicación:\n{str(e)}"
        logger.error(f"❌ {error_msg}")
        
        try:
            messagebox.showerror("Error crítico", error_msg)
        except:
            print(f"ERROR CRÍTICO: {error_msg}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()
