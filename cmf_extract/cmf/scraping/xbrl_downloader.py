#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMF XBRL Downloader
Descarga archivos XBRL desde la CMF para análisis financiero.
Adaptado para cmf/ package - paths configurables via CMFConfig.
"""

import os
import time
import logging
import pandas as pd
import re
import requests
from urllib.parse import urljoin, urlparse
import zipfile
import shutil
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Tuple, Dict
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select
    from selenium.webdriver.chrome.options import Options
    from selenium.common.exceptions import (
        TimeoutException, ElementClickInterceptedException, NoSuchElementException
    )
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

# Configurar logging (incluye ID de hilo para depurar concurrencia)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [WORKER %(thread)d] | %(message)s'
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Unavailable-periods cache
# ---------------------------------------------------------------------------
import json
import threading

_CACHE_LOCK = threading.RLock()  # RLock: reentrant — _mark_unavailable → _save_cache


def _cache_path() -> Path:
    """Return path to the unavailable-periods cache file."""
    from cmf.config import CMFConfig
    return CMFConfig().repo_root / "data" / "unavailable_periods.json"


def _load_cache() -> dict[str, list[str]]:
    """Load the cache; returns {} on any error."""
    p = _cache_path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache: dict[str, list[str]]) -> None:
    """Persist the cache to disk (thread-safe)."""
    p = _cache_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with _CACHE_LOCK:
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.debug(f"Could not save unavailable-periods cache: {e}")


def _mark_unavailable(rut: str, year: int, month: int) -> None:
    """Record a (rut, period) as unavailable in the cache."""
    period = f"{year}{month:02d}"
    with _CACHE_LOCK:
        cache = _load_cache()
        key = str(rut)
        periods = set(cache.get(key, []))
        if period not in periods:
            periods.add(period)
            cache[key] = sorted(periods)
            _save_cache(cache)


def _get_unavailable(rut: str) -> set[str]:
    """Return set of YYYYMM strings known to be unavailable for *rut*."""
    cache = _load_cache()
    return set(cache.get(str(rut), []))


# ---------------------------------------------------------------------------
# Sleep factor – scale all navigation sleeps via env var
# ---------------------------------------------------------------------------
def _sleep(seconds: float) -> None:
    """Sleep for *seconds* scaled by ``CMF_XBRL_SLEEP_FACTOR`` (default 1.0)."""
    factor = float(os.environ.get("CMF_XBRL_SLEEP_FACTOR", "1.0"))
    time.sleep(seconds * max(0.1, factor))


# ---------------------------------------------------------------------------
# Extracted helpers (previously nested inside download_cmf_xbrl)
# ---------------------------------------------------------------------------

def _resolve_company_info(rut_numero: str) -> tuple[str | None, str | None]:
    """Look up DV and company name from the companies CSV.

    Returns ``(dv, company_name)`` – either may be ``None``.
    """
    try:
        from cmf.config import CMFConfig
        _cfg = CMFConfig()
        csv_path = str(_cfg.companies_csv)
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            match = df[df['RUT_Numero'].astype(str) == str(rut_numero)]
            if not match.empty:
                dv = str(match.iloc[0]['DV']).strip()
                company_name = None
                for col in ['Empresa', 'Nombre', 'RazonSocial', 'Entidad']:
                    if col in df.columns and not pd.isna(match.iloc[0].get(col)):
                        company_name = str(match.iloc[0][col]).strip()
                        break
                if dv and dv != 'nan':
                    logger.info(f"Información encontrada - RUT: {rut_numero}-{dv}, Empresa: {company_name}")
                    return dv, company_name
            logger.warning(f"No se encontró información completa para RUT {rut_numero} en el CSV")
        else:
            logger.warning(f"No se encontró archivo CSV: {csv_path}")
    except Exception as e:
        logger.warning(f"Error obteniendo información para RUT {rut_numero}: {e}")
    return None, None


def _compute_target_dir(
    rut: str,
    dv: str | None,
    company_name: str,
    mode: str,
) -> str:
    """Build the XBRL target directory path for a company + mode.

    If a directory for this RUT already exists (with a proper company name),
    reuses it instead of creating a new fallback-named one.

    Returns the absolute path (directory is created if needed).
    """
    safe_company_name = "".join(
        c for c in company_name if c.isalnum() or c in (' ', '-', '_')
    ).strip().replace(' ', '_')
    rut_completo = f"{rut}-{dv}" if dv else rut

    dir_map = {"total": "Total", "quarterly": "Trimestral", "annual": "Anual"}
    period_dir_name = dir_map.get(mode, "Total")

    try:
        from cmf.config import CMFConfig
        _xbrl_root = str(CMFConfig().xbrl_base_dir.parent)
    except Exception:
        _xbrl_root = "./data/XBRL"

    parent_dir = os.path.join(_xbrl_root, period_dir_name)

    # Check if a directory for this RUT already exists (e.g. from a
    # previous download with a resolved company name).  Reuse it instead
    # of creating a fallback "Empresa_RUT_..." stub.
    if os.path.isdir(parent_dir):
        prefix = f"{rut_completo}_"
        for entry in os.listdir(parent_dir):
            if entry.startswith(prefix) and os.path.isdir(os.path.join(parent_dir, entry)):
                existing = os.path.join(parent_dir, entry)
                logger.info(f"Reutilizando directorio existente: {existing}")
                return existing

    target_dir = os.path.join(parent_dir, f"{rut_completo}_{safe_company_name}")
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def _discover_existing_periods(base_dir: str) -> set[str]:
    """Return set of YYYYMM strings for ``*_extracted`` folders in *base_dir*."""
    existing: set[str] = set()
    pattern = re.compile(r"Estados_financieros_\(XBRL\)\d+_(\d{6})_extracted")
    try:
        if os.path.isdir(base_dir):
            for item in os.listdir(base_dir):
                if os.path.isdir(os.path.join(base_dir, item)):
                    m = pattern.search(item)
                    if m:
                        existing.add(m.group(1))
    except Exception as e:
        logger.warning(f"No se pudo explorar períodos existentes en {base_dir}: {e}")
    return existing


def _discover_existing_all_buckets(
    rut: str,
    rut_full: str | None,
    target_dir: str,
) -> set[str]:
    """Scan all bucket directories (Anual/Trimestral/Total) for existing periods."""
    found = _discover_existing_periods(target_dir)
    base_root = os.path.join("./data", "XBRL")
    for bucket in ("Anual", "Trimestral", "Total"):
        bucket_dir = os.path.join(base_root, bucket)
        if not os.path.isdir(bucket_dir):
            continue
        try:
            for sub in os.listdir(bucket_dir):
                sub_path = os.path.join(bucket_dir, sub)
                if not os.path.isdir(sub_path):
                    continue
                if sub.startswith(str(rut)) or (rut_full and sub.startswith(str(rut_full))):
                    found |= _discover_existing_periods(sub_path)
        except Exception:
            continue
    return found


def _create_browser(headless: bool, download_dir: str):
    """Create and return a configured Chrome WebDriver instance.

    Requires ``SELENIUM_AVAILABLE`` to be ``True``.
    """
    chrome_options = Options()
    prefs = {
        "download.default_directory": download_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    if headless:
        try:
            chrome_options.add_argument("--headless=new")
        except Exception:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        # Stability flags for concurrent instances
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        logger.info("Iniciando Chrome en modo headless")
    else:
        logger.info("Iniciando Chrome con ventana visible")

    return webdriver.Chrome(options=chrome_options)


def _compute_planned_periods(
    start_year: int,
    end_year: int,
    mode: str,
    step: int,
    quarterly: bool,
    rut: str,
    skip_existing: bool,
    existing_periods: set[str],
    skip_unavailable: bool,
    target_dir: str,
) -> tuple[list[tuple[int, int]], str, list[int], int]:
    """Compute and filter the list of ``(year, month)`` periods to process.

    Returns ``(planned_periods, period_type, months_to_process, iteration_step)``.
    """
    normalized_mode: str | None = None
    if mode in {"annual", "quarterly", "total"}:
        normalized_mode = mode
    else:
        normalized_mode = "quarterly" if quarterly else "annual"

    if normalized_mode == "total":
        months_to_process = [3, 6, 9, 12]
        period_type = "total"
        iteration_step = -1
    elif normalized_mode == "quarterly":
        months_to_process = [3, 6, 9, 12]
        period_type = "trimestral"
        iteration_step = step
    else:
        months_to_process = [12]
        period_type = "anual"
        iteration_step = step

    planned_periods: list[tuple[int, int]] = []
    for year in range(start_year, end_year - 1, iteration_step):
        for month in months_to_process:
            planned_periods.append((year, month))

    if skip_existing:
        before = len(planned_periods)
        planned_periods = [
            (y, m) for (y, m) in planned_periods
            if f"{y}{m:02d}" not in existing_periods
        ]
        skipped = before - len(planned_periods)
        if skipped > 0:
            logger.info(f"Omitiendo {skipped} período(s) ya existente(s) en {target_dir}")
        logger.info(f"Períodos existentes detectados: {len(existing_periods)} | Ejemplos: {sorted(list(existing_periods))[:8]}")

    if skip_unavailable:
        unavailable = _get_unavailable(rut)
        if unavailable:
            before_ua = len(planned_periods)
            planned_periods = [
                (y, m) for (y, m) in planned_periods
                if f"{y}{m:02d}" not in unavailable
            ]
            skipped_ua = before_ua - len(planned_periods)
            if skipped_ua > 0:
                logger.info(f"Omitiendo {skipped_ua} período(s) sin XBRL conocido (cache)")

    return planned_periods, period_type, months_to_process, iteration_step


# ---------------------------------------------------------------------------
# Download helpers (used by both sequential and parallel paths)
# ---------------------------------------------------------------------------

def _wait_for_download_and_move(
    downloads_dir: str,
    expected_rut: str,
    target_dir: str,
    timeout: int = 60,
) -> str | None:
    """Wait for a ZIP download to complete, then move it to *target_dir*.

    Returns the final file path on success, ``None`` on timeout.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            for file in os.listdir(downloads_dir):
                if file.startswith("Estados_financieros_(XBRL)") and file.endswith(".zip"):
                    file_path = os.path.join(downloads_dir, file)
                    if expected_rut and expected_rut not in file:
                        continue
                    if not file.endswith('.crdownload') and os.path.exists(file_path):
                        try:
                            with zipfile.ZipFile(file_path, 'r'):
                                pass  # readable → complete
                            target_path = os.path.join(target_dir, file)
                            if os.path.exists(target_path):
                                os.remove(target_path)
                            shutil.move(file_path, target_path)
                            logger.info(f"Archivo descargado y movido: {file}")
                            return target_path
                        except (zipfile.BadZipFile, PermissionError):
                            _sleep(1)
                            continue
        except Exception:
            pass
        _sleep(2)
    logger.warning(f"Timeout esperando descarga después de {timeout} segundos")
    return None


