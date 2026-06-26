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

from bs4 import BeautifulSoup

from xbrl.http_throttle import (
    UA_POOL,
    build_polite_session,
    polite_request as _polite_request,
)

logger = logging.getLogger(__name__)

# Compat con código legacy que importaba _UA del módulo.
_UA = UA_POOL[0]
_DEF_CSV = "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
_RUT_DV_RE = re.compile(r"(\d{7,8})\s*-\s*([\dkK])")


def _entidad_url(rut: str) -> str:
    return (f"https://www.cmfchile.cl/institucional/mercados/entidad.php"
            f"?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI"
            f"&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3")


def _build_session(max_workers: int, retries: int = 3):
    """Wrapper retrocompatible — la lógica vive en xbrl.http_throttle."""
    return build_polite_session(max_workers, retries)


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
    """Guardar y extraer el ZIP en {target}/Estados_financieros_(XBRL){rut}_{yyyymm}_extracted/.

    Valida lo MÍNIMO: `.xbrl` + `.xsd`. Los `-label.xml` y `-definition.xml`
    son opcionales — algunos períodos los traen y otros no (CMF entrega ambos
    formatos legítimamente; Arelle resuelve labels/links desde la taxonomía
    cacheada cuando no vienen empaquetados).
    """
    extract_dir = target_dir / f"Estados_financieros_(XBRL){rut}_{yyyymm}_extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)
    import io
    import shutil
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        logger.warning("ZIP inválido %s_%s: %s", rut, yyyymm, e)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None

    required_suffixes = (".xbrl", ".xsd")
    present = {p.name for p in extract_dir.rglob("*") if p.is_file()}
    missing = [s for s in required_suffixes if not any(n.endswith(s) for n in present)]
    if missing:
        logger.warning("ZIP corrupto %s_%s, faltan core files %s; descartando para reintentar",
                       rut, yyyymm, missing)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None
    return extract_dir


