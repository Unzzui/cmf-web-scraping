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


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def arelle_cache_path(url: str) -> Path:
    """Devuelve la ruta donde Arelle guarda este URL en su HTTP cache."""
    p = urlparse(url)
    scheme_dir = "https" if p.scheme == "https" else "http"
    return _CACHE_ROOT / scheme_dir / p.netloc / p.path.lstrip("/")


def _cached_either_scheme(url: str) -> bool:
    """True si la URL está cacheada en http:// o https:// (cualquiera vale)."""
    primary = arelle_cache_path(url)
    if primary.exists():
        return True
    alt_str = str(primary)
    if "/cache/http/" in alt_str:
        alt = Path(alt_str.replace("/cache/http/", "/cache/https/"))
    elif "/cache/https/" in alt_str:
        alt = Path(alt_str.replace("/cache/https/", "/cache/http/"))
    else:
        return False
    return alt.exists()


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

    Retorna la cantidad de URLs descargadas.

    Parameters
    ----------
    company_dir:
        Directorio de la empresa que contiene los datasets XBRL extraídos.
    progress_cb:
        Callback opcional ``(message, current, total)`` para reportar avance.
    max_iterations:
        Cap de iteraciones del BFS (para evitar loops infinitos en casos
        patológicos).
    """
    company_name = company_dir.name
    pending = _scan_company_xsds(company_dir)
    to_download = sorted(u for u in pending if not _cached_either_scheme(u))

    if not to_download:
        return 0

    if progress_cb:
        progress_cb(
            f"{company_name} - Cache Arelle: descargando "
            f"{len(to_download)} taxonomías faltantes",
            0, len(to_download),
        )

    total_downloaded = 0
    total_failed = 0
    for _ in range(max_iterations):
        if not to_download:
            break
        ok, fail, new_deps = _download_missing(to_download, progress_cb,
                                                company_name)
        total_downloaded += ok
        total_failed += fail
        to_download = sorted(new_deps)

    if progress_cb:
        progress_cb(
            f"{company_name} - Cache poblado: {total_downloaded} OK, "
            f"{total_failed} con error",
            total_downloaded, total_downloaded,
        )
    return total_downloaded
