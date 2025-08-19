#!/usr/bin/env python3
"""
CMF XBRL Availability Checker - Versión Optimizada y Concurrente
Verifica qué archivos XBRL nuevos están disponibles en la CMF desde la fecha más reciente local
"""

import os
import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Generator, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# Agregar el directorio raíz del proyecto al path
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
sys.path.insert(0, str(project_root))

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import Select
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
    from webdriver_manager.chrome import ChromeDriverManager
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Selenium o webdriver-manager no disponible. Instala con: pip install selenium webdriver-manager")

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(threadName)s] - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

class CMFXBRLChecker:
    """Verificador de disponibilidad XBRL en CMF - Versión optimizada y concurrente"""
    
    def __init__(self, headless: bool = True, debug: bool = False):
        self.headless = headless
        self.debug = debug
        self.xbrl_base_path = project_root / "data" / "XBRL" / "Total"
        
        if debug:
            logger.setLevel(logging.DEBUG)
    
    def _create_driver(self) -> webdriver.Chrome:
        """Configurar y devolver un driver de Chrome para un worker."""
        if not SELENIUM_AVAILABLE:
            raise ImportError("Selenium no está disponible")
        
        options = Options()
        if self.headless:
            options.add_argument("--headless")
        
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        
        prefs = {
            "download.default_directory": str(project_root / "temp"),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
            "profile.default_content_settings.popups": 0,
            "profile.default_content_setting_values.automatic_downloads": 1
        }
        options.add_experimental_option("prefs", prefs)
        
        try:
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            return driver
        except Exception as e:
            logger.error(f"Error configurando Chrome driver para worker: {e}")
            raise
    
    def get_local_companies_info(self) -> Dict[str, Dict]:
        """Obtener información de empresas locales de forma más eficiente"""
        logger.info(f"Escaneando empresas locales en: {self.xbrl_base_path}")
        
        if not self.xbrl_base_path.exists():
            logger.warning(f"Ruta XBRL no existe: {self.xbrl_base_path}")
            return {}
        
        companies = {}
        for company_dir in self.xbrl_base_path.iterdir():
            if not company_dir.is_dir():
                continue

            company_name = company_dir.name
            periods = []
            
            for period_dir in company_dir.glob("*_extracted"):
                try:
                    period_match = period_dir.name.split('_')[-2]
                    if len(period_match) == 6 and period_match.isdigit():
                        periods.append(period_match)
                except IndexError:
                    logger.debug(f"No se pudo extraer período de: {period_dir.name}")

            if periods:
                rut = company_name.split('_')[0]
                latest_period = max(periods)
                companies[company_name] = {
                    'rut': rut,
                    'latest_period': latest_period,
                    'total_periods': len(periods)
                }
                logger.debug(f"{company_name}: RUT {rut}, último período {latest_period}")
        
        logger.info(f"Encontradas {len(companies)} empresas locales")
        return companies

    def _generate_check_periods(self, latest_local_period: str) -> Generator[Tuple[int, int], None, None]:
        """Generador de períodos a verificar - empieza desde el SIGUIENTE al último local"""
        latest_year = int(latest_local_period[:4])
        latest_month = int(latest_local_period[4:6])
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        if latest_month == 3: start_year, start_month = latest_year, 6
        elif latest_month == 6: start_year, start_month = latest_year, 9
        elif latest_month == 9: start_year, start_month = latest_year, 12
        elif latest_month == 12: start_year, start_month = latest_year + 1, 3
        else: start_year, start_month = latest_year, 6
        
        logger.debug(f"Último período local: {latest_year}-{latest_month:02d}. Verificando desde: {start_year}-{start_month:02d}")
        
        year, month = start_year, start_month
        
        while year <= current_year:
            if year > current_year or (year == current_year and month > current_month):
                break
            yield year, month
            if month == 3: month = 6
            elif month == 6: month = 9
            elif month == 9: month = 12
            elif month == 12: month, year = 3, year + 1

    def check_new_xbrl_availability(self, driver: webdriver.Chrome, company_name: str, rut: str, latest_local_period: str) -> List[str]:
        """Verificar disponibilidad XBRL para una empresa (diseñado para ser llamado por un worker)."""
        rut_numero = rut.split('-')[0]
        url = f"https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut_numero}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
        new_periods = []
        
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.ID, "fm")))
            
            periods_to_check = list(self._generate_check_periods(latest_local_period))
            if not periods_to_check:
                return new_periods
            
            for i, (year, month) in enumerate(periods_to_check):
                period_key = f"{year}{month:02d}"
                logger.info(f"Verificando período {i+1}/{len(periods_to_check)}: {year}-{month:02d} para {company_name}")
                
                try:
                    if "cmfchile.cl" not in driver.current_url:
                        driver.get(url)
                        wait.until(EC.presence_of_element_located((By.ID, "fm")))
                    
                    Select(driver.find_element(By.ID, "aa")).select_by_visible_text(str(year))
                    Select(driver.find_element(By.ID, "mm")).select_by_visible_text(f"{month:02d}")
                    
                    try: Select(driver.find_element(By.NAME, "tipo")).select_by_visible_text("Consolidado")
                    except: pass
                    try: Select(driver.find_element(By.NAME, "tipo_norma")).select_by_visible_text("Estándar IFRS")
                    except: pass
                    
                    submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                    try:
                        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
                        time.sleep(0.5)
                        submit_button.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", submit_button)
                    
                    try:
                        wait.until(EC.presence_of_element_located(
                            (By.XPATH, "//a[contains(text(), 'Estados financieros (XBRL)')]")
                        ))
                        new_periods.append(period_key)
                        logger.info(f"✅ XBRL disponible para {company_name} en {year}-{month:02d}")
                    except TimeoutException:
                        logger.info(f"❌ XBRL no disponible para {company_name} en {year}-{month:02d}")
                    
                    driver.back()
                    wait.until(EC.presence_of_element_located((By.ID, "fm")))

                except (NoSuchElementException, TimeoutException) as e:
                    logger.warning(f"Error en período {year}-{month:02d} para {company_name}: {e}. Intentando recuperar.")
                    driver.get(url)
                    wait.until(EC.presence_of_element_located((By.ID, "fm")))
                    continue
            
            return new_periods
        
        except Exception as e:
            logger.error(f"Error fatal verificando {company_name}: {e}", exc_info=self.debug)
            return new_periods

    def _worker_check(self, company_info: Tuple[str, Dict]) -> Tuple[str, List[str]]:
        """Función ejecutada por cada worker en el pool."""
        company_name, info = company_info
        driver = None
        try:
            driver = self._create_driver()
            new_periods = self.check_new_xbrl_availability(
                driver, company_name, info['rut'], info['latest_period']
            )
            return company_name, new_periods
        except Exception as e:
            logger.error(f"Error en worker para {company_name}: {e}", exc_info=self.debug)
            return company_name, []
        finally:
            if driver:
                driver.quit()

    def run_check(self, company_filter: Optional[str] = None, max_workers: int = 4) -> None:
        """Ejecutar verificación completa de forma optimizada y concurrente."""
        logger.info("INICIANDO VERIFICACION DE DISPONIBILIDAD XBRL")
        logger.info(f"Usando hasta {max_workers} workers simultáneos.")
        logger.info("=" * 60)
        
        local_companies = self.get_local_companies_info()
        
        if not local_companies:
            logger.warning("No se encontraron empresas locales para verificar.")
            return

        if company_filter:
            if company_filter in local_companies:
                local_companies = {company_filter: local_companies[company_filter]}
            else:
                logger.error(f"Empresa '{company_filter}' no encontrada en los registros locales.")
                return
        
        summary = self._initialize_summary(local_companies)
        
        with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='XBRLChecker') as executor:
            tasks = list(local_companies.items())
            future_to_company = {executor.submit(self._worker_check, task): task[0] for task in tasks}
            
            for future in as_completed(future_to_company):
                company_name_from_future = future_to_company[future]
                try:
                    company_name, new_periods = future.result()
                    
                    if new_periods:
                        summary['companies_with_new_xbrl'] += 1
                        summary['total_new_periods'] += len(new_periods)
                        summary['details'][company_name].update({
                            'new_periods_available': new_periods,
                            'count_new_periods': len(new_periods)
                        })
                except Exception as exc:
                    logger.error(f"El worker para {company_name_from_future} generó una excepción: {exc}", exc_info=self.debug)

        self.show_final_summary(summary)

    def _initialize_summary(self, companies: Dict) -> Dict:
        """Inicializar el diccionario de resumen"""
        return {
            'total_companies': len(companies),
            'companies_with_new_xbrl': 0,
            'total_new_periods': 0,
            'details': {
                name: {
                    'rut': info['rut'],
                    'latest_local_period': info['latest_period'],
                    'new_periods_available': [],
                    'count_new_periods': 0
                } for name, info in companies.items()
            }
        }

    def show_final_summary(self, summary: Dict) -> None:
        """Mostrar resumen final de la verificación"""
        logger.info("=" * 60)
        logger.info("RESUMEN FINAL DE VERIFICACION")
        logger.info("=" * 60)
        
        logger.info(f"Total de empresas verificadas: {summary['total_companies']}")
        logger.info(f"Empresas con XBRL nuevo: {summary['companies_with_new_xbrl']}")
        logger.info(f"Total de períodos nuevos: {summary['total_new_periods']}")
        
        if summary['total_new_periods'] > 0:
            logger.info("\nPERIODOS NUEVOS DISPONIBLES PARA DESCARGA:")
            for company, detail in summary['details'].items():
                if detail['new_periods_available']:
                    logger.info(f"\nEmpresa: {company} (RUT: {detail['rut']})")
                    logger.info(f"  Último período local: {detail['latest_local_period']}")
                    logger.info(f"  Períodos nuevos: {', '.join(detail['new_periods_available'])}")
        else:
            logger.info("\nNo se encontraron períodos nuevos. Tu colección de XBRL está actualizada.")
        
        self.save_summary(summary)

    def save_summary(self, summary: Dict) -> None:
        """Guardar resumen en un archivo de texto"""
        results_dir = project_root / "output" / "xbrl_checker"
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = results_dir / f"xbrl_summary_{timestamp}.txt"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write("RESUMEN DE VERIFICACION XBRL CMF\n")
                f.write("=" * 50 + "\n")
                f.write(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Total empresas: {summary['total_companies']}\n")
                f.write(f"Empresas con XBRL nuevo: {summary['companies_with_new_xbrl']}\n")
                f.write(f"Total períodos nuevos: {summary['total_new_periods']}\n\n")
                
                if summary['total_new_periods'] > 0:
                    f.write("PERIODOS NUEVOS DISPONIBLES:\n")
                    f.write("-" * 30 + "\n")
                    for company, detail in summary['details'].items():
                        if detail['new_periods_available']:
                            f.write(f"\n{company} (RUT: {detail['rut']})\n")
                            f.write(f"  Último local: {detail['latest_local_period']}\n")
                            f.write(f"  Nuevos: {', '.join(detail['new_periods_available'])}\n")
            
            logger.info(f"Resumen guardado en: {filename}")
        except IOError as e:
            logger.error(f"No se pudo guardar el resumen en {filename}: {e}")

def main():
    """Función principal para ejecutar el verificador desde la línea de comandos"""
    parser = argparse.ArgumentParser(description="Verificador de disponibilidad XBRL CMF - Versión Optimizada y Concurrente")
    parser.add_argument("-c", "--company", help="Verificar solo una empresa específica por nombre")
    parser.add_argument("-w", "--workers", type=int, default=4, help="Número de workers (navegadores) simultáneos. Default: 4")
    parser.add_argument("--no-headless", action="store_true", help="Ejecutar con ventana de navegador visible")
    parser.add_argument("-d", "--debug", action="store_true", help="Activar logging de depuración")
    
    args = parser.parse_args()
    
    checker = CMFXBRLChecker(
        headless=not args.no_headless,
        debug=args.debug
    )
    
    try:
        checker.run_check(company_filter=args.company, max_workers=args.workers)
    except KeyboardInterrupt:
        logger.info("\nVerificación interrumpida por el usuario.")
    except Exception as e:
        logger.critical(f"Error fatal no controlado: {e}", exc_info=args.debug)
        sys.exit(1)

if __name__ == "__main__":
    main()