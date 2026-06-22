#!/usr/bin/env python3
"""Descargador XBRL de la CMF por HTTP puro (sin navegador).

Reemplaza el flujo Selenium (lento: ~15 s por período) por peticiones HTTP
concurrentes. Mecanismo descubierto en la web de la CMF:

    1. GET  entidad.php?...&pestania=3            -> abre sesión (cookies) + nombre empresa
    2. POST entidad.php  {forma=P, aa, mm, tipo=C, tipo_norma=IFRS}
                                                  -> HTML con el enlace "Estados financieros (XBRL)"
    3. GET  safec_ifrs_verarchivo.php?auth=..&send=..  -> descarga el ZIP

Medido: ~16 períodos en ~11 s (6 workers) vs ~4 min con navegador (~22x).

Firma compatible con la usada por el orquestador del pipeline; los kwargs de
Selenium (headless, strategy, ...) se aceptan y se ignoran.
"""

from __future__ import annotations

import logging
import os
import re
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore

logger = logging.getLogger(__name__)

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
_DEF_CSV = "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
_RUT_DV_RE = re.compile(r"(\d{7,8})\s*-\s*([\dkK])")


def _entidad_url(rut: str) -> str:
    return (f"https://www.cmfchile.cl/institucional/mercados/entidad.php"
            f"?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI"
            f"&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3")


def _build_session(max_workers: int, retries: int = 3) -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": _UA})
    if Retry is not None:
        retry = Retry(total=retries, connect=retries, read=retries, status=retries,
                      backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["GET", "POST"])
        adapter = HTTPAdapter(pool_connections=max(8, max_workers * 2),
                              pool_maxsize=max(8, max_workers * 2), max_retries=retry)
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    return s


def _company_info_from_csv(rut: str, csv_path: str) -> tuple[Optional[str], Optional[str]]:
    try:
        import pandas as pd
        if not os.path.exists(csv_path):
            return None, None
        df = pd.read_csv(csv_path)
        match = df[df["RUT_Numero"].astype(str) == str(rut)]
        if match.empty:
            return None, None
        dv = str(match.iloc[0]["DV"]).strip()
        name = None
        for col in ("Empresa", "Nombre", "RazonSocial", "Entidad", "Razon Social"):
            if col in df.columns and not pd.isna(match.iloc[0].get(col)):
                name = str(match.iloc[0][col]).strip()
                break
        if dv and dv.lower() != "nan":
            return dv, name
    except Exception as e:  # pragma: no cover
        logger.debug("CSV company info fallo: %s", e)
    return None, None


def _company_info_from_page(html: str) -> tuple[Optional[str], Optional[str]]:
    """Fallback: extraer DV y nombre desde la página de entidad."""
    soup = BeautifulSoup(html, "html.parser")
    dv = None
    el = soup.find(id="datos_ent")
    text = el.get_text("\n") if el else html
    m = _RUT_DV_RE.search(text)
    if m:
        dv = m.group(2).upper()
    name = None
    if el:
        parts = [p.strip() for p in el.get_text("\n").split("\n") if p.strip()]
        if len(parts) >= 2:
            name = parts[1]
    return dv, name


def _safe_name(name: str) -> str:
    safe = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).strip()
    return safe.replace(" ", "_")


def _period_dir_name(mode: str) -> str:
    m = (mode or "total").lower()
    if m == "annual":
        return "Anual"
    if m == "quarterly":
        return "Trimestral"
    return "Total"


def _months_for_mode(mode: str) -> list[int]:
    return [12] if (mode or "total").lower() == "annual" else [3, 6, 9, 12]


def _extract_zip(content: bytes, target_dir: Path, rut: str, yyyymm: str) -> Optional[Path]:
    """Guardar y extraer el ZIP en {target}/Estados_financieros_(XBRL){rut}_{yyyymm}_extracted/."""
    extract_dir = target_dir / f"Estados_financieros_(XBRL){rut}_{yyyymm}_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    import io
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(extract_dir)
        return extract_dir
    except Exception as e:
        logger.warning("ZIP inválido %s_%s: %s", rut, yyyymm, e)
        try:
            extract_dir.rmdir()
        except Exception:
            pass
        return None


