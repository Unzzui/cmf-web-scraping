#!/usr/bin/env bash
# Respaldo incremental del pipeline FindataChile a Google Drive vía rclone.
#
# Qué respalda (configurable por env):
#   - data/XBRL              XBRL crudo descargado de la CMF (lo irreemplazable)
#   - cmf_extract/Products   Excel intermedios
#   - cmf_extract/Product_v1 Excel finales de análisis
#   - data/RUT_Chilean_Companies  CSV maestro de empresas
#
# Qué excluye: out_*/ (CSVs derivados de Arelle, regenerables), logs.
#
# Estrategia: `rclone sync` con --backup-dir → el remoto es un espejo, pero
# nada se borra jamás: lo que desaparece localmente se mueve a _papelera/<fecha>
# en el Drive. Con ~200 empresas el primer sync tarda; los siguientes son
# incrementales (solo lo nuevo/cambiado).
#
# Setup una sola vez:   rclone config   (crear remote "gdrive" tipo drive)
# Prueba sin subir:     ./scripts/backup_to_drive.sh --dry-run
#
# Env opcionales:
#   RCLONE_REMOTE   nombre del remote (default: gdrive)
#   BACKUP_ROOT     carpeta raíz en Drive (default: FindataChile_Backup)
#   HEALTHCHECK_URL si está definida, hace ping al terminar (healthchecks.io)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REMOTE="${RCLONE_REMOTE:-gdrive}"
ROOT="${BACKUP_ROOT:-FindataChile_Backup}"
STAMP="$(date +%Y-%m-%d_%H%M)"
LOG_DIR="${PROJECT_ROOT}/logs"
LOG_FILE="${LOG_DIR}/backup_${STAMP}.log"
EXTRA_FLAGS=("$@")   # p.ej. --dry-run

mkdir -p "$LOG_DIR"

if ! command -v rclone >/dev/null 2>&1; then
    echo "ERROR: rclone no está instalado (pacman -S rclone / apt install rclone)" >&2
    exit 3
fi
if ! rclone listremotes | grep -q "^${REMOTE}:$"; then
    echo "ERROR: remote '${REMOTE}:' no configurado. Corre: rclone config" >&2
    echo "       (tipo 'drive', dale el nombre '${REMOTE}')" >&2
    exit 3
fi

# dirs a respaldar: "ruta_local:subcarpeta_en_drive"
BACKUP_DIRS=(
    "data/XBRL:XBRL"
    "cmf_extract/Products:Products"
    "cmf_extract/Product_v1:Product_v1"
    "data/RUT_Chilean_Companies:RUT_Chilean_Companies"
)

COMMON_FLAGS=(
    --transfers 8
    --checkers 16
    --drive-chunk-size 64M
    --fast-list
    --exclude "out_*/**"
    --exclude "*.log"
    --exclude "venv/**"
    --exclude "__pycache__/**"
    --log-file "$LOG_FILE"
    --log-level INFO
    --stats-one-line
    --stats 60s
)

status=0
for entry in "${BACKUP_DIRS[@]}"; do
    local_dir="${PROJECT_ROOT}/${entry%%:*}"
    remote_sub="${entry##*:}"
    if [[ ! -d "$local_dir" ]]; then
        echo "AVISO: no existe ${local_dir}, se omite" | tee -a "$LOG_FILE"
        continue
    fi
    echo "Sync ${local_dir} -> ${REMOTE}:${ROOT}/${remote_sub}"
    if ! rclone sync "$local_dir" "${REMOTE}:${ROOT}/${remote_sub}" \
        --backup-dir "${REMOTE}:${ROOT}/_papelera/${STAMP}/${remote_sub}" \
        "${COMMON_FLAGS[@]}" "${EXTRA_FLAGS[@]}"; then
        echo "ERROR en sync de ${remote_sub} (ver ${LOG_FILE})" >&2
        status=1
    fi
done

# Retención de logs locales: conservar los últimos 30
ls -1t "${LOG_DIR}"/backup_*.log 2>/dev/null | tail -n +31 | xargs -r rm --

if [[ -n "${HEALTHCHECK_URL:-}" ]]; then
    if [[ $status -eq 0 ]]; then
        curl -fsS -m 10 --retry 3 "${HEALTHCHECK_URL}" >/dev/null || true
    else
        curl -fsS -m 10 --retry 3 "${HEALTHCHECK_URL}/fail" >/dev/null || true
    fi
fi

if [[ $status -eq 0 ]]; then
    echo "Respaldo OK (log: ${LOG_FILE})"
else
    echo "Respaldo con errores (log: ${LOG_FILE})" >&2
fi
exit $status
