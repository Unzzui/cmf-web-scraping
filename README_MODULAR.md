# CMF Financial Data Scraper - Estructura Modular

## Descripción

Interfaz gráfica profesional modularizada para la extracción de datos financieros de la Comisión para el Mercado Financiero (CMF) de Chile.

## Estructura del Proyecto

```
cmf-web-scraping/
├── cmf_gui_modular.py          # Lanzador principal de la aplicación
├── cmf_gui.py                  # GUI original (mantenida por compatibilidad)
├── cmf_annual_reports_scraper.py  # Motor de scraping
├── gui/                        # Módulo GUI modularizado
│   ├── __init__.py
│   ├── main_window.py          # Ventana principal
│   ├── components/             # Componentes de la interfaz
│   │   ├── __init__.py
│   │   ├── company_table.py    # Tabla de empresas
│   │   ├── control_panel.py    # Panel de control
│   │   └── log_viewer.py       # Visor de logs
│   ├── styles/                 # Estilos y temas
│   │   ├── __init__.py
│   │   └── professional_theme.py  # Tema profesional
│   └── utils/                  # Utilidades
│       ├── __init__.py
│       ├── csv_manager.py      # Manejo de archivos CSV
│       └── system_utils.py     # Utilidades del sistema
└── data/                       # Datos y resultados
    ├── RUT_Chilean_Companies/  # Archivos CSV de empresas
    └── Reports/                # Reportes generados
```

## Ejecución

### Activar entorno virtual (si aplica)

```bash
# Si usas un entorno virtual, actívalo primero
source .venv/bin/activate  # En Linux/Mac
# o
.venv\Scripts\activate     # En Windows
```

### GUI Modular (Recomendada)

```bash
python cmf_gui_modular.py
```

### GUI Original (Compatibilidad)

```bash
python cmf_gui.py
```

## Características de la Versión Modular

### Ventajas

- **Arquitectura modular**: Código organizado en componentes reutilizables
- **Mantenimiento mejorado**: Fácil modificación y extensión
- **Separación de responsabilidades**: Cada módulo tiene una función específica
- **Diseño profesional**: Interfaz moderna sin emojis
- **Mejor gestión de errores**: Validaciones y manejo robusto de excepciones
- **Código más limpio**: Siguiendo principios de programación orientada a objetos

### Componentes Principales

#### 1. `main_window.py`

- Ventana principal de la aplicación
- Coordinación entre componentes
- Gestión del estado global

#### 2. `components/company_table.py`

- Tabla interactiva de empresas
- Búsqueda y filtrado
- Selección múltiple

#### 3. `components/control_panel.py`

- Panel de configuración de años
- Botones de control de ejecución
- Indicador de progreso

#### 4. `components/log_viewer.py`

- Visor de logs con timestamps
- Diferentes niveles de log
- Funciones de guardar y limpiar

#### 5. `styles/professional_theme.py`

- Configuración de estilos profesionales
- Colores y fuentes consistentes
- Temas adaptables

#### 6. `utils/csv_manager.py`

- Carga y validación de archivos CSV
- Limpieza de datos
- Gestión de errores

#### 7. `utils/system_utils.py`

- Funciones del sistema operativo
- Apertura de carpetas
- Utilidades multiplataforma

## Dependencias

### Módulos Python Requeridos

- `tkinter` (incluido con Python)
- `pandas` - Manejo de datos
- `selenium` - Automatización web
- `beautifulsoup4` - Parsing HTML
- `xlsxwriter` - Generación de Excel

### Instalación de Dependencias

#### Con entorno virtual (recomendado)

```bash
# Crear entorno virtual si no existe
python -m venv .venv

# Activar entorno virtual
source .venv/bin/activate  # Linux/Mac
# o
.venv\Scripts\activate     # Windows

# Instalar dependencias
pip install pandas selenium beautifulsoup4 xlsxwriter
```

#### Instalación global

```bash
pip install pandas selenium beautifulsoup4 xlsxwriter
```

## Configuración

### Archivo CSV de Empresas

El archivo debe contener las siguientes columnas:

- `Razón Social`: Nombre de la empresa
- `RUT`: RUT con formato
- `RUT_Sin_Guión`: RUT solo números
- `Anual (Diciembre)`: Información del reporte anual

### Rutas por Defecto

- CSV de empresas: `./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv`
- Reportes generados: `./data/Reports/`

## Uso de la Aplicación

### 1. Carga de Datos

- La aplicación carga automáticamente el CSV por defecto
- Use "Examinar" para seleccionar otro archivo
- Use "Recargar" para actualizar el archivo actual

### 2. Selección de Empresas

- Busque empresas por nombre o RUT
- Seleccione empresas individualmente haciendo clic
- Use "Seleccionar Todo" o "Limpiar Selección"

### 3. Configuración

- Configure el rango de años (desde/hasta)
- Seleccione el incremento (-1, -2, -3 años)

### 4. Ejecución

- Haga clic en "Iniciar Extracción"
- Monitoree el progreso en el log
- Use "Detener Proceso" si es necesario

### 5. Resultados

- Los archivos se guardan en `./data/Reports/`
- Use "Abrir Carpeta de Resultados" para ver los archivos

## Solución de Problemas

### Error de Entorno Virtual

Si la aplicación dice que faltan dependencias pero las tienes instaladas:

1. Verifica que el entorno virtual esté activado:

```bash
which python  # Debe mostrar la ruta del .venv
```

2. Si no está activado:

```bash
source .venv/bin/activate  # Linux/Mac
# o
.venv\Scripts\activate     # Windows
```

3. Verifica que los módulos estén instalados en el entorno:

```bash
pip list | grep -E "(pandas|selenium|beautifulsoup4|xlsxwriter)"
```

### Error de Columnas CSV

Asegúrese de que el CSV tenga las columnas requeridas:

- Razón Social
- RUT
- RUT_Sin_Guión

### Error de Dependencias

Instale los módulos faltantes:

```bash
pip install [módulo_faltante]
```

### Error de Scraper

Verifique que `cmf_annual_reports_scraper.py` esté en el mismo directorio.

## Desarrollo

### Agregar Nuevos Componentes

1. Cree un nuevo archivo en `gui/components/`
2. Implemente la clase del componente
3. Impórtelo en `main_window.py`
4. Intégrelo en la interfaz

### Modificar Estilos

Edite `gui/styles/professional_theme.py` para cambiar:

- Colores
- Fuentes
- Estilos de botones
- Temas

### Agregar Utilidades

Cree nuevas funciones en `gui/utils/` para:

- Manejo de archivos
- Validaciones
- Funciones del sistema

## Licencia

Este proyecto es para uso interno y análisis financiero corporativo.

## Soporte

Para problemas o mejoras, contacte al equipo de desarrollo.
