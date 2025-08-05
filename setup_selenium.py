#!/usr/bin/env python3
"""
Script de configuración para ChromeDriver
Verifica e instala ChromeDriver si es necesario
"""

import os
import sys
import subprocess
import requests
import zipfile
import platform
from pathlib import Path

def check_chrome_installed():
    """Verificar si Chrome está instalado"""
    try:
        if platform.system() == "Linux":
            result = subprocess.run(["google-chrome", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return True
        elif platform.system() == "Windows":
            # Verificar rutas comunes de Chrome en Windows
            chrome_paths = [
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
            ]
            for path in chrome_paths:
                if os.path.exists(path):
                    return True
        elif platform.system() == "Darwin":  # macOS
            result = subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                return True
    except:
        pass
    return False

def check_chromedriver():
    """Verificar si ChromeDriver está en PATH"""
    try:
        result = subprocess.run(["chromedriver", "--version"], 
                              capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ ChromeDriver encontrado: {result.stdout.strip()}")
            return True
    except:
        pass
    return False

def install_chromedriver_linux():
    """Instalar ChromeDriver en Linux"""
    try:
        print("📦 Instalando ChromeDriver para Linux...")
        
        # Obtener versión de Chrome
        result = subprocess.run(["google-chrome", "--version"], 
                              capture_output=True, text=True)
        chrome_version = result.stdout.split()[2].split('.')[0]
        
        # Descargar ChromeDriver
        url = f"https://chromedriver.storage.googleapis.com/LATEST_RELEASE_{chrome_version}"
        response = requests.get(url)
        driver_version = response.text.strip()
        
        download_url = f"https://chromedriver.storage.googleapis.com/{driver_version}/chromedriver_linux64.zip"
        
        # Descargar y extraer
        print(f"📥 Descargando ChromeDriver {driver_version}...")
        response = requests.get(download_url)
        
        with open("chromedriver.zip", "wb") as f:
            f.write(response.content)
        
        with zipfile.ZipFile("chromedriver.zip", 'r') as zip_ref:
            zip_ref.extractall()
        
        # Mover a /usr/local/bin y dar permisos
        subprocess.run(["sudo", "mv", "chromedriver", "/usr/local/bin/"])
        subprocess.run(["sudo", "chmod", "+x", "/usr/local/bin/chromedriver"])
        
        # Limpiar
        os.remove("chromedriver.zip")
        
        print("✅ ChromeDriver instalado exitosamente")
        return True
        
    except Exception as e:
        print(f"❌ Error instalando ChromeDriver: {e}")
        return False

def setup_selenium_environment():
    """Configurar entorno para Selenium"""
    print("🔧 Configurando entorno para Selenium...")
    print("=" * 50)
    
    # Verificar Chrome
    if not check_chrome_installed():
        print("❌ Google Chrome no está instalado")
        print("📝 Instale Google Chrome desde: https://www.google.com/chrome/")
        return False
    else:
        print("✅ Google Chrome encontrado")
    
    # Verificar ChromeDriver
    if not check_chromedriver():
        print("⚠️  ChromeDriver no encontrado")
        
        if platform.system() == "Linux":
            if install_chromedriver_linux():
                return check_chromedriver()
        else:
            print("📝 Instale ChromeDriver manualmente:")
            print("   1. Descargue desde: https://chromedriver.chromium.org/")
            print("   2. Agregue ChromeDriver al PATH del sistema")
            return False
    else:
        print("✅ ChromeDriver configurado correctamente")
        return True

def main():
    """Función principal"""
    print("🚀 Configurador de Selenium para CMF Scraper")
    print("=" * 50)
    
    success = setup_selenium_environment()
    
    if success:
        print("\n🎉 Configuración completada exitosamente!")
        print("💡 Ahora puede ejecutar:")
        print("   python rut_chilean_companies.py")
        print("   python test_extractor.py")
    else:
        print("\n❌ Configuración incompleta")
        print("📖 Consulte la documentación para configuración manual")
    
    return success

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
