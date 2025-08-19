# CMF Web Scraping - Sistema de Extracción de Estados Financieros

## Descripción

Sistema automatizado para la extracción de estados financieros de empresas chilenas desde la Comisión para el Mercado Financiero (CMF). Utiliza tecnologías web modernas como Selenium y BeautifulSoup para proporcionar una solución robusta y eficiente para el análisis financiero y la investigación de mercado en Chile.

El proyecto incluye múltiples interfaces y herramientas especializadas para diferentes necesidades de usuario, desde interfaces gráficas profesionales hasta extractores automatizados en segundo plano.

## Características Principales

### Sistema Modular

- Arquitectura modular con componentes separados para mejor mantenibilidad
- Interfaces gráficas profesionales sin elementos distractivos
- Código organizado en módulos especializados (GUI, utilidades, estilos)

### Extracción Avanzada

- Scraping automatizado de estados financieros (Balance General, Estado de Resultados, Flujo de Efectivo)
- Detección automática de taxonomías IFRS disponibles
- Modo headless para operación en segundo plano sin interferencias
- Manejo robusto de errores y recuperación automática

### Procesamiento de Datos

- Generación de archivos Excel con formato profesional
- Preservación del orden jerárquico de conceptos contables
- Exportación múltiple (CSV y Excel)
- Validación automática de datos extraídos

### Herramientas Complementarias

- Extractor de listado completo de empresas chilenas
- Sistema de logging detallado para seguimiento de procesos
- Scripts de prueba y validación automatizada
- Configuración automática de dependencias

## Estructura del Proyecto

```
cmf-web-scraping/
├── cmf_gui_modular.py          # Lanzador de la aplicación GUI modular
├── cmf_gui.py                  # GUI original (compatibilidad)
├── cmf_annual_reports_scraper.py  # Motor principal de scraping
├── cmf_scraper_headless.py     # Versión sin ventana para segundo plano
├── rut_chilean_companies.py    # Extractor de empresas CMF
├── test_extractor.py           # Pruebas del extractor de empresas
├── test_cmf_scraper.py         # Pruebas del scraper principal
├── setup_selenium.py           # Configurador automático de ChromeDriver
├── validate_system.py          # Validador completo del sistema
├── gui/                        # Módulo GUI modularizado
│   ├── main_window.py          # Ventana principal
│   ├── components/             # Componentes de interfaz
│   ├── styles/                 # Estilos y temas profesionales
│   └── utils/                  # Utilidades del sistema
└── data/                       # Datos y resultados
    ├── RUT_Chilean_Companies/  # Listados de empresas
    └── Reports/                # Reportes financieros generados
```

## Requisitos del Sistema

### Software Requerido

- Python 3.7 o superior
- Google Chrome instalado
- ChromeDriver (configuración automática disponible)

### Dependencias Python

```bash
selenium>=4.0.0
beautifulsoup4>=4.9.0
pandas>=1.3.0
xlsxwriter>=3.0.0
tkinter (incluido en Python estándar)
```

## Instalación

### Configuración Rápida

```bash
# Clonar el repositorio
git clone <url_repositorio>
cd cmf-web-scraping

# Instalar dependencias
pip install -r requirements.txt

# Configurar ChromeDriver automáticamente (Linux)
python setup_selenium.py

# Validar instalación completa
python validate_system.py
```

### Configuración Manual de ChromeDriver

Si la configuración automática falla:

**Linux:**

```bash
sudo apt-get install chromium-chromedriver
```

**Windows/Mac:**

- Descargar ChromeDriver desde: https://chromedriver.chromium.org/
- Agregar al PATH del sistema

## Uso del Sistema

### Interfaz Gráfica Modular (Recomendada)

```bash
python cmf_gui_modular.py
```

- Interfaz profesional sin elementos distractivos
- Selección persistente de empresas con filtros
- Monitoreo en tiempo real del proceso de extracción
- Gestión automatizada de archivos CSV de empresas

### Interfaz Gráfica Original

```bash
python cmf_gui.py
```

- Mantenida por compatibilidad
- Funcionalidad completa del sistema original

### Scraper en Modo Headless

```bash
python cmf_scraper_headless.py
```

- Operación silenciosa sin ventana de navegador
- Ideal para ejecución en segundo plano
- No interfiere con otras actividades del usuario
- Logging detallado en archivo separado

### Extractor de Empresas

```bash
# Extracción completa de empresas CMF
python rut_chilean_companies.py

# Prueba del extractor
python test_extractor.py
```

## Herramientas de Desarrollo

### Validación del Sistema

```bash
python validate_system.py
```

