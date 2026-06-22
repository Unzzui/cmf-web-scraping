#!/usr/bin/env bash
set -euo pipefail

# Simple launcher for the EEFF structure editor server
# Usage: bash run_editor.sh [--host 127.0.0.1] [--port 3000]

HOST="127.0.0.1"
PORT="3000"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--host) HOST="$2"; shift 2;;
    -p|--port) PORT="$2"; shift 2;;
    *) echo "Unknown arg: $1" >&2; exit 2;;
  esac
done

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$ROOT_DIR/analisis_excel"
SERVER="$APP_DIR/editor_server.py"

if [[ ! -f "$SERVER" ]]; then
  echo "Server not found: $SERVER" >&2
  exit 1
fi

PY_BIN="python3"
command -v python3 >/dev/null 2>&1 || PY_BIN="python"

echo "Starting editor server on http://$HOST:$PORT ..."

cd "$APP_DIR"

"$PY_BIN" "$SERVER" --host "$HOST" --port "$PORT" &
PID=$!

cleanup(){
  if kill -0 "$PID" >/dev/null 2>&1; then
    echo "\nShutting down server (PID $PID)..."
    kill "$PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup INT TERM EXIT

INFO_FILE="$APP_DIR/.editor_server_info.json"

# Esperar a que el servidor escriba el archivo de info (máx 5s)
for i in {1..50}; do
  if [[ -f "$INFO_FILE" ]]; then
    break
  fi
  sleep 0.1
done

if [[ -f "$INFO_FILE" ]]; then
  mapfile -t URLS < <( "$PY_BIN" -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('url','')); print(d.get('api',''))" "$INFO_FILE" 2>/dev/null || true )
  EDITOR_URL="${URLS[0]:-}"
  API_URL="${URLS[1]:-}"
  if [[ -n "$EDITOR_URL" ]]; then
    echo "Editor available at: $EDITOR_URL"
    echo "API endpoint:        $API_URL"
  else
    echo "Editor available at: http://$HOST:$PORT/editor_estructura.html"
    echo "API endpoint:        http://$HOST:$PORT/api/estructura"
  fi
else
  echo "Editor available at: http://$HOST:$PORT/editor_estructura.html"
  echo "API endpoint:        http://$HOST:$PORT/api/estructura"
fi

echo "Press Ctrl+C to stop."

wait "$PID"
