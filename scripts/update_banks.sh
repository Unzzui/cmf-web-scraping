#!/usr/bin/env bash
# Mantiene al dia la data de bancos (API oficial CMF) y regenera los Excel de analisis.
#
# Los bancos reportan MENSUAL, con algunas semanas de rezago. Esto ingiere una ventana
# reciente (para capturar el mes nuevo y eventuales revisiones de meses previos) y luego
# regenera los Excel. La ingesta es idempotente (upsert), asi que correrlo de mas no
# duplica nada y las corridas sin datos nuevos terminan rapido.
#
# Uso:
#   scripts/update_banks.sh                 # ventana por defecto (ultimos 4 meses)
#   MESES_ATRAS=6 scripts/update_banks.sh   # ventana mas amplia
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-.venv/bin/python}"
MESES_ATRAS="${MESES_ATRAS:-4}"

TO="$(date +%m/%Y)"
FROM="$(date -d "-${MESES_ATRAS} months" +%m/%Y)"

echo "[update_banks] $(date '+%F %T')  ingesta ${FROM} .. ${TO}"
"$PY" scripts/ingest_banks.py --from "$FROM" --to "$TO" --pause 0.3

echo "[update_banks] $(date '+%F %T')  regenerando Excel de todos los bancos"
"$PY" scripts/generate_bank_excel.py

echo "[update_banks] $(date '+%F %T')  listo"
