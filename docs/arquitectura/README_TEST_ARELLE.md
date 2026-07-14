# 🧪 Scripts de Prueba para Arelle con Columnas Extendidas

Este directorio contiene scripts para testear la funcionalidad de Arelle con columnas adicionales en el proyecto CMF_extract.

## 📋 Descripción

Los scripts permiten probar la extracción de datos XBRL usando Arelle con columnas extendidas que incluyen:

- `dimensions` - Información de dimensiones XBRL
- `segment` - Segmentos de negocio
- `scenario` - Escenarios de reporte

## 🚀 Scripts Disponibles

### 1. `test_arelle_extended_columns.py` - Script Completo

**Propósito**: Script independiente que replica la funcionalidad de `run_arelle_exports` con columnas extendidas.

**Características**:

- ✅ No modifica archivos originales
- ✅ Ejecuta Arelle directamente
- ✅ Genera output en directorio separado
- ✅ Logging detallado del proceso
- ✅ Manejo de errores robusto

**Uso**:

```bash
python test_arelle_extended_columns.py
```

**Output**: Archivos CSV en `data/XBRL/Total/91705000-7_QUIÑENCO_SA/Estados_financieros_(XBRL)91705000_202503_extracted/test_output_extended/`

### 2. `test_arelle_simple.py` - Script de Modificación Temporal

**Propósito**: Modifica temporalmente `batch_xbrl_to_excel.py` para usar columnas extendidas.

**Características**:

- ⚠️ Modifica temporalmente archivos originales
- ✅ Hace backup automático
- ✅ Restaura archivos al finalizar
- ✅ Usa el flujo completo del proyecto
- ✅ Procesa solo 1 archivo para testing

**Uso**:

```bash
python test_arelle_simple.py
```

**Output**: Usa el flujo normal del proyecto, genera archivos en las ubicaciones estándar.

## 🔧 Configuración Requerida

### Prerequisitos

- ✅ Arelle instalado en `~/Documents/Arelle`
- ✅ Archivo XBRL de QUIÑENCO SA disponible
- ✅ Python 3.7+ con dependencias del proyecto

### Estructura de Directorios

```
CMF_extract/
├── data/XBRL/Total/91705000-7_QUIÑENCO_SA/
│   └── Estados_financieros_(XBRL)91705000_202503_extracted/
│       └── 91705000_202503_C.xbrl  # Archivo a procesar
├── test_arelle_extended_columns.py
├── test_arelle_simple.py
└── README_TEST_ARELLE.md
```

## 📊 Columnas Configuradas

### Columnas Originales

```
Label,localName,contextRef,unitRef,Dec,Prec,Lang,Value,entityIdentifier,periodStart,periodEnd,instant,endInstant,qname
```

### Columnas Extendidas (Testing)

```
Label,localName,contextRef,unitRef,Dec,Prec,Lang,Value,entityIdentifier,periodStart,periodEnd,instant,endInstant,qname,dimensions,segment,scenario
```

## 🎯 Casos de Uso

### Caso 1: Testing Rápido

```bash
# Usar script independiente
python test_arelle_extended_columns.py
```

### Caso 2: Testing con Flujo Completo

```bash
# Usar script que modifica temporalmente
python test_arelle_simple.py
```

### Caso 3: Testing Manual

```bash
# Modificar manualmente batch_xbrl_to_excel.py
# Cambiar fact_cols en la función run_arelle_exports
# Ejecutar: python batch_xbrl_to_excel.py --base-dir data/XBRL/Total --arelle-dir ~/Documents/Arelle --langs es
```

## 🔍 Verificación de Resultados

### Archivos Generados

- `facts_91705000_202503_es.csv` - Facts con columnas extendidas
- `presentation_91705000_202503_es.csv` - Presentación
- `arelle_facts_es.log` - Log de extracción de facts
- `arelle_pre_es.log` - Log de extracción de presentación

### Verificación de Columnas

```bash
# Verificar que las columnas extendidas estén presentes
head -1 facts_91705000_202503_es.csv | tr ',' '\n' | nl
```

## ⚠️ Consideraciones Importantes

### Script Independiente (`test_arelle_extended_columns.py`)

- ✅ **Seguro**: No modifica archivos del proyecto
- ✅ **Aislado**: Output en directorio separado
- ✅ **Reutilizable**: Puede ejecutarse múltiples veces

### Script de Modificación (`test_arelle_simple.py`)

- ⚠️ **Modifica archivos**: Hace cambios temporales en `batch_xbrl_to_excel.py`
- ✅ **Backup automático**: Crea respaldo antes de modificar
- ✅ **Restauración automática**: Vuelve al estado original al finalizar
- ⚠️ **Interrupción**: Si se interrumpe, restaurar manualmente desde backup

## 🚨 Solución de Problemas

### Error: "Directorio de Arelle no encontrado"

```bash
# Verificar instalación de Arelle
ls -la ~/Documents/Arelle/
```

### Error: "Archivo XBRL no encontrado"

```bash
# Verificar que existe el archivo
ls -la data/XBRL/Total/91705000-7_QUIÑENCO_SA/Estados_financieros_\(XBRL\)91705000_202503_extracted/
```

### Error: "Columnas no encontradas"

```bash
# Verificar que batch_xbrl_to_excel.py tiene el formato esperado
grep -n "fact_cols" batch_xbrl_to_excel.py
```

### Restauración Manual (si es necesario)

```bash
# Si el script se interrumpió y no restauró automáticamente
cp batch_xbrl_to_excel.py.backup batch_xbrl_to_excel.py
```

## 📝 Logs y Debugging

### Habilitar Debug Detallado

```bash
# Para script independiente
X2E_DEBUG=1 python test_arelle_extended_columns.py

# Para script de modificación
X2E_DEBUG=1 python test_arelle_simple.py
```

### Ver Logs de Arelle

```bash
# Revisar logs generados
cat data/XBRL/Total/91705000-7_QUIÑENCO_SA/Estados_financieros_\(XBRL\)91705000_202503_extracted/test_output_extended/arelle_facts_es.log
```

## 🔄 Flujo de Testing Recomendado

1. **Primera ejecución**: Usar `test_arelle_extended_columns.py` para verificar que Arelle funciona
2. **Testing de integración**: Usar `test_arelle_simple.py` para verificar el flujo completo
3. **Validación**: Verificar que las columnas extendidas estén presentes en los CSVs generados
4. **Análisis**: Revisar si las columnas adicionales contienen datos útiles

## 📞 Soporte

Si encuentras problemas:

1. Verificar que Arelle esté instalado correctamente
2. Revisar los logs generados
3. Verificar que las rutas de archivos sean correctas
4. Usar el script independiente primero para aislar problemas
