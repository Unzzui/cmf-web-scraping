"""
Módulo GUI para CMF Financial Data Scraper
Interfaz profesional modular para extracción de datos financieros
"""

# En servidores headless no hay tkinter; el subpaquete .pipeline debe seguir
# siendo importable (lo usa run_pipeline_cli.py).
try:
    from .main_window import CMFScraperGUI
    from .components.xbrl_status_panel import XBRLStatusPanel
except ImportError:
    CMFScraperGUI = None
    XBRLStatusPanel = None

__version__ = "1.0.0"
__author__ = "CMF Scraper Team"

__all__ = ['CMFScraperGUI']
