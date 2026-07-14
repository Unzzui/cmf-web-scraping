# Script de Sincronización XBRL

Este script sincroniza archivos y carpetas XBRL desde el directorio de origen (`cmf-web-scraping`) al directorio de destino (`CMF_extract`).

## Características

- ✅ **Identificación inteligente**: Detecta archivos, carpetas principales y subcarpetas
- 🔄 **Comparación de contenido**: Verifica si los archivos son idénticos antes de sobrescribir
- 💾 **Sistema de backup**: Crea copias de seguridad antes de sobrescribir archivos
- 📊 **Resumen detallado**: Muestra estadísticas de archivos y carpetas
- 🎯 **Control granular**: Permite decidir qué copiar, sobrescribir o eliminar

## Uso

### Ejecutar el script

```bash
python3 sync_xbrl_data.py
```

O si ya tiene permisos de ejecución:

```bash
./sync_xbrl_data.py
```

### Flujo de trabajo

1. **Confirmación inicial**: El script pide confirmación antes de proceder
2. **Escaneo**: Analiza ambos directorios (origen y destino)
3. **Resumen**: Muestra estadísticas de archivos y carpetas
4. **Carpetas principales nuevas**: Pregunta si copiar carpetas principales completas
5. **Subcarpetas nuevas**: Pregunta si copiar subcarpetas individuales
6. **Archivos nuevos**: Copia archivos que no existen en destino
7. **Archivos existentes**: Pregunta si sobrescribir archivos diferentes
8. **Limpieza**: Pregunta si eliminar archivos/carpetas solo en destino

## Estructura de directorios

### Origen

```
/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total/
├── 90413000-1_COMPAÑIA_CERVECERIAS_UNIDAS_SA/
│   ├── Estados_financieros_(XBRL)90413000_202506_extracted/
│   ├── Estados_financieros_(XBRL)90413000_202509_extracted/
│   └── ...
├── 93834000-5_CENCOSUD_SA/
│   └── ...
└── ...
```

### Destino

```
/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/
├── 90413000-1_COMPAÑIA_CERVECERIAS_UNIDAS_SA/
│   ├── Estados_financieros_(XBRL)90413000_202506_extracted/
│   └── ...
├── 93834000-5_CENCOSUD_SA/
│   └── ...
└── ...
```

## Ejemplos de uso

### Caso 1: Nueva carpeta principal

Si en origen tienes `91041000-8_VIÑA_SAN_PEDRO_TARAPACA_SA/` y no existe en destino:

- El script la identificará como "carpeta principal nueva"
- Preguntará si quieres copiarla completa con todo su contenido

### Caso 2: Nueva subcarpeta

Si en origen tienes `Estados_financieros_(XBRL)90749000_202509_extracted/` dentro de una carpeta existente:

- El script la identificará como "subcarpeta nueva"
- Preguntará si quieres copiarla individualmente

### Caso 3: Archivos diferentes

Si un archivo existe en ambos directorios pero con contenido diferente:

- El script lo identificará como "archivo diferente"
- Preguntará si quieres sobrescribirlo (con backup automático)

## Respuestas esperadas

Para todas las preguntas del script, puedes responder:

- `s`, `si`, `sí`, `y`, `yes` → **Sí, proceder**
- `n`, `no` → **No, omitir**

## Archivos de backup

Los archivos sobrescritos se respaldan automáticamente en:

```
/home/unzzui/Documents/coding/CMF_extract/data/backup_sync/
```

## Requisitos

- Python 3.6+
- Permisos de lectura en el directorio origen
- Permisos de escritura en el directorio destino
- Espacio suficiente para backups

## Seguridad

- ✅ **No elimina sin confirmación**: Siempre pregunta antes de eliminar
- ✅ **Backup automático**: Crea copias antes de sobrescribir
- ✅ **Verificación de rutas**: Valida que existan los directorios
- ✅ **Manejo de errores**: Continúa procesando aunque falle un archivo

## Solución de problemas

### Error: "La ruta de origen no existe"

Verifica que la ruta `/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total/` exista.

### Error: "La ruta de destino no existe"

Verifica que la ruta `/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/` exista.

### Error de permisos

Asegúrate de tener permisos de lectura en origen y escritura en destino.

## Notas importantes

- El script **NO** modifica el directorio origen
- Los backups se crean automáticamente antes de sobrescribir
- Puedes interrumpir el proceso en cualquier momento con `Ctrl+C`
- El script mantiene la estructura de directorios original
