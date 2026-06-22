# Análisis Excel Modularizado

## 📊 Descripción

Sistema modularizado para análisis financiero automatizado de archivos Excel con estados financieros. Permite procesar archivos individuales o múltiples archivos de manera masiva con análisis completo de ratios financieros.

## 🏗️ Estructura del Módulo

```
analisis-excel/
├── __init__.py              # Módulo principal
├── data_extractor.py        # Extracción de datos de Excel
├── ratio_calculator.py      # Cálculo de ratios financieros
├── formula_builder.py       # Construcción de fórmulas Excel
├── excel_formatter.py       # Formateo y estilizado
└── bulk_processor.py        # Procesamiento masivo
```

## 🚀 Instalación y Configuración

### Requisitos

```bash
pip install pandas openpyxl numpy
```

### Estructura de Archivos Esperada

Los archivos Excel deben contener las siguientes hojas:

- `Balance General`
- `Estado Resultados (Función)`
- `Flujo Efectivo`

## 💻 Uso

### 1. Archivo Único

```bash
# Análisis con fórmulas Excel (dinámico)
python run_analisis_excel.py --mode single --file archivo.xlsx

# Análisis con valores calculados (estático)
python run_analisis_excel.py --mode single --file archivo.xlsx --analysis-type values
```

### 2. Procesamiento Masivo

```bash
# Procesar todos los archivos de una carpeta
python run_analisis_excel.py --mode bulk --input-dir ./data/Reports --output-dir ./data/Analisis

# Con configuraciones específicas
python run_analisis_excel.py --mode bulk --input-dir ./data/Reports --workers 8 --analysis-type formulas
```

### 3. Uso Programático

```python
from analisis_excel import DataExtractor, RatioCalculator, BulkProcessor

# Archivo único
extractor = DataExtractor("mi_archivo.xlsx")
extractor.load_data()
financial_data = extractor.get_all_financial_data()

calculator = RatioCalculator(financial_data)
ratios = calculator.calculate_all_ratios()

# Procesamiento masivo
processor = BulkProcessor("./input", "./output")
stats = processor.process_bulk()
```

## 📊 Ratios Calculados

### Liquidez

- Liquidez Corriente
- Prueba Ácida
- Cash Ratio
- Capital de Trabajo

### Solvencia y Estructura

- Endeudamiento (D/E)
- Apalancamiento (D/A)
- Cobertura de Intereses
- Deuda / EBITDA
- Autonomía Financiera

### Rentabilidad

- Margen Bruto
- Margen Operativo (EBIT)
- Margen EBITDA
- Margen Neto
- ROE (Return on Equity)
- ROA (Return on Assets)

### Eficiencia Operativa

- Rotación de Activos
- Rotación de Inventarios
- Días de Inventario
- Rotación de Cuentas por Cobrar
- Período Promedio de Cobro
- Rotación de Cuentas por Pagar
- Período Promedio de Pago
- Ciclo de Conversión de Efectivo

### Flujos y Adicionales

- Conversión de Caja (CFO/Utilidad Neta)
- Free Cash Flow (CFO - CAPEX)
- AC / AT (Activo Corriente / Activo Total)
- PC / PT (Pasivo Corriente / Pasivo Total)

## 🎨 Características del Análisis

### Tipo "Formulas" (Recomendado)

- ✅ Fórmulas Excel dinámicas que referencian celdas originales
- ✅ Actualización automática si cambian los datos fuente
- ✅ Transparencia total en cálculos
- ✅ Incluye sección tooltip con explicaciones

### Tipo "Values"

- ✅ Valores calculados estáticamente
- ✅ Procesamiento más rápido
- ✅ Menor tamaño de archivo
- ✅ Ideal para análisis comparativo

### Formateo Visual

- 🎨 Colores por categoría de ratios
- 📊 Formateo condicional con escalas de color
- 📈 Barras de datos en columnas resumen
- 🔒 Paneles congelados para navegación fácil
- 📋 Sección tooltip con definiciones

## ⚡ Procesamiento Masivo

### Características

- 🚀 Procesamiento paralelo configurable
- 📊 Estadísticas detalladas del procesamiento
- 📋 Reporte de resumen automático
- 🔍 Logging completo
- ⚠️ Manejo robusto de errores

### Configuración

```python
# Configurar procesador masivo
processor = BulkProcessor(
    input_directory="./data/Reports",
    output_directory="./data/Analisis",
    max_workers=4  # Número de procesos paralelos
)

# Procesar archivos
stats = processor.process_bulk(
    analysis_type="formulas",  # o "values"
    file_pattern="*.xlsx"      # patrón de archivos
)

# Generar reporte
summary_file = processor.generate_summary_report()
```

