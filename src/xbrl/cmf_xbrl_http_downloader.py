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
from calendar import monthrange
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date
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

    # No basta con "algún .xsd": el .xbrl declara por nombre el schema del emisor
    # (<link:schemaRef href="<rut>_<yyyymm>_C_shell.xsd">) y ese es el que define
    # los conceptos cl-ci:*. Varios datasets traen el `_dimension.xsd` pero NO el
    # shell, y pasaban la validación: Arelle luego no resolvía ni un concepto,
    # exportaba cero hechos y terminaba con exit 0. Resultado: huecos silenciosos
    # en el Balance. Se exige el schema que el propio .xbrl referencia.
    faltante = _schema_ref_faltante(extract_dir)
    if faltante:
        logger.warning("ZIP incompleto %s_%s: falta el schema declarado %s; "
                       "descartando para reintentar", rut, yyyymm, faltante)
        shutil.rmtree(extract_dir, ignore_errors=True)
        return None
    return extract_dir


# El href puede venir con comillas dobles O simples: la CMF emite ambos estilos.
_SCHEMA_REF_RE = re.compile(r"""schemaRef[^>]*href=["']([^"']+\.xsd)["']""", re.I)


def _schema_ref_faltante(extract_dir: Path) -> Optional[str]:
    """Devuelve el nombre del .xsd que el .xbrl declara y no está en el dataset."""
    xbrl = next(iter(extract_dir.rglob("*.xbrl")), None)
    if xbrl is None:
        return None
    try:
        cabecera = xbrl.read_bytes()[:4000].decode("utf-8", "ignore")
    except OSError:
        return None
    m = _SCHEMA_REF_RE.search(cabecera)
    if not m:
        return None
    href = m.group(1)
    if href.startswith(("http://", "https://")):
        return None  # schema remoto: lo resuelve Arelle desde su cache
    nombre = Path(href).name
    existe = any(p.name == nombre for p in extract_dir.rglob("*") if p.is_file())
    return None if existe else nombre


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


def _quarter_end(year: int, month: int) -> _date:
    """Último día del trimestre representado por (año, mes de cierre 3/6/9/12)."""
    return _date(year, month, monthrange(year, month)[1])


def _existing_periods_on_disk(target_dir: Path, rut: str) -> set[str]:
    """YYYYMM ya descargados en *target_dir* para *rut* (carpetas *_extracted)."""
    pat = re.compile(
        rf"Estados_financieros_\(XBRL\){re.escape(str(rut))}_(\d{{6}})_extracted$"
    )
    found: set[str] = set()
    try:
        for p in target_dir.glob("Estados_financieros_*_extracted"):
            m = pat.search(p.name)
            if m:
                found.add(m.group(1))
    except Exception:  # pragma: no cover
        pass
    return found


# ---------------------------------------------------------------------------
# Cache de entidades SIN XBRL
# ---------------------------------------------------------------------------
# Muchas entidades del set IFRS (sobre todo fondos de inversión) no publican
# XBRL en la CMF. Para no re-sondearlas en cada corrida, se persiste su RUT en
# `data/no_xbrl_companies.json`. En corridas futuras se omiten SIN tocar la red.
# Auto-sanación: si una entidad cacheada aparece con datos en disco, se saca del
# cache. Para forzar re-verificación: env `CMF_NO_XBRL_RECHECK=1`.
import json as _json
import threading as _threading

_NOXBRL_LOCK = _threading.Lock()


def _no_xbrl_cache_path() -> Path:
    return Path("./data/no_xbrl_companies.json")


def _load_no_xbrl_cache() -> dict:
    p = _no_xbrl_cache_path()
    if not p.exists():
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:  # pragma: no cover
        return {}


def _is_cached_no_xbrl(rut: str) -> bool:
    return str(rut) in _load_no_xbrl_cache()


def _write_no_xbrl_cache(cache: dict) -> None:
    p = _no_xbrl_cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            _json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
    except Exception as e:  # pragma: no cover
        logger.debug("[http] no pude escribir cache sin-XBRL: %s", e)