def _find_xbrl_link(html: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    # El enlace real de descarga apunta a `safec_ifrs_verarchivo.php`. Buscamos
    # por href para evitar confundirlo con enlaces informativos del sitio (p.ej.
    # "XBRL Mercado de Valores") que también contienen el texto "XBRL".
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = (a.get_text() or "").strip()
        if "verarchivo" in href.lower() and "ifrs" in href.lower() and "XBRL" in text:
            return href
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
    max_workers: int = 3,
    companies_csv: Optional[str] = None,
    http_retries: int = 3,
    http_timeout: int = 60,
    **_ignored,
) -> tuple[str, list[str]]:
    """Descarga XBRL por HTTP puro. Devuelve (target_dir, lista de carpetas extraídas).

    Concurrencia global: además de ``max_workers`` por empresa, hay un semáforo
    de proceso (env ``CMF_HTTP_MAX_INFLIGHT``, default 6) que limita el total de
    requests en vuelo a la CMF, válido aunque se descarguen muchas empresas
    en paralelo. Ante 403/429/Retry-After se aplica cooldown global automático.
    """
    rut = str(rut).strip()
    mode = (mode or ("quarterly" if quarterly else "total")).lower()
    base = _entidad_url(rut)
    session = _build_session(max_workers, http_retries)

    # 1) Abrir sesión y obtener nombre/dv
    try:
        r0 = _polite_request(session, "GET", base, timeout=http_timeout)
        r0.raise_for_status()
    except Exception as e:
        raise RuntimeError(f"No se pudo abrir la entidad en la CMF: {e}")

    csv_path = companies_csv or _DEF_CSV
    dv, name = _company_info_from_csv(rut, csv_path)
    if not dv or not name:
        pdv, pname = _company_info_from_page(r0.text)
        dv = dv or pdv
        name = name or pname
    rut_completo = f"{rut}-{dv}" if dv else rut

    # Si no obtuvimos el nombre real, ANTES de caer al placeholder
    # `Empresa_RUT_<rut>` revisamos si ya existe una carpeta con datos para
    # este RUT (con o sin dígito verificador). Reutilizarla evita crear
    # directorios huérfanos que rompen la consolidación con
    # "Sin datasets XBRL en este directorio".
    base_dir = Path("./data/XBRL") / _period_dir_name(mode)
    target_dir: Optional[Path] = None
    if base_dir.is_dir():
        # Glob amplio: matchea con o sin DV (e.g. `93007000-9_...` y `93007000_...`).
        candidates = list(base_dir.glob(f"{rut}-*"))
        candidates += list(base_dir.glob(f"{rut}_*"))
        # Preferir carpetas con datasets reales; placeholders al final.
        candidates.sort(
            key=lambda p: (0 if any(p.glob("Estados_financieros_*_extracted")) else 1,
                           1 if "Empresa_RUT_" in p.name else 0)
        )
        for cand in candidates:
            if not cand.is_dir():
                continue
            has_data = any(cand.glob("Estados_financieros_*_extracted"))
            placeholder = "Empresa_RUT_" in cand.name
            if has_data or (target_dir is None and not placeholder):
                target_dir = cand
                # Recuperar nombre + DV del nombre del dir cuando faltan.
                # Formato: "<rut>-<dv>_<NOMBRE_SAFE>" o "<rut>_<NOMBRE_SAFE>".
                cand_name = cand.name
                if "_" in cand_name:
                    prefix, _, suffix = cand_name.partition("_")
                    if "-" in prefix and not dv:
                        try:
                            _r, _d = prefix.split("-", 1)
                            if _r == rut:
                                dv = _d
                        except ValueError:
                            pass
                    if not name:
                        name = suffix.replace("_", " ").strip()
                if has_data:
                    break

    # Recalcular rut_completo después de posiblemente recuperar DV del dir.
    rut_completo = f"{rut}-{dv}" if dv else rut

    if target_dir is None:
        if not name:
            name = f"Empresa_RUT_{rut}"
        safe_name = _safe_name(name)
        target_dir = base_dir / f"{rut_completo}_{safe_name}"
    target_dir.mkdir(parents=True, exist_ok=True)
    if not name:
        name = "Empresa"
    safe_name = _safe_name(name)

    # 2) Lista de períodos
    iteration_step = -1 if mode == "total" else (step if step else -1)
    if iteration_step >= 0:
        iteration_step = -1
    months = _months_for_mode(mode)
    periods: list[tuple[int, int]] = []
    for year in range(start_year, end_year - 1, iteration_step):
        for month in months:
            periods.append((year, month))

    # skip de los ya existentes en disco. Si la carpeta existe pero le faltan
    # los CORE files (.xbrl / .xsd), se considera corrupta y se re-descarga.
    # `-label.xml` y `-definition.xml` son opcionales (la CMF entrega algunos
    # períodos con solo 3 archivos legítimamente).
    import shutil as _shutil
    required_suffixes = (".xbrl", ".xsd")

    def _is_complete(d: Path) -> bool:
        if not d.is_dir():
            return False
        present = {p.name for p in d.rglob("*") if p.is_file()}
        return all(any(n.endswith(s) for n in present) for s in required_suffixes)

    if skip_existing:
        pending = []
        for (y, m) in periods:
            yyyymm = f"{y}{m:02d}"
            ext = target_dir / f"Estados_financieros_(XBRL){rut}_{yyyymm}_extracted"
            if ext.is_dir():
                if _is_complete(ext):
                    continue
                # Carpeta parcial → limpiar para reintentar la descarga.
                logger.info("[http] re-descargando %s %s-%02d (extract incompleto)",
                            rut, y, m)
                _shutil.rmtree(ext, ignore_errors=True)
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
                resp = _polite_request(session, "POST", base, data={
                    "forma": "P", "aa": str(year), "mm": f"{month:02d}",
                    "tipo": tipo, "tipo_norma": "IFRS",
                }, timeout=http_timeout)
                href = _find_xbrl_link(resp.text)
                if not href:
                    continue
                dl = urljoin(base, href)
                rr = _polite_request(session, "GET", dl,
                                     timeout=http_timeout,
                                     headers={"Referer": base})
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

    # Cleanup: si el target era un placeholder `Empresa_RUT_*` y quedó vacío,
    # lo eliminamos. Así no contamina la próxima corrida (donde reutilizaríamos
    # erróneamente esta carpeta huérfana).
    try:
        is_placeholder = "Empresa_RUT_" in target_dir.name
        has_data = any(target_dir.glob("Estados_financieros_*_extracted"))
        if is_placeholder and not has_data:
            target_dir.rmdir()
            logger.info("[http] Placeholder vacío eliminado: %s", target_dir)
    except Exception:
        pass

    return str(target_dir.resolve()), downloaded
