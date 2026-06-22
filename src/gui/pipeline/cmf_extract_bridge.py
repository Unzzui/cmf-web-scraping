#!/usr/bin/env python3
"""Cliente que ejecuta CMF_EXTRACT en su propio intérprete y traduce su JSONL.

Lanza ``cmf_extract_runner.py`` con el python configurado para CMF_EXTRACT,
lee el protocolo JSONL de stdout y reenvía los logs de stderr. Soporta
cancelación (mata el proceso) para el botón "Detener".
"""

from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

from .settings import PipelineSettings


class CmfExtractBridge:
    """Ejecuta la consolidación CMF_EXTRACT para UNA empresa."""

    def __init__(self, settings: PipelineSettings):
        self.settings = settings
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True
        proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass

    def run(
        self,
        *,
        company_dir: str,
        rut: str,
        rut_completo: str,
        phases: list[str],
        on_stage: Callable[[str, str, dict], None],
        on_progress: Callable[[str, int, int, str], None],
        on_log: Callable[[str], None],
        xbrl_base_dir: Optional[str] = None,
    ) -> dict:
        """Ejecuta el runner y devuelve el dict 'final'.

        on_stage(stage, status, info)   -> cambios de etapa (running/done/error/skipped)
        on_progress(stage, cur, tot, msg)
        on_log(line)                    -> líneas de stderr (diagnóstico)
        """
        s = self.settings
        cmd = [
            s.cmf_extract_python,
            str(s.runner_path()),
            "--repo-root", s.cmf_extract_repo,
            "--company-dir", company_dir,
            "--rut", rut,
            "--rut-completo", rut_completo,
            "--xbrl-base-dir", xbrl_base_dir or s.xbrl_base_dir,
            "--products-dir", s.products_dir,
            "--product-v1-dir", s.product_v1_dir,
            "--arelle-dir", s.arelle_dir,
            "--langs", ",".join(s.langs),
            "--workers", str(s.effective_arelle_workers()),
            "--phases", ",".join(phases),
        ]
        if s.companies_csv:
            cmd += ["--companies-csv", s.companies_csv]
        if s.skip_existing:
            cmd.append("--skip-existing")
        if s.debug:
            cmd.append("--debug")

        env = {**os.environ, "PYTHONPATH": s.cmf_extract_repo, "PYTHONUNBUFFERED": "1"}

        final: dict = {"status": "error", "error": "El proceso no devolvió resultado", "outputs": []}

        try:
            self._proc = subprocess.Popen(
                cmd, cwd=s.cmf_extract_repo, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, bufsize=1,
            )
        except FileNotFoundError as e:
            return {"status": "error",
                    "error": f"No se pudo ejecutar el intérprete '{s.cmf_extract_python}': {e}",
                    "outputs": []}
        except Exception as e:  # pragma: no cover
            return {"status": "error", "error": str(e), "outputs": []}

        # Hilo lector de stderr -> logs
        def _drain_stderr() -> None:
            assert self._proc and self._proc.stderr
            for line in self._proc.stderr:
                line = line.rstrip("\n")
                if line:
                    try:
                        on_log(line)
                    except Exception:
                        pass

        err_thread = threading.Thread(target=_drain_stderr, daemon=True)
        err_thread.start()

        # Lectura del protocolo JSONL en stdout
        assert self._proc.stdout is not None
        for raw in self._proc.stdout:
            raw = raw.strip()
            if not raw:
                continue
            try:
                evt = json.loads(raw)
            except json.JSONDecodeError:
                # Cualquier ruido que se cuele en stdout lo tratamos como log
                on_log(raw)
                continue
            kind = evt.get("event")
            if kind == "stage":
                on_stage(evt.get("stage", ""), evt.get("status", ""), evt)
            elif kind == "progress":
                on_progress(evt.get("stage", ""), int(evt.get("current", 0)),
                            int(evt.get("total", 0)), evt.get("message", ""))
            elif kind == "final":
                final = evt

        self._proc.wait()
        err_thread.join(timeout=2)

        if self._cancelled:
            return {"status": "error", "error": "Cancelado por el usuario", "outputs": []}

        if self._proc.returncode not in (0, None) and final.get("status") != "error":
            final = {"status": "error",
                     "error": f"El runner terminó con código {self._proc.returncode}",
                     "outputs": final.get("outputs", [])}
        return final