def _check_xbrl_link_available(driver) -> bool:
    """Return True if a XBRL download link is visible on the current page."""
    try:
        xbrl_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)")
        return len(xbrl_links) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Parallel browser worker
# ---------------------------------------------------------------------------

def _probe_periods_worker(
    rut: str,
    url: str,
    periods: list[tuple[int, int]],
    target_dir: str,
    existing_periods: set[str],
    headless: bool,
    downloads_dir: str,
    skip_existing: bool = True,
    progress_hook=None,
    progress_lock: threading.Lock | None = None,
    shared_counter: list[int] | None = None,
    total_periods: int = 0,
) -> list[str]:
    """Probe + download a subset of periods using a dedicated browser.

    Each thread gets its own Chrome instance.  Returns a list of
    downloaded file paths (ZIP or extracted directory).
    """
    import random

    worker_id = threading.get_ident()
    logger.info(f"[WORKER {worker_id}] Iniciando con {len(periods)} período(s)")

    driver = _create_browser(headless, downloads_dir)
    downloaded: list[str] = []

    try:
        # Set timeouts to prevent hangs
        driver.set_page_load_timeout(45)
        driver.set_script_timeout(20)

        # Navigate to the entity page (retry once on failure)
        for attempt in range(2):
            try:
                driver.get(url)
                wait = WebDriverWait(driver, 20)
                wait.until(EC.presence_of_element_located((By.ID, "fm")))
                break
            except Exception as nav_err:
                if attempt == 0:
                    logger.warning(f"[WORKER {worker_id}] Navegación falló, reintentando: {str(nav_err)[:100]}")
                    _sleep(3.0)
                else:
                    raise

        for year, month in periods:
            period_key = f"{year}{month:02d}"

            # Double-check existence (another worker may have downloaded it)
            if skip_existing and period_key in existing_periods:
                logger.info(f"[WORKER {worker_id}] Saltando {year}-{month:02d} (ya existe)")
                _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'skipped_period')
                continue

            try:
                # Small jitter to stagger concurrent requests
                _sleep(random.uniform(0.2, 0.5))

                # Always navigate fresh to the form page for each period.
                # Using driver.back() or URL checks is unreliable because
                # the results page is also on cmfchile.cl but lacks the form.
                driver.get(url)

                # Wait for form
                wait.until(EC.presence_of_element_located((By.ID, "fm")))

                # Select year
                Select(driver.find_element(By.ID, "aa")).select_by_visible_text(str(year))
                # Select month
                Select(driver.find_element(By.ID, "mm")).select_by_visible_text(f"{month:02d}")
                # Select tipo
                try:
                    Select(driver.find_element(By.NAME, "tipo")).select_by_visible_text("Consolidado")
                except Exception:
                    pass
                # Select norma
                try:
                    Select(driver.find_element(By.NAME, "tipo_norma")).select_by_visible_text("Estándar IFRS")
                except Exception:
                    pass

                # Submit
                submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                    _sleep(0.5)
                    submit_button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", submit_button)

                _sleep(2.0)  # reduced from 5.0

                # Check XBRL link
                if not _check_xbrl_link_available(driver):
                    logger.warning(f"[WORKER {worker_id}] No hay XBRL para {year}-{month:02d}")
                    _mark_unavailable(rut, year, month)
                    _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'no_xbrl')
                    continue

                # Click XBRL link
                try:
                    xbrl_link = wait.until(
                        EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)"))
                    )

                    # Check href for already-downloaded period
                    href = xbrl_link.get_attribute('href') or ''
                    m_link = re.search(r"(20\d{2})(0[1-9]|1[0-2])", href)
                    if m_link and skip_existing:
                        yyyymm_in_link = m_link.group(1) + m_link.group(2)
                        if yyyymm_in_link in existing_periods:
                            logger.info(f"[WORKER {worker_id}] Saltando {year}-{month:02d} (enlace {yyyymm_in_link} ya existe)")
                            _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'skipped_period')
                            continue

                    driver.execute_script("arguments[0].scrollIntoView(true);", xbrl_link)
                    _sleep(0.5)
                    try:
                        xbrl_link.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", xbrl_link)

                    moved = _wait_for_download_and_move(downloads_dir, rut, target_dir, timeout=60)
                    if moved:
                        downloaded.append(moved)
                        logger.info(f"[WORKER {worker_id}] Descarga OK {year}-{month:02d}")
                        _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'period_completed')
                    else:
                        logger.warning(f"[WORKER {worker_id}] Timeout descarga {year}-{month:02d}")
                        _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'timeout')

                except TimeoutException:
                    logger.warning(f"[WORKER {worker_id}] No se encontró enlace XBRL para {year}-{month:02d}")
                    _mark_unavailable(rut, year, month)
                    _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'no_xbrl')

            except Exception as e:
                err_str = str(e)
                logger.error(f"[WORKER {worker_id}] Error {year}-{month:02d}: {err_str[:200]}")
                _bump_progress(progress_lock, shared_counter, total_periods, rut, year, month, progress_hook, 'error')

                # Detect dead driver (chromedriver crash / connection refused)
                if "Connection refused" in err_str or "disconnected" in err_str or "no such session" in err_str.lower():
                    logger.warning(f"[WORKER {worker_id}] Browser muerto, abortando períodos restantes")
                    break
                # Otherwise continue to next period — driver.get(url) will reset state

    finally:
        logger.info(f"[WORKER {worker_id}] Cerrando browser...")
        try:
            driver.quit()
        except Exception:
            pass
        # Force kill chromedriver process as fallback
        try:
            if hasattr(driver, 'service') and hasattr(driver.service, 'process'):
                proc = driver.service.process
                if proc.poll() is None:  # still running
                    proc.kill()
        except Exception:
            pass
        logger.info(f"[WORKER {worker_id}] Browser cerrado")

    logger.info(f"[WORKER {worker_id}] Finalizado: {len(downloaded)} archivo(s)")
    return downloaded


