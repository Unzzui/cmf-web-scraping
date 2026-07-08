#!/usr/bin/env python3
"""Worker persistente de Arelle: procesa múltiples exports en un solo proceso.

Corre con el python del venv de Arelle y cwd = directorio de Arelle (igual que
``arelleCmdLine.py``). Lee jobs JSONL por stdin y responde JSONL por stdout:

    entrada:  {"id": "76036453_202412", "args": ["-f", "...", "--factTable", ...]}
    salida:   {"id": "76036453_202412", "ok": true}
              {"id": "76036453_202412", "ok": false, "error": "..."}

El ahorro viene de pagar el arranque del intérprete + ``import arelle`` una
sola vez por worker en lugar de una vez por dataset (miles de veces en una
corrida completa). El driver del lado del pipeline es ``arelle_pool.py``.

Protocolo: stdout queda reservado para las respuestas JSONL; cualquier print
de Arelle se redirige a stderr.
"""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    # Reservar el stdout real para el protocolo; Arelle imprime a stderr.
    proto = os.fdopen(os.dup(1), "w", encoding="utf-8")
    sys.stdout = sys.stderr

    # cwd = directorio de Arelle (igual que al correr arelleCmdLine.py desde
    # ahí): permite importar el checkout fuente aunque el venv no tenga el
    # paquete arelle instalado.
    sys.path.insert(0, os.getcwd())

    try:
        from arelle import CntlrCmdLine  # import pesado: una sola vez por worker
    except Exception as exc:  # pragma: no cover - depende del venv de Arelle
        proto.write(json.dumps({"id": None, "ok": False,
                                "error": f"import arelle: {exc}"}) + "\n")
        proto.flush()
        return 1

    proto.write(json.dumps({"id": None, "ok": True, "ready": True}) + "\n")
    proto.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        job_id = None
        try:
            job = json.loads(line)
            job_id = job.get("id")
            CntlrCmdLine.parseAndRun(job["args"])
            resp = {"id": job_id, "ok": True}
        except SystemExit as exc:
            code = exc.code if exc.code is not None else 0
            resp = ({"id": job_id, "ok": True} if code == 0 else
                    {"id": job_id, "ok": False, "error": f"SystemExit({code})"})
        except Exception as exc:
            resp = {"id": job_id, "ok": False, "error": str(exc)[:300]}
        proto.write(json.dumps(resp) + "\n")
        proto.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
