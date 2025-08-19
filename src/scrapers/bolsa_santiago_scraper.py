# -*- coding: utf-8 -*-
"""
RUTAS CORREGIDAS PARA REORGANIZACIÓN
====================================
Las rutas han sido actualizadas para la nueva estructura del proyecto.

Cambios realizados:
# - Ruta corregida: ./data/RUT_Chilean_Companies/RUT_Chilean_Companies_Enriched.csv → data/companies/RUT_Chilean_Companies_Enriched.csv
# - Ruta corregida: data/RUT_Chilean_Companies/RUT_Chilean_Companies_Enriched.csv → data/companies/RUT_Chilean_Companies_Enriched.csv
"""

# -*- coding: utf-8 -*-
"""
RUTAS CORREGIDAS PARA REORGANIZACIÓN
====================================
Las rutas han sido actualizadas para la nueva estructura del proyecto.

Cambios realizados:
# - Ruta corregida: data/companies/RUT_Chilean_Companies_Enriched.csv → data/companies/RUT_Chilean_Companies_Enriched.csv
# - Ruta corregida: data/companies/RUT_Chilean_Companies_Enriched.csv → data/companies/RUT_Chilean_Companies_Enriched.csv
"""

#!/usr/bin/env python3
"""
Scraper de Bolsa de Santiago para enriquecer datos de empresas chilenas.
- Lee archivo Excel/CSV con datos base de empresas.
- Para cada empresa con ticker, extrae descripción y sitio web desde Bolsa de Santiago.
- Guarda resultado enriquecido manteniendo todas las columnas originales.
- Soporta modo headless y no-headless para debugging.
- Política estricta de reintentos con refresh automático.

Uso:
  python3 bolsa_santiago_scraper.py --input data/RUT_Chilean_Companies_Enriched.csv --output data/bolsa_enriched.xlsx
  python3 bolsa_santiago_scraper.py --ticker VSPT --test  # Solo probar un ticker
"""

import os
import sys
import time
import logging
import argparse
import urllib.parse
from typing import Optional, Dict, Tuple

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, WebDriverException

BOLSA_RESUMEN_URL = "https://www.bolsadesantiago.com/resumen_instrumento/{ticker}"

# Columnas esperadas en el archivo de entrada
EXPECTED_COLUMNS = [
    'Razón Social', 'RUT', 'Intermedio (Marzo)', 'Intermedio (Junio)', 
    'Intermedio (Septiembre)', 'Anual (Diciembre)', 'RUT_Numero', 'DV', 
    'RUT_Sin_Guión', 'RUT_CMF', 'Razon Social CMF', 'Nombre Fantasia', 
    'Vigencia', 'Telefono', 'Fax', 'Domicilio', 'Region', 'Ciudad', 
    'Comuna', 'Email Contacto', 'Sitio Web CMF', 'Codigo Postal', 'Ticker', 
    'Descripcion Empresa', 'Sitio Empresa'
]


