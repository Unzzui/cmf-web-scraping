#!/usr/bin/env python3
"""Subida automática de los Excel de análisis a FinDataChile.

Flujo (coincide con la API admin de FinDataChile):
  1. POST /api/admin/login    JSON {username, password}  -> cookie admin-token
  2. POST /api/admin/process-excel  multipart, campo 'files'  (requiere la cookie)

FinDataChile deduce empresa/RUT/sector/años/idioma DEL NOMBRE del archivo
(``parseFileName`` / ``parseRutFromFileName`` / ``determineSector``). El nombre
que produce CMF_EXTRACT ("Empresa - RUT - Análisis ... [ES].xlsx") no parsea
bien allí, así que subimos con un nombre NORMALIZADO que mapea exacto:

    EMPRESA_EEFF_{RUT}-{DV}_{Anual|Trimestral}_{ini}-{fin}.xlsx

El archivo en disco no se renombra; sólo cambiamos el nombre del part multipart.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

try:
    import requests
    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    requests = None  # type: ignore
    _HAS_REQUESTS = False

from .settings import PipelineSettings

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def normalize_upload_name(
    company_name: str,
    rut_completo: str,
    start_year: Optional[int],
    end_year: Optional[int],
    quarterly: bool,
) -> str:
    """Construir un nombre que FinDataChile parsea sin ambigüedad."""
    name = re.sub(r"[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]+", "_", (company_name or "EMPRESA").strip().upper())
    name = re.sub(r"_+", "_", name).strip("_") or "EMPRESA"
    freq = "Trimestral" if quarterly else "Anual"
    sy = start_year if start_year else ""
    ey = end_year if end_year else ""
    years = f"{sy}-{ey}" if sy and ey else "0000-0000"
    rut = rut_completo or "0-0"
    return f"{name}_EEFF_{rut}_{freq}_{years}.xlsx"


class FinDataChileUploader:
    """Cliente mínimo y reutilizable para subir Excel a FinDataChile."""

    def __init__(self, settings: PipelineSettings):
        self.settings = settings
        self._session = requests.Session() if _HAS_REQUESTS else None
        self._logged_in = False

    @property
    def available(self) -> bool:
        return _HAS_REQUESTS

    # ------------------------------------------------------------------ #
    def login(self) -> tuple[bool, str]:
        if not _HAS_REQUESTS:
            return False, "La librería 'requests' no está instalada (pip install requests)"
        s = self.settings
        if not (s.fdc_username and s.fdc_password):
            return False, "Faltan credenciales de FinDataChile"
        url = s.fdc_base_url.rstrip("/") + "/api/admin/login"
        try:
            resp = self._session.post(
                url, json={"username": s.fdc_username, "password": s.fdc_password},
                timeout=30,
            )
        except Exception as e:
            return False, f"No se pudo conectar a {url}: {e}"
        if resp.status_code == 200 and resp.json().get("success"):
            self._logged_in = True
            return True, "Sesión admin iniciada"
        try:
            msg = resp.json().get("error", f"HTTP {resp.status_code}")
        except Exception:
            msg = f"HTTP {resp.status_code}"
        return False, f"Login falló: {msg}"

    # ------------------------------------------------------------------ #
    def upload_file(
        self,
        file_path: str,
        *,
        company_name: str,
        rut_completo: str,
        start_year: Optional[int],
        end_year: Optional[int],
        quarterly: bool,
    ) -> tuple[bool, str]:
        """Sube un Excel. Reintenta una vez si la sesión expiró (401)."""
        if not _HAS_REQUESTS:
            return False, "La librería 'requests' no está instalada"
        path = Path(file_path)
        if not path.exists():
            return False, f"No existe el archivo a subir: {path}"

        if not self._logged_in:
            ok, msg = self.login()
            if not ok:
                return False, msg

        upload_name = normalize_upload_name(
            company_name, rut_completo, start_year, end_year, quarterly
        )
        url = self.settings.fdc_base_url.rstrip("/") + "/api/admin/process-excel"

        def _do_post():
            with open(path, "rb") as fh:
                files = [("files", (upload_name, fh, _XLSX_MIME))]
                return self._session.post(url, files=files, timeout=180)

        try:
            resp = _do_post()
            if resp.status_code == 401:
                # Sesión expirada: re-login y reintento único
                self._logged_in = False
                ok, msg = self.login()
                if not ok:
                    return False, f"Sesión expirada y re-login falló: {msg}"
                resp = _do_post()
        except Exception as e:
            return False, f"Error subiendo: {e}"

        if resp.status_code != 200:
            try:
                err = resp.json().get("error", f"HTTP {resp.status_code}")
            except Exception:
                err = f"HTTP {resp.status_code}"
            return False, f"Subida rechazada: {err}"

        data = resp.json()
        if data.get("errorDetails"):
            return False, "; ".join(data["errorDetails"])
        processed = data.get("processed", 0)
        if processed:
            return True, f"Subido como '{upload_name}'"
        return False, "El servidor no procesó ningún archivo"