def _bump_progress(
    lock: threading.Lock | None,
    counter: list[int] | None,
    total: int,
    rut: str,
    year: int,
    month: int,
    hook,
    status: str,
) -> None:
    """Atomically increment progress counter and call *hook*."""
    current = 0
    if lock is not None and counter is not None:
        with lock:
            counter[0] += 1
            current = counter[0]
    remaining = max(0, total - current)
    eta = remaining * 8  # ~8s per period estimate
    try:
        if callable(hook):
            hook(rut, current, total, year, month, eta, status)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Parallel orchestrator
# ---------------------------------------------------------------------------

def _split_periods(periods: list[tuple[int, int]], n: int) -> list[list[tuple[int, int]]]:
    """Round-robin split *periods* into *n* non-empty chunks."""
    chunks: list[list[tuple[int, int]]] = [[] for _ in range(n)]
    for i, p in enumerate(periods):
        chunks[i % n].append(p)
    return [c for c in chunks if c]


def download_cmf_xbrl_parallel(
    rut: str,
    start_year: int = 2024,
    end_year: int = 2014,
    step: int = -2,
    headless: bool = True,
    mode: str = "total",
    skip_existing: bool = True,
    skip_unavailable: bool = True,
    max_browsers: int = 2,
    progress_hook=None,
    download_dir: str | None = None,
) -> tuple[str, list[str]]:
    """Download XBRL files using *max_browsers* parallel Chrome instances.

    API mirrors ``download_cmf_xbrl`` but splits periods across browsers
    for a significant speed-up.

    Falls back to sequential ``download_cmf_xbrl`` when there are <= 1
    planned periods.
    """
    if not SELENIUM_AVAILABLE:
        raise ImportError("selenium no esta instalado. Instala con: pip install selenium")

    import multiprocessing

    # --- Resolve company info ---
    dv, company_name_csv = _resolve_company_info(rut)
    company_name = company_name_csv or f"Empresa_RUT_{rut}"

    rut_completo = f"{rut}-{dv}" if dv else rut
    normalized_mode = mode if mode in {"annual", "quarterly", "total"} else "total"
    target_dir = _compute_target_dir(rut, dv, company_name, normalized_mode)
    logger.info(f"[PARALLEL] Directorio destino: {target_dir}")

    existing_periods = _discover_existing_all_buckets(rut, rut_completo if dv else None, target_dir) if skip_existing else set()

    planned_periods, period_type, _, _ = _compute_planned_periods(
        start_year=start_year,
        end_year=end_year,
        mode=normalized_mode,
        step=step,
        quarterly=(normalized_mode == "quarterly"),
        rut=rut,
        skip_existing=skip_existing,
        existing_periods=existing_periods,
        skip_unavailable=skip_unavailable,
        target_dir=target_dir,
    )

    total_periods = len(planned_periods)
    logger.info(f"[PARALLEL] Períodos a procesar: {total_periods} | max_browsers={max_browsers}")

    if total_periods == 0:
        logger.info("[PARALLEL] No hay períodos pendientes")
        return target_dir, []

    # Cap browsers to available periods and CPU count
    effective_browsers = min(max_browsers, total_periods, max(1, multiprocessing.cpu_count()))
    chunks = _split_periods(planned_periods, effective_browsers)
    logger.info(f"[PARALLEL] Lanzando {len(chunks)} browser(s) para {total_periods} período(s)")

    url = (
        f"https://www.cmfchile.cl/institucional/mercados/entidad.php?"
        f"mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
    )

    # Shared progress state
    progress_lock = threading.Lock()
    shared_counter = [0]

    # Notify progress init
    try:
        if callable(progress_hook):
            progress_hook(rut, 0, total_periods, None, None, total_periods * 8, 'strategy_browser')
            progress_hook(rut, 0, total_periods, None, None, total_periods * 8, 'init')
    except Exception:
        pass

    all_downloaded: list[str] = []

    with ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = []
        for i, chunk in enumerate(chunks):
            # Each worker ALWAYS gets its own temp directory to avoid file conflicts
            base = download_dir or tempfile.gettempdir()
            worker_dl_dir = tempfile.mkdtemp(prefix=f"cmf_xbrl_w{i}_", dir=base if os.path.isdir(base) else None)
            fut = pool.submit(
                _probe_periods_worker,
                rut=rut,
                url=url,
                periods=chunk,
                target_dir=target_dir,
                existing_periods=existing_periods,
                headless=headless,
                downloads_dir=worker_dl_dir,
                skip_existing=skip_existing,
                progress_hook=progress_hook,
                progress_lock=progress_lock,
                shared_counter=shared_counter,
                total_periods=total_periods,
            )
            futures.append(fut)
            # Stagger browser launches to avoid resource contention
            if i < len(chunks) - 1:
                time.sleep(2.0)

        for fut in as_completed(futures):
            try:
                result = fut.result()
                all_downloaded.extend(result)
                logger.info(f"[PARALLEL] Worker terminó: {len(result)} archivo(s)")
            except Exception as e:
                logger.error(f"[PARALLEL] Worker error: {e}")

    logger.info(f"[PARALLEL] Todos los workers finalizados. Archivos: {len(all_downloaded)}")

    # --- Extract ZIPs ---
    zip_list = [p for p in all_downloaded if isinstance(p, str) and p.endswith('.zip')]
    if zip_list:
        extracted_count = 0
        with ThreadPoolExecutor(max_workers=min(4, len(zip_list))) as pool:
            def _extract(path_: str):
                ed, _, ok = auto_extract_and_cleanup_zip(path_)
                return (ed, ok, path_)
            for fut in as_completed([pool.submit(_extract, p) for p in zip_list]):
                ed, ok, orig = fut.result()
                if ok and ed:
                    extracted_count += 1
                    try:
                        all_downloaded.remove(orig)
                    except ValueError:
                        pass
                    all_downloaded.append(ed)
        logger.info(f"[PARALLEL] Extracción: {extracted_count}/{len(zip_list)} ZIPs")

    return target_dir, all_downloaded