def _find_xbrl_link(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        if "XBRL" in (a.get_text() or ""):
            return a.get("href")
    # fallback por href
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        if "verarchivo" in href.lower() and "ifrs" in href.lower():
            return href
    return None


def download_cmf_xbrl_http(
    rut: str,
    start_year: int = 2024,
    end_year: int = 2014,
    step: int = -1,
    *,
    quarterly: bool = False,
    mode: str = "total",
    progress_hook: Optional[Callable] = None,
    skip_existing: bool = True,
    max_workers: int = 6,
    companies_csv: Optional[str] = None,
    http_retries: int = 3,
    http_timeout: int = 60,
    **_ignored,
) -> tuple[str, list[str]]:
    """Descarga XBRL por HTTP puro. Devuelve (target_dir, lista de carpetas extraídas)."""
    rut = str(rut).strip()
    mode = (mode or ("quarterly" if quarterly else "total")).lower()
    base = _entidad_url(rut)
    session = _build_session(max_workers, http_retries)

    # 1) Abrir sesión y obtener nombre/dv
    try:
        r0 = session.get(base, timeout=http_timeout)
        r0.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"No se pudo abrir la entidad en la CMF: {e}")

    csv_path = companies_csv or _DEF_CSV
    dv, name = _company_info_from_csv(rut, csv_path)
    if not dv or not name:
        pdv, pname = _company_info_from_page(r0.text)
        dv = dv or pdv
        name = name or pname
    if not name:
        name = f"Empresa_RUT_{rut}"
    rut_completo = f"{rut}-{dv}" if dv else rut
    safe_name = _safe_name(name)

    target_dir = Path("./data/XBRL") / _period_dir_name(mode) / f"{rut_completo}_{safe_name}"
    target_dir.mkdir(parents=True, exist_ok=True)

    # 2) Lista de períodos
    iteration_step = -1 if mode == "total" else (step if step else -1)
    if iteration_step >= 0:
        iteration_step = -1
    months = _months_for_mode(mode)
    periods: list[tuple[int, int]] = []
    for year in range(start_year, end_year - 1, iteration_step):
        for month in months:
            periods.append((year, month))

    # skip de los ya existentes en disco
    if skip_existing:
        pending = []
        for (y, m) in periods:
            yyyymm = f"{y}{m:02d}"
            if (target_dir / f"Estados_financieros_(XBRL){rut}_{yyyymm}_extracted").is_dir():
                continue
            pending.append((y, m))
    else:
        pending = list(periods)

    total = len(pending)
    logger.info("[http] %s (%s): %d períodos a bajar (de %d), %d workers",
                name, rut_completo, total, len(periods), max_workers)
    if progress_hook:
        try:
            progress_hook(rut, 0, total, None, None, 0, "strategy_direct")
        except Exception:
            pass

    if total == 0:
        return str(target_dir.resolve()), []

    downloaded: list[str] = []
    done = 0
    start_ts = time.time()
    lock_done = __import__("threading").Lock()

    def _fetch(year: int, month: int) -> Optional[str]:
        yyyymm = f"{year}{month:02d}"
        # POST del período. Primario: Consolidado/IFRS; fallback: Individual/IFRS.
        for tipo in ("C", "I"):
            try:
                resp = session.post(base, data={
                    "forma": "P", "aa": str(year), "mm": f"{month:02d}",
                    "tipo": tipo, "tipo_norma": "IFRS",
                }, timeout=http_timeout)
                href = _find_xbrl_link(resp.text)
                if not href:
                    continue
                dl = urljoin(base, href)
                rr = session.get(dl, timeout=http_timeout, headers={"Referer": base})
                if rr.status_code != 200 or rr.content[:2] != b"PK":
                    continue
                ext = _extract_zip(rr.content, target_dir, rut, yyyymm)
                if ext is not None:
                    return str(ext)
            except Exception as e:
                logger.debug("[http] %s período %s tipo %s error: %s", rut, yyyymm, tipo, e)
                continue
        return None

    def _task(period: tuple[int, int]):
        nonlocal done
        year, month = period
        res = _fetch(year, month)
        with lock_done:
            done += 1
            cur = done
        eta = None
        if cur and cur < total:
            per = (time.time() - start_ts) / cur
            eta = per * (total - cur)
        if progress_hook:
            try:
                status = "period_completed" if res else "in_progress"
                progress_hook(rut, cur, total, year, month, eta, status)
            except Exception:
                pass
        if not res:
            logger.warning("[http] sin XBRL: %s %s-%02d", rut, year, month)
        return res

    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        futs = [ex.submit(_task, p) for p in pending]
        for f in as_completed(futs):
            try:
                r = f.result()
                if r:
                    downloaded.append(r)
            except Exception as e:  # pragma: no cover
                logger.warning("[http] tarea falló: %s", e)

    logger.info("[http] Completado %s | %d/%d períodos | %.1fs",
                rut_completo, len(downloaded), total, time.time() - start_ts)
    return str(target_dir.resolve()), downloaded
