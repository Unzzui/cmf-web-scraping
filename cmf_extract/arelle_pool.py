#!/usr/bin/env python3
"""Pool de workers persistentes de Arelle (driver de ``arelle_worker.py``).

Uso desde el pipeline (ver ``batch_xbrl_to_excel.run_arelle``)::

    pool = ArelleWorkerPool.get(arelle_python, arelle_dir)
    pool.run(args, timeout=180)   # args = argv de arelleCmdLine sin el programa

Cada worker es un subprocess ``python arelle_worker.py`` que ya pagó el costo
de importar Arelle. Los workers se piden prestados de una cola (un job a la
vez por worker), y ante timeout o muerte del proceso se reemplazan por uno
nuevo. El tamaño del pool lo fija CMF_ARELLE_PARALLEL (default 6), igual que
el paralelismo de la fase Arelle en ``cmf.pipeline.consolidation``.

Activación: CMF_ARELLE_WORKER=1 (por defecto apagado; el pipeline cae al modo
subprocess clásico ante cualquier error del pool).
"""

from __future__ import annotations

import json
import os
import queue
import select
import subprocess
import sys
import threading
from pathlib import Path

_WORKER_SCRIPT = Path(__file__).resolve().parent / "arelle_worker.py"


class ArelleWorkerError(RuntimeError):
    pass


class _Worker:
    """Un subprocess worker; atiende un job a la vez."""

    def __init__(self, arelle_python: Path, arelle_dir: Path, ready_timeout: float):
        self.proc = subprocess.Popen(
            [str(arelle_python), str(_WORKER_SCRIPT)],
            cwd=str(arelle_dir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        self._seq = 0
        # Esperar el handshake {"ready": true}; si Arelle no importa, fallar ya.
        resp = self._read_response(ready_timeout)
        if not (resp.get("ok") and resp.get("ready")):
            self.kill()
            raise ArelleWorkerError(f"worker no inició: {resp.get('error', resp)}")

    def _read_response(self, timeout: float) -> dict:
        stdout = self.proc.stdout
        assert stdout is not None
        rlist, _, _ = select.select([stdout], [], [], timeout)
        if not rlist:
            raise TimeoutError(f"worker sin respuesta tras {timeout:.0f}s")
        line = stdout.readline()
        if not line:
            raise ArelleWorkerError("worker terminó inesperadamente (EOF)")
        return json.loads(line)

    def run(self, args: list[str], timeout: float) -> None:
        self._seq += 1
        job = {"id": self._seq, "args": args}
        stdin = self.proc.stdin
        assert stdin is not None
        stdin.write(json.dumps(job) + "\n")
        stdin.flush()
        resp = self._read_response(timeout)
        if not resp.get("ok"):
            raise ArelleWorkerError(resp.get("error", "error desconocido"))

    @property
    def alive(self) -> bool:
        return self.proc.poll() is None

    def kill(self) -> None:
        try:
            self.proc.kill()
            self.proc.wait(timeout=5)
        except Exception:
            pass


class ArelleWorkerPool:
    """Singleton por (python, arelle_dir); thread-safe (patrón borrow)."""

    _instances: dict[tuple[str, str], "ArelleWorkerPool"] = {}
    _instances_lock = threading.Lock()

    @classmethod
    def get(cls, arelle_python: Path, arelle_dir: Path) -> "ArelleWorkerPool":
        key = (str(arelle_python), str(arelle_dir))
        with cls._instances_lock:
            pool = cls._instances.get(key)
            if pool is None:
                pool = cls(arelle_python, arelle_dir)
                cls._instances[key] = pool
            return pool

    def __init__(self, arelle_python: Path, arelle_dir: Path):
        self.arelle_python = Path(arelle_python)
        self.arelle_dir = Path(arelle_dir)
        try:
            size = max(1, int(os.getenv("CMF_ARELLE_PARALLEL", "6")))
        except ValueError:
            size = 6
        self._idle: "queue.Queue[_Worker | None]" = queue.Queue()
        # Slots perezosos: None = "aún sin worker"; se crea al primer uso.
        for _ in range(size):
            self._idle.put(None)

    def run(self, args: list[str], timeout: float = 180.0) -> None:
        """Ejecuta un job en un worker libre; reemplaza workers muertos."""
        slot = self._idle.get()
        worker: _Worker | None = slot
        try:
            if worker is None or not worker.alive:
                worker = _Worker(self.arelle_python, self.arelle_dir,
                                 ready_timeout=max(60.0, timeout))
            try:
                worker.run(args, timeout)
            except (TimeoutError, ArelleWorkerError, OSError, ValueError):
                # Worker en estado dudoso: matarlo; el slot se repone vacío.
                worker.kill()
                worker = None
                raise
        finally:
            self._idle.put(worker)

    def shutdown(self) -> None:
        drained: list[_Worker | None] = []
        try:
            while True:
                drained.append(self._idle.get_nowait())
        except queue.Empty:
            pass
        for w in drained:
            if w is not None:
                try:
                    if w.proc.stdin:
                        w.proc.stdin.close()  # EOF → el worker sale solo
                    w.proc.wait(timeout=5)
                except Exception:
                    w.kill()
            self._idle.put(None)


def shutdown_all() -> None:
    with ArelleWorkerPool._instances_lock:
        pools = list(ArelleWorkerPool._instances.values())
    for p in pools:
        p.shutdown()
