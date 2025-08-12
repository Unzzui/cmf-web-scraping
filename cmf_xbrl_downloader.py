#!/usr/bin/env python3

"""
CMF XBRL Downloader - Versión Mejorada
Descarga archivos XBRL desde la CMF para análisis financiero

FASE 1: Descarga tranquila de todos los archivos
FASE 2: Organización de archivos desde ~/Downloads

Basado en el scraper original pero enfocado en descarga de archivos XBRL
Los archivos XBRL contienen información de múltiples períodos
"""

import os
import time
import logging
import pandas as pd
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
import requests
from urllib.parse import urljoin, urlparse
import zipfile
import shutil
from pathlib import Path
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

# Configurar logging (incluye ID de hilo para depurar concurrencia)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | [WORKER %(thread)d] | %(message)s'
)
logger = logging.getLogger(__name__)


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
):
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
    
    # Función para obtener DV y nombre de empresa desde el CSV
    def get_company_info(rut_numero):
        """Obtener el DV y nombre de la empresa desde el archivo CSV"""
        try:
            csv_path = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                match = df[df['RUT_Numero'].astype(str) == str(rut_numero)]
                if not match.empty:
                    dv = str(match.iloc[0]['DV']).strip()
                    # Intentar obtener el nombre de empresa desde varias columnas posibles
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
    
    # Configurar Chrome
    chrome_options = Options()
    
    # Configurar directorio de descarga por worker para evitar colisiones entre hilos
    # Si no se especifica, crear uno temporal único por llamada
    downloads_dir = download_dir or tempfile.mkdtemp(prefix="cmf_xbrl_dl_")
    
    # Configuraciones de Chrome
    prefs = {
        "download.default_directory": downloads_dir,
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
        "profile.default_content_settings.popups": 0,
        "profile.default_content_setting_values.automatic_downloads": 1
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    if headless:
        # Usar modo headless moderno cuando esté disponible
        try:
            chrome_options.add_argument("--headless=new")
        except Exception:
            chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        logger.info("Iniciando Chrome en modo headless")
    else:
        logger.info("Iniciando Chrome con ventana visible")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Obtener información de la empresa
        dv, company_name_csv = get_company_info(rut)
        
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
        
        # Crear directorio de destino
        safe_company_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_company_name = safe_company_name.replace(' ', '_')
        
        if dv:
            rut_completo = f"{rut}-{dv}"
        else:
            rut_completo = rut
            
        # Determinar modo/meses/step/carpeta
        normalized_mode = None
        if mode in {"annual", "quarterly", "total"}:
            normalized_mode = mode
        else:
            normalized_mode = "quarterly" if quarterly else "annual"

        if normalized_mode == "total":
            months_to_process = [3, 6, 9, 12]
            period_type = "total"
            iteration_step = -1
            period_dir_name = "Total"
        elif normalized_mode == "quarterly":
            months_to_process = [3, 6, 9, 12]
            period_type = "trimestral"
            iteration_step = step
            period_dir_name = "Trimestral"
        else:
            months_to_process = [12]
            period_type = "anual"
            iteration_step = step
            period_dir_name = "Anual"

        target_dir = os.path.join("./data/XBRL", period_dir_name, f"{rut_completo}_{safe_company_name}")
        os.makedirs(target_dir, exist_ok=True)
        logger.info(f"Directorio de destino: {target_dir}")

        # Detectar períodos ya existentes en la carpeta destino para omitir su descarga
        def discover_existing_periods(base_dir: str) -> set[str]:
            existing = set()
            try:
                # Buscar patrones YYYYMM con delimitadores opcionales
                pattern = re.compile(r"(20\d{2})[-_]?((?:0[1-9]|1[0-2]))")
                for root_dir, dirs, files in os.walk(base_dir):
                    for name in dirs + files:
                        match = pattern.search(name)
                        if match:
                            yyyymm = match.group(1) + match.group(2)
                            existing.add(yyyymm)
            except Exception as e:
                logger.warning(f"No se pudo explorar períodos existentes en {base_dir}: {e}")
            return existing

        # Construir un set de períodos existentes a partir de todas las carpetas posibles
        def discover_existing_periods_all_buckets(rut_num: str, rut_full: str | None, company_safe: str) -> set[str]:
            found: set[str] = set()
            # 1) Carpeta objetivo actual
            found |= discover_existing_periods(target_dir)

            # 2) Otras buckets: Anual, Trimestral, Total
            base_root = os.path.join("./data", "XBRL")
            candidates = ["Anual", "Trimestral", "Total"]
            for bucket in candidates:
                bucket_dir = os.path.join(base_root, bucket)
                if not os.path.isdir(bucket_dir):
                    continue
                try:
                    for sub in os.listdir(bucket_dir):
                        sub_path = os.path.join(bucket_dir, sub)
                        if not os.path.isdir(sub_path):
                            continue
                        # Emparejar por prefijo de RUT (con o sin DV)
                        if sub.startswith(str(rut_num)) or (rut_full and sub.startswith(str(rut_full))):
                            # Recolectar períodos desde esta carpeta
                            found |= discover_existing_periods(sub_path)
                except Exception:
                    continue
            return found

        existing_periods = discover_existing_periods_all_buckets(rut, rut_completo if dv else None, safe_company_name) if skip_existing else set()
        
        logger.info(f"Modo de descarga: {period_type}")
        logger.info(f"Meses a procesar: {months_to_process}")
        
        # Construir lista de períodos planeados y filtrar existentes (si corresponde)
        planned_periods = []
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
                logger.info(f"🔁 Omitiendo {skipped} período(s) ya existente(s) en {target_dir}")
            logger.info(f"📚 Períodos existentes detectados: {len(existing_periods)} | Ejemplos: {sorted(list(existing_periods))[:8]}")

        # Calcular total de operaciones para contador
        total_periods = len(planned_periods)
        logger.info(f"📊 Total de períodos a procesar: {total_periods}")
        logger.info(f"⏱️ Tiempo estimado: {total_periods * 30} segundos (~{(total_periods * 30) // 60} minutos)")

        # Progreso inicial (0)
        try:
            if callable(progress_hook):
                progress_hook(rut, 0, total_periods, None, None, total_periods * 30, 'init')
        except Exception:
            pass

        # Si no hay nada que descargar, devolver inmediatamente
        if total_periods == 0:
            logger.info("✅ No hay períodos nuevos para descargar. Saltando.")
            try:
                if callable(progress_hook):
                    progress_hook(rut, 0, 0, None, None, 0, 'skipped_all')
            except Exception:
                pass
            return target_dir, []
        
        downloaded_files = []
        current_operation = 0
        
        # FASE 1: DESCARGA TRANQUILA - Solo descargar sin mover archivos
        logger.debug("FASE 1: INICIANDO DESCARGA TRANQUILA (logs detallados enviados a archivo si el dashboard está activo)")
        
        # Función para limpiar archivos temporales antiguos en el directorio de descargas
        def clean_old_downloads():
            """Limpiar archivos XBRL antiguos (más de 2 horas)"""
            try:
                for file in os.listdir(downloads_dir):
                    if file.startswith("Estados_financieros_(XBRL)") and file.endswith(".zip"):
                        file_path = os.path.join(downloads_dir, file)
                        # Solo eliminar archivos antiguos (más de 2 horas)
                        if time.time() - os.path.getctime(file_path) > 7200:
                            os.remove(file_path)
                            logger.info(f"Archivo temporal antiguo eliminado: {file}")
            except Exception as e:
                logger.warning(f"Error limpiando directorio de descargas: {e}")
        
        # Función para verificar si hay un archivo XBRL completo y nuevo
        def check_new_download(timeout=60):
            """Verificar si hay una nueva descarga completada"""
            start_time = time.time()
            initial_files = set()
            
            # Obtener archivos iniciales
            try:
                initial_files = {f for f in os.listdir(downloads_dir) 
                               if f.startswith("Estados_financieros_(XBRL)") and f.endswith(".zip")}
            except:
                pass
            
            while time.time() - start_time < timeout:
                try:
                    current_files = {f for f in os.listdir(downloads_dir) 
                                   if f.startswith("Estados_financieros_(XBRL)") and f.endswith(".zip")}
                    
                    # Buscar archivos nuevos
                    new_files = current_files - initial_files
                    
                    for new_file in new_files:
                        file_path = os.path.join(downloads_dir, new_file)
                        
                        # Verificar que no sea un archivo temporal de descarga
                        if not new_file.endswith('.crdownload') and os.path.exists(file_path):
                            try:
                                # Verificar que el archivo esté completo
                                with zipfile.ZipFile(file_path, 'r') as zf:
                                    pass  # Si puede abrir, está completo
                                
                                logger.info(f"✅ Nueva descarga completada: {new_file}")
                                return True
                                
                            except (zipfile.BadZipFile, PermissionError):
                                # Archivo aún siendo descargado
                                continue
                
                except Exception as e:
                    pass
                
                time.sleep(2)  # Esperar más tiempo entre verificaciones
            
            logger.warning(f"No se detectó nueva descarga después de {timeout} segundos")
            return False
        
        # Función para verificar si hay enlace XBRL disponible
        def check_xbrl_link_available():
            """Verificar si hay enlace de descarga XBRL disponible"""
            try:
                # Buscar enlace que contenga "Estados financieros (XBRL)"
                xbrl_links = driver.find_elements(By.PARTIAL_LINK_TEXT, "Estados financieros (XBRL)")
                return len(xbrl_links) > 0
            except:
                return False
        
        # Función para esperar y mover archivo descargado
        def wait_for_download_and_move(expected_rut, target_dir, timeout=60):
            """Esperar que se complete la descarga y mover el archivo"""
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                # Buscar archivos XBRL en Downloads
                try:
                    for file in os.listdir(downloads_dir):
                        if file.startswith("Estados_financieros_(XBRL)") and file.endswith(".zip"):
                            file_path = os.path.join(downloads_dir, file)
                            
                            # Si se usa un directorio de descargas aislado por hilo, evitamos eliminar nada
                            # Solo ignoramos archivos que aún no correspondan si se especificó expected_rut
                            if expected_rut and expected_rut not in file:
                                # Ignorar y permitir que otros workers manejen sus propios directorios
                                continue
                            
                            # Verificar que el archivo no esté siendo descargado (sin .crdownload)
                            if not file.endswith('.crdownload') and os.path.exists(file_path):
                                # Verificar que el archivo no esté siendo usado
                                try:
                                    # Intentar abrir el archivo para verificar que está completo
                                    with zipfile.ZipFile(file_path, 'r') as zf:
                                        # Si podemos leer el zip, está completo
                                        pass
                                    
                                    # Mover archivo a directorio de destino
                                    target_path = os.path.join(target_dir, file)
                                    
                                    # Si ya existe el archivo, sobrescribir
                                    if os.path.exists(target_path):
                                        os.remove(target_path)
                                    
                                    shutil.move(file_path, target_path)
                                    logger.info(f"✅ Archivo descargado y movido: {file}")
                                    return target_path
                                    
                                except (zipfile.BadZipFile, PermissionError):
                                    # Archivo aún siendo descargado o corrupto
                                    time.sleep(1)
                                    continue
                
                except Exception as e:
                    # Error accediendo al directorio, continuar intentando
                    pass
                
                time.sleep(2)  # Esperar más tiempo entre verificaciones
            
            logger.warning(f"⚠️ Timeout esperando descarga después de {timeout} segundos")
            return None
        
        # Limpiar descargas anteriores
        clean_old_downloads()
        
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
                # Notificación opcional para dashboard de consola vía callback global si existe
                try:
                    from gui.main_window import CMFScraperGUI  # evita import top-level
                    pass
                except Exception:
                    pass
                # Verificar que estamos en la página correcta
                if "cmfchile.cl" not in driver.current_url:
                    logger.debug("Recargando página principal...")
                    driver.get(url)
                    time.sleep(3)

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
                    time.sleep(1)
                    submit_button.click()
                except ElementClickInterceptedException:
                    logger.debug("Click interceptado, usando JavaScript...")
                    driver.execute_script("arguments[0].click();", submit_button)

                # Esperar carga de la página
                time.sleep(5)

                # Verificar que estamos en la página correcta de la empresa
                try:
                    # Verificar que el RUT aparece en la página
                    page_source = driver.page_source
                    if rut not in page_source:
                        logger.warning(f"⚠️ El RUT {rut} no aparece en la página actual")
                        # Recargar la página principal
                        driver.get(url)
                        time.sleep(3)
                        continue

                    # Verificar nombre de empresa si está disponible
                    try:
                        current_company = driver.find_element(By.ID, "datos_ent").text
                        if "VIÑA SAN PEDRO" not in current_company.upper() and rut == "91041000":
                            logger.warning(f"⚠️ Empresa incorrecta detectada: {current_company}")
                            driver.get(url)
                            time.sleep(3)
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
                if not check_xbrl_link_available():
                    logger.warning(f"❌ No hay enlace XBRL disponible para {year}-{month:02d}")
                    driver.back()
                    time.sleep(2)
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
                        time.sleep(2)
                        continue

                    # Hacer click en el enlace con mejor manejo
                    try:
                        # Hacer scroll al enlace
                        driver.execute_script("arguments[0].scrollIntoView(true);", xbrl_link)
                        time.sleep(1)
                        xbrl_link.click()
                    except ElementClickInterceptedException:
                        logger.info("Click en enlace XBRL interceptado, usando JavaScript...")
                        driver.execute_script("arguments[0].click();", xbrl_link)

                    # Esperar a que se inicie la descarga
                    logger.debug("Esperando descarga...")
                    downloaded_file = wait_for_download_and_move(
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
                    time.sleep(3)

                except TimeoutException:
                    logger.warning(f"❌ No se encontró enlace XBRL para {year}-{month:02d}")
                    driver.back()
                    time.sleep(2)
                    continue

            except Exception as e:
                logger.error(f"❌ Error procesando período {year}-{month:02d}: {e}")

                # Intentar recuperarse
                try:
                    driver.back()
                    time.sleep(3)
                except:
                    # Si no puede volver atrás, recargar página
                    driver.get(url)
                    time.sleep(5)
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
        
        for file_path in downloaded_files.copy():  # Usar copy() para poder modificar la lista
            if file_path.endswith('.zip'):
                logger.debug(f"Extrayendo: {os.path.basename(file_path)}")
                extract_dir, extracted_files, success = auto_extract_and_cleanup_zip(file_path)
                
                if success:
                    extracted_count += 1
                    # Actualizar la lista para incluir la carpeta extraída en lugar del ZIP
                    downloaded_files.remove(file_path)
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
