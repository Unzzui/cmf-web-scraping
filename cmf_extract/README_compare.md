# Script de Comparación XBRL vs Productos Finales

Este script compara los archivos XBRL disponibles con los productos finales generados para identificar qué empresas no tienen su análisis financiero completo.

## 🎯 Propósito

Identificar:

- ✅ Empresas que tienen datos XBRL pero NO tienen análisis financiero
- ⚠️ Empresas que tienen productos pero les faltan algunos períodos
- 🔍 Empresas que tienen productos pero NO están en XBRL
- 📊 Estadísticas completas de cobertura

## 🚀 Uso

### Ejecutar el script

```bash
python3 compare_xbrl_products.py
```

O si ya tiene permisos de ejecución:

```bash
./compare_xbrl_products.py
```

## 📁 Directorios analizados

### Origen XBRL

```
/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/
├── 90413000-1_COMPAÑIA_CERVECERIAS_UNIDAS_SA/
│   ├── Estados_financieros_(XBRL)90413000_202506_extracted/
│   ├── Estados_financieros_(XBRL)90413000_202509_extracted/
│   └── ...
├── 93834000-5_CENCOSUD_SA/
│   └── ...
└── ...
```

### Productos Finales

```
/home/unzzui/Documents/coding/CMF_extract/Product_v1/Total/
├── AGUAS ANDINAS SA - 61808000-5 - Análisis Financiero 2014-2025Q1 [ES].xlsx
├── CAP SA - 91297000-0 - Análisis Financiero 2014-2025Q1 [ES].xlsx
├── CENCOSUD SA - 93834000-5 - Análisis Financiero 2014-2025Q1 [ES].xlsx
└── ...
```

## 🔍 Funcionalidades

### 1. Extracción de información XBRL

- Identifica carpetas de empresas por RUT
- Extrae períodos disponibles de cada empresa
- Normaliza formatos de fechas (2014-2025Q1, 2024Q1, etc.)

### 2. Extracción de información de productos

- Parsea nombres de archivos Excel
- Extrae RUT, empresa y período
- Identifica idioma (ES/EN)

### 3. Comparación inteligente

- Empresas faltantes en productos
- Períodos faltantes por empresa
- Empresas solo en productos

### 4. Reporte detallado

- Estadísticas generales
- Lista de empresas faltantes
- Acciones recomendadas
- Exportación a CSV

## 📊 Ejemplo de salida

```
🔍 Iniciando comparación XBRL vs Productos Finales...
============================================================
🔍 Escaneando archivos XBRL en: /home/.../data/XBRL/Total
🔍 Escaneando productos finales en: /home/.../Product_v1/Total

================================================================================
📊 REPORTE DE COMPARACIÓN XBRL vs PRODUCTOS FINALES
================================================================================

📈 ESTADÍSTICAS GENERALES:
   Empresas en XBRL: 25
   Empresas en Productos: 23
   Empresas faltantes en productos: 2
   Empresas solo en productos: 0
   Empresas con períodos faltantes: 5

❌ EMPRESAS FALTANTES EN PRODUCTOS (2):
   Estas empresas tienen datos XBRL pero NO tienen análisis financiero generado:
------------------------------------------------------------
   📁 91041000-8
      Períodos XBRL disponibles: 2014-12, 2016-12, 2018-12, 2020-12, 2022-12, 2024-12

   📁 93834000-5
      Períodos XBRL disponibles: 2018-12, 2020-12, 2022-12, 2024-12

⚠️  EMPRESAS CON PERÍODOS FALTANTES (5):
   Estas empresas tienen productos pero les faltan algunos períodos:
------------------------------------------------------------
   📁 61808000-5
      Períodos en productos: 2014-2025Q1
      Períodos faltantes: 2024-06, 2024-09, 2024-12

🎯 ACCIONES RECOMENDADAS:
   1. Generar análisis financiero para 2 empresas faltantes
      - 91041000-8
      - 93834000-5
   2. Completar períodos faltantes para 5 empresas

💾 Reporte detallado guardado en: /home/.../reporte_comparacion_xbrl_productos.csv
```

## 📋 Archivo CSV generado

El script genera un archivo CSV con el siguiente formato:

| RUT        | Estado     | Períodos_XBRL                                   | Períodos_Productos | Períodos_Faltantes      | Acción_Requerida                     |
| ---------- | ---------- | ----------------------------------------------- | ------------------ | ----------------------- | ------------------------------------ |
| 91041000-8 | FALTANTE   | 2014-12;2016-12;2018-12;2020-12;2022-12;2024-12 |                    |                         | Generar análisis financiero completo |
| 61808000-5 | INCOMPLETO | 2014-12;2016-12;2018-12;2020-12;2022-12;2024-12 | 2014-2025Q1        | 2024-06;2024-09;2024-12 | Completar períodos faltantes         |

## 🎯 Casos de uso

### Caso 1: Empresa completamente faltante

- **Situación**: Empresa tiene datos XBRL pero NO tiene productos
- **Acción**: Generar análisis financiero completo
- **Ejemplo**: `91041000-8_VIÑA_SAN_PEDRO_TARAPACA_SA`

### Caso 2: Períodos faltantes

- **Situación**: Empresa tiene productos pero faltan algunos períodos
- **Acción**: Completar períodos faltantes
- **Ejemplo**: Faltan `2024-06`, `2024-09`, `2024-12` en AGUAS ANDINAS

### Caso 3: Empresa solo en productos

- **Situación**: Empresa tiene productos pero NO está en XBRL
- **Acción**: Verificar datos XBRL
- **Ejemplo**: Producto generado pero sin datos fuente

## 🔧 Requisitos

- Python 3.6+
- Acceso a directorios XBRL y Product_v1
- Permisos de lectura en ambos directorios
- Permisos de escritura para generar CSV

## 📝 Notas importantes

- **No modifica archivos**: Solo lee y compara
- **Backup automático**: No es necesario, solo genera reportes
- **Formato flexible**: Maneja diferentes formatos de períodos
- **Exportación CSV**: Para análisis posterior en Excel

## 🚨 Solución de problemas

### Error: "La ruta XBRL no existe"

Verifica que `/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/` exista.

### Error: "La ruta de productos no existe"

Verifica que `/home/unzzui/Documents/coding/CMF_extract/Product_v1/Total/` exista.

### No se encuentran empresas

Verifica que los directorios tengan la estructura esperada:

- XBRL: `RUT_NOMBRE_EMPRESA/Estados_financieros_(XBRL)RUT_PERIODO_extracted/`
- Productos: `NOMBRE - RUT - Análisis Financiero PERIODO [IDIOMA].xlsx`

## 💡 Consejos de uso

1. **Ejecutar regularmente**: Para mantener control de cobertura
2. **Revisar CSV**: Para análisis detallado en Excel
3. **Priorizar faltantes**: Empresas sin productos son prioridad alta
4. **Verificar períodos**: Completar períodos faltantes por empresa
