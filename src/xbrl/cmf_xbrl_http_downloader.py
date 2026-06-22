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
import random
import re
import threading
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

# Rotación leve de User-Agents para no enviar siempre exactamente la misma firma.
_UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]
_UA = _UA_POOL[0]  # compat con código legacy
_DEF_CSV = "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
_RUT_DV_RE = re.compile(r"(\d{7,8})\s*-\s*([\dkK])")

# -------------------- Throttle + cooldown global (cross-empresa) ---------- #
# Cap total de requests en vuelo a CMF independiente de cuántas empresas se
# descarguen en paralelo. Override por env CMF_HTTP_MAX_INFLIGHT.
_GLOBAL_INFLIGHT = threading.BoundedSemaphore(
    max(1, int(os.environ.get("CMF_HTTP_MAX_INFLIGHT", "6")))
)
_COOLDOWN_LOCK = threading.Lock()
_COOLDOWN_UNTIL: float = 0.0  # epoch seconds; antes de esto, nadie envía

# Estado de "salud" del backoff: si seguimos viendo bloqueos, el siguiente
# cooldown se alarga (exp backoff cross-empresa). Se resetea tras éxitos.
_BACKOFF_LOCK = threading.Lock()
_CONSEC_BLOCKS: int = 0


def _trigger_cooldown(seconds: float, reason: str) -> None:
    """Programa un cooldown global. Sólo lo extiende, nunca lo acorta."""
    global _COOLDOWN_UNTIL
    until = time.time() + max(0.0, float(seconds))
    with _COOLDOWN_LOCK:
        if until > _COOLDOWN_UNTIL:
            _COOLDOWN_UNTIL = until
            logger.warning("[http] cooldown global %.1fs (%s)", seconds, reason)


def _wait_cooldown() -> None:
    """Bloquea al hilo actual hasta que termine el cooldown global, si lo hay."""
    while True:
        with _COOLDOWN_LOCK:
            wait = _COOLDOWN_UNTIL - time.time()
        if wait <= 0:
            return
        time.sleep(min(wait, 2.0))


def _note_block() -> float:
    """Anota un bloqueo y devuelve el cooldown sugerido (segundos)."""
    global _CONSEC_BLOCKS
    with _BACKOFF_LOCK:
        _CONSEC_BLOCKS += 1
        n = _CONSEC_BLOCKS
    # 30s, 60s, 120s, 240s, 480s (cap 600s)
    return min(600.0, 30.0 * (2 ** (n - 1))) + random.uniform(0, 10)


def _note_success() -> None:
    """Anota una respuesta sana; relaja el contador de bloqueos consecutivos."""
    global _CONSEC_BLOCKS
    with _BACKOFF_LOCK:
        if _CONSEC_BLOCKS:
            _CONSEC_BLOCKS = max(0, _CONSEC_BLOCKS - 1)


_BLOCK_KEYWORDS = (
    "captcha", "blocked", "forbidden", "intrusion",
    "temporarily unavailable", "acceso denegado", "rate limit",
)


def _looks_blocked(resp: requests.Response) -> bool:
    """Detecta páginas-trampa: 403/429 o HTML con palabras-clave sospechosas."""
    if resp.status_code in (403, 429):
        return True
    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" in ctype:
        sample = (resp.text or "")[:3000].lower()
        if any(w in sample for w in _BLOCK_KEYWORDS):
            return True
    return False


def _retry_after_seconds(resp: requests.Response, default: float) -> float:
    """Lee el header Retry-After (segundos o HTTP date). Cae a default."""
    ra = resp.headers.get("Retry-After")
    if not ra:
        return default
    try:
        return max(float(ra), default)
    except (TypeError, ValueError):
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(ra)
            return max((dt.timestamp() - time.time()), default)
        except Exception:
            return default


def _polite_request(session: requests.Session, method: str, url: str,
                    *, max_attempts: int = 6, **kwargs) -> requests.Response:
    """Envía con throttle global, cooldown automático y reintento ante bloqueos.

    Lanza requests.RequestException si tras *max_attempts* sigue bloqueado.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        _wait_cooldown()
        with _GLOBAL_INFLIGHT:
            # jitter dentro del slot para evitar ráfagas perfectamente alineadas
            time.sleep(random.uniform(0.05, 0.30))
            try:
                resp = session.request(method, url, **kwargs)
            except requests.RequestException as e:
                last_exc = e
                wait = min(30.0, 1.5 ** attempt) + random.uniform(0, 1.5)
                logger.debug("[http] %s %s error red: %s (attempt %d) sleep %.1fs",
                             method, url, e, attempt, wait)
                time.sleep(wait)
                continue

        if _looks_blocked(resp):
            cd = _retry_after_seconds(resp, _note_block())
            _trigger_cooldown(cd, f"HTTP {resp.status_code} en {url[:60]}")
            # consume el body para liberar conexión y reintenta
            try:
                resp.content  # noqa: B018
            except Exception:
                pass
            continue

        _note_success()
        return resp

    if last_exc is not None:
        raise last_exc
    raise requests.RequestException("Bloqueo persistente tras reintentos")


def _entidad_url(rut: str) -> str:
    return (f"https://www.cmfchile.cl/institucional/mercados/entidad.php"
            f"?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI"
            f"&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3")


def _build_session(max_workers: int, retries: int = 3) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(_UA_POOL),
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if Retry is not None:
        # status_forcelist sin 403/429: esos los maneja _polite_request con
        # cooldown global; aquí sólo retry para errores transitorios de red.
        retry = Retry(total=retries, connect=retries, read=retries, status=retries,
                      backoff_factor=0.8, status_forcelist=[500, 502, 503, 504],
                      allowed_methods=["GET", "POST"],
                      respect_retry_after_header=True)
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
    return str(target_dir.resolve()), downloaded
