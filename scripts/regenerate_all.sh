#!/usr/bin/env bash
# Regenera TODO el pipeline CMF y sube a Supabase en un solo comando.
#
# Pasos que ejecuta (via scripts/upload_to_supabase.py --full):
#   Fase 1: Consolidacion XBRL    (Arelle facts -> CSV consolidado)
#   Fase 2: Generacion Excel      (CSV consolidado -> Excel primario)
#   Fase 3: Analisis financiero   (Excel primario -> Excel analisis)
#   Fase 4: Export a CSV          (Excel analisis -> CSV TO_SQL)
#   Upload -> Supabase            (upsert line_items + financial_data)
#   Ratios -> financial_ratios    (recalculo de Liquidez/Solvencia/etc.)
#   DCF    -> dcf_analysis        (recalculo excel-aligned)
#
# Uso:
#   scripts/regenerate_all.sh                       # Todo, todas las empresas
#   scripts/regenerate_all.sh --only 61808000-5     # Solo AGUAS ANDINAS
#   scripts/regenerate_all.sh --dry-run             # Pipeline + diff sin tocar BD
#   scripts/regenerate_all.sh --skip-pipeline       # Solo regenerar CSV + upload
#                                                    (asume Excels ya estan al dia)
#
# Cualquier flag adicional se pasa tal cual a upload_to_supabase.py.

set -euo pipefail

# Localizar repo root (script vive en scripts/)
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Activar venv si existe (prioridad: .venv > venv)
if [[ -f ".venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source ".venv/bin/activate"
    PYTHON_BIN="$(command -v python)"
elif [[ -f "venv/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "venv/bin/activate"
    PYTHON_BIN="$(command -v python)"
else
    PYTHON_BIN="$(command -v python3)"
fi

echo "[regenerate_all] repo:   $REPO_ROOT"
echo "[regenerate_all] python: $PYTHON_BIN"

# Apuntar la pipeline CMF a los paths reales (la raiz del repo, no a
# cmf_extract/data) — sino el CompanyRegistry busca XBRL en el lugar
# equivocado y la pipeline se omite.
if [[ -d "data/XBRL/Total" && -z "${CMF_XBRL_BASE_DIR:-}" ]]; then
    export CMF_XBRL_BASE_DIR="$REPO_ROOT/data/XBRL/Total"
    echo "[regenerate_all] CMF_XBRL_BASE_DIR=$CMF_XBRL_BASE_DIR"
fi
if [[ -f "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv" && -z "${CMF_COMPANIES_CSV:-}" ]]; then
    export CMF_COMPANIES_CSV="$REPO_ROOT/data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
    echo "[regenerate_all] CMF_COMPANIES_CSV=$CMF_COMPANIES_CSV"
fi

# Modo por defecto: pipeline completa + upload + ratios + DCF (--full)
# --skip-pipeline cambia a "solo regenerar CSV desde Excels existentes + upload"
MODE_FLAG="--full"
EXTRA_ARGS=()
for arg in "$@"; do
    case "$arg" in
        --skip-pipeline)
            MODE_FLAG="--regenerate-csv --with-all"
            ;;
        *)
            EXTRA_ARGS+=("$arg")
            ;;
    esac
done

# shellcheck disable=SC2086
exec "$PYTHON_BIN" scripts/upload_to_supabase.py $MODE_FLAG "${EXTRA_ARGS[@]}"
