#!/usr/bin/env python3
"""Lanzador de la GUI unificada del Pipeline CMF.

Flujo end-to-end en una sola interfaz:
    Descargar (CMF)  →  Consolidar a Excel (CMF_EXTRACT)  →  Subir a FinDataChile

Uso:
    python run_pipeline_gui.py
"""

import os
import sys

# Raíz del proyecto en el path para imports tipo `src.gui...`
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
# Trabajar siempre desde la raíz del repo: las descargas usan rutas
# relativas (./data/XBRL/...) y deben caer dentro del proyecto.
os.chdir(PROJECT_ROOT)


def main() -> int:
    try:
        from src.gui.unified_window import main as run_gui
    except Exception as e:  # pragma: no cover
        print(f"❌ No se pudo cargar la GUI unificada: {e}")
        import traceback
        traceback.print_exc()
        return 1

    run_gui()
    return 0


if __name__ == "__main__":
    sys.exit(main())
