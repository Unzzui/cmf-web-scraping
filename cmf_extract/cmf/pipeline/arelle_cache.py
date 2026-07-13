"""Pre-poblado del HTTP cache de Arelle con taxonomías CMF.

Arelle se cuelga / recibe 403 al pedir taxonomías de `http://www.cmfchile.cl/...`
porque CMF redirige 301 → https y throttea. Aquí descargamos lo que falta usando
``requests`` (que sí sigue redirects), guardando los archivos en la estructura
que Arelle espera (``~/.config/arelle/cache/{http,https}/<host>/<path>``).

Uso típico desde el pipeline de consolidación::

    from cmf.pipeline.arelle_cache import populate_arelle_cache
    n_descargadas = populate_arelle_cache(company_dir, progress_cb)

La función es idempotente: si los archivos ya están cacheados, no hace nada.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Callable, Optional, Set
from urllib.parse import urljoin, urlparse


_SCHEMA_LOC_RE = re.compile(r'schemaLocation="([^"]+)"')
_HREF_RE = re.compile(r'\bxlink:href="([^"#]+)')
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

ProgressCallback = Callable[[str, int, int], None]

_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "Chrome/120.0 Safari/537.36"
)

_CACHE_ROOT = Path(os.path.expanduser("~/.config/arelle/cache"))

# URLs que ya fallaron en esta corrida. Las taxonomías CMF inalcanzables son las
# MISMAS para todas las empresas, y sin esto se reintentaban (con timeout de red)
# una vez por empresa: con 232 empresas × ~177 URLs muertas el pre-poblado pasaba
# a dominar el tiempo del pipeline. Se intenta una vez por proceso y basta.
_FAILED_URLS: Set[str] = set()


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def arelle_cache_path(url: str) -> Path:
    """Devuelve la ruta donde Arelle guarda este URL en su HTTP cache."""
    p = urlparse(url)
    scheme_dir = "https" if p.scheme == "https" else "http"
    return _CACHE_ROOT / scheme_dir / p.netloc / p.path.lstrip("/")


def _cached_path_either_scheme(url: str) -> Optional[Path]:
    """Ruta del archivo cacheado (http:// o https://, cualquiera vale) o None."""
    primary = arelle_cache_path(url)
    if primary.exists():
        return primary
    alt_str = str(primary)
    if "/cache/http/" in alt_str:
        alt = Path(alt_str.replace("/cache/http/", "/cache/https/"))
    elif "/cache/https/" in alt_str:
        alt = Path(alt_str.replace("/cache/https/", "/cache/http/"))
    else:
        return None
    return alt if alt.exists() else None


def _cached_either_scheme(url: str) -> bool:
    """True si la URL está cacheada en http:// o https:// (cualquiera vale)."""
    return _cached_path_either_scheme(url) is not None


# ---------------------------------------------------------------------------
# XSD scanning
# ---------------------------------------------------------------------------


def _xsd_base_url(xsd_path: Path) -> Optional[str]:
    """Si el .xsd vive dentro del cache local, deriva su URL original.

    Necesario para resolver imports relativos (e.g. ``../foo.xsd``) dentro de
    taxonomías cacheadas.
    """
    try:
        rel = xsd_path.relative_to(_CACHE_ROOT)
    except ValueError:
        return None
    parts = rel.parts
    if not parts or parts[0] not in ("http", "https"):
        return None
    scheme, netloc, *rest = parts
    return f"{scheme}://{netloc}/" + "/".join(rest)


def collect_xsd_imports(xsd_path: Path) -> Set[str]:
    """Devuelve los URLs (http/https) que importa un .xsd local."""
    try:
        text = xsd_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return set()
    base = _xsd_base_url(xsd_path)
    urls: Set[str] = set()
    for pattern in (_SCHEMA_LOC_RE, _HREF_RE):
        for m in pattern.finditer(text):
            loc = m.group(1)
            if _URL_RE.match(loc):
                urls.add(loc)
            elif base and not loc.startswith("#"):
                urls.add(urljoin(base, loc))
    return urls


def _scan_company_xsds(company_dir: Path) -> Set[str]:
    """Recolecta URLs referenciados por todos los .xsd de la empresa."""
    pending: Set[str] = set()
    for xsd in company_dir.rglob("*.xsd"):
        pending |= collect_xsd_imports(xsd)
    return pending


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------


def _build_session():
    import requests  # local import: módulo opcional

    s = requests.Session()
    s.headers.update({
        "User-Agent": _USER_AGENT,
        "Accept": "text/xml,application/xml,*/*",
    })
    return s


# Sólo estos códigos significan "el archivo no existe". Todo lo demás (5xx, 429,
# timeouts, conexiones cortadas) es transitorio y SE REINTENTA.
_STATUS_DEFINITIVOS = {403, 404, 410}


def _fetch_with_retry(sess, url: str, intentos: int = 3) -> Optional[bytes]:
    """Descarga una URL, reintentando ante fallos transitorios.

    Distinguir "muerta" de "falló una vez" es crítico: esta descarga es un BFS sobre
    la clausura de la taxonomía, así que si una URL se marca como muerta por un timeout
    de red, TODO lo que cuelga de ella deja de descargarse y el cache queda truncado.
    Arelle offline entonces no resuelve el DTS, exporta CERO hechos y termina con exit
    0: el fallo es invisible hasta que aparecen huecos en los Excel.
    """
    import time as _time

    for intento in range(intentos):
        try:
            r = sess.get(url, timeout=20, allow_redirects=True)
            if r.status_code == 200 and r.content:
                return r.content
            if r.status_code in _STATUS_DEFINITIVOS:
                _FAILED_URLS.add(url)  # no existe: no reintentar nunca
                return None
            # 5xx / 429 / respuesta vacía: transitorio
        except Exception:
            pass  # timeout, DNS, conexión cortada: transitorio
        if intento < intentos - 1:
            _time.sleep(0.5 * (2 ** intento))

    # Agotados los reintentos: NO se agrega a _FAILED_URLS, para que la próxima
    # empresa (o la próxima corrida) vuelva a intentarlo.
    return None


def _download_missing(urls: list[str], cb: Optional[ProgressCallback],
                      company_name: str) -> tuple[int, int, Set[str]]:
    """Descarga URLs faltantes en el cache. Devuelve (ok, errors, new_deps).

    ``new_deps`` son URLs descubiertas dentro de los .xsd recién descargados,
    para iterar (BFS).
    """
    try:
        sess = _build_session()
    except Exception:
        return 0, 0, set()

    ok, fail = 0, 0
    new_deps: Set[str] = set()
    for i, url in enumerate(urls, 1):
        cache_path = arelle_cache_path(url)
        try:
            r = sess.get(url, timeout=20, allow_redirects=True)
            if r.status_code == 200 and r.content:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_bytes(r.content)
                ok += 1
                if url.lower().endswith(".xsd"):
                    for u in collect_xsd_imports(cache_path):
                        if not _cached_either_scheme(u):
                            new_deps.add(u)
            else:
                fail += 1
        except Exception:
            fail += 1
        if cb and i % 10 == 0:
            cb(f"{company_name} - Cache: {ok} OK, {fail} fail", ok, len(urls))
    return ok, fail, new_deps


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def populate_arelle_cache(company_dir: Path,
                          progress_cb: Optional[ProgressCallback] = None,
                          max_iterations: int = 8) -> int:
    """Pre-puebla el HTTP cache de Arelle con todas las taxonomías que
    referencian los .xsd locales (transitivamente).

    BFS sobre la clausura completa: también re-escanea archivos YA cacheados
    en busca de dependencias faltantes (si una corrida anterior quedó a
    medias, los huecos profundos no se veían), y escanea linkbases ``.xml``
    además de ``.xsd``. Sin esto, Arelle offline termina "ok" (exit 0) pero
    con IOerror por archivos faltantes → facts/labels incompletos.

    Retorna la cantidad de URLs descargadas.

    Parameters
    ----------
    company_dir:
        Directorio de la empresa que contiene los datasets XBRL extraídos.
    progress_cb:
        Callback opcional ``(message, current, total)`` para reportar avance.
    max_iterations:
        Conservado por compatibilidad (el BFS con conjunto `seen` ya no puede
        ciclar).
    """
    from collections import deque

    company_name = company_dir.name
    pending = deque(sorted(_scan_company_xsds(company_dir)))
    seen: Set[str] = set()
    downloaded = 0
    failed = 0
    sess = None

    while pending:
        url = pending.popleft()
        if url in seen or url in _FAILED_URLS:
            continue
        seen.add(url)

        path = _cached_path_either_scheme(url)
        if path is None:
            if sess is None:
                try:
                    sess = _build_session()
                except Exception:
                    break  # sin requests no podemos descargar nada
            cache_path = arelle_cache_path(url)
            content = _fetch_with_retry(sess, url)
            if content is None:
                failed += 1
                continue
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(content)
            downloaded += 1
            path = cache_path
            if progress_cb and downloaded % 10 == 0:
                progress_cb(f"{company_name} - Cache: {downloaded} OK, {failed} fail",
                            downloaded, downloaded + len(pending))

        # Escanear también linkbases .xml: referencian esquemas vía href.
        if path.suffix.lower() in (".xsd", ".xml"):
            for u in collect_xsd_imports(path):
                if u not in seen:
                    pending.append(u)

    if (downloaded or failed) and progress_cb:
        progress_cb(
            f"{company_name} - Cache poblado: {downloaded} OK, "
            f"{failed} con error",
            downloaded, downloaded,
        )
    return downloaded
