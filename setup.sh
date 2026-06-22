#!/usr/bin/env bash
#
# Setup portable del Pipeline CMF en CUALQUIER PC.
# Deja listo todo lo necesario para: python run_pipeline_gui.py
#
#   1. .venv               -> GUI + descarga (tkinter, selenium, pandas...)
#   2. cmf_extract/.venv   -> consolidacion CMF_EXTRACT (pandas 2.3.x, etc.)
#   3. tools/Arelle        -> motor XBRL (se clona y se le crea su .venv)
#
# Uso:  ./setup.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

say() { printf "\n\033[1m== %s ==\033[0m\n" "$*"; }
die() { printf "\n[ERROR] %s\n" "$*" >&2; exit 1; }

# --- 1. Elegir un Python base con tkinter y version >= 3.11 -----------------
say "Buscando un Python base (tkinter + >=3.11)"
PYBASE=""
CANDIDATES=(
  "python3.12" "python3.11"
  "$HOME/.pyenv/versions/3.12.2/bin/python3"
  "python3" "/usr/bin/python3"
)
# Anexar cualquier version pyenv 3.11/3.12 disponible
if [ -d "$HOME/.pyenv/versions" ]; then
  for d in "$HOME"/.pyenv/versions/3.1[12].*/bin/python3; do
    [ -x "$d" ] && CANDIDATES+=("$d")
  done
fi
for c in "${CANDIDATES[@]}"; do
  cmd="$(command -v "$c" 2>/dev/null || true)"
  [ -n "$cmd" ] || { [ -x "$c" ] && cmd="$c"; }
  [ -n "${cmd:-}" ] || continue
  if "$cmd" -c 'import sys,tkinter; assert sys.version_info[:2] >= (3,11)' 2>/dev/null; then
    PYBASE="$cmd"; break
  fi
done
[ -n "$PYBASE" ] || die "No encontre un Python >=3.11 con tkinter.
  Instala tkinter (ej: 'sudo apt install python3-tk') o pyenv 3.12 y reintenta."
echo "Usando: $PYBASE ($($PYBASE --version 2>&1))"

mkvenv() {  # $1=dir  $2=requirements
  local dir="$1" req="$2"
  if [ ! -x "$dir/bin/python" ]; then
    "$PYBASE" -m venv "$dir"
  fi
  "$dir/bin/python" -m pip install --upgrade pip -q
  if [ -f "$req" ]; then
    "$dir/bin/python" -m pip install -r "$req" -q
  fi
}

# --- 2. venv de la GUI ------------------------------------------------------
say "Creando .venv (GUI + descarga)"
mkvenv ".venv" "src/config/requirements_pipeline.txt"

# --- 3. venv de CMF_EXTRACT -------------------------------------------------
say "Creando cmf_extract/.venv (consolidacion)"
mkvenv "cmf_extract/.venv" "cmf_extract/requirements.txt"

# --- 4. Arelle (clon + su venv) ---------------------------------------------
say "Preparando Arelle en tools/Arelle"
mkdir -p tools
if [ ! -f "tools/Arelle/arelleCmdLine.py" ]; then
  echo "Clonando Arelle (shallow)..."
  git clone --depth 1 https://github.com/Arelle/Arelle.git tools/Arelle
else
  echo "Arelle ya presente."
fi
# Arelle corre con un python >=3.9; reutilizamos PYBASE
if [ ! -x "tools/Arelle/.venv/bin/python" ]; then
  "$PYBASE" -m venv tools/Arelle/.venv
fi
tools/Arelle/.venv/bin/python -m pip install --upgrade pip -q
tools/Arelle/.venv/bin/python -m pip install -r tools/Arelle/requirements.txt -q
( cd tools/Arelle && ./.venv/bin/python arelleCmdLine.py --version >/dev/null 2>&1 ) \
  && echo "Arelle OK" || echo "[aviso] Arelle no respondio --version (revisar)"

# --- 5. Generar config in-repo + verificar ----------------------------------
say "Generando configuracion y verificando entorno"
.venv/bin/python - <<'PY'
import sys, os
sys.path.insert(0, os.getcwd())
from src.gui.pipeline.settings import PipelineSettings
s = PipelineSettings.with_defaults(); s.save()
allok = True
for c in s.verify():
    mark = "OK " if c["ok"] else "FALLA"
    if not c["ok"]:
        allok = False
    print(f"  [{mark}] {c['name']}: {c['detail']}")
print("\nListo." if allok else "\nHay items en FALLA (revisa arriba).")
PY

say "Setup completo"
echo "Ejecuta la GUI con:"
echo "    .venv/bin/python run_pipeline_gui.py"
