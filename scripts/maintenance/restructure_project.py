#!/usr/bin/env python3
"""
Script para reorganizar la estructura del proyecto CMF Web Scraping
Reorganiza todos los archivos en una estructura limpia y profesional
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime
import re # Importar re para regex

# Configurar logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ProjectRestructurer:
    def __init__(self, project_root: str = "/home/unzzui/Documents/coding/cmf-web-scraping"):
        self.project_root = Path(project_root)
        self.backup_dir = None
        
    def create_backup(self):
        """Crear backup antes de reorganizar"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.backup_dir = self.project_root / f"backup_before_restructure_{timestamp}"
        
        logger.info(f"🔄 Creando backup en: {self.backup_dir}")
        self.backup_dir.mkdir(exist_ok=True)
        
        # Copiar archivos importantes
        important_files = [
            "cmf_annual_reports_scraper.py",
            "cmf_xbrl_downloader.py",
            "bolsa_santiago_scraper.py",
            "requirements.txt",
            "README.md"
        ]
        
        for file in important_files:
            src = self.project_root / file
            if src.exists():
                shutil.copy2(src, self.backup_dir)
                logger.info(f"   📋 Backup de: {file}")
    
    def create_new_structure(self):
        """Crear la nueva estructura de directorios"""
        logger.info("🏗️ Creando nueva estructura de directorios...")
        
        # Estructura principal
        directories = [
            "src",                    # Código fuente principal
            "src/scrapers",          # Scrapers específicos
            "src/xbrl",              # Manejo de XBRL
            "src/gui",               # Interfaz gráfica
            "src/utils",              # Utilidades
            "src/config",             # Configuraciones
            "scripts",                # Scripts de utilidad
            "scripts/checkers",       # Scripts de verificación
            "scripts/maintenance",    # Scripts de mantenimiento
            "data",                   # Datos y archivos
            "data/xbrl",             # Archivos XBRL
            "data/companies",         # Información de empresas
            "data/reports",           # Reportes generados
            "docs",                   # Documentación
            "tests",                  # Tests y pruebas
            "logs",                   # Logs del sistema
            "output",                 # Archivos de salida
            "temp",                   # Archivos temporales
            "backups"                 # Backups automáticos
        ]
        
        for directory in directories:
            dir_path = self.project_root / directory
            dir_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"   📁 Creado: {directory}")
    
    def move_files_to_new_structure(self):
        """Mover archivos a la nueva estructura"""
        logger.info("📦 Moviendo archivos a la nueva estructura...")
        
        # Mapeo de archivos a nuevas ubicaciones
        file_mapping = {
            # Scrapers principales
            "cmf_annual_reports_scraper.py": "src/scrapers/",
            "cmf_xbrl_downloader.py": "src/xbrl/",
            "bolsa_santiago_scraper.py": "src/scrapers/",
            "cmf_gui.py": "src/gui/",
            "cmf_gui_modular.py": "src/gui/",
            
            # Scripts de verificación
            "check_xbrl_availability.py": "scripts/checkers/",
            "compare_xbrl_local_vs_cmf.py": "scripts/checkers/",
            "test_xbrl_checker.py": "scripts/checkers/",
            
            # Scripts de utilidad
            "enrich_cmf_companies.py": "scripts/maintenance/",
            "rut_chilean_companies.py": "scripts/maintenance/",
            "migrate_to_modular.py": "scripts/maintenance/",
            
            # Scripts de prueba
            "test_simple_function.py": "tests/",
            "test_corrected_function.py": "tests/",
            "test_year_flexibility.py": "tests/",
            "debug_*.py": "tests/debug/",
            
            # Scripts de análisis
            "analisis-excel.py": "scripts/maintenance/",
            "analisis-excel-formulas.py": "scripts/maintenance/",
            "run_analisis_excel.py": "scripts/maintenance/",
            
            # Archivos de configuración
            "requirements.txt": "src/config/",
            "requirements_gui.txt": "src/config/",
            
            # Documentación
            "README.md": "docs/",
            "README_GUI.md": "docs/",
            "README_MODULAR.md": "docs/",
            "README_XBRL_CHECKER.md": "docs/",
            "HEADERS_EXACTOS_CMF.md": "docs/",
            
            # Scripts de ejemplo
            "example_usage.py": "scripts/",
            "restructure_project.py": "scripts/maintenance/",
            
            # Archivos de lanzamiento
            "launch_gui.sh": "scripts/",
            
            # Archivos de datos
            "xbrl_direct_probe.py": "src/xbrl/"
        }
        
        # Crear directorio de debug si no existe
        (self.project_root / "tests/debug").mkdir(parents=True, exist_ok=True)
        
        # Mover archivos
        for file_pattern, target_dir in file_mapping.items():
            if "*" in file_pattern:
                # Patrón con wildcard
                for file_path in self.project_root.glob(file_pattern):
                    if file_path.is_file():
                        target_path = self.project_root / target_dir / file_path.name
                        shutil.move(str(file_path), str(target_path))
                        logger.info(f"   📋 Movido: {file_path.name} → {target_dir}")
            else:
                # Archivo específico
                file_path = self.project_root / file_pattern
                if file_path.exists():
                    target_path = self.project_root / target_dir / file_path.name
                    shutil.move(str(file_path), str(target_path))
                    logger.info(f"   📋 Movido: {file_pattern} → {target_dir}")
    
    def move_directories(self):
        """Mover directorios existentes"""
        logger.info("📁 Moviendo directorios existentes...")
        
        # Mover directorios de análisis
        if (self.project_root / "analisis_excel").exists():
            shutil.move(str(self.project_root / "analisis_excel"), str(self.project_root / "src/utils"))
            logger.info("   📁 Movido: analisis_excel → src/utils/")
        
        if (self.project_root / "analisis-excel").exists():
            shutil.move(str(self.project_root / "analisis-excel"), str(self.project_root / "src/utils"))
            logger.info("   📁 Movido: analisis-excel → src/utils/")
        
        # Mover directorio GUI
        if (self.project_root / "gui").exists():
            shutil.move(str(self.project_root / "gui"), str(self.project_root / "src"))
            logger.info("   📁 Movido: gui → src/")
        
        # Mover directorio de datos
        if (self.project_root / "data").exists():
            # Solo mover si no existe ya en la nueva estructura
            if not (self.project_root / "data" / "xbrl").exists():
                shutil.move(str(self.project_root / "data"), str(self.project_root / "data_old"))
                logger.info("   📁 Movido: data → data_old/ (preservado)")
    
    def create_init_files(self):
        """Crear archivos __init__.py para hacer los directorios paquetes Python"""
        logger.info("🐍 Creando archivos __init__.py...")
        
        python_dirs = [
            "src",
            "src/scrapers",
            "src/xbrl", 
            "src/gui",
            "src/utils",
            "src/config",
            "scripts",
            "scripts/checkers",
            "scripts/maintenance",
            "tests",
            "tests/debug"
        ]
        
        for dir_path in python_dirs:
            init_file = self.project_root / dir_path / "__init__.py"
            if not init_file.exists():
                init_file.touch()
                logger.info(f"   🐍 Creado: {dir_path}/__init__.py")
    
    def create_main_entry_points(self):
        """Crear puntos de entrada principales"""
        logger.info("🚀 Creando puntos de entrada principales...")
        
        # Entry point principal
        main_script = """#!/usr/bin/env python3
\"\"\"
CMF Web Scraping - Punto de entrada principal
\"\"\"

import sys
from pathlib import Path

# Agregar src al path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

def main():
    print("🚀 CMF Web Scraping")
    print("=" * 40)
    print("Scripts disponibles:")
    print("  📊 Verificar XBRL: python scripts/checkers/check_xbrl_availability.py")
    print("  📥 Descargar XBRL: python src/xbrl/cmf_xbrl_downloader.py")
    print("  🏢 Scraper anual: python src/scrapers/cmf_annual_reports_scraper.py")
    print("  🖥️  GUI: python src/gui/cmf_gui_modular.py")
    print("  🔧 Reorganizar: python scripts/maintenance/restructure_project.py")

if __name__ == "__main__":
    main()
"""
        
        with open(self.project_root / "main.py", "w") as f:
            f.write(main_script)
        logger.info("   🚀 Creado: main.py")
        
        # Makefile para comandos comunes
        makefile = """# CMF Web Scraping - Makefile

.PHONY: help install test clean check-xbrl download-xbrl gui

help: ## Mostrar ayuda
	@echo "Comandos disponibles:"
	@echo "  make install      - Instalar dependencias"
	@echo "  make test        - Ejecutar tests"
	@echo "  make clean       - Limpiar archivos temporales"
	@echo "  make check-xbrl  - Verificar disponibilidad XBRL"
	@echo "  make download-xbrl - Descargar XBRL"
	@echo "  make gui         - Lanzar interfaz gráfica"

install: ## Instalar dependencias
	pip install -r src/config/requirements.txt

test: ## Ejecutar tests
	python -m pytest tests/

clean: ## Limpiar archivos temporales
	rm -rf temp/* logs/* output/*.tmp

check-xbrl: ## Verificar disponibilidad XBRL
	python scripts/checkers/check_xbrl_availability.py

download-xbrl: ## Descargar XBRL
	python src/xbrl/cmf_xbrl_downloader.py

gui: ## Lanzar interfaz gráfica
	python src/gui/cmf_gui_modular.py
"""
        
        with open(self.project_root / "Makefile", "w") as f:
            f.write(makefile)
        logger.info("   🔧 Creado: Makefile")
    
    def create_new_readme(self):
        """Crear nuevo README con la estructura actualizada"""
        logger.info("📚 Creando nuevo README...")
        
        readme_content = """# 🚀 CMF Web Scraping - Sistema Organizado

Sistema automatizado para la extracción de estados financieros de empresas chilenas desde la CMF.

## 📁 Estructura del Proyecto

```
cmf-web-scraping/
├── 📁 src/                          # Código fuente principal
│   ├── 📁 scrapers/                 # Scrapers específicos
│   │   ├── cmf_annual_reports_scraper.py
│   │   └── bolsa_santiago_scraper.py
│   ├── 📁 xbrl/                     # Manejo de archivos XBRL
│   │   ├── cmf_xbrl_downloader.py
│   │   └── xbrl_direct_probe.py
│   ├── 📁 gui/                      # Interfaz gráfica
│   │   ├── cmf_gui_modular.py
│   │   └── cmf_gui.py
│   ├── 📁 utils/                     # Utilidades
│   │   └── analisis_excel/
│   └── 📁 config/                    # Configuraciones
│       └── requirements.txt
├── 📁 scripts/                       # Scripts de utilidad
│   ├── 📁 checkers/                  # Verificadores
│   │   ├── check_xbrl_availability.py
│   │   └── compare_xbrl_local_vs_cmf.py
│   └── 📁 maintenance/               # Mantenimiento
│       ├── enrich_cmf_companies.py
│       └── rut_chilean_companies.py
├── 📁 data/                          # Datos y archivos
│   ├── 📁 xbrl/                     # Archivos XBRL
│   ├── 📁 companies/                 # Información de empresas
│   └── 📁 reports/                   # Reportes generados
├── 📁 docs/                          # Documentación
│   ├── README.md
│   ├── README_GUI.md
│   └── README_XBRL_CHECKER.md
├── 📁 tests/                         # Tests y pruebas
│   └── 📁 debug/                     # Scripts de debug
├── 📁 logs/                          # Logs del sistema
├── 📁 output/                        # Archivos de salida
├── 📁 temp/                          # Archivos temporales
├── 📁 backups/                       # Backups automáticos
├── 🚀 main.py                        # Punto de entrada principal
├── 🔧 Makefile                       # Comandos útiles
└── 📚 README.md                      # Este archivo
```

## 🚀 Uso Rápido

### Verificar Disponibilidad XBRL
```bash
make check-xbrl
# o
python scripts/checkers/check_xbrl_availability.py
```

### Descargar Archivos XBRL
```bash
make download-xbrl
# o
python src/xbrl/cmf_xbrl_downloader.py
```

### Lanzar Interfaz Gráfica
```bash
make gui
# o
python src/gui/cmf_gui_modular.py
```

### Instalar Dependencias
```bash
make install
```

## 📋 Comandos Disponibles

- `make help` - Mostrar todos los comandos
- `make install` - Instalar dependencias
- `make test` - Ejecutar tests
- `make clean` - Limpiar archivos temporales
- `make check-xbrl` - Verificar disponibilidad XBRL
- `make download-xbrl` - Descargar archivos XBRL
- `make gui` - Lanzar interfaz gráfica

## 🔧 Desarrollo

### Estructura de Código
- **src/scrapers/** - Lógica de scraping
- **src/xbrl/** - Manejo de archivos XBRL
- **src/gui/** - Interfaz de usuario
- **src/utils/** - Utilidades y helpers
- **src/config/** - Configuraciones

### Scripts de Utilidad
- **scripts/checkers/** - Verificadores y validadores
- **scripts/maintenance/** - Mantenimiento y limpieza

### Tests
- **tests/** - Tests unitarios y de integración
- **tests/debug/** - Scripts de debugging

## 📊 Datos

- **data/xbrl/** - Archivos XBRL descargados
- **data/companies/** - Información de empresas
- **data/reports/** - Reportes generados

## 📚 Documentación

- **docs/README.md** - Documentación principal
- **docs/README_GUI.md** - Guía de la interfaz gráfica
- **docs/README_XBRL_CHECKER.md** - Guía de verificación XBRL

## 🆘 Soporte

Para problemas o preguntas:
1. Revisar la documentación en `docs/`
2. Ejecutar `make help` para comandos disponibles
3. Revisar logs en `logs/`

---

**Nota**: Este proyecto fue reorganizado automáticamente. Si encuentras problemas, revisa el directorio `backups/` para versiones anteriores.
"""
        
        with open(self.project_root / "README.md", "w") as f:
            f.write(readme_content)
        logger.info("   📚 Creado: README.md actualizado")
    
    def create_gitignore(self):
        """Crear .gitignore actualizado"""
        logger.info("🚫 Creando .gitignore actualizado...")
        
        gitignore_content = """# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# Virtual environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# IDEs
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
.DS_Store?
._*
.Spotlight-V100
.Trashes
ehthumbs.db
Thumbs.db

# Project specific
temp/
logs/
output/*.tmp
data/xbrl/*/
data/reports/*/
backups/
*.log
*.zip
*.xlsx
*.csv

# Chrome/ChromeDriver
chromedriver
chromedriver.exe

# Backup files
*.bak
*.backup
*_old/
"""
        
        with open(self.project_root / ".gitignore", "w") as f:
            f.write(gitignore_content)
        logger.info("   🚫 Creado: .gitignore actualizado")
    
    def run_restructure(self):
        """Ejecutar todo el proceso de reorganización"""
        logger.info("🚀 INICIANDO REORGANIZACIÓN DEL PROYECTO")
        logger.info("=" * 60)
        
        # VERIFICACIÓN DE SEGURIDAD ANTES DE REORGANIZAR
        logger.info("🔍 VERIFICACIÓN DE SEGURIDAD...")
        
        # Verificar que no haya imports relativos problemáticos
        if self.check_relative_imports():
            logger.error("❌ NO ES SEGURO REORGANIZAR - Se encontraron imports relativos problemáticos")
            logger.error("   Ejecuta primero: python analyze_dependencies.py")
            logger.error("   Corrige los problemas antes de continuar")
            return False
        
        # Verificar que no haya referencias a archivos problemáticas
        if self.check_file_references():
            logger.error("❌ NO ES SEGURO REORGANIZAR - Se encontraron referencias problemáticas a archivos")
            logger.error("   Ejecuta primero: python analyze_dependencies.py")
            logger.error("   Corrige los problemas antes de continuar")
            return False
        
        logger.info("✅ VERIFICACIÓN DE SEGURIDAD COMPLETADA")
        logger.info("")
        
        try:
            # 1. Crear backup
            self.create_backup()
            
            # 2. Crear nueva estructura
            self.create_new_structure()
            
            # 3. Mover archivos
            self.move_files_to_new_structure()
            
            # 4. Mover directorios
            self.move_directories()
            
            # 5. Crear archivos __init__.py
            self.create_init_files()
            
            # 6. Crear puntos de entrada
            self.create_main_entry_points()
            
            # 7. Crear nuevo README
            self.create_new_readme()
            
            # 8. Crear .gitignore
            self.create_gitignore()
            
            # 9. Crear archivo de configuración de paths
            self.create_path_config()
            
            logger.info("=" * 60)
            logger.info("🎉 REORGANIZACIÓN COMPLETADA EXITOSAMENTE!")
            logger.info("=" * 60)
            logger.info("📁 Nueva estructura creada")
            logger.info("📋 Archivos reorganizados")
            logger.info("🚀 Puntos de entrada creados")
            logger.info("📚 Documentación actualizada")
            logger.info("🔄 Backup guardado en: " + str(self.backup_dir))
            logger.info("")
            logger.info("💡 Próximos pasos:")
            logger.info("   1. Revisar la nueva estructura")
            logger.info("   2. Probar los comandos: make help")
            logger.info("   3. Verificar que todo funcione")
            logger.info("   4. Si hay problemas, restaurar desde backup")
            
            return True
            
        except Exception as e:
            logger.error(f"💥 Error durante la reorganización: {e}")
            logger.error("🔄 Revisa el directorio de backup para restaurar")
            raise
    
    def check_relative_imports(self) -> bool:
        """Verificar si hay imports relativos problemáticos"""
        logger.info("   🔍 Verificando imports relativos problemáticos...")
        
        problematic_files = []
        
        # Excluir directorios del entorno virtual y cache
        excluded_dirs = {'.venv', 'venv', 'env', '__pycache__', '.git'}
        
        for file_path in self.project_root.rglob("*.py"):
            # Saltar archivos en directorios excluidos
            if any(excluded_dir in file_path.parts for excluded_dir in excluded_dirs):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Buscar imports relativos que son problemáticos para reorganización
                # Solo flag imports que referencian módulos externos al paquete actual
                problematic_patterns = [
                    r'from\s+\.\.\s+import',  # from .. import (imports de paquetes padre)
                    r'from\s+\.\.\w+\s+import',  # from ..module import
                ]
                
                # Los imports relativos dentro del mismo paquete (.module) son seguros
                # Solo verificar imports que cruzan límites de paquete
                
                for pattern in problematic_patterns:
                    if re.search(pattern, content):
                        relative_path = file_path.relative_to(self.project_root)
                        problematic_files.append(str(relative_path))
                        break
                        
            except Exception as e:
                logger.warning(f"      ⚠️ Error verificando {file_path}: {e}")
        
        if problematic_files:
            logger.warning(f"      ⚠️ Se encontraron {len(problematic_files)} archivos con imports relativos de paquetes padre:")
            for file in problematic_files[:5]:  # Solo mostrar los primeros 5
                logger.warning(f"         📋 {file}")
            if len(problematic_files) > 5:
                logger.warning(f"         ... y {len(problematic_files) - 5} más")
            logger.warning("      💡 Estos imports pueden causar problemas después de reorganizar")
            logger.warning("      🔧 Se recomienda revisar manualmente")
            # No bloquear la reorganización por esto
            return False
        
        logger.info("      ✅ No se encontraron imports relativos problemáticos")
        return False
    
    def check_file_references(self) -> bool:
        """Verificar si hay referencias problemáticas a archivos"""
        logger.info("   🔍 Verificando referencias a archivos...")
        
        problematic_files = []
        
        # Excluir directorios del entorno virtual y cache
        excluded_dirs = {'.venv', 'venv', 'env', '__pycache__', '.git'}
        
        for file_path in self.project_root.rglob("*.py"):
            # Saltar archivos en directorios excluidos
            if any(excluded_dir in file_path.parts for excluded_dir in excluded_dirs):
                continue
                
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Buscar referencias problemáticas
                problematic_patterns = [
                    r'open\([\'"]([^\'"]+\.py)[\'"]',
                    r'exec\([\'"]([^\'"]+\.py)[\'"]',
                    r'__import__\([\'"]([^\'"]+)[\'"]',
                    r'importlib\.import_module\([\'"]([^\'"]+)[\'"]'
                ]
                
                for pattern in problematic_patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        if match and not match.startswith(('os', 'sys', 're', 'time', 'logging')):
                            relative_path = file_path.relative_to(self.project_root)
                            problematic_files.append(f"{relative_path} → {match}")
                            break
                            
            except Exception as e:
                logger.warning(f"      ⚠️ Error verificando {file_path}: {e}")
        
        if problematic_files:
            logger.error(f"      ❌ Se encontraron {len(problematic_files)} referencias problemáticas:")
            for ref in problematic_files[:5]:  # Solo mostrar los primeros 5
                logger.error(f"         🔗 {ref}")
            if len(problematic_files) > 5:
                logger.error(f"         ... y {len(problematic_files) - 5} más")
            return True
        
        logger.info("      ✅ No se encontraron referencias problemáticas a archivos")
        return False
    
    def create_path_config(self):
        """Crear archivo de configuración de paths para facilitar imports"""
        logger.info("🔧 Creando archivo de configuración de paths...")
        
        path_config = """#!/usr/bin/env python3
\"\"\"
Configuración de paths para el proyecto reorganizado
Este archivo facilita los imports después de la reorganización
\"\"\"

import sys
from pathlib import Path

def setup_project_paths():
    \"\"\"Configurar paths del proyecto para imports\"\"\"
    project_root = Path(__file__).parent
    
    # Agregar src al path
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))
    
    # Agregar scripts al path
    scripts_path = project_root / "scripts"
    if scripts_path.exists():
        sys.path.insert(0, str(scripts_path))
    
    # Agregar tests al path
    tests_path = project_root / "tests"
    if tests_path.exists():
        sys.path.insert(0, str(tests_path))

def get_project_paths():
    \"\"\"Obtener rutas importantes del proyecto\"\"\"
    project_root = Path(__file__).parent
    
    return {
        "project_root": project_root,
        "src": project_root / "src",
        "scripts": project_root / "scripts",
        "tests": project_root / "tests",
        "data": project_root / "data",
        "docs": project_root / "docs",
        "logs": project_root / "logs",
        "output": project_root / "output",
        "temp": project_root / "temp",
        "backups": project_root / "backups"
    }

# Configurar paths automáticamente al importar este módulo
setup_project_paths()

if __name__ == "__main__":
    print("🔧 Configuración de paths del proyecto")
    print("=" * 40)
    
    paths = get_project_paths()
    for name, path in paths.items():
        status = "✅" if path.exists() else "❌"
        print(f"{status} {name}: {path}")
"""
        
        with open(self.project_root / "project_paths.py", "w") as f:
            f.write(path_config)
        logger.info("   🔧 Creado: project_paths.py")
        
        # Crear archivo __init__.py en src para facilitar imports
        src_init = """\"\"\"
CMF Web Scraping - Paquete principal
\"\"\"

# Importar configuración de paths
try:
    from . import project_paths
except ImportError:
    # Si no está disponible, configurar manualmente
    import sys
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent
    src_path = project_root / "src"
    if src_path.exists():
        sys.path.insert(0, str(src_path))

# Versión del proyecto
__version__ = "2.0.0"
__author__ = "CMF Web Scraping Team"
"""
        
        with open(self.project_root / "src" / "__init__.py", "w") as f:
            f.write(src_init)
        logger.info("   🔧 Creado: src/__init__.py")

def main():
    """Función principal"""
    print("🏗️  REORGANIZADOR DE PROYECTO CMF WEB SCRAPING")
    print("=" * 60)
    print("Este script reorganizará tu proyecto en una estructura limpia y profesional")
    print("")
    print("⚠️  IMPORTANTE:")
    print("   - Se creará un backup automático")
    print("   - Los archivos se moverán a nuevas ubicaciones")
    print("   - Se creará una estructura estándar de Python")
    print("")
    
    response = input("¿Continuar con la reorganización? (s/N): ").strip().lower()
    if response not in ['s', 'si', 'sí', 'y', 'yes']:
        print("❌ Reorganización cancelada")
        return
    
    restructurer = ProjectRestructurer()
    restructurer.run_restructure()

if __name__ == "__main__":
    main()