def _mark_no_xbrl(rut: str, name: str, reason: str) -> None:
    with _NOXBRL_LOCK:
        cache = _load_no_xbrl_cache()
        cache[str(rut)] = {
            "name": name or "",
            "reason": reason,
            "checked": _date.today().isoformat(),
        }
        _write_no_xbrl_cache(cache)


def _unmark_no_xbrl(rut: str) -> None:
    with _NOXBRL_LOCK:
        cache = _load_no_xbrl_cache()
        if str(rut) in cache:
            cache.pop(str(rut), None)
            _write_no_xbrl_cache(cache)


def _has_local_data(base_dir: Path, rut: str) -> bool:
    """True si ya hay al menos un dataset extraído en disco para *rut* (offline)."""
    if not base_dir.is_dir():
        return False
    for cand in list(base_dir.glob(f"{rut}-*")) + list(base_dir.glob(f"{rut}_*")):
        if cand.is_dir() and any(cand.glob("Estados_financieros_*_extracted")):
            return True
    return False


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

    # --- Fast-skip (sin red) de entidades cacheadas como "sin XBRL" ---
    # Si la entidad está en `data/no_xbrl_companies.json` y NO tiene datos en
    # disco, se omite sin abrir sesión ni sondear (ahorra ~9 requests/empresa).
    # Se auto-sana: si ya tiene datos en disco, se saca del cache y se procesa.
    force_recheck = os.environ.get("CMF_NO_XBRL_RECHECK", "0") == "1"
    base_dir = Path("./data/XBRL") / _period_dir_name(mode)
    has_local = _has_local_data(base_dir, rut)
    if has_local and _is_cached_no_xbrl(rut):
        _unmark_no_xbrl(rut)  # apareció con datos → ya no es "sin XBRL"
    if (not has_local) and (not force_recheck) and _is_cached_no_xbrl(rut):
        dv_csv, name_csv = _company_info_from_csv(rut, companies_csv or _DEF_CSV)
        rc = f"{rut}-{dv_csv}" if dv_csv else rut
        logger.info(
            "[http] %s (%s): omitida — cacheada como entidad sin XBRL "
            "(usa CMF_NO_XBRL_RECHECK=1 o borra data/no_xbrl_companies.json para reintentar)",
            name_csv or rut, rc)
        if progress_hook:
            try:
                progress_hook(rut, 0, 0, None, None, 0, "skipped_no_xbrl")
            except Exception:
                pass
        safe = _safe_name(name_csv) if name_csv else f"Empresa_RUT_{rut}"
        return str((base_dir / f"{rc}_{safe}").resolve()), []

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

    # --- Poda temporal: nunca pedir un período cuyo trimestre aún no ha
    #     cerrado; ese informe todavía no puede existir en la CMF. Es 100%
    #     seguro (solo descarta períodos imposibles, jamás datos publicables)
    #     y evita requests inútiles a, p. ej., 2026-09/2026-12 en julio de 2026.
    today = _date.today()
    future = [p for p in pending if _quarter_end(*p) > today]
    if future:
        pending = [p for p in pending if _quarter_end(*p) <= today]
        logger.info("[http] %s: %d período(s) futuro(s) omitido(s) (trimestre no cerrado): %s",
                    rut_completo, len(future),
                    ", ".join(f"{y}-{m:02d}" for y, m in sorted(future)))

    # --- Corto-circuito del borde reciente (leading edge) ---
    # La CMF publica en orden cronológico ascendente: si el trimestre más
    # antiguo del borde reciente no existe, los posteriores tampoco. Definimos
    # como "borde" los períodos del año en curso/futuros y los más nuevos que
    # lo ya descargado en disco; se procesan en orden ASCENDENTE y nos
    # detenemos en el primer faltante (los siguientes se dan por inexistentes).
    # El histórico ("backfill", con posibles huecos pre-listado) se descarga en
    # paralelo como siempre, sin corto-circuito, para no perder datos.
    existing_yyyymm = _existing_periods_on_disk(target_dir, rut)
    latest_existing = max((int(p) for p in existing_yyyymm), default=None)
    current_year = today.year

    def _is_leading(period: tuple[int, int]) -> bool:
        y, m = period
        if y >= current_year:
            return True
        if latest_existing is not None and int(f"{y}{m:02d}") > latest_existing:
            return True
        return False

    leading = sorted((p for p in pending if _is_leading(p)), key=lambda p: (p[0], p[1]))
    backfill = [p for p in pending if not _is_leading(p)]

    total = len(pending)
    logger.info("[http] %s (%s): %d períodos a bajar (de %d) — borde=%d, histórico=%d, %d workers",
                name, rut_completo, total, len(periods), len(leading), len(backfill), max_workers)
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

    def _fetch(year: int, month: int) -> tuple[Optional[str], bool]:
        """Devuelve ``(path|None, definitive)``.

        - ``(path, True)``  → descargado OK.
        - ``(None, True)``  → CONCLUYENTE sin XBRL: respuestas HTTP 200 limpias
          (sin bloqueo) que simplemente no traen el enlace XBRL.
        - ``(None, False)`` → INCONCLUYENTE: hubo excepción / posible bloqueo /
          timeout tras los reintentos del throttle, o había enlace pero la
          descarga no fue un ZIP. NO debe tratarse como ausencia (no cachear).

        `polite_request` ya reintenta y hace cooldown ante 403/429/HTML-bloqueo;
        si aún así falla, lanza excepción → aquí se marca como inconcluso.
        """
        yyyymm = f"{year}{month:02d}"
        had_error = False
        # POST del período. Primario: Consolidado/IFRS; fallback: Individual/IFRS.
        for tipo in ("C", "I"):
            try:
                resp = _polite_request(session, "POST", base, data={
                    "forma": "P", "aa": str(year), "mm": f"{month:02d}",
                    "tipo": tipo, "tipo_norma": "IFRS",
                }, timeout=http_timeout)
            except Exception as e:
                logger.debug("[http] %s %s tipo %s POST inconcluso: %s", rut, yyyymm, tipo, e)
                had_error = True
                continue
            href = _find_xbrl_link(resp.text)
            if not href:
                continue  # HTTP 200 limpio sin enlace = ausencia para este tipo
            dl = urljoin(base, href)
            try:
                rr = _polite_request(session, "GET", dl,
                                     timeout=http_timeout,
                                     headers={"Referer": base})
            except Exception as e:
                logger.debug("[http] %s %s GET inconcluso: %s", rut, yyyymm, e)
                had_error = True
                continue
            if rr.status_code != 200 or rr.content[:2] != b"PK":
                # Había enlace pero la descarga no fue un ZIP: sospechoso (una
                # entidad sin XBRL no tendría enlace) → inconcluso, no ausencia.
                logger.debug("[http] %s %s enlace presente pero descarga no-ZIP (status=%s)",
                             rut, yyyymm, rr.status_code)
                had_error = True
                continue
            ext = _extract_zip(rr.content, target_dir, rut, yyyymm)
            if ext is not None:
                return str(ext), True
            had_error = True  # ZIP inválido/corrupto → reintentar, no es ausencia
        # No hubo descarga: concluyente SOLO si no hubo ningún error/bloqueo.
        return None, (not had_error)

    def _emit_progress(year, month, res, status_override=None):
        nonlocal done
        with lock_done:
            done += 1
            cur = done
        eta = None
        if cur and cur < total:
            per = (time.time() - start_ts) / cur
            eta = per * (total - cur)
        if progress_hook:
            try:
                status = status_override or ("period_completed" if res else "in_progress")
                progress_hook(rut, cur, total, year, month, eta, status)
            except Exception:
                pass

    def _task(period: tuple[int, int]):
        year, month = period
        res, _definitive = _fetch(year, month)
        _emit_progress(year, month, res)
        if not res:
            # DEBUG, no WARNING: un período sin XBRL es normal (pre-listado o
            # entidad que no publica). El resumen por empresa va al final.
            logger.debug("[http] sin XBRL: %s %s-%02d (%s)", rut, year, month,
                         "concluyente" if _definitive else "inconcluso")
        return res

    # --- Compuerta anti-"entidad sin XBRL" (solo si NO hay datos en disco) ---
    # Muchos fondos de inversión y entidades del set IFRS del CSV simplemente NO
    # publican XBRL en la CMF. Sin esto se sondean sus ~48 períodos y todos
    # fallan (lento y ruidoso). Para una empresa SIN datos locales, sondeamos
    # primero sus períodos MÁS RECIENTES (descendente) y paramos en el primer
    # acierto; si NINGUNO de los `CMF_HTTP_FRONTIER_PROBE` (def. 8) más recientes
    # tiene XBRL, es una entidad que no publica XBRL → se omite el resto. Las
    # empresas que sí publican tienen datos recientes y pasan de inmediato.
    probed: set[tuple[int, int]] = set()
    company_has_no_xbrl = False
    if latest_existing is None and pending:
        gate_n = max(1, int(os.environ.get("CMF_HTTP_FRONTIER_PROBE", "8")))
        gate_periods = sorted(pending, key=lambda p: (p[0], p[1]), reverse=True)[:gate_n]
        gate_hit = False
        gate_any_error = False  # ¿algún sondeo fue INCONCLUYENTE (posible bloqueo)?
        for (gy, gm) in gate_periods:
            r, definitive = _fetch(gy, gm)
            probed.add((gy, gm))
            _emit_progress(gy, gm, r)
            if r:
                downloaded.append(r)
                gate_hit = True
                break
            if not definitive:
                gate_any_error = True
        if not gate_hit:
            company_has_no_xbrl = True  # se omite el resto de esta corrida
            skipped = [p for p in pending if p not in probed]
            if gate_any_error:
                # Al menos un sondeo fue inconcluso (posible bloqueo/timeout de la
                # CMF). NO concluimos "sin XBRL" ni cacheamos: se reintenta en la
                # próxima corrida. Así un bloqueo NUNCA marca a una empresa real.
                logger.warning(
                    "[http] %s (%s): sondeo reciente INCONCLUYENTE (posible bloqueo/"
                    "timeout de la CMF) → NO se cachea, se reintentará en la próxima corrida",
                    name, rut_completo)
            else:
                # Todas las respuestas fueron HTTP 200 limpias sin enlace XBRL:
                # ausencia real → cachear para no re-sondear.
                logger.info(
                    "[http] %s (%s): sin XBRL en los %d período(s) más reciente(s) → "
                    "entidad que no publica XBRL, se omiten %d período(s) histórico(s)",
                    name, rut_completo, len(probed), len(skipped),
                )
                _mark_no_xbrl(rut, name, f"sin XBRL en {len(probed)} períodos recientes")
            for (sy, sm) in skipped:
                _emit_progress(sy, sm, None, status_override="skipped_period")

    if not company_has_no_xbrl:
        # Excluir de borde/histórico los períodos ya sondeados por la compuerta.
        if probed:
            leading = [p for p in leading if p not in probed]
            backfill = [p for p in backfill if p not in probed]

        # Borde reciente: secuencial y ascendente, con corto-circuito en el
        # primer faltante (los períodos posteriores se dan por no publicados).
        for i, (year, month) in enumerate(leading):
            res, _def = _fetch(year, month)
            _emit_progress(year, month, res)
            if res:
                downloaded.append(res)
                continue
            # Primer faltante del borde → omitir el resto del borde.
            rest = leading[i + 1:]
            logger.info(
                "[http] %s %s-%02d sin XBRL en el borde reciente → se omiten %d "
                "período(s) posterior(es) aún no publicado(s): %s",
                rut, year, month, len(rest),
                ", ".join(f"{y}-{m:02d}" for y, m in rest) or "(ninguno)",
            )
            for (ry, rm) in rest:
                _emit_progress(ry, rm, None, status_override="skipped_period")
            break

        # Histórico: en paralelo, sin corto-circuito.
        if backfill:
            with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
                futs = [ex.submit(_task, p) for p in backfill]
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