class BolsaSantiagoScraper:
    def __init__(self, input_path: Optional[str] = None, output_path: Optional[str] = None, 
                 browser: str = "chrome", headless: bool = True, timeout: int = 25, force_all: bool = False):
        self.input_path = input_path or "data/companies/RUT_Chilean_Companies_Enriched.csv"
        self.output_path = output_path
        self.browser = browser.lower()
        self.headless = headless
        self.timeout = timeout
        self.force_all = force_all
        self.driver = None
        self.logger = self._setup_logger()
        self.stats = {
            'processed': 0,
            'bolsa_ok': 0,
            'bolsa_nodata': 0,
            'bolsa_timeout': 0,
            'bolsa_bad_request': 0,
            'bolsa_error': 0,
            'skipped_no_ticker': 0,
            'skipped_already_done': 0
        }

    def _setup_logger(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.StreamHandler(sys.stdout), 
                logging.FileHandler("bolsa_santiago_scraper.log")
            ],
        )
        return logging.getLogger("bolsa_scraper")

    def _setup_driver(self):
        """Configura el WebDriver según las opciones especificadas."""
        try:
            if self.browser == "firefox":
                opts = FirefoxOptions()
                if self.headless:
                    opts.add_argument("--headless")
                try:
                    opts.page_load_strategy = 'eager'
                except Exception:
                    pass
                opts.set_preference("intl.accept_languages", "es-CL,es,en-US,en")
                try:
                    opts.set_preference("general.useragent.override", 
                                      "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0")
                except Exception:
                    pass
                
                self.driver = webdriver.Firefox(options=opts)
                self.driver.set_window_size(1280, 900)
                self.driver.implicitly_wait(5)
                self.driver.set_page_load_timeout(90)
                self.driver.set_script_timeout(30)
                self.logger.info(f"WebDriver iniciado (Firefox, {'headless' if self.headless else 'NO headless'})")
                
            else:  # Chrome
                opts = ChromeOptions()
                if self.headless:
                    opts.add_argument("--headless=new")
                    opts.add_argument("--disable-gpu")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                opts.add_argument("--window-size=1280,900")
                opts.add_argument("--lang=es-CL")
                try:
                    opts.page_load_strategy = 'eager'
                except Exception:
                    pass
                opts.add_argument(
                    "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
                )
                try:
                    opts.add_experimental_option("excludeSwitches", ["enable-automation"])  
                    opts.add_experimental_option('useAutomationExtension', False)
                except Exception:
                    pass

                self.driver = webdriver.Chrome(options=opts)
                try:
                    self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                        'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined});'
                    })
                except Exception:
                    pass
                self.driver.implicitly_wait(5)
                self.driver.set_page_load_timeout(90)
                self.driver.set_script_timeout(30)
                self.logger.info(f"WebDriver iniciado (Chrome, {'headless' if self.headless else 'NO headless'})")
                
            return True
        except WebDriverException as e:
            self.logger.error(f"No se pudo iniciar WebDriver: {e}")
            return False

    def _dismiss_cookies(self):
        """Cierra banners de cookies comunes."""
        candidates = [
            "//button[contains(., 'Aceptar')]",
            "//button[contains(., 'ACEPTAR')]",
            "//button[contains(., 'Entendido')]",
            "//a[contains(., 'Aceptar')]",
        ]
        for xp in candidates:
            try:
                el = self.driver.find_element(By.XPATH, xp)
                if el.is_displayed():
                    try:
                        el.click()
                    except Exception:
                        self.driver.execute_script("arguments[0].click();", el)
                    self.logger.info(f"Banner/cookies cerrado con selector: {xp}")
                    break
            except Exception:
                continue

    def _click_resena_tab(self, timeout: int) -> bool:
        """Hace click en la pestaña 'Reseña de compañia'."""
        xpaths = [
            "//li[.//span[contains(., 'Reseña')]]",
            "//li[contains(@class,'k-item')][.//span[contains(., 'Rese')]]",
        ]
        for xp in xpaths:
            try:
                el = WebDriverWait(self.driver, max(4, timeout // 4)).until(
                    EC.element_to_be_clickable((By.XPATH, xp))
                )
                try:
                    self.driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", el)
                except Exception:
                    pass
                try:
                    el.click()
                except Exception:
                    self.driver.execute_script("arguments[0].click();", el)
                self.logger.info(f"Click en pestaña 'Reseña' con selector: {xp}")
                return True
            except Exception:
                continue
        self.logger.warning("No se encontró/activó la pestaña 'Reseña'")
        return False

    def _handle_captcha_with_visible_browser(self, url: str, ticker: str) -> bool:
        """
        Maneja CAPTCHA abriendo un navegador visible para resolverlo manualmente.
        Retorna True si se resolvió exitosamente, False si no.
        """
        self.logger.warning("=== CAPTCHA DETECTADO ===")
        self.logger.warning("Abriendo navegador visible para resolver CAPTCHA manualmente...")
        
        # Cerrar el driver headless actual
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        
        # Crear un nuevo driver no-headless
        original_headless = self.headless
        self.headless = False
        
        try:
            if not self._setup_driver():
                self.logger.error("No se pudo abrir navegador visible")
                return False
            
            self.logger.info(f"Navegador visible abierto. Cargando: {url}")
            self.driver.get(url)
            
            self.logger.warning("=== INSTRUCCIONES ===")
            self.logger.warning("1. Resuelve el CAPTCHA en la ventana del navegador")
            self.logger.warning("2. Espera a que la página cargue completamente")
            self.logger.warning("3. Presiona ENTER en esta terminal cuando termines")
            
            try:
                input("Presiona ENTER cuando hayas resuelto el CAPTCHA y la página esté cargada... ")
            except EOFError:
                pass
            
            # Verificar que se resolvió el CAPTCHA
            time.sleep(2)
            if self._detect_botwall():
                self.logger.error("CAPTCHA aún presente. Intento fallido.")
                return False
            
            self.logger.info("CAPTCHA resuelto exitosamente. Esperando 7 segundos...")
            time.sleep(7)
            
            # Mantener el navegador no-headless para evitar futuros CAPTCHAs
            self.logger.info("Manteniendo navegador visible para el resto de la sesión (evita más CAPTCHAs)")
            return True
            
        except Exception as e:
            self.logger.error(f"Error manejando CAPTCHA: {e}")
            return False
        # NO restaurar headless - mantener visible para evitar más CAPTCHAs

    def _detect_botwall(self) -> bool:
        """Detecta si hay un botwall/CAPTCHA activo."""
        try:
            ps = (self.driver.page_source or "").lower()
            texts = [
                "we apologize for the inconvenience",
                "please solve this captcha",
                "your activity and behavior on this site",
                "request unblock",
                "incident id:",
            ]
            return any(t in ps for t in texts)
        except Exception:
            return False

    def _save_debug(self, ticker: str, label: str):
        """Guarda HTML y screenshot para debugging."""
        outdir = os.path.join("data", "debug")
        os.makedirs(outdir, exist_ok=True)
        html_path = os.path.join(outdir, f"{ticker}_{label}.html")
        png_path = os.path.join(outdir, f"{ticker}_{label}.png")
        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(self.driver.page_source)
            self.driver.save_screenshot(png_path)
            self.logger.info(f"Debug guardado: {html_path}, {png_path}")
        except Exception as e:
            self.logger.warning(f"No se pudo guardar debug: {e}")

    def _ticker_variants(self, ticker: str) -> list[str]:
        """Genera variantes del ticker para probar."""
        t = (ticker or "").strip().upper()
        if not t:
            return []
        base = t
        no_spaces = t.replace(" ", "")
        hyphens = t.replace(" ", "-")
        dots_removed = t.replace(".", "")
        slashes_removed = t.replace("/", "")
        variants = [base, no_spaces, hyphens, dots_removed, slashes_removed]
        # Deduplicate preserving order
        seen = set()
        ordered = []
        for v in variants:
            if v and v not in seen:
                seen.add(v)
                ordered.append(v)
        return ordered

    def scrape_ticker_resena(self, ticker: str) -> Tuple[str, str]:
        """
        Extrae reseña y link 'Visitar Empresa' desde Bolsa de Santiago por ticker.
        Aplica política estricta: I1, I2 (dos intentos rápidos). Si vacío: refresh -> 5s -> click pestaña -> 2s -> R1, R2.
        
        Returns:
            Tuple[str, str]: (descripcion, sitio_empresa)
        """
        if not ticker:
            return ("", "")

        for variant in self._ticker_variants(ticker):
            url = BOLSA_RESUMEN_URL.format(ticker=urllib.parse.quote(variant))
            try:
                self.logger.info(f"[Bolsa] Abriendo URL: {url}")
                self.driver.get(url)
                self.logger.info("Navegación completada (o DOMContentLoaded) tras driver.get")
                self._dismiss_cookies()

                # Detección rápida de "400 Bad Request" y similares
                time.sleep(0.3)
                ps = (self.driver.page_source or "").lower()
                if "400 bad request" in ps or "the page you are looking for is unavailable" in ps:
                    self.logger.warning(f"Bolsa 400 Bad Request para '{ticker}' (variante: '{variant}') -> se omite variante")
                    self.stats['bolsa_bad_request'] += 1
                    continue
                    
                # También por DOM explícito (con manejo robusto de errores)
                try:
                    h2 = self.driver.find_elements(By.XPATH, "//h2[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '400 bad request')]")
                    if h2:
                        self.logger.warning(f"Bolsa 400 Bad Request DOM para '{ticker}' (variante: '{variant}') -> se omite variante")
                        self.stats['bolsa_bad_request'] += 1
                        continue
                except Exception as e:
                    self.logger.debug(f"Error chequeando DOM 400: {e}")
                    pass

                # Detección de botwall/CAPTCHA (con manejo robusto de errores)
                try:
                    if self._detect_botwall():
                        if self.headless:
                            # Cambiar automáticamente a modo visible para resolver CAPTCHA
                            if self._handle_captcha_with_visible_browser(url, ticker):
                                self.logger.info("CAPTCHA resuelto. Continuando con scraping...")
                                # Continuar con el scraping normal desde aquí
                            else:
                                self.logger.error("No se pudo resolver CAPTCHA. Saltando ticker.")
                                self.stats['bolsa_error'] += 1
                                continue
                        else:
                            self.logger.warning("Detectado botwall/CAPTCHA. Resuélvelo manualmente en la ventana del navegador.")
                            self._save_debug(ticker, "botwall")
                            try:
                                input("Cuando termines el CAPTCHA y la página cargue, presiona ENTER para continuar… ")
                            except EOFError:
                                pass
                            self.logger.info("Esperando 7 segundos tras resolución manual...")
                            time.sleep(7)
                except Exception as e:
                    self.logger.warning(f"Error en detección de botwall: {e}")
                    # Continuar asumiendo que no hay botwall

                # Espera inicial de la app (encabezado del instrumento)
                try:
                    WebDriverWait(self.driver, max(6, self.timeout // 3)).until(
                        EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'card-header')]//h4"))
                    )
                    self.logger.info("Encabezado del instrumento cargado")
                except Exception:
                    self.logger.warning("No apareció encabezado del instrumento a tiempo")

                # Intentar activar la pestaña "Reseña de compañia"
                self._click_resena_tab(self.timeout)

                # Esperar contenedor de la reseña o mensaje "No existe información."
                try:
                    self.logger.info("Esperando contenedor de reseña o mensaje 'No existe información.'…")
                    WebDriverWait(self.driver, self.timeout).until(
                        EC.presence_of_element_located((
                            By.XPATH,
                            "//div[contains(@ng-controller,'resenaCompaniaController')]"
                            " | //nodata//span[contains(., 'No existe información')]"
                            " | //span[contains(., 'No existe información')]"
                        ))
                    )
                    self.logger.info("Contenedor de reseña presente")
                    container_ready = True
                except TimeoutException:
                    self.logger.warning(f"Bolsa: contenedor de reseña no presente en {self.timeout}s para '{ticker}' → se forzará refresh y reintento")
                    container_ready = False

                # Intentar leer el título h4 (suele contener el ticker/empresa) — no es obligatorio
                try:
                    self.logger.info("Buscando título h4 de reseña…")
                    h4 = self.driver.find_element(By.XPATH, "//div[contains(@ng-controller,'resenaCompaniaController')]//div[contains(@class,'card-header')]//h4")
                    _title = (h4.text or "").strip()
                    self.logger.info(f"Título reseña (h4): {_title or '-'}")
                except Exception:
                    self.logger.info("No se encontró título h4 de reseña")

                # Mensaje nodata
                if container_ready:
                    try:
                        nodata = self.driver.find_element(By.XPATH, "//span[contains(., 'No existe información')]")
                        if nodata and nodata.is_displayed():
                            self.stats['bolsa_nodata'] += 1
                            self.logger.info("Resultado: No existe información.")
                            return ("No existe información.", "")
                    except Exception:
                        pass

                # Política estricta: I1, I2 (dos intentos rápidos). Si vacío: refresh -> 5s -> click pestaña -> 2s -> R1, R2.
                body_xpath = "//div[contains(@ng-controller,'resenaCompaniaController')]//div[contains(@class,'card-body')][not(contains(@class,'ng-hide'))]"
                p_xpath = body_xpath + "//p"

                def read_ticks(prefix: str, ticks: int) -> str:
                    local_body = None
                    try:
                        local_body = WebDriverWait(self.driver, min(self.timeout, 3)).until(
                            EC.visibility_of_element_located((By.XPATH, body_xpath))
                        )
                    except Exception:
                        local_body = None
                    for i in range(1, ticks + 1):
                        try:
                            if local_body is None:
                                local_body = self.driver.find_element(By.XPATH, body_xpath)
                            try:
                                cls = local_body.get_attribute("class")
                                html_len = len(local_body.get_attribute("innerHTML") or "")
                                self.logger.info(f"{prefix} t={i}s clase='{cls}', innerHTML={html_len} bytes")
                            except Exception:
                                pass
                            try:
                                p_el = self.driver.find_element(By.XPATH, p_xpath)
                                txt = (p_el.text or "").strip()
                            except Exception:
                                txt = (local_body.text or "").strip()
                            self.logger.info(f"{prefix} intento desc t={i}s -> {len(txt)} chars")
                            if txt:
                                return txt
                        except Exception:
                            pass
                        time.sleep(1)
                    return ""

                # Dos intentos iniciales (I1, I2)
                descripcion = read_ticks("I1", 1)
                if not descripcion:
                    descripcion = read_ticks("I2", 1)

                if not descripcion or not container_ready:
                    # Refresh, esperar 5s, reactivar pestaña, esperar 2s y reintentar
                    try:
                        self.driver.refresh()
                    except Exception:
                        pass
                    # Espera breve por DOM base y estabilización post-refresh
                    try:
                        WebDriverWait(self.driver, min(self.timeout, 10)).until(
                            EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'card-header')]//h4"))
                        )
                    except Exception:
                        pass
                    self.logger.info("Bolsa: esperando 5s tras refresh…")
                    time.sleep(5)
                    self._click_resena_tab(max(6, self.timeout // 3))
                    self.logger.info("Bolsa: esperando 2s tras click en 'Reseña'…")
                    time.sleep(2)
                    descripcion = read_ticks("R1", 1)
                    if not descripcion:
                        descripcion = read_ticks("R2", 1)

                # Link "Visitar Empresa"
                sitio = ""
                try:
                    a = self.driver.find_element(
                        By.XPATH,
                        "//div[contains(@ng-controller,'resenaCompaniaController')]//a[contains(., 'Visitar Empresa')]"
                    )
                    sitio = a.get_attribute("href") or ""
                except NoSuchElementException:
                    sitio = ""

                if sitio:
                    self.logger.info(f"Link 'Visitar Empresa': {sitio}")
                else:
                    self.logger.info("No se encontró link 'Visitar Empresa'")
                self.logger.info(f"Descripción ({len(descripcion)} chars): {descripcion[:200]}{'...' if len(descripcion)>200 else ''}")

                self.stats['bolsa_ok'] += 1
                self.logger.debug(f"Bolsa OK con variante '{variant}' URL={url}")
                return (descripcion or "", sitio or "")
                
            except TimeoutException:
                self.logger.warning(f"Timeout Bolsa para ticker '{ticker}' (variante: '{variant}') URL={url}")
                self.stats['bolsa_timeout'] += 1
                # Tratar timeout como "No existe información."
                self.logger.info(f"Bolsa: se asume 'No existe información.' para ticker '{ticker}' tras timeout en variante '{variant}'")
                self.stats['bolsa_nodata'] += 1
                return ("No existe información.", "")
            except Exception as e:
                self.logger.error(f"Error Bolsa para ticker '{ticker}' (variante: '{variant}'): {e}")
                self.stats['bolsa_error'] += 1
                continue

        # Si ninguna variante funcionó ni timeouteó, retornar vacío
        return ("", "")

    def process_file(self) -> bool:
        """Procesa el archivo de entrada y enriquece con datos de Bolsa de Santiago.
        
        Implementa lógica dual:
        1. Lee los tickers del archivo base (input_path)
        2. Verifica descripciones existentes en el archivo de salida (_BolsaEnriched.csv)
        """
        if not self._setup_driver():
            return False

        try:
            # Leer archivo de entrada (base para tickers)
            if self.input_path.endswith('.xlsx'):
                df_base = pd.read_excel(self.input_path)
            else:
                df_base = pd.read_csv(self.input_path)
                
            self.logger.info(f"Archivo base leído: {self.input_path} ({len(df_base)} filas)")

            # Verificar que existan las columnas necesarias
            if 'Ticker' not in df_base.columns:
                self.logger.error("El archivo base debe contener una columna 'Ticker'")
                return False

            # Intentar leer archivo de salida previo con descripciones de Bolsa
            output_dir = "./data/RUT_Chilean_Companies"
            base_name = os.path.splitext(os.path.basename(self.input_path))[0]
            existing_output_path = os.path.join(output_dir, f"{base_name}_BolsaEnriched.csv")
            
            df_enriched = None
            existing_descriptions = {}
            
            if os.path.exists(existing_output_path) and not self.force_all:
                try:
                    df_enriched = pd.read_csv(existing_output_path)
                    self.logger.info(f"Archivo enriquecido previo encontrado: {existing_output_path} ({len(df_enriched)} filas)")
                    
                    # Crear diccionario de descripciones existentes basado en Ticker
                    for idx, row in df_enriched.iterrows():
                        ticker = str(row.get('Ticker', '')).strip()
                        desc = str(row.get('Descripcion Empresa', '')).strip()
                        sitio = str(row.get('Sitio Empresa', '')).strip()
                        
                        # Solo considerar válidas las descripciones con contenido real
                        if (ticker and desc and 
                            desc.lower() not in ['nan', 'none', '', 'null', '<na>', 'n/a'] and 
                            len(desc) > 10):  # Mínimo 10 chars
                            existing_descriptions[ticker] = {
                                'descripcion': desc,
                                'sitio': sitio,
                                'row_data': row.to_dict()
                            }
                    
                    self.logger.info(f"Descripciones previas encontradas: {len(existing_descriptions)} tickers")
                    
                except Exception as e:
                    self.logger.warning(f"Error leyendo archivo enriquecido previo: {e}")
                    df_enriched = None
            else:
                if self.force_all:
                    self.logger.info("Modo FORCE-ALL: ignorando archivo de salida previo")
                else:
                    self.logger.info("No se encontró archivo de salida previo")

            # Trabajar con el archivo base como punto de partida
            df = df_base.copy()
            
            # Agregar columnas de Bolsa si no existen (con dtype string)
            if 'Descripcion Empresa' not in df.columns:
                df['Descripcion Empresa'] = pd.Series([""] * len(df), dtype="string")
            if 'Sitio Empresa' not in df.columns:
                df['Sitio Empresa'] = pd.Series([""] * len(df), dtype="string")
            
            # Asegurar que las columnas existentes sean string para evitar warnings
            if 'Descripcion Empresa' in df.columns:
                df['Descripcion Empresa'] = df['Descripcion Empresa'].astype("string")
            if 'Sitio Empresa' in df.columns:
                df['Sitio Empresa'] = df['Sitio Empresa'].astype("string")

            # Si hay archivo enriquecido previo, usar esos datos como base
            if df_enriched is not None and len(existing_descriptions) > 0:
                # Actualizar descripciones desde archivo previo
                for idx, row in df.iterrows():
                    ticker = str(row.get('Ticker', '')).strip()
                    if ticker in existing_descriptions:
                        df.at[idx, 'Descripcion Empresa'] = existing_descriptions[ticker]['descripcion']
                        df.at[idx, 'Sitio Empresa'] = existing_descriptions[ticker]['sitio']

            total = len(df)
            self.logger.info(f"Procesando {total} empresas...")
            
            if self.force_all:
                self.logger.info("Modo FORCE-ALL activado: se procesarán todas las filas (incluso las que ya tienen descripción)")

            # Contar cuántas ya tienen descripción
            already_processed = 0
            for idx, row in df.iterrows():
                existing_desc = str(row.get('Descripcion Empresa', '')).strip()
                # Verificar si tiene contenido real (no vacío, no NaN, no null, no <NA>)
                if (existing_desc and 
                    existing_desc.lower() not in ['nan', 'none', '', 'null', '<na>', 'n/a'] and 
                    len(existing_desc) > 10):  # Mínimo 10 chars para ser considerado válido
                    already_processed += 1
            
            pending = total - already_processed
            if not self.force_all:
                self.logger.info(f"Ya procesadas: {already_processed}, Pendientes: {pending}")
            else:
                self.logger.info(f"Ya procesadas: {already_processed} (se reprocesarán), Total a procesar: {total}")

            # Procesar cada fila
            for idx, row in df.iterrows():
                ticker = str(row.get('Ticker', '')).strip()
                empresa = str(row.get('Razón Social', row.get('Razon Social CMF', ''))).strip()
                existing_desc = str(row.get('Descripcion Empresa', '')).strip()
                
                self.logger.info(f"[{idx+1}/{total}] Procesando: {empresa} | Ticker: {ticker or 'N/A'}")
                
                # Verificar si ya tiene descripción (excepto si se fuerza procesar todas)
                if (not self.force_all and existing_desc and 
                    existing_desc.lower() not in ['nan', 'none', '', 'null', '<na>', 'n/a'] and 
                    len(existing_desc) > 10):  # Mínimo 10 chars para ser considerado válido
                    self.logger.info(f"[{idx+1}/{total}] Ya tiene descripción ({len(existing_desc)} chars) -> SALTANDO")
                    self.stats['skipped_already_done'] += 1
                    self.stats['processed'] += 1
                    continue
                
                if not ticker or ticker.lower() in ['nan', 'none', '']:
                    self.logger.info(f"[{idx+1}/{total}] Sin ticker válido; se omite Bolsa de Santiago")
                    self.stats['skipped_no_ticker'] += 1
                    self.stats['processed'] += 1
                    continue

                # Scraping de Bolsa de Santiago
                self.logger.info(f"[{idx+1}/{total}] Buscando descripción en Bolsa de Santiago...")
                descripcion, sitio = self.scrape_ticker_resena(ticker)
                df.at[idx, 'Descripcion Empresa'] = descripcion
                df.at[idx, 'Sitio Empresa'] = sitio
                
                if descripcion == "No existe información.":
                    self.logger.info(f"[{idx+1}/{total}] Bolsa NODATA (No existe información.)")
                elif descripcion:
                    self.logger.info(f"[{idx+1}/{total}] Bolsa OK, desc {len(descripcion)} chars, sitio='{sitio or '-'}'")
                else:
                    self.logger.info(f"[{idx+1}/{total}] Bolsa sin datos")

                self.stats['processed'] += 1
                
                # Pausa breve entre solicitudes
                time.sleep(1.0)

            # Guardar resultado
            if self.output_path:
                if self.output_path.endswith('.xlsx'):
                    df.to_excel(self.output_path, index=False)
                else:
                    df.to_csv(self.output_path, index=False, encoding='utf-8')
                self.logger.info(f"Archivo enriquecido guardado: {self.output_path}")
            else:
                # Auto-generar nombre de salida
                output_dir = "./data/RUT_Chilean_Companies"
                os.makedirs(output_dir, exist_ok=True)
                base_name = os.path.splitext(os.path.basename(self.input_path))[0]
                output_xlsx = f"{output_dir}/{base_name}_BolsaEnriched.xlsx"
                output_csv = f"{output_dir}/{base_name}_BolsaEnriched.csv"

                df.to_excel(output_xlsx, index=False)
                df.to_csv(output_csv, index=False, encoding='utf-8')
                self.logger.info(f"Archivos guardados: {output_xlsx}, {output_csv}")

            # Resumen
            self.logger.info("==== RESUMEN BOLSA DE SANTIAGO ====")
            self.logger.info(f"Procesadas: {self.stats['processed']} / {total}")
            self.logger.info(f"Ya tenían descripción: {self.stats['skipped_already_done']}")
            self.logger.info(f"Sin ticker: {self.stats['skipped_no_ticker']}")
            self.logger.info(f"Bolsa -> OK: {self.stats['bolsa_ok']}, Sin datos: {self.stats['bolsa_nodata']}, "
                           f"Timeouts: {self.stats['bolsa_timeout']}, BadRequest: {self.stats['bolsa_bad_request']}, "
                           f"Errores: {self.stats['bolsa_error']}")
            
            # Sugerencia si hay muchos errores por CAPTCHA
            if self.stats['bolsa_error'] > 0 and self.headless:
                self.logger.warning("=== RECOMENDACIÓN ===")
                self.logger.warning("Se detectaron errores por CAPTCHA/botwall en modo headless.")
                self.logger.warning("Para mejor compatibilidad, intenta ejecutar con --no-headless:")
                self.logger.warning(f"python {sys.argv[0]} --no-headless --input {self.input_path}")

            return True

        except Exception as e:
            self.logger.error(f"Error procesando archivo: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver cerrado")

    def test_single_ticker(self, ticker: str, keep_open: bool = False) -> int:
        """Prueba un solo ticker en modo debugging."""
        if not self._setup_driver():
            return 1

        try:
            self.logger.info(f"=== MODO TEST: {ticker} ===")
            descripcion, sitio = self.scrape_ticker_resena(ticker)
            
            self.logger.info("=== RESULTADO ===")
            self.logger.info(f"Ticker: {ticker}")
            self.logger.info(f"Descripción ({len(descripcion)} chars): {descripcion}")
            self.logger.info(f"Sitio Empresa: {sitio or '-'}")
            
            if keep_open and not self.headless:
                input("Presiona ENTER para cerrar el navegador… ")
                
            return 0
            
        except Exception as e:
            self.logger.error(f"Error en test: {e}")
            return 1
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver cerrado")


def main():
    parser = argparse.ArgumentParser(description="Scraper de Bolsa de Santiago para enriquecer datos de empresas chilenas")
    parser.add_argument("--input", default="data/companies/RUT_Chilean_Companies_Enriched.csv", 
                       help="Archivo de entrada (Excel/CSV) con datos de empresas (default: data/companies/RUT_Chilean_Companies_Enriched.csv)")
    parser.add_argument("--output", help="Archivo de salida (Excel/CSV) enriquecido")
    parser.add_argument("--browser", choices=["chrome", "firefox"], default="chrome", help="Navegador (default: chrome)")
    parser.add_argument("--headless", action="store_true", default=True, help="Modo headless (default: True)")
    parser.add_argument("--no-headless", dest="headless", action="store_false", help="Desactivar modo headless")
    parser.add_argument("--timeout", type=int, default=25, help="Timeout en segundos (default: 25)")
    parser.add_argument("--force-all", action="store_true", help="Forzar procesamiento de todas las filas (incluso las que ya tienen descripción)")
    
    # Modo test
    parser.add_argument("--test", action="store_true", help="Modo test: probar solo un ticker")
    parser.add_argument("--ticker", default="VSPT", help="Ticker para modo test (default: VSPT)")
    parser.add_argument("--keep-open", action="store_true", help="Mantener navegador abierto tras test")
    
    args = parser.parse_args()

    if args.test:
        # Modo test de un solo ticker
        scraper = BolsaSantiagoScraper(
            browser=args.browser,
            headless=args.headless,
            timeout=args.timeout
        )
        return scraper.test_single_ticker(args.ticker, args.keep_open)
    else:
        # Modo procesamiento de archivo
        scraper = BolsaSantiagoScraper(
            input_path=args.input,
            output_path=args.output,
            browser=args.browser,
            headless=args.headless,
            timeout=args.timeout,
            force_all=args.force_all
        )
        return 0 if scraper.process_file() else 1


if __name__ == "__main__":
    sys.exit(main())
