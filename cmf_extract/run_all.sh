#!/usr/bin/env bash
set -euo pipefail

# === Config por defecto (se puede override con flags) ===
CMF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARELLE_DIR="$HOME/Documents/Arelle"
BASE_DIR="$CMF_DIR/data/XBRL"
LANGS_CSV="es,en"     # es,en | es | en
MAX_DATASETS=0          # 0 = sin límite
CLEAN_PRODUCTS=false
DRY_RUN=false
FACTS_STRATEGY="es_only"   # es_only | both
WORKERS="auto"              # auto | N

usage() {
  cat <<USAGE
Uso: ./run_all.sh [opciones]

Opciones:
  --arelle-dir <path>     Directorio de Arelle (default: $ARELLE_DIR)
  --base-dir <path>       Raíz con carpetas por empresa (default: $BASE_DIR)
  --langs <csv>           Idiomas: es,en | es | en (default: $LANGS_CSV)
  --max <N>               Limitar número de datasets (default: $MAX_DATASETS)
  --clean-products        Limpia la carpeta Products antes de generar
  --dry-run               Solo listar sin ejecutar Arelle/Excel
  --facts-strategy <opt>  es_only (rápido) o both (exporta facts en ambos idiomas)
  --workers <N|auto>      Paralelismo (por defecto auto)
  -h|--help               Esta ayuda
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --arelle-dir) shift; ARELLE_DIR="${1:-$ARELLE_DIR}"; shift ;;
    --base-dir)   shift; BASE_DIR="${1:-$BASE_DIR}"; shift ;;
    --langs)      shift; LANGS_CSV="${1:-$LANGS_CSV}"; shift ;;
    --max)        shift; MAX_DATASETS="${1:-0}"; shift ;;
    --clean-products) CLEAN_PRODUCTS=true; shift ;;
    --dry-run)    DRY_RUN=true; shift ;;
    --facts-strategy) shift; FACTS_STRATEGY="${1:-$FACTS_STRATEGY}"; shift ;;
    --workers) shift; WORKERS="${1:-$WORKERS}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Opción desconocida: $1"; usage; exit 1 ;;
  esac
done

if [[ ! -d "$ARELLE_DIR" ]]; then
  echo "❌ ARELLE_DIR no existe: $ARELLE_DIR"; exit 1
fi

mkdir -p "$BASE_DIR"
mkdir -p "$CMF_DIR/Products"

if $CLEAN_PRODUCTS; then
  echo "Limpiando Products..."
  find "$CMF_DIR/Products" -type f -name 'estados_*.xlsx' -delete || true
fi

# Asegurar dependencia Excel
python -m pip install --user -q XlsxWriter >/dev/null 2>&1 || true

# Preparar flags
IFS=',' read -ra LANGS_ARR <<< "$LANGS_CSV"

CMD=( python "$CMF_DIR/batch_xbrl_to_excel.py"
      --base-dir "$BASE_DIR"
      --arelle-dir "$ARELLE_DIR"
)

if [[ ${#LANGS_ARR[@]} -gt 0 ]]; then
  CMD+=( --langs )
  for L in "${LANGS_ARR[@]}"; do CMD+=( "$L" ); done
fi

if [[ "$MAX_DATASETS" != "0" ]]; then
  CMD+=( --max "$MAX_DATASETS" )
fi

if $DRY_RUN; then
  CMD+=( --dry-run )
fi

echo "Ejecutando: ${CMD[*]}"
"${CMD[@]}"

echo
echo "Productos generados en: $CMF_DIR/Products"
ls -1 "$CMF_DIR/Products" || true


