#!/usr/bin/env python3
"""Subida automática de los Excel de análisis a FinDataChile (leg 3A).

Flujo (coincide con la API admin de FinDataChile):
  1. POST /api/admin/login          JSON {username, password}  -> cookie admin-token
  2. POST /api/admin/process-files  multipart {file, metadata}  (requiere la cookie)

Usamos ``process-files`` (el mismo endpoint que el panel admin), NO
``process-excel``: process-files es el que gestiona el catálogo real con
**versionado** y **un solo producto por empresa** (id = RUT). Cada Excel entra
como una VERSIÓN (product_versions) bajo el producto de la empresa, de modo que
quien compró la empresa accede a todas las actualizaciones sin volver a pagar.

FinDataChile deduce empresa/RUT/años/idioma del NOMBRE del archivo y de la
``metadata`` que enviamos. Mandamos el Excel con su nombre real
("Empresa - RUT - Análisis Financiero 2014-2026Q1 [ES].xlsx") porque ese es el
formato que parsea el server.
"""

from __future__ import annotations

import json
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


def parse_file_info(filename: str) -> dict:
    """Extrae idioma / año-versión / trimestre del nombre del Excel.

    Réplica de ``parseFileInfo`` del panel admin
    (components/admin/file-upload-manager.tsx) para que el server versione igual.
    Devuelve ``{language, period_type, version_year, quarter, is_versioned}``.
    """
    name = filename
    language = "ES"
    if re.search(r"\[EN\]", name, re.I):
        language = "EN"
    elif re.search(r"\[ES\]", name, re.I):
        language = "ES"

    version_year: Optional[int] = None
    quarter = 0
    is_versioned = False

    m = re.search(r"(\d{4})-(\d{4})\s*Q([1-4])", name, re.I)
    if m:  # 1) rango con trimestre: 2014-2026Q1
        version_year = int(m.group(2))
        quarter = int(m.group(3))
        is_versioned = True
    else:
        m = re.search(r"(\d{4})\s*Q([1-4])", name, re.I)
        if m:  # 2) año con trimestre (con rango opcional)
            y = int(m.group(1))
            quarter = int(m.group(2))
            mr = re.search(r"(\d{4})-(\d{4})", name)
            version_year = int(mr.group(2)) if mr else y
            is_versioned = True
        else:
            mr = re.search(r"(\d{4})-(\d{4})", name)
            if mr:  # 3) rango anual: 2014-2025
                version_year = int(mr.group(2))
                quarter = 0
                is_versioned = True
            else:
                ms = re.search(r"(\d{4})", name)
                if ms:  # 4) solo año
                    version_year = int(ms.group(1))
                    quarter = 0
                    is_versioned = True

    # Los Excel del pipeline son el histórico completo (Total) -> 'completo'.
    period_type = "trimestral" if quarter > 0 else "completo"
    return {
        "language": language,
        "period_type": period_type,
        "version_year": version_year,
        "quarter": quarter,
        "is_versioned": is_versioned,
    }


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
        """Sube un Excel como versión del producto de la empresa (id = RUT).

        Reintenta una vez si la sesión expiró (401).
        """
        if not _HAS_REQUESTS:
            return False, "La librería 'requests' no está instalada"
        path = Path(file_path)
        if not path.exists():
            return False, f"No existe el archivo a subir: {path}"

        if not self._logged_in:
            ok, msg = self.login()
            if not ok:
                return False, msg

        info = parse_file_info(path.name)
        metadata = {
            "rut": rut_completo,
            "periodType": info["period_type"],
            "language": info["language"],
            "versionInfo": {
                "year": info["version_year"] or end_year,
                "quarter": info["quarter"],
                "isVersioned": True,
            },
            # createVersion=True -> ruta versionada (crea/actualiza la versión
            # bajo el producto de la empresa). overwriteExisting para refrescar
            # el archivo si ya existe esa versión.
            "createVersion": True,
            "isNewVersion": True,
            "overwriteExisting": True,
            "priceOverride": int(self.settings.fdc_price or 7500),
        }

        url = self.settings.fdc_base_url.rstrip("/") + "/api/admin/process-files"

        def _do_post():
            with open(path, "rb") as fh:
                # Mandamos el Excel con su NOMBRE REAL (el server lo parsea).
                files = {"file": (path.name, fh, _XLSX_MIME)}
                data = {"metadata": json.dumps(metadata, ensure_ascii=False)}
                return self._session.post(url, files=files, data=data, timeout=180)

        try:
            resp = _do_post()
            if resp.status_code == 401:
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

        try:
            data = resp.json()
        except Exception:
            return False, "Respuesta no-JSON del servidor"

        if not data.get("success") or data.get("totalErrors"):
            pf = (data.get("processedFiles") or [{}])[0]
            return False, pf.get("error") or "El servidor no procesó el archivo"

        pf = (data.get("processedFiles") or [{}])[0]
        pid = pf.get("productId") or pf.get("baseProductId") or rut_completo
        return True, f"Publicado en producto '{pid}' (${metadata['priceOverride']})"
