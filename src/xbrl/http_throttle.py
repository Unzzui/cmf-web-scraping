"""Throttle global + cooldown automático para clientes HTTP de la CMF.

La CMF (`cmfchile.cl`) bloquea / throttea fácilmente requests sostenidos.
Este módulo provee:

* **`GLOBAL_INFLIGHT`**: ``BoundedSemaphore`` cross-empresa que limita el total
  de requests concurrentes (override por env ``CMF_HTTP_MAX_INFLIGHT``,
  default 6).

* **Cooldown global**: ante 403/429/HTML-bloqueado, ``trigger_cooldown`` pausa
  a todos los workers por N segundos. Honra ``Retry-After``.

* **`polite_request`**: helper que envuelve ``session.request`` aplicando
  throttle, cooldown, jitter (50-300ms) y reintentos.

* **`build_polite_session`**: ``requests.Session`` con retries para errores
  transitorios (no 403/429, que se manejan a nivel cooldown), pool de
  conexiones dimensionado y rotación de User-Agent.

Uso:

    from xbrl.http_throttle import build_polite_session, polite_request

    sess = build_polite_session(max_workers=3)
    resp = polite_request(sess, "GET", url, timeout=30)
"""

from __future__ import annotations

import logging
import os
import random
import threading
import time
from typing import Optional

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None  # type: ignore


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User-Agent rotation
# ---------------------------------------------------------------------------

UA_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/121.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:120.0) Gecko/20100101 Firefox/120.0",
]


# ---------------------------------------------------------------------------
# Throttle global y estado de cooldown
# ---------------------------------------------------------------------------

GLOBAL_INFLIGHT = threading.BoundedSemaphore(
    max(1, int(os.environ.get("CMF_HTTP_MAX_INFLIGHT", "6")))
)

_COOLDOWN_LOCK = threading.Lock()
_COOLDOWN_UNTIL: float = 0.0  # epoch seconds; antes de esto, nadie envía

_BACKOFF_LOCK = threading.Lock()
_CONSEC_BLOCKS: int = 0


def trigger_cooldown(seconds: float, reason: str) -> None:
    """Programa un cooldown global. Sólo lo extiende, nunca lo acorta."""
    global _COOLDOWN_UNTIL
    until = time.time() + max(0.0, float(seconds))
    with _COOLDOWN_LOCK:
        if until > _COOLDOWN_UNTIL:
            _COOLDOWN_UNTIL = until
            logger.warning("[http] cooldown global %.1fs (%s)", seconds, reason)


def wait_cooldown() -> None:
    """Bloquea al hilo actual hasta que termine el cooldown global, si lo hay."""
    while True:
        with _COOLDOWN_LOCK:
            wait = _COOLDOWN_UNTIL - time.time()
        if wait <= 0:
            return
        time.sleep(min(wait, 2.0))


def note_block() -> float:
    """Anota un bloqueo y devuelve el cooldown sugerido (segundos)."""
    global _CONSEC_BLOCKS
    with _BACKOFF_LOCK:
        _CONSEC_BLOCKS += 1
        n = _CONSEC_BLOCKS
    # 30s, 60s, 120s, 240s, 480s (cap 600s) + jitter
    return min(600.0, 30.0 * (2 ** (n - 1))) + random.uniform(0, 10)


def note_success() -> None:
    """Relaja el contador de bloqueos consecutivos."""
    global _CONSEC_BLOCKS
    with _BACKOFF_LOCK:
        if _CONSEC_BLOCKS:
            _CONSEC_BLOCKS = max(0, _CONSEC_BLOCKS - 1)


# ---------------------------------------------------------------------------
# Block detection
# ---------------------------------------------------------------------------

BLOCK_KEYWORDS = (
    "captcha", "blocked", "forbidden", "intrusion",
    "temporarily unavailable", "acceso denegado", "rate limit",
)


def looks_blocked(resp: requests.Response) -> bool:
    """Detecta páginas-trampa: 403/429 o HTML con palabras-clave sospechosas."""
    if resp.status_code in (403, 429):
        return True
    ctype = resp.headers.get("Content-Type", "").lower()
    if "text/html" in ctype:
        sample = (resp.text or "")[:3000].lower()
        if any(w in sample for w in BLOCK_KEYWORDS):
            return True
    return False


def retry_after_seconds(resp: requests.Response, default: float) -> float:
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


# ---------------------------------------------------------------------------
# Session + request helper
# ---------------------------------------------------------------------------


def build_polite_session(max_workers: int, retries: int = 3) -> requests.Session:
    """Sesión configurada con retries para errores transitorios (5xx) y
    pool de conexiones dimensionado a ``max_workers``.

    NO incluye 403/429 en el ``status_forcelist`` porque esos los maneja
    ``polite_request`` con cooldown global.
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": random.choice(UA_POOL),
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    if Retry is not None:
        retry = Retry(
            total=retries, connect=retries, read=retries, status=retries,
            backoff_factor=0.8,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
            respect_retry_after_header=True,
        )
        pool_size = max(8, max_workers * 2)
        adapter = HTTPAdapter(
            pool_connections=pool_size, pool_maxsize=pool_size, max_retries=retry,
        )
        s.mount("https://", adapter)
        s.mount("http://", adapter)
    return s


def polite_request(session: requests.Session, method: str, url: str,
                   *, max_attempts: int = 6, **kwargs) -> requests.Response:
    """Envía con throttle global, cooldown automático y reintento ante bloqueos.

    Lanza ``requests.RequestException`` si tras *max_attempts* sigue bloqueado.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, max_attempts + 1):
        wait_cooldown()
        with GLOBAL_INFLIGHT:
            # Jitter dentro del slot para evitar ráfagas perfectamente alineadas.
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

        if looks_blocked(resp):
            cd = retry_after_seconds(resp, note_block())
            trigger_cooldown(cd, f"HTTP {resp.status_code} en {url[:60]}")
            # Consume el body para liberar conexión y reintenta
            try:
                resp.content  # noqa: B018
            except Exception:
                pass
            continue

        note_success()
        return resp

    if last_exc is not None:
        raise last_exc
    raise requests.RequestException("Bloqueo persistente tras reintentos")
