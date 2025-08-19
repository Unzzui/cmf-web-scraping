#!/usr/bin/env python3
"""
Utilidades del sistema para el CMF Scraper
"""

import os
import sys
import subprocess
from typing import Optional


def open_folder(folder_path: str) -> bool:
    """
    Abrir carpeta en el explorador del sistema
    
    Args:
        folder_path: Ruta de la carpeta a abrir
        
    Returns:
        bool: True si se abrió correctamente, False en caso contrario
    """
    try:
        if not os.path.exists(folder_path):
            return False
        
        if sys.platform.startswith('linux'):
            subprocess.run(['xdg-open', folder_path], check=True)
        elif sys.platform.startswith('darwin'):  # macOS
            subprocess.run(['open', folder_path], check=True)
        elif sys.platform.startswith('win'):
            subprocess.run(['explorer', folder_path], check=True)
        else:
            return False
        
        return True
        
    except subprocess.CalledProcessError:
        return False
    except Exception:
        return False


def ensure_directory_exists(directory_path: str) -> bool:
    """
    Asegurar que un directorio existe, creándolo si es necesario
    
    Args:
        directory_path: Ruta del directorio
        
    Returns:
        bool: True si el directorio existe o se creó correctamente
    """
    try:
        os.makedirs(directory_path, exist_ok=True)
        return True
    except Exception:
        return False


def get_available_browsers() -> list:
    """Obtener lista de navegadores disponibles en el sistema"""
    browsers = []
    
    # Navegadores comunes por sistema
    if sys.platform.startswith('linux'):
        common_browsers = ['firefox', 'chromium-browser', 'google-chrome', 'opera']
    elif sys.platform.startswith('darwin'):
        common_browsers = ['firefox', 'google chrome', 'safari', 'opera']
    elif sys.platform.startswith('win'):
        common_browsers = ['firefox.exe', 'chrome.exe', 'msedge.exe', 'opera.exe']
    else:
        return browsers
    
    for browser in common_browsers:
        try:
            if sys.platform.startswith('win'):
                # En Windows, buscar en rutas comunes
                result = subprocess.run(['where', browser], 
                                      capture_output=True, text=True, check=True)
            else:
                # En Unix-like, usar which
                result = subprocess.run(['which', browser], 
                                      capture_output=True, text=True, check=True)
            
            if result.returncode == 0:
                browsers.append(browser)
        except subprocess.CalledProcessError:
            continue
        except Exception:
            continue
    
    return browsers


def get_system_info() -> dict:
    """Obtener información del sistema"""
    import platform
    
    return {
        'system': platform.system(),
        'platform': sys.platform,
        'architecture': platform.architecture(),
        'python_version': sys.version,
        'machine': platform.machine(),
        'processor': platform.processor() if hasattr(platform, 'processor') else 'Unknown'
    }


def validate_file_path(file_path: str, extensions: Optional[list] = None) -> bool:
    """
    Validar ruta de archivo
    
    Args:
        file_path: Ruta del archivo
        extensions: Lista de extensiones permitidas (ej: ['.csv', '.xlsx'])
        
    Returns:
        bool: True si el archivo es válido
    """
    if not file_path or not os.path.exists(file_path):
        return False
    
    if not os.path.isfile(file_path):
        return False
    
    if extensions:
        file_extension = os.path.splitext(file_path)[1].lower()
        if file_extension not in [ext.lower() for ext in extensions]:
            return False
    
    return True


class FileWatcher:
    """Observador simple de archivos"""
    
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.last_modified = None
        self._update_timestamp()
    
    def _update_timestamp(self):
        """Actualizar timestamp del archivo"""
        try:
            if os.path.exists(self.file_path):
                self.last_modified = os.path.getmtime(self.file_path)
        except Exception:
            self.last_modified = None
    
    def has_changed(self) -> bool:
        """Verificar si el archivo ha cambiado"""
        try:
            if not os.path.exists(self.file_path):
                return self.last_modified is not None
            
            current_modified = os.path.getmtime(self.file_path)
            changed = current_modified != self.last_modified
            
            if changed:
                self.last_modified = current_modified
            
            return changed
        except Exception:
            return False
