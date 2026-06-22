# CMF Extract - Modo Combinado

## 📊 Descripción

El **Modo Combinado** permite generar informes Excel que combinan:

- **Datos anuales (Q4)**: Para análisis histórico y tendencias
- **Datos trimestrales recientes**: Para información actualizada
- **Agrupación de columnas**: Los trimestres se agrupan bajo cada año para mejor visualización
- **Ratios anuales + TTM**: Los ratios se calculan solo con datos anuales, con TTM en los últimos trimestres

## 🚀 Uso

### Opción 1: CLI Interactivo (Recomendado)

```bash
python cmf_cli.py
```

1. Selecciona **"Ambos (XBRL y luego análisis)"**
2. Selecciona **"Combinado (Total)"** como frecuencia
3. Configura el número de trimestres para TTM (por defecto: 2)
4. El sistema procesará automáticamente desde `data/XBRL/Total/`

### Opción 2: Script Directo

```bash
python generate_combined_from_total.py --langs es,en --workers 4
```

### Opción 3: Análisis Solo

```bash
python run_products_analysis.py --input-dir Products/Combinado --output-dir Product_v1/Combinado --frequency Combinado --langs es,en
```

## 📁 Estructura de Directorios

```
data/
├── XBRL/
│   ├── Anual/          # Datos anuales (Q4)
│   ├── Trimestral/     # Datos trimestrales (Q1-Q3)
│   └── Total/          # Datos combinados (anuales + trimestrales)
├── Products/
│   └── Combinado/      # Archivos Excel consolidados combinados
└── Product_v1/
    └── Combinado/      # Análisis final con fórmulas y ratios
```

## ⚙️ Configuración

### Variables de Entorno

```bash
# Activar modo combinado
export CMF_ANALYSIS_COMBINED=1
export X2E_COMBINED=1

# Configurar TTM (últimos N trimestres)
export CMF_COMBINED_TTM_LAST_N=2

# Mantener todas las fechas disponibles
export X2E_KEEP_ALL_DATES=1
```

### Configuración en CLI

El CLI configura automáticamente estas variables cuando seleccionas "Combinado".

## 🔧 Funcionalidades

### 1. Consolidación de Datos

- Combina datasets anuales y trimestrales desde `XBRL/Total/`
- Mantiene tanto años completos como trimestres individuales
- Ordena por año descendente (más reciente primero)

### 2. Agrupación de Columnas

- Los trimestres se agrupan bajo cada año en Excel
- Usa la funcionalidad de outline/grouping de Excel
- Permite expandir/colapsar trimestres por año

### 3. Cálculo de Ratios

- **Ratios anuales**: Solo con datos de Q4 (años completos)
- **TTM (Trailing Twelve Months)**: En los últimos N trimestres
- Configurable: `CMF_COMBINED_TTM_LAST_N`

### 4. Formato Excel

- Encabezados claros: `2024`, `2024Q1`, `2024Q2`, `2024Q3`, `2024Q4`
- Agrupación automática de columnas trimestrales
- Fórmulas que referencian solo columnas anuales

## 📋 Ejemplo de Salida

### Columnas Generadas

```
Concepto          | 2024 | 2024Q1 | 2024Q2 | 2024Q3 | 2024Q4 | 2023 | 2023Q1 | ...
------------------|------|--------|--------|--------|--------|------|--------|-----
Activo Total      | 1000 |  950   |  975   |  990   |  1000  | 900  |  850   | ...
Pasivo Total      |  600 |  570   |  580   |  590   |  600   | 540  |  510   | ...
```

### Agrupación en Excel

- **2024** (colapsado)
  - 2024Q1
  - 2024Q2
  - 2024Q3
  - 2024Q4
- **2023** (colapsado)
  - 2023Q1
  - 2023Q2
  - 2023Q3
  - 2023Q4

## 🧪 Pruebas

### Verificar Instalación

```bash
python test_combined_mode.py
```

### Verificar CLI

```bash
python test_cli_combined.py
```

## 🔍 Troubleshooting

### Error: "No se encontraron datasets"

- Verifica que `data/XBRL/Total/` contenga datasets
- Ejecuta primero: `python generate_combined_from_total.py`

### Error: "batch_xbrl_to_excel.py finalizó con código X"

- Revisa logs en `data/debug/xbrl_run.log`
- Verifica permisos y espacio en disco

### Error: "run_products_analysis finalizó con código X"

- Revisa logs en `data/debug/products_run.log`
- Verifica que los archivos de entrada existan

## 📚 Archivos Clave

- `batch_xbrl_to_excel.py`: Procesamiento XBRL → Excel
- `xbrl_to_excel.py`: Generación de Excel con agrupación
- `analisis_excel/bulk_processor.py`: Cálculo de ratios y TTM
- `run_products_analysis.py`: Análisis final y fórmulas
- `generate_combined_from_total.py`: Generación desde XBRL/Total
- `cmf_cli.py`: CLI interactivo

## 🎯 Casos de Uso

### Análisis Financiero

- **Histórico**: Datos anuales para tendencias
- **Actual**: Trimestres recientes para estado actual
- **Ratios**: Anuales para comparabilidad, TTM para actualidad

### Reporting

- **Interno**: Datos detallados con agrupación
- **Externo**: Resumen anual con TTM actualizado
- **Auditoría**: Trazabilidad completa de datos

### Trading/Inversión

- **Análisis técnico**: Series temporales completas
- **Fundamental**: Ratios anuales + TTM actualizado
- **Comparación**: Múltiples empresas en mismo formato

## 🤝 Contribución

Para reportar bugs o sugerir mejoras:

1. Verifica que el problema no esté en la configuración
2. Incluye logs relevantes de `data/debug/`
3. Describe el comportamiento esperado vs. actual
4. Incluye ejemplo de datos que causan el problema