def download_cmf_xbrl(
    rut,
    start_year=2024,
    end_year=2014,
    step=-2,
    headless=True,
    quarterly=False,
    download_dir: str | None = None,
    progress_hook=None,  # callable: (rut, current, total, year, month, eta_sec, status)
    mode: str | None = None,  # 'annual' | 'quarterly' | 'total' (preferido sobre 'quarterly')
    skip_existing: bool = True,  # si True, omite períodos ya descargados en target_dir
    skip_unavailable: bool = True,  # si True, omite períodos previamente marcados sin XBRL
    # Estrategia: 'browser' (Selenium) o 'direct' (requests concurrente)
    strategy: str = "browser",
    # Red HTTP
    max_http_workers: int = 6,
    http_retries: int = 3,
    http_timeout: tuple[int, int] = (20, 600),  # (connect, read)
    # Fallback automático a navegador si falla el modo directo tras http_retries
    enable_browser_fallback: bool = True,
    browser_fallback_timeout: int = 120,
    # Reintentos de aplicación por período en modo directo (además de los del adaptador HTTP)
    direct_attempts_per_period: int = 3,
    # Habilitar explícitamente estrategia 'direct' (además de variable de entorno)
    allow_direct_debug: bool = False,
):
    if not SELENIUM_AVAILABLE:
        raise ImportError(
            "selenium no esta instalado. Instala con: pip install selenium"
        )
    import threading
    worker_id = threading.get_ident()
    logger.info(f"[WORKER {worker_id}] Iniciando descarga XBRL para RUT: {rut}")
    """
    Descarga archivos XBRL desde la CMF

    IMPORTANTE: Los archivos XBRL contienen información de múltiples períodos.
    Por ejemplo, al consultar 2024, se obtiene un archivo que incluye 2023.
    La CMF maneja la información con step=-2, así que cada archivo cubre 2 años.

    Args:
        rut: RUT de la empresa sin guión ni dígito verificador
        start_year: Año inicial
        end_year: Año final
        step: Incremento entre años (por defecto -2, según manejo de CMF)
        headless: Si True, ejecuta Chrome sin ventana visible
        quarterly: Si True, descarga datos trimestrales, si False solo anuales
        mode: Si se especifica, valores 'annual' | 'quarterly' | 'total'.
              'total' equivale a trimestral con paso -1 (obtiene 3,6,9,12)
              y crea carpeta 'Total'. Si None, se usa 'quarterly'.
    """

    # --- Use extracted helpers for setup ---
    downloads_dir = download_dir or tempfile.mkdtemp(prefix="cmf_xbrl_dl_")
    driver = _create_browser(headless, downloads_dir)

    try:
        # Normalizar estrategia: permitir 'direct' solo si se habilita explícitamente
        try:
            if str(strategy).lower() == "direct":
                env_allow = os.getenv("CMF_XBRL_ALLOW_DIRECT", "0")
                if not allow_direct_debug and env_allow != "1":
                    logger.info("Estrategia 'direct' habilitada solo en modo pruebas. Usando 'browser'.")
                    strategy = "browser"
                else:
                    logger.info("Estrategia 'direct' habilitada.")
        except Exception:
            pass

        # Obtener información de la empresa
        dv, company_name_csv = _resolve_company_info(rut)

        # Construir URL
        url = f"https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
        logger.info(f"Accediendo a: {url}")
        driver.get(url)

        # Esperar hasta que el formulario esté presente
        wait = WebDriverWait(driver, 15)
        form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

        # Obtener nombre de la empresa desde la página
        try:
            company_element = driver.find_element(By.ID, "datos_ent")
            company_name_web = company_element.text.split("\n")[1].strip()
        except:
            company_name_web = f"Empresa_RUT_{rut}"

        # Usar el nombre más completo disponible
        company_name = company_name_csv if company_name_csv else company_name_web
        logger.info(f"Procesando: {company_name}")

        # Crear directorio de destino y compute rut_completo
        rut_completo = f"{rut}-{dv}" if dv else rut
        target_dir = _compute_target_dir(rut, dv, company_name, mode or ("quarterly" if quarterly else "annual"))
        logger.info(f"Directorio de destino: {target_dir}")

        existing_periods = _discover_existing_all_buckets(rut, rut_completo if dv else None, target_dir) if skip_existing else set()

        planned_periods, period_type, months_to_process, iteration_step = _compute_planned_periods(
            start_year=start_year,
            end_year=end_year,
            mode=mode or "",
            step=step,
            quarterly=quarterly,
            rut=rut,
            skip_existing=skip_existing,
            existing_periods=existing_periods,
            skip_unavailable=skip_unavailable,
            target_dir=target_dir,
        )
        logger.info(f"Modo de descarga: {period_type}")
        logger.info(f"Meses a procesar: {months_to_process}")

        # Calcular total de operaciones para contador (planeadas)
        total_periods = len(planned_periods)
        logger.info(f"Total de períodos a procesar: {total_periods}")
        logger.info(f"Tiempo estimado (navegador): {total_periods * 30} segundos (~{(total_periods * 30) // 60} minutos)")

        # Early exit: nothing to do
        if total_periods == 0:
            logger.info("No hay períodos pendientes por procesar")
            return target_dir, []

        downloaded_files = []
        current_operation = 0

        # FASE 1: DESCARGA/RECOLECCIÓN
        logger.debug("FASE 1: Preparación de descargas")
        
        # Si la estrategia es directa, recolectar enlaces con Selenium pero descargar con requests en paralelo
        if strategy.lower() == "direct":
            # Notificar estrategia al dashboard
            try:
                if callable(progress_hook):
                    progress_hook(rut, 0, 0, None, None, 0, 'strategy_direct')
            except Exception:
                pass
            # Construir sesión HTTP con cookies y User-Agent del navegador
            def _build_requests_session(webdriver_instance) -> requests.Session:
                session = requests.Session()
                # Copiar cookies del navegador
                try:
                    for c in webdriver_instance.get_cookies():
                        try:
                            session.cookies.set(
                                name=c.get('name'),
                                value=c.get('value'),
                                domain=c.get('domain'),
                                path=c.get('path', '/')
                            )
                        except Exception:
                            continue
                except Exception:
                    pass
                # Establecer User-Agent
                try:
                    ua = webdriver_instance.execute_script("return navigator.userAgent")
                    if ua:
                        session.headers.update({"User-Agent": ua})
                        logger.info(f"[direct] UA: {ua}")
                except Exception:
                    pass
                # Retries/pool
                try:
                    retry = Retry(
                        total=http_retries,
                        read=http_retries,
                        connect=http_retries,
                        status=http_retries,
                        backoff_factor=0.5,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["HEAD", "GET", "OPTIONS"]
                    )
                    adapter = HTTPAdapter(
                        pool_connections=max(8, max_http_workers * 2),
                        pool_maxsize=max(8, max_http_workers * 2),
                        max_retries=retry
                    )
                    session.mount('https://', adapter)
                    session.mount('http://', adapter)
                except Exception:
                    pass
                # Log cookies básicas
                try:
                    cookie_names = [c.get('name') for c in webdriver_instance.get_cookies()][:5]
                    logger.info(f"[direct] Cookies transferidas: {cookie_names}")
                except Exception:
                    pass
                return session

            def _parse_content_disposition_filename(disposition_value: Optional[str]) -> Optional[str]:
                if not disposition_value:
                    return None
                try:
                    m = re.search(r"filename\*=UTF-8''([^']+)", disposition_value)
                    if m:
                        return m.group(1)
                    m = re.search(r'filename="?([^";]+)"?', disposition_value)
                    if m:
                        return m.group(1)
                except Exception:
                    return None
                return None

            def _download_one(session: requests.Session, href: str, tgt_dir: str, fallback_name: str, diag_ctx: tuple | None = None) -> str | None:
                try:
                    abs_url = urljoin("https://www.cmfchile.cl/", href)
                    # Algunos servidores requieren Referer; usar la página de entidad
                    try:
                        session.headers.setdefault('Referer', url)
                    except Exception:
                        pass
                    logger.info(f"[direct] GET {abs_url}")
                    try:
                        if diag_ctx is not None:
                            rut_ctx, year_ctx, month_ctx, hook_ctx = diag_ctx
                            if callable(hook_ctx):
                                hook_ctx(rut_ctx, 0, 0, year_ctx, month_ctx, 0, f"diag_get|{abs_url}")
                    except Exception:
                        pass
                    with session.get(abs_url, stream=True, timeout=http_timeout) as resp:
                        status = resp.status_code
                        ctype = resp.headers.get('Content-Type', '')
                        clen = resp.headers.get('Content-Length', '-')
                        logger.info(f"[direct] <- {status} Content-Type={ctype} Content-Length={clen}")
                        try:
                            if diag_ctx is not None:
                                rut_ctx, year_ctx, month_ctx, hook_ctx = diag_ctx
                                if callable(hook_ctx):
                                    hook_ctx(rut_ctx, 0, 0, year_ctx, month_ctx, 0, f"diag_http|{status}|{ctype}|{clen}")
                        except Exception:
                            pass
                        if status >= 400:
                            logger.warning(f"[direct] HTTP error {status} en {abs_url}")
                            resp.raise_for_status()
                        cd = resp.headers.get('Content-Disposition')
                        fname = _parse_content_disposition_filename(cd) or fallback_name
                        if not fname.lower().endswith('.zip'):
                            fname = f"{fname}.zip"
                        final_path = os.path.join(tgt_dir, fname)
                        tmp_path = final_path + '.part'
                        with open(tmp_path, 'wb') as fh:
                            for chunk in resp.iter_content(chunk_size=1_048_576):
                                if chunk:
                                    fh.write(chunk)
                        # Validar ZIP
                        try:
                            with zipfile.ZipFile(tmp_path, 'r') as _zf:
                                pass
                        except Exception:
                            # Guardar pequeño preview cuando no sea ZIP válido
                            try:
                                with open(tmp_path, 'rb') as fh:
                                    preview = fh.read(256)
                                logger.warning(f"[direct] Respuesta no ZIP. Preview bytes: {preview[:64]!r} ...")
                            except Exception:
                                pass
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass
                            logger.warning(f"Archivo inválido desde {abs_url}")
                            return None
                        os.replace(tmp_path, final_path)
                        logger.info(f"✅ Descargado (direct): {os.path.basename(final_path)}")
                        return final_path
                except Exception as e:
                    logger.warning(f"Fallo descarga directa: {e}")
                    return None

            # Utilidades UI (paridad con probe)
            def _dismiss_ui_obstacles():
                try:
                    modals = driver.find_elements(By.CSS_SELECTOR, '.modal.show, .modal.in')
                    for m in modals:
                        try:
                            close_btn = m.find_element(By.CSS_SELECTOR, 'button.close, [data-dismiss="modal"]')
                            driver.execute_script("arguments[0].click();", close_btn)
                            time.sleep(0.2)
                        except Exception:
                            continue
                except Exception:
                    pass
                try:
                    candidates = driver.find_elements(By.XPATH, "//button[contains(translate(., 'ACEPTAROKENTENDIDO', 'aceptarokentendido'), 'acept') or contains(translate(., 'ACEPTAROKENTENDIDO', 'aceptarokentendido'), 'ok') or contains(translate(., 'ACEPTAROKENTENDIDO', 'aceptarokentendido'), 'entendido')]")
                    for btn in candidates[:3]:
                        try:
                            driver.execute_script("arguments[0].click();", btn)
                            time.sleep(0.2)
                        except Exception:
                            continue
                except Exception:
                    pass
                try:
                    el = driver.find_element(By.ID, 'contenido')
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                except Exception:
                    pass

            def _reopen_financial_tab():
                try:
                    link = driver.find_element(By.CSS_SELECTOR, 'ul#listado_reportes a[href*="pestania=3"]')
                    driver.execute_script("arguments[0].click();", link)
                    time.sleep(0.5)
                except Exception:
                    try:
                        link = driver.find_element(By.XPATH, "//a[contains(@href,'pestania=3') and contains(., 'Información')]")
                        driver.execute_script("arguments[0].click();", link)
                        time.sleep(0.5)
                    except Exception:
                        pass

            # Recolectar tareas (hrefs) para cada período
            tasks: List[Dict[str, object]] = []
            for (year, month) in planned_periods:
                try:
                    # Verificar que estamos en la página correcta
                    if "cmfchile.cl" not in driver.current_url:
                        driver.get(url)
                        time.sleep(1.5)
                    _dismiss_ui_obstacles()
                    _reopen_financial_tab()
                    try:
                        wait.until(EC.presence_of_element_located((By.ID, "fm")))
                    except Exception:
                        pass
                    # Seleccionar año
                    try:
                        select_aa = Select(driver.find_element(By.ID, "aa"))
                    except Exception:
                        try:
                            select_aa = Select(driver.find_element(By.NAME, "aa"))
                        except Exception:
                            select_aa = None
                    if select_aa is not None:
                        try:
                            select_aa.select_by_visible_text(str(year))
                        except Exception:
                            pass
                    # Seleccionar mes
                    try:
                        select_mm = Select(driver.find_element(By.ID, "mm"))
                    except Exception:
                        try:
                            select_mm = Select(driver.find_element(By.NAME, "mm"))
                        except Exception:
                            select_mm = None
                    month_str = f"{month:02d}"
                    if select_mm is not None:
                        try:
                            select_mm.select_by_visible_text(month_str)
                        except Exception:
                            pass
                    # Seleccionar tipo y norma
                    try:
                        select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                        select_tipo.select_by_visible_text("Consolidado")
                    except Exception:
                        pass
                    try:
                        select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                        select_tipo_norma.select_by_visible_text("Estándar IFRS")
                    except Exception:
                        pass
                    # Submit
                    try:
                        submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                    except Exception:
                        try:
                            submit_button = driver.find_element(By.XPATH, "//input[@type='submit' or @type='button' or self::button][contains(., 'Aplicar') or contains(., 'Consultar')]")
                        except Exception:
                            submit_button = None
                    try:
                        if submit_button is not None:
                            driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                            time.sleep(0.5)
                            submit_button.click()
                    except ElementClickInterceptedException:
                        if submit_button is not None:
                            driver.execute_script("arguments[0].click();", submit_button)
                    _sleep(1.5)
                    _dismiss_ui_obstacles()

                    # Localizar enlace XBRL y recoger href
                    try:
                        xbrl_link = wait.until(
                            EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)"))
                        )
                        href = xbrl_link.get_attribute('href') if xbrl_link else ''
                    except TimeoutException:
                        try:
                            html = driver.page_source
                            mm = re.search(r'href=\"([^\"]+)\"[^>]*>\s*Estados\s+financieros\s*\(XBRL\)\s*<', html, re.IGNORECASE)
                            href = mm.group(1) if mm else ''
                        except Exception:
                            href = ''
                        if not href:
                            logger.warning(f"❌ No hay XBRL para {year}-{month:02d}")
                            _mark_unavailable(rut, year, month)
                            continue
                    try:
                        logger.info(f"[direct] HREF {year}-{month:02d}: {href}")
                        if str(href).lower().startswith('javascript'):
                            logger.info(f"[direct] HREF usa javascript: posible no descargable directo para {year}-{month:02d}")
                        # Emitir al dashboard
                        try:
                            if callable(progress_hook):
                                progress_hook(rut, 0, 0, year, month, 0, f"diag_href|{href}")
                        except Exception:
                            pass
                    except Exception:
                        pass
                    yyyymm_in_link = None
                    try:
                        mmatch = re.search(r"(20\d{2})(0[1-9]|1[0-2])", href or '')
                        if mmatch:
                            yyyymm_in_link = mmatch.group(1) + mmatch.group(2)
                    except Exception:
                        pass
                    if skip_existing and yyyymm_in_link and yyyymm_in_link in existing_periods:
                        logger.info(f"⏭️  Saltando {year}-{month:02d} (detectado en enlace: {yyyymm_in_link} ya existe)")
                        continue
                    fallback_name = f"Estados_financieros_(XBRL)_{rut}_{year}{month:02d}.zip"
                    tasks.append({
                        "year": year,
                        "month": month,
                        "url": href,
                        "fallback": fallback_name,
                    })
                except Exception as e:
                    logger.warning(f"Error recolectando {year}-{month:02d}: {e}")

            if not tasks:
                logger.info("[direct] No se recolectaron enlaces directos. Activando fallback a navegador para todos los períodos planificados.")
                if enable_browser_fallback:
                    try:
                        if callable(progress_hook):
                            progress_hook(rut, 0, 0, None, None, 0, 'strategy_browser_fallback')
                    except Exception:
                        pass
                    # Fallback navegador por cada período planificado
                    for (year, month) in planned_periods:
                        try:
                            if skip_existing and f"{year}{month:02d}" in existing_periods:
                                logger.info(f"⏭️  Fallback: saltando {year}-{month:02d} (ya existe)")
                                continue
                            if "cmfchile.cl" not in driver.current_url:
                                driver.get(url)
                                _sleep(1.5)
                            form = wait.until(EC.presence_of_element_located((By.ID, "fm")))
                            select_aa = Select(driver.find_element(By.ID, "aa"))
                            select_aa.select_by_visible_text(str(year))
                            select_mm = Select(driver.find_element(By.ID, "mm"))
                            select_mm.select_by_visible_text(f"{month:02d}")
                            try:
                                select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                                select_tipo.select_by_visible_text("Consolidado")
                            except Exception:
                                pass
                            try:
                                select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                                select_tipo_norma.select_by_visible_text("Estándar IFRS")
                            except Exception:
                                pass
                            submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                            try:
                                driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                                _sleep(0.5)
                                submit_button.click()
                            except ElementClickInterceptedException:
                                driver.execute_script("arguments[0].click();", submit_button)
                            _sleep(2.0)
                            try:
                                xbrl_link = wait.until(
                                    EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)"))
                                )
                            except TimeoutException:
                                logger.warning(f"Fallback: no hay enlace XBRL para {year}-{month:02d}")
                                _mark_unavailable(rut, year, month)
                                continue
                            try:
                                driver.execute_script("arguments[0].scrollIntoView(true);", xbrl_link)
                                _sleep(0.5)
                                xbrl_link.click()
                            except ElementClickInterceptedException:
                                driver.execute_script("arguments[0].click();", xbrl_link)
                            moved = _wait_for_download_and_move(downloads_dir, rut, target_dir, timeout=browser_fallback_timeout)
                            if moved:
                                downloaded_files.append(moved)
                                logger.info(f"Fallback OK {rut} {year}-{month:02d}")
                            else:
                                logger.warning(f"Fallback sin éxito para {year}-{month:02d}")
                            driver.back()
                            _sleep(1.0)
                        except Exception as e:
                            logger.warning(f"Fallback ERROR {year}-{month:02d}: {e}")
                    # Tras fallback, continuar con extracción
                else:
                    try:
                        if callable(progress_hook):
                            progress_hook(rut, 0, 0, None, None, 0, 'skipped_all')
                    except Exception:
                        pass
                    return target_dir, []

            # Progreso inicial para descargas directas
            try:
                if callable(progress_hook):
                    progress_hook(rut, 0, len(tasks), None, None, len(tasks) * 12, 'init')
            except Exception:
                pass

            session = _build_requests_session(driver)

            # Descargar en paralelo
            def _runner(task: Dict[str, object]) -> Tuple[int, int, str | None]:
                y = int(task["year"])  # type: ignore
                m = int(task["month"])  # type: ignore
                href = str(task["url"])  # type: ignore
                fb = str(task["fallback"])  # type: ignore
                # Reintentos a nivel de aplicación por período
                attempts = max(1, int(direct_attempts_per_period))
                last_path = None
                for attempt_idx in range(attempts):
                    path_ = _download_one(session, href, target_dir, fb, diag_ctx=(rut, y, m, progress_hook))
                    if path_:
                        last_path = path_
                        break
                    # backoff simple
                    time.sleep(1 * (attempt_idx + 1))
                return (y, m, last_path)

            with ThreadPoolExecutor(max_workers=max(1, int(max_http_workers))) as pool:
                futures = [pool.submit(_runner, t) for t in tasks]
                failed_periods: List[Tuple[int, int]] = []
                for fut in as_completed(futures):
                    y, m, p = fut.result()
                    current_operation += 1
                    remaining = len(tasks) - current_operation
                    eta = remaining * 10
                    if p:
                        downloaded_files.append(p)
                        logger.info(f"Descarga completada {rut} {y}-{m:02d} (direct)")
                        try:
                            if callable(progress_hook):
                                progress_hook(rut, current_operation, len(tasks), y, m, eta, 'period_completed')
                        except Exception:
                            pass
                    else:
                        logger.warning(f"⚠️ No se pudo completar la descarga directa para {y}-{m:02d}")
                        failed_periods.append((y, m))

            # Fallback a modo navegador si hay múltiples fallas
            if enable_browser_fallback and len(failed_periods) >= 3:
                logger.info(f"🔁 Activando fallback (browser/headless) para {len(failed_periods)} período(s) fallido(s)")
                try:
                    if callable(progress_hook):
                        progress_hook(rut, current_operation, len(tasks), None, None, 0, 'strategy_browser_fallback')
                except Exception:
                    pass
                for (year, month) in failed_periods:
                    try:
                        # Verificación rápida de existencia en disco
                        if skip_existing and f"{year}{month:02d}" in existing_periods:
                            logger.info(f"⏭️  Fallback: saltando {year}-{month:02d} (ya existe)")
                            continue

                        # Asegurar estar en página correcta
                        if "cmfchile.cl" not in driver.current_url:
                            driver.get(url)
                            _sleep(1.5)
                        form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

                        # Selecciones
                        select_aa = Select(driver.find_element(By.ID, "aa"))
                        select_aa.select_by_visible_text(str(year))
                        select_mm = Select(driver.find_element(By.ID, "mm"))
                        select_mm.select_by_visible_text(f"{month:02d}")
                        try:
                            select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                            select_tipo.select_by_visible_text("Consolidado")
                        except Exception:
                            pass
                        try:
                            select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                            select_tipo_norma.select_by_visible_text("Estándar IFRS")
                        except Exception:
                            pass

                        # Enviar
                        submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                        try:
                            driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                            _sleep(0.5)
                            submit_button.click()
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].click();", submit_button)
                        _sleep(2.0)

                        # Verificar enlace XBRL
                        try:
                            xbrl_link = wait.until(
                                EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)"))
                            )
                        except TimeoutException:
                            logger.warning(f"Fallback: no hay enlace XBRL para {year}-{month:02d}")
                            _mark_unavailable(rut, year, month)
                            continue

                        try:
                            driver.execute_script("arguments[0].scrollIntoView(true);", xbrl_link)
                            _sleep(0.5)
                            xbrl_link.click()
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].click();", xbrl_link)

                        # Esperar y mover
                        moved = _wait_for_download_and_move(downloads_dir, rut, target_dir, timeout=browser_fallback_timeout)
                        if moved:
                            downloaded_files.append(moved)
                            logger.info(f"Fallback OK {rut} {year}-{month:02d}")
                        else:
                            logger.warning(f"Fallback sin éxito para {year}-{month:02d}")
                        driver.back()
                        _sleep(1.0)
                    except Exception as e:
                        logger.warning(f"Fallback ERROR {year}-{month:02d}: {e}")
        else:
            # Progreso inicial (modo navegador)
            try:
                # Notificar estrategia al dashboard
                if callable(progress_hook):
                    progress_hook(rut, 0, total_periods, None, None, total_periods * 30, 'strategy_browser')
            except Exception:
                pass
            try:
                if callable(progress_hook):
                    progress_hook(rut, 0, total_periods, None, None, total_periods * 30, 'init')
            except Exception:
                pass

            # Procesar cada año
            for (year, month) in planned_periods:
                logger.debug(f"Consultando período {year}-{month:02d} - Modo {period_type}")
                try:
                    current_operation += 1
                    progress_percent = (current_operation / total_periods) * 100
                    remaining_operations = total_periods - current_operation
                    estimated_remaining_time = remaining_operations * 30  # 30 seg por operación
                    
                    logger.debug(f"Procesando período {year}-{month:02d} | Progreso {current_operation}/{total_periods} ({progress_percent:.1f}%) | ETA ~{estimated_remaining_time // 60} min")
                    # Notificar progreso al dashboard
                    try:
                        if callable(progress_hook):
                            progress_hook(rut, current_operation, total_periods, year, month, estimated_remaining_time, 'in_progress')
                    except Exception:
                        pass
                    # Verificar que estamos en la página correcta
                    if "cmfchile.cl" not in driver.current_url:
                        logger.debug("Recargando página principal...")
                        driver.get(url)
                        _sleep(2.0)

                    # Esperar formulario
                    form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

                    # Seleccionar año
                    select_aa = Select(driver.find_element(By.ID, "aa"))
                    select_aa.select_by_visible_text(str(year))

                    # Seleccionar mes
                    select_mm = Select(driver.find_element(By.ID, "mm"))
                    month_str = f"{month:02d}"
                    select_mm.select_by_visible_text(month_str)

                    # Seleccionar tipo (si está disponible)
                    try:
                        select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                        select_tipo.select_by_visible_text("Consolidado")
                    except:
                        logger.warning("No se pudo seleccionar 'Consolidado'")

                    # Seleccionar norma (si está disponible)
                    try:
                        select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                        select_tipo_norma.select_by_visible_text("Estándar IFRS")
                    except:
                        logger.warning("No se pudo seleccionar 'Estándar IFRS'")

                    # Submit formulario con mejor manejo de errores
                    submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                    try:
                        # Hacer scroll al elemento antes de hacer click
                        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                        _sleep(0.5)
                        submit_button.click()
                    except ElementClickInterceptedException:
                        logger.debug("Click interceptado, usando JavaScript...")
                        driver.execute_script("arguments[0].click();", submit_button)

                    # Esperar carga de la página
                    _sleep(2.0)

                    # Verificar que estamos en la página correcta de la empresa
                    try:
                        # Verificar que el RUT aparece en la página
                        page_source = driver.page_source
                        if rut not in page_source:
                            logger.warning(f"⚠️ El RUT {rut} no aparece en la página actual")
                            # Recargar la página principal
                            driver.get(url)
                            _sleep(2.0)
                            continue

                        # Verificar nombre de empresa si está disponible
                        try:
                            current_company = driver.find_element(By.ID, "datos_ent").text
                            if "VIÑA SAN PEDRO" not in current_company.upper() and rut == "91041000":
                                logger.warning(f"⚠️ Empresa incorrecta detectada: {current_company}")
                                driver.get(url)
                                _sleep(2.0)
                                continue
                        except:
                            pass

                    except Exception as e:
                        logger.warning(f"Error verificando página: {e}")

                    # Verificación rápida: si ya existe, saltar (doble seguridad)
                    if skip_existing and f"{year}{month:02d}" in existing_periods:
                        logger.info(f"⏭️  Saltando {year}-{month:02d} (ya existe en disco)")
                        try:
                            if callable(progress_hook):
                                progress_hook(rut, current_operation, total_periods, year, month, estimated_remaining_time, 'skipped_period')
                        except Exception:
                            pass
                        continue

                    # Verificar si hay enlace XBRL disponible
                    if not _check_xbrl_link_available(driver):
                        logger.warning(f"❌ No hay enlace XBRL disponible para {year}-{month:02d}")
                        _mark_unavailable(rut, year, month)
                        driver.back()
                        _sleep(1.0)
                        continue

                    # Buscar y hacer click en enlace XBRL
                    try:
                        xbrl_link = wait.until(
                            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)"))
                        )

                        logger.debug(f"Encontrado enlace XBRL para {year}-{month:02d}")

                        # Comprobar período real del href antes de descargar para saltar si ya existe
                        try:
                            href = xbrl_link.get_attribute('href')
                        except Exception:
                            href = ''
                        yyyymm_in_link = None
                        try:
                            mmatch = re.search(r"(20\d{2})(0[1-9]|1[0-2])", href or '')
                            if mmatch:
                                yyyymm_in_link = mmatch.group(1) + mmatch.group(2)
                        except Exception:
                            pass
                        if skip_existing and yyyymm_in_link and yyyymm_in_link in existing_periods:
                            logger.info(f"⏭️  Saltando {year}-{month:02d} (detectado en enlace: {yyyymm_in_link} ya existe)")
                            try:
                                if callable(progress_hook):
                                    progress_hook(rut, current_operation, total_periods, year, month, estimated_remaining_time, 'skipped_period')
                            except Exception:
                                pass
                            driver.back()
                            _sleep(1.0)
                            continue

                        # Hacer click en el enlace con mejor manejo
                        try:
                            # Hacer scroll al enlace
                            driver.execute_script("arguments[0].scrollIntoView(true);", xbrl_link)
                            _sleep(0.5)
                            xbrl_link.click()
                        except ElementClickInterceptedException:
                            logger.info("Click en enlace XBRL interceptado, usando JavaScript...")
                            driver.execute_script("arguments[0].click();", xbrl_link)

                        # Esperar a que se inicie la descarga
                        logger.debug("Esperando descarga...")
                        downloaded_file = _wait_for_download_and_move(
                            downloads_dir,
                            rut,  # Mantener verificación si el nombre lo contiene
                            target_dir,
                            timeout=60
                        )

                        if downloaded_file:
                            downloaded_files.append(downloaded_file)
                            logger.info(f"Descarga completada {rut} {year}-{month:02d}")
                            # Notificar descarga del período al dashboard (como 'period_completed')
                            try:
                                if callable(progress_hook):
                                    progress_hook(rut, current_operation, total_periods, year, month, estimated_remaining_time, 'period_completed')
                            except Exception:
                                pass
                        else:
                            logger.warning(f"⚠️ No se pudo completar la descarga para {year}-{month:02d}")

                        # Volver a la página anterior
                        driver.back()
                        _sleep(1.5)

                    except TimeoutException:
                        logger.warning(f"❌ No se encontró enlace XBRL para {year}-{month:02d}")
                        _mark_unavailable(rut, year, month)
                        driver.back()
                        _sleep(1.0)
                        continue

                except Exception as e:
                    logger.error(f"❌ Error procesando período {year}-{month:02d}: {e}")

                    # Intentar recuperarse
                    try:
                        driver.back()
                        _sleep(1.5)
                    except:
                        # Si no puede volver atrás, recargar página
                        driver.get(url)
                        _sleep(3.0)
                    continue
        
        # Resumen final
        logger.info(f"Completado XBRL | Empresa={company_name} | RUT={rut_completo} | Archivos={len(downloaded_files)} | Dir={target_dir}")
        
        for file_path in downloaded_files:
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
            logger.info(f"  📁 {file_name} ({file_size:.2f} MB)")
        
        # =============================================================
        # FASE 3: EXTRACCIÓN AUTOMÁTICA Y LIMPIEZA
        # =============================================================
        logger.debug("FASE 3: Extrayendo ZIPs y eliminando originales")
        extracted_count = 0
        failed_extractions = 0
        
        zip_list = [p for p in downloaded_files if isinstance(p, str) and p.endswith('.zip')]
        if zip_list:
            def _extract_one(path_: str) -> Tuple[str | None, bool, str]:
                extract_dir, extracted_files, success = auto_extract_and_cleanup_zip(path_)
                return (extract_dir, success, path_)
            with ThreadPoolExecutor(max_workers=min(4, len(zip_list))) as pool:
                for fut in as_completed([pool.submit(_extract_one, p) for p in zip_list]):
                    extract_dir, success, orig = fut.result()
                    if success and extract_dir:
                        extracted_count += 1
                        try:
                            downloaded_files.remove(orig)
                        except Exception:
                            pass
                        downloaded_files.append(extract_dir)
                    else:
                        failed_extractions += 1
        logger.info(f"Extracción completada | OK={extracted_count} | Fails={failed_extractions} | ZIPs eliminados={extracted_count}")
        
        return target_dir, downloaded_files
        
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        raise
    
    finally:
        try:
            driver.quit()
        finally:
                        logger.debug("Driver cerrado correctamente")