Ejecuta una verificación completa de:

- Dependencias instaladas
- Estructura del proyecto
- Módulos GUI
- Funcionalidad del extractor
- Integridad de datos

### Configuración de Selenium

```bash
python setup_selenium.py
```

- Detección automática de versión de Chrome
- Instalación automática de ChromeDriver (Linux)
- Guías de configuración manual para otros sistemas

### Scripts de Prueba

```bash
# Prueba rápida del extractor de empresas
python test_extractor.py

# Prueba completa del scraper principal
python test_cmf_scraper.py
```

## Ventajas del Modo Headless

### Operación Sin Interferencias

- No abre ventanas de navegador visibles
- Permite multitarea sin interrupciones
- Evita interferencias de mouse y teclado
- Operación más estable y confiable

### Eficiencia de Recursos

- Menor consumo de memoria RAM
- Reducción del uso de CPU
- Velocidad de procesamiento optimizada
- Ideal para servidores y automatización

### Casos de Uso Recomendados

- Extracción masiva de datos
- Procesamiento nocturno automatizado
- Integración con otros sistemas
- Operación en servidores remotos

## Arquitectura Técnica

### Componentes Principales

**Motor de Scraping:**

- Selenium WebDriver con opciones optimizadas
- BeautifulSoup para parsing HTML avanzado
- Detección automática de taxonomías IFRS
- Manejo de errores con reintentos automáticos

**Sistema de GUI:**

- Tkinter con temas profesionales personalizados
- Arquitectura de componentes modulares
- Gestión de estado persistente
- Integración fluida con motores de scraping

**Procesamiento de Datos:**

- Pandas para manipulación de datos estructurados
- XlsxWriter para generación de Excel con formato
- Validación automática de integridad de datos
- Preservación de jerarquías contables

### Flujo de Trabajo

1. **Selección de Empresas:** Interface gráfica o programática
2. **Configuración de Parámetros:** Años, tipos de estados, formatos
3. **Extracción Automatizada:** Navegación web automatizada
4. **Procesamiento de Datos:** Limpieza y estructuración
5. **Generación de Reportes:** Archivos Excel formateados
6. **Validación:** Verificación automática de integridad

## Formatos de Salida

### Archivos Excel

- Hojas separadas por tipo de estado financiero
- Formato profesional con colores y estilos
- Columnas ordenadas cronológicamente
- Preservación de categorías y subcategorías contables

### Archivos CSV

- Formato estándar para integración con otros sistemas
- Codificación UTF-8 para caracteres especiales
- Estructura tabular optimizada para análisis

### Logs Detallados

- Registro completo de operaciones realizadas
- Información de errores y recuperaciones
- Timestamps para auditoría de procesos
- Métricas de rendimiento y estadísticas

## Troubleshooting

### Problemas Comunes

**ChromeDriver no encontrado:**

```bash
python setup_selenium.py
```

**Error de dependencias:**

```bash
pip install -r requirements.txt --upgrade
```

**Problemas de conectividad:**

- Verificar conexión a internet
- Comprobar acceso a cmfchile.cl
- Revisar configuración de proxy si aplica

**Archivos no generados:**

- Verificar permisos de escritura en directorio ./data/
- Comprobar espacio disponible en disco
- Revisar logs para errores específicos

### Validación de Instalación

```bash
python validate_system.py
```

Este comando ejecuta una verificación completa y reporta cualquier problema de configuración.

## Contribución y Desarrollo

### Estructura de Contribución

- Fork del repositorio
- Crear branch específica para la feature
- Mantener consistencia con el estilo de código existente
- Incluir pruebas para nueva funcionalidad
- Documentar cambios en README

### Estándares de Código

- Comentarios en español para lógica de negocio
- Docstrings descriptivas para funciones públicas
- Manejo explícito de errores
- Logging apropiado para debugging

### Testing

- Ejecutar validate_system.py antes de commit
- Probar tanto modo GUI como headless
- Verificar compatibilidad con diferentes empresas
- Validar formatos de salida

## Contacto y Soporte

**Desarrollador:** Diego Bravo  
**Email:** diegobravobe@gmail.com  
**GitHub:** @Unzzui

### Reporte de Issues

- Incluir logs completos del error
- Especificar sistema operativo y versión de Python
- Detallar pasos para reproducir el problema
- Adjuntar archivos de configuración si es relevante

### Solicitudes de Features

- Describir caso de uso específico
- Proporcionar ejemplos de entrada y salida esperada
- Considerar impacto en rendimiento y compatibilidad
- Revisar documentación existente antes de solicitar
