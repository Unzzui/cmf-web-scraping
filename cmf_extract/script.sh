#!/usr/bin/env bash
set -euo pipefail

# === CONFIGURACIÓN ===
ARELLE_DIR="$HOME/Documents/Arelle"
ZIP_PATH="/home/unzzui/Documents/coding/CMF_extract/data/Estados_financieros_(XBRL)91041000_202412.zip"
WORK_DIR="/home/unzzui/Documents/coding/CMF_extract/data"
CMF_DIR="/home/unzzui/Documents/coding/CMF_extract/"
STEM="91041000_202412"
OUT_DIR="$WORK_DIR/out_${STEM}"
XBRL_TO_EXCEL="/home/unzzui/Documents/coding/CMF_extract/xbrl_to_excel.py"

# === PREPARAR ===
mkdir -p "$OUT_DIR"

# 1) Descomprimir el ZIP
UNZIP_DIR="$WORK_DIR/xbrl_${STEM}"
unzip -o "$ZIP_PATH" -d "$UNZIP_DIR" >/dev/null

# 2) Detectar archivo .xbrl
XBRL_FILE="$UNZIP_DIR/${STEM}_C.xbrl"
if [[ ! -f "$XBRL_FILE" ]]; then
    XBRL_FILE="$(find "$UNZIP_DIR" -type f -name "*.xbrl" | head -n1 || true)"
fi
if [[ -z "${XBRL_FILE:-}" || ! -f "$XBRL_FILE" ]]; then
    echo "❌ No se encontró un archivo .xbrl en $UNZIP_DIR"
    exit 1
fi
echo "Usando XBRL: $XBRL_FILE"

# 3) Ejecutar Arelle (desde su carpeta)
cd "$ARELLE_DIR"
source .venv/bin/activate

# Exportar facts con tabla completa (factTable en lugar de facts) - VERSIÓN EN ESPAÑOL
python arelleCmdLine.py -f "$XBRL_FILE" --labelLang=es-CL --factTable "$OUT_DIR/facts_${STEM}_es.csv" --factTableCols "Label,localName,contextRef,unitRef,Dec,Prec,Lang,Value,entityIdentifier,periodStart,periodEnd,instant,endInstant,qname" --logFile "$OUT_DIR/arelle_facts_es.log"
python arelleCmdLine.py -f "$XBRL_FILE" --labelLang=es-CL --pre   "$OUT_DIR/presentation_${STEM}_es.csv" --logFile "$OUT_DIR/arelle_pre_es.log"

# Exportar facts con tabla completa (factTable en lugar de facts) - VERSIÓN EN INGLÉS
python arelleCmdLine.py -f "$XBRL_FILE" --labelLang=en --factTable "$OUT_DIR/facts_${STEM}_en.csv" --factTableCols "Label,localName,contextRef,unitRef,Dec,Prec,Lang,Value,entityIdentifier,periodStart,periodEnd,instant,endInstant,qname" --logFile "$OUT_DIR/arelle_facts_en.log"
python arelleCmdLine.py -f "$XBRL_FILE" --labelLang=en --pre   "$OUT_DIR/presentation_${STEM}_en.csv" --logFile "$OUT_DIR/arelle_pre_en.log"

# 4) Generar Excel final - AMBAS VERSIONES

cd "$CMF_DIR"
source .venv/bin/activate

# Generar versión en español
python "$XBRL_TO_EXCEL" "$OUT_DIR" "$STEM" "es"

# Generar versión en inglés  
python "$XBRL_TO_EXCEL" "$OUT_DIR" "$STEM" "en"

echo "✔ Listo - Versión Español: $OUT_DIR/estados_${STEM}_es.xlsx"
echo "✔ Listo - Versión Inglés: $OUT_DIR/estados_${STEM}_en.xlsx"
