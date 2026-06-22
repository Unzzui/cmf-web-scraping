#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMF XBRL Availability Checker - Optimized concurrent version.
Adapted for cmf/ package - uses CMFConfig for paths.
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

logger = logging.getLogger(__name__)


class CMFXBRLChecker:
    """Concurrent XBRL availability checker for CMF."""

    def __init__(self, headless: bool = True, debug: bool = False, config=None):
        self.headless = headless
        self.debug = debug

        if config is None:
            from cmf.config import CMFConfig
            config = CMFConfig()
        self.config = config
        self.xbrl_base_path = config.xbrl_base_dir

        if debug:
            logger.setLevel(logging.DEBUG)

    def _create_driver(self):
        if not SELENIUM_AVAILABLE:
            raise ImportError("selenium no esta instalado")

        options = Options()
        if self.headless:
            options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        prefs = {
            "download.default_directory": str(self.config.repo_root / "temp"),
            "download.prompt_for_download": False,
            "download.directory_upgrade": True,
            "safebrowsing.enabled": True,
        }
        options.add_experimental_option("prefs", prefs)

        # Selenium 4.10+ includes Selenium Manager which auto-downloads
        # a compatible ChromeDriver. No need for webdriver-manager.
        driver = webdriver.Chrome(options=options)
        driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        return driver

    def get_local_companies_info(self) -> Dict[str, Dict]:
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
                    period_match = period_dir.name.split("_")[-2]
                    if len(period_match) == 6 and period_match.isdigit():
                        periods.append(period_match)
                except IndexError:
                    pass

            if periods:
                rut = company_name.split("_")[0]
                latest_period = max(periods)
                companies[company_name] = {
                    "rut": rut,
                    "latest_period": latest_period,
                    "total_periods": len(periods),
                }
        logger.info(f"Encontradas {len(companies)} empresas locales")
        return companies

    def _generate_check_periods(
        self, latest_local_period: str
    ) -> Generator[Tuple[int, int], None, None]:
        latest_year = int(latest_local_period[:4])
        latest_month = int(latest_local_period[4:6])
        current_year = datetime.now().year
        current_month = datetime.now().month

        if latest_month == 3:
            start_year, start_month = latest_year, 6
        elif latest_month == 6:
            start_year, start_month = latest_year, 9
        elif latest_month == 9:
            start_year, start_month = latest_year, 12
        elif latest_month == 12:
            start_year, start_month = latest_year + 1, 3
        else:
            start_year, start_month = latest_year, 6

        year, month = start_year, start_month
        while year <= current_year:
            if year > current_year or (year == current_year and month > current_month):
                break
            yield year, month
            if month == 3:
                month = 6
            elif month == 6:
                month = 9
            elif month == 9:
                month = 12
            elif month == 12:
                month, year = 3, year + 1

    def check_new_xbrl_availability(
        self, driver, company_name: str, rut: str, latest_local_period: str
    ) -> List[str]:
        rut_numero = rut.split("-")[0]
        url = (
            f"https://www.cmfchile.cl/institucional/mercados/entidad.php"
            f"?mercado=V&rut={rut_numero}&grupo=&tipoentidad=RVEMI"
            f"&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
        )
        new_periods = []
        try:
            driver.get(url)
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.ID, "fm")))
            periods_to_check = list(
                self._generate_check_periods(latest_local_period)
            )
            if not periods_to_check:
                return new_periods

            for i, (year, month) in enumerate(periods_to_check):
                logger.info(
                    f"Verificando {i+1}/{len(periods_to_check)}: "
                    f"{year}-{month:02d} para {company_name}"
                )
                try:
                    if "cmfchile.cl" not in driver.current_url:
                        driver.get(url)
                        wait.until(EC.presence_of_element_located((By.ID, "fm")))
                    Select(driver.find_element(By.ID, "aa")).select_by_visible_text(
                        str(year)
                    )
                    Select(driver.find_element(By.ID, "mm")).select_by_visible_text(
                        f"{month:02d}"
                    )
                    try:
                        Select(
                            driver.find_element(By.NAME, "tipo")
                        ).select_by_visible_text("Consolidado")
                    except Exception:
                        pass
                    try:
                        Select(
                            driver.find_element(By.NAME, "tipo_norma")
                        ).select_by_visible_text("Estándar IFRS")
                    except Exception:
                        pass

                    submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                    try:
                        driver.execute_script(
                            "arguments[0].scrollIntoView(true);", submit_button
                        )
                        time.sleep(0.5)
                        submit_button.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", submit_button)

                    try:
                        wait.until(
                            EC.presence_of_element_located(
                                (
                                    By.XPATH,
                                    "//a[contains(text(), 'Estados financieros (XBRL)')]",
                                )
                            )
                        )
                        new_periods.append(f"{year}{month:02d}")
                        logger.info(
                            f"XBRL disponible para {company_name} en {year}-{month:02d}"
                        )
                    except TimeoutException:
                        logger.info(
                            f"XBRL no disponible para {company_name} en {year}-{month:02d}"
                        )
                    driver.back()
                    wait.until(EC.presence_of_element_located((By.ID, "fm")))
                except (NoSuchElementException, TimeoutException) as e:
                    logger.warning(
                        f"Error en {year}-{month:02d} para {company_name}: {e}"
                    )
                    driver.get(url)
                    wait.until(EC.presence_of_element_located((By.ID, "fm")))
            return new_periods
        except Exception as e:
            logger.error(f"Error verificando {company_name}: {e}")
            return new_periods

    def _worker_check(
        self, company_info: Tuple[str, Dict]
    ) -> Tuple[str, List[str]]:
        company_name, info = company_info
        driver = None
        try:
            driver = self._create_driver()
            new_periods = self.check_new_xbrl_availability(
                driver, company_name, info["rut"], info["latest_period"]
            )
            return company_name, new_periods
        except Exception as e:
            logger.error(f"Error en worker para {company_name}: {e}")
            return company_name, []
        finally:
            if driver:
                driver.quit()

    def run_check(
        self, company_filter: Optional[str] = None, max_workers: int = 4
    ) -> Dict:
        logger.info("INICIANDO VERIFICACION DE DISPONIBILIDAD XBRL")
        local_companies = self.get_local_companies_info()
        if not local_companies:
            logger.warning("No se encontraron empresas locales.")
            return {}

        if company_filter:
            if company_filter in local_companies:
                local_companies = {company_filter: local_companies[company_filter]}
            else:
                logger.error(f"Empresa '{company_filter}' no encontrada.")
                return {}

        summary = {
            "total_companies": len(local_companies),
            "companies_with_new_xbrl": 0,
            "total_new_periods": 0,
            "details": {
                name: {
                    "rut": info["rut"],
                    "latest_local_period": info["latest_period"],
                    "new_periods_available": [],
                    "count_new_periods": 0,
                }
                for name, info in local_companies.items()
            },
        }

        with ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="XBRLChecker"
        ) as executor:
            tasks = list(local_companies.items())
            future_to_company = {
                executor.submit(self._worker_check, task): task[0] for task in tasks
            }
            for future in as_completed(future_to_company):
                try:
                    company_name, new_periods = future.result()
                    if new_periods:
                        summary["companies_with_new_xbrl"] += 1
                        summary["total_new_periods"] += len(new_periods)
                        summary["details"][company_name].update(
                            {
                                "new_periods_available": new_periods,
                                "count_new_periods": len(new_periods),
                            }
                        )
                except Exception as exc:
                    logger.error(f"Worker exception: {exc}")

        return summary