def extract_and_analyze_xbrl(zip_file_path):
    """
    Extraer y analizar archivos XBRL descargados
    
    Args:
        zip_file_path: Ruta al archivo ZIP descargado
    """
    try:
        extract_dir = zip_file_path.replace('.zip', '_extracted')
        
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        logger.info(f"📂 Archivo extraído en: {extract_dir}")
        
        # Listar archivos extraídos
        extracted_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                extracted_files.append(file_path)
                logger.info(f"  📄 {file}")
        
        return extract_dir, extracted_files
        
    except Exception as e:
        logger.error(f"Error extrayendo archivo XBRL: {e}")
        return None, []


def auto_extract_and_cleanup_zip(zip_file_path):
    """
    Extraer archivo ZIP automáticamente y eliminar el ZIP original
    
    Args:
        zip_file_path: Ruta al archivo ZIP a extraer
    
    Returns:
        tuple: (extract_dir, extracted_files, success)
    """
    try:
        # Crear directorio de extracción
        extract_dir = zip_file_path.replace('.zip', '_extracted')
        
        # Extraer archivo
        with zipfile.ZipFile(zip_file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # Listar archivos extraídos
        extracted_files = []
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                file_path = os.path.join(root, file)
                extracted_files.append(file_path)
        
        # Obtener tamaño del ZIP antes de eliminarlo
        zip_size = os.path.getsize(zip_file_path) / (1024 * 1024)  # MB
        zip_name = os.path.basename(zip_file_path)
        
        # Eliminar el archivo ZIP original
        os.remove(zip_file_path)
        
        logger.info(f"✅ {zip_name} ({zip_size:.2f} MB) → Extraído y ZIP eliminado")
        logger.info(f"   📂 Carpeta: {os.path.basename(extract_dir)}")
        logger.info(f"   📄 Archivos: {len(extracted_files)} archivos XBRL")
        
        return extract_dir, extracted_files, True
        
    except Exception as e:
        logger.error(f"❌ Error extrayendo/eliminando {os.path.basename(zip_file_path)}: {e}")
        return None, [], False


def process_multiple_companies_xbrl(
    ruts,
    start_year: int = 2024,
    end_year: int = 2014,
    headless: bool = True,
    quarterly: bool = False,
    max_workers: int | None = None
):
    """
    Descargar archivos XBRL para múltiples empresas en paralelo usando hilos.

    Args:
        ruts: lista de RUTs sin guión
        start_year: año inicial
        end_year: año final
        headless: ejecutar navegador en modo headless
        quarterly: True para trimestral, False para anual
        max_workers: número máximo de hilos; por defecto min(6, len(ruts))
    """
    import threading

    if not ruts:
        return []

    workers = max_workers or min(6, len(ruts))
    results = []

    logger.info(f"Iniciando descarga XBRL en paralelo: {len(ruts)} empresas, workers={workers}")

    def worker(rut: str, idx: int):
        worker_id = threading.get_ident()
        logger.info(f"[WORKER {worker_id}] Empresa {idx+1}/{len(ruts)} RUT {rut}")
        # Directorio aislado para este worker
        per_worker_dl = tempfile.mkdtemp(prefix=f"cmf_xbrl_w{worker_id}_")
        try:
            target_dir, downloaded_files = download_cmf_xbrl(
                rut=rut,
                start_year=start_year,
                end_year=end_year,
                headless=headless,
                quarterly=quarterly,
                download_dir=per_worker_dl
            )
            logger.info(f"[WORKER {worker_id}] ✓ {rut}: {len(downloaded_files)} archivos")
            return (rut, target_dir, downloaded_files, "SUCCESS")
        except Exception as e:
            logger.error(f"[WORKER {worker_id}] ✗ Error {rut}: {e}")
            return (rut, None, [], f"ERROR: {str(e)}")
        finally:
            # Limpiar el directorio temporal del worker si sigue existiendo y quedó vacío
            try:
                if os.path.isdir(per_worker_dl) and not os.listdir(per_worker_dl):
                    os.rmdir(per_worker_dl)
            except Exception:
                pass

    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_rut = {executor.submit(worker, rut, idx): rut for idx, rut in enumerate(ruts)}
        for future in as_completed(future_to_rut):
            results.append(future.result())

    # Resumen final
    logger.info(f"\n{'='*60}")
    logger.info("RESUMEN DE DESCARGA XBRL")
    logger.info(f"{'='*60}")
    successful = sum(1 for _, _, _, status in results if status == "SUCCESS")
    logger.info(f"Empresas procesadas exitosamente: {successful}/{len(ruts)}")
    for rut, target_dir, files, status in results:
        if status == "SUCCESS":
            logger.info(f"✓ RUT {rut}: {len(files)} archivos en {target_dir}")
        else:
            logger.info(f"✗ RUT {rut}: {status}")
    return results


def main():
    """
    Función principal para ejecutar el descargador XBRL
    """
    # Configuración de prueba
    rut = "91041000"  # VIÑA SAN PEDRO TARAPACA S.A.
    
    try:
        logger.info("INICIANDO DESCARGA DE ARCHIVOS XBRL CMF")
        logger.info(f"RUT: {rut}")
        logger.info(f"Período: 2024-2020")
        logger.info(f"Modo: Anual (solo diciembre)")
        logger.info(f"NOTA: Cada archivo XBRL contiene múltiples períodos")
        
        target_dir, downloaded_files = download_cmf_xbrl(
            rut=rut,
            start_year=2024,
            end_year=2014,
            step=-2,  # Step -2 según manejo de CMF
            headless=False,  # Mostrar ventana para debugging inicial
            quarterly=False  # Solo anual
        )
        
        if downloaded_files:
            print(f"\n✅ Proceso completado exitosamente")
            print(f"📁 Directorio: {target_dir}")
            print(f"📊 Archivos descargados: {len(downloaded_files)}")
            
            # Analizar primer archivo como ejemplo
            if downloaded_files:
                print(f"\n🔍 Analizando primer archivo...")
                extract_dir, extracted_files = extract_and_analyze_xbrl(downloaded_files[0])
                
        else:
            print(f"\n❌ No se pudieron descargar archivos XBRL para esta empresa")
        
    except Exception as e:
        print(f"\n💥 Error en el procesamiento: {e}")


def main_quarterly():
    """
    Función para ejecutar el descargador en modo trimestral
    """
    rut = "91041000"  # VIÑA SAN PEDRO TARAPACA S.A.
    
    try:
        logger.info("INICIANDO DESCARGA DE ARCHIVOS XBRL CMF - MODO TRIMESTRAL")
        logger.info(f"RUT: {rut}")
        logger.info(f"Período: 2024-2022")
        logger.info(f"Modo: Trimestral (marzo, junio, septiembre, diciembre)")
        
        target_dir, downloaded_files = download_cmf_xbrl(
            rut=rut,
            start_year=2024,
            end_year=2022,
            step=-1,
            headless=True,
            quarterly=True  # Modo trimestral
        )
        
        if downloaded_files:
            print(f"\n✅ Proceso completado exitosamente")
            print(f"📁 Directorio: {target_dir}")
            print(f"📊 Archivos descargados: {len(downloaded_files)}")
        else:
            print(f"\n❌ No se pudieron descargar archivos XBRL")
        
    except Exception as e:
        print(f"\n💥 Error en el procesamiento: {e}")


if __name__ == "__main__":
    # Por defecto ejecutar en modo anual con ventana visible para pruebas
    main()
    
    # Para ejecutar en modo trimestral:
    # main_quarterly()
    
    # Para múltiples empresas:
    """
    ruts = ["91041000", "96505760", "96509660"]
    results = process_multiple_companies_xbrl(ruts, start_year=2024, end_year=2020, headless=True, quarterly=False)
    """