## 📁 Estructura de Salida

```
output/
├── Empresa1_Analisis_Formulas.xlsx
├── Empresa2_Analisis_Formulas.xlsx
├── processing_summary.xlsx          # Reporte de resumen
└── bulk_processing.log              # Log del procesamiento
```

## 🔧 Personalización

### Agregar Nuevos Ratios

```python
# En ratio_calculator.py
def calculate_custom_ratios(self) -> Dict[str, pd.Series]:
    ratios = {}

    # Nuevo ratio personalizado
    ventas = self.income.get("Ventas", pd.Series(dtype=float))
    empleados = self.custom_data.get("Empleados", pd.Series(dtype=float))
    ratios["Ventas por Empleado"] = ventas.divide(empleados, fill_value=np.nan)

    return ratios
```

### Personalizar Formateo

```python
# En excel_formatter.py
self.custom_fills = {
    "MI_CATEGORIA": PatternFill("solid", fgColor="FF6B6B")
}
```

## 🚀 Migración desde Sistema Anterior

```bash
# Ejecutar script de migración
python migrate_to_modular.py
```

Este script:

- ✅ Procesa archivos existentes con el nuevo sistema
- ✅ Compara resultados con archivos anteriores
- ✅ Crea configuración de ejemplo
- ✅ Proporciona instrucciones detalladas

## 📊 Ventajas del Sistema Modularizado

### Mantenibilidad

- 🔧 Código organizado en módulos específicos
- 🧪 Fácil testing y depuración
- 📚 Documentación integrada
- ♻️ Reutilización de componentes

### Escalabilidad

- ⚡ Procesamiento paralelo eficiente
- 📈 Manejo de grandes volúmenes de datos
- 🔄 Procesamiento incremental
- 💾 Optimización de memoria

### Flexibilidad

- 🎯 Configuración por empresa/industria
- 📊 Ratios personalizables
- 🎨 Formateo adaptable
- 🔌 API extensible

## 🐛 Solución de Problemas

### Error: Import "analisis_excel" could not be resolved

```bash
# Asegúrate de estar en el directorio correcto
cd /ruta/al/proyecto

# Verificar estructura
ls -la analisis-excel/
```

### Error: No se encuentran conceptos en Excel

- ✅ Verificar nombres exactos de hojas: "Balance General", etc.
- ✅ Revisar nombres de conceptos en columna A
- ✅ Verificar formato de fechas en encabezados

### Rendimiento Lento en Procesamiento Masivo

```bash
# Reducir workers si hay problemas de memoria
python run_analisis_excel.py --mode bulk --workers 2

# Usar análisis por valores para mayor velocidad
python run_analisis_excel.py --mode bulk --analysis-type values
```

## 📚 Ejemplos Adicionales

### Análisis Comparativo

```python
from analisis_excel import RatioCalculator

# Cargar múltiples empresas
empresas_data = {}
for archivo in archivos_excel:
    extractor = DataExtractor(archivo)
    extractor.load_data()
    empresas_data[archivo] = extractor.get_all_financial_data()

# Comparar ratios específicos
for empresa, data in empresas_data.items():
    calculator = RatioCalculator(data)
    ratios = calculator.calculate_liquidity_ratios()
    print(f"{empresa}: Liquidez = {ratios['Liquidez Corriente'].mean():.2f}")
```

### Exportar a Otros Formatos

```python
# Exportar ratios a CSV para análisis estadístico
import pandas as pd

calculator = RatioCalculator(financial_data)
all_ratios = calculator.calculate_all_ratios()

# Convertir a DataFrame para análisis
df_ratios = pd.DataFrame()
for category, ratios in all_ratios.items():
    for ratio_name, series in ratios.items():
        df_ratios[f"{category}_{ratio_name}"] = series

df_ratios.to_csv("ratios_para_analisis.csv")
```

## 🤝 Contribuir

Para agregar nuevas funcionalidades:

1. 🔀 Fork del proyecto
2. 🌿 Crear rama feature
3. ✅ Agregar tests
4. 📝 Actualizar documentación
5. 🔄 Pull request

## 📝 Licencia

Proyecto de código abierto para análisis financiero automatizado.

---

**💡 Tip**: Comienza con el archivo de demostración para familiarizarte con el sistema antes de procesar archivos reales.
