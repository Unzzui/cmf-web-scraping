# Script de Procesamiento de PDF de Estados Financieros

Este script procesa un PDF de Estados Financieros, detecta números junto a las etiquetas definidas en `cuentas.json`, y genera un archivo Excel donde coloca la fecha en lugar de los valores numéricos.

## Configuración

El script está configurado con rutas hardcodeadas:

- **PDF**: `/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/testeo_pdf/Estados_financieros_(PDF)91297000_202506-1.pdf`
- **Cuentas**: `/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/cuentas.json`
- **Directorio de salida**: `/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/testeo_pdf/output`
- **Período**: `30.06.2025`

## Uso

### Instalar dependencias

```bash
pip install -r requirements.txt
```

### Ejecutar el script

```bash
python script_pdf.py
```

## Funcionalidad

1. **Lectura de cuentas**: Lee el archivo `cuentas.json` que contiene el mapeo de etiquetas en español a inglés
2. **Procesamiento de PDF**: Extrae texto del PDF y lo convierte en líneas procesables
3. **Detección de valores**: Busca números junto a las etiquetas definidas
4. **Generación de Excel**: Crea un archivo Excel con tres hojas:
   - Balance
   - Estado de Resultados
   - Flujo de Efectivo

## Estructura del Excel

Cada hoja contiene las columnas:

- **Tipo**: Siempre "item"
- **Cuenta**: Etiqueta en español
- **Valor**: Fecha del período si se detectó un número, vacío si no

## Salida

El archivo se guarda en el directorio de salida con un timestamp en el nombre:
`estados_financieros_YYYYMMDD_HHMMSS.xlsx`

## Requisitos

- Python 3.8+
- PyMuPDF (fitz)
- pandas
- xlsxwriter
