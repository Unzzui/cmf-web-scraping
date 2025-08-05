# CMF Financial Data Scraper - GUI Interactiva 🏦

Una interfaz gráfica intuitiva para extraer datos financieros del sitio web de la CMF (Comisión para el Mercado Financiero) de Chile.

## 🌟 Características

- **Interfaz Gráfica Intuitiva**: Fácil de usar con tkinter
- **Selección de Empresas**: Carga automática desde archivo CSV
- **Búsqueda y Filtrado**: Encuentra empresas rápidamente
- **Configuración Flexible**: Ajusta años y períodos de extracción
- **Monitoreo en Tiempo Real**: Log de progreso y estado
- **Procesamiento en Lotes**: Selecciona múltiples empresas
- **Resultados Organizados**: Archivos Excel con formato jerárquico

## 🚀 Inicio Rápido

### Método 1: Script Automático (Recomendado)

```bash
./launch_gui.sh
```

### Método 2: Manual

```bash
# Instalar dependencias
pip3 install -r requirements_gui.txt

# Ejecutar GUI
python3 cmf_gui.py
```

## 📁 Estructura de Archivos

```
cmf-web-scraping/
├── cmf_gui.py                      # Interfaz gráfica principal
├── cmf_annual_reports_scraper.py   # Motor de scraping
├── launch_gui.sh                   # Script de inicio automático
├── requirements_gui.txt            # Dependencias
├── data/
│   ├── RUT_Chilean_Companies/
│   │   └── RUT_Chilean_Companies.csv  # Base de datos de empresas
│   └── Reports/                       # Archivos Excel generados
└── README_GUI.md                   # Esta documentación
```

## 🔧 Uso de la Interfaz

### 1. Cargar Archivo de Empresas

- La GUI carga automáticamente `data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv`
- También puedes examinar y cargar otro archivo CSV
- El archivo debe tener las columnas: `Razón Social`, `RUT`, `RUT_Sin_Guión`

### 2. Seleccionar Empresas

- **Búsqueda**: Usa el campo de búsqueda para filtrar empresas
- **Selección Individual**: Haz clic en las empresas para seleccionarlas (☐ → ☑️)
- **Selección Masiva**: Usa "Seleccionar Todo" o "Deseleccionar Todo"
- **Teclado**: Usa la tecla `Espacio` para alternar selección

### 3. Configurar Parámetros

- **Año Inicial**: Año de inicio (ej: 2024)
- **Año Final**: Año de finalización (ej: 2014)
- **Incremento**: Paso entre años (ej: -2 para cada 2 años)

### 4. Ejecutar Scraping

- Haz clic en "▶️ Iniciar Scraping"
- Monitorea el progreso en el log en tiempo real
- Los resultados se guardan en `data/Reports/`

### 5. Gestionar Resultados

- Usa "📁 Abrir Carpeta de Resultados" para ver los archivos generados
- Cada empresa genera un archivo Excel con formato jerárquico

## 📊 Formato de Salida

Los archivos Excel incluyen:

### Hojas Generadas

- **Balance General** ([210000]): Estado de situación financiera
- **Estado Resultados** ([320000]): Estado del resultado por naturaleza
- **Flujo Efectivo** ([510000]): Estado de flujos de efectivo método directo

### Formato Jerárquico

- **Categorías [sinopsis]**: Fondo azul, texto en negrita
- **Subcategorías**: Indentación visual, formato estándar
- **Valores Numéricos**: Formato de miles con separadores

## 🎨 Características de la Interfaz

### Secciones Principales

1. **📁 Archivo de Empresas**

   - Cargar y recargar archivos CSV
   - Información del archivo cargado

2. **🏢 Selección de Empresas**

   - Lista filtrable de empresas
   - Selección múltiple con checkboxes visuales
   - Información de empresa (RUT, fechas anuales)

3. **⚙️ Configuración**

   - Parámetros de extracción de años
   - Configuración de incrementos

4. **🚀 Ejecución**

   - Botones de control (Iniciar/Detener)
   - Barra de progreso
   - Información de estado

5. **📝 Log de Ejecución**
   - Monitoreo en tiempo real
   - Mensajes de error y éxito
   - Scroll automático

### Indicadores Visuales

- ☐ / ☑️ : Estado de selección de empresas
- 🔍 : Campo de búsqueda
- ✅ : Operaciones exitosas
- ❌ : Errores
- ⏳ : Procesos en curso
- 📁 : Archivos y carpetas

## 🔄 Estados del Proceso

1. **Listo**: GUI cargada, esperando selección
2. **Configurado**: Empresas seleccionadas, listo para iniciar
3. **Ejecutando**: Scraping en proceso, UI bloqueada parcialmente
4. **Completado**: Proceso terminado, resultados disponibles
5. **Detenido**: Proceso interrumpido por el usuario

## 🛠️ Solución de Problemas

### Error: "tkinter no disponible"

```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# CentOS/RHEL
sudo yum install tkinter

# Arch Linux
sudo pacman -S tk
```

### Error: "Archivo CSV no encontrado"

- Asegúrate de que `data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv` existe
- O usa "Examinar..." para cargar otro archivo

### Error: "Chrome driver no encontrado"

- Asegúrate de tener Chrome/Chromium instalado
- El driver se descarga automáticamente con Selenium 4+

### Rendimiento Lento

- Reduce el número de empresas seleccionadas
- Usa incrementos mayores (ej: -3 en lugar de -1)
- Verifica la conexión a internet

## 📝 Logs y Debugging

Los logs incluyen:

- Timestamps de cada operación
- Progreso de cada empresa
- Errores detallados
- Estadísticas de categorías detectadas
- Archivos generados

## 🤝 Contribuir

1. Fork el repositorio
2. Crea una rama para tu feature
3. Realiza tus cambios
4. Envía un Pull Request

## 📄 Licencia

Este proyecto está bajo la licencia MIT. Ver archivo LICENSE para más detalles.

## 🆘 Soporte

Para reportar bugs o solicitar features:

1. Abre un Issue en GitHub
2. Incluye logs relevantes
3. Describe el comportamiento esperado vs actual

---

**¡Disfruta extrayendo datos financieros de manera fácil e intuitiva! 🚀**
