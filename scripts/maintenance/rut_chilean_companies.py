#!/usr/bin/env python3
"""
Extractor de RUT de Empresas Chilenas desde CMF
Descarga la lista actualizada de empresas desde la CMF y genera archivos CSV y Excel
"""

import os
import sys
import logging
from datetime import datetime
from typing import Optional, Tuple
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import (
    WebDriverException, TimeoutException, NoSuchElementException
)
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd


class CMFCompanyExtractor:
    """Extractor de empresas desde CMF"""
    
    def __init__(self, year: int = None, output_dir: str = "./data/RUT_Chilean_Companies"):
        self.year = year or datetime.now().year - 1  # Año anterior por defecto
        self.output_dir = output_dir
        self.driver = None
        
        # Configurar logging
        self._setup_logging()
        
        # Asegurar que el directorio de salida existe
        os.makedirs(self.output_dir, exist_ok=True)
    
    def _setup_logging(self):
        """Configurar sistema de logging"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('cmf_extractor.log'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def _setup_driver(self) -> bool:
        """Configurar WebDriver con opciones optimizadas"""
        try:
            chrome_options = Options()
            chrome_options.add_argument('--headless')  # Ejecutar sin ventana
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
            
            # Deshabilitar imágenes para mayor velocidad
            prefs = {"profile.managed_default_content_settings.images": 2}
            chrome_options.add_experimental_option("prefs", prefs)
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.implicitly_wait(10)
            
            self.logger.info("WebDriver configurado exitosamente")
            return True
            
        except WebDriverException as e:
            self.logger.error(f"Error configurando WebDriver: {e}")
            return False
    
    def _navigate_to_cmf(self) -> bool:
        """Navegar a la página de CMF"""
        try:
            url = "https://www.cmfchile.cl/institucional/mercados/novedades_envio_fechas_eeff.php"
            self.logger.info(f"Navegando a: {url}")
            
            self.driver.get(url)
            
            # Esperar hasta que el formulario esté presente
            wait = WebDriverWait(self.driver, 20)
            form = wait.until(EC.presence_of_element_located((By.ID, "frm_consulta")))
            
            self.logger.info("Página cargada correctamente")
            return True
            
        except TimeoutException:
            self.logger.error("Timeout al cargar la página de CMF")
            return False
        except Exception as e:
            self.logger.error(f"Error navegando a CMF: {e}")
            return False
    
    def _select_year_and_submit(self) -> bool:
        """Seleccionar año y enviar formulario"""
        try:
            self.logger.info(f"Seleccionando año: {self.year}")
            
            # Encontrar y seleccionar el año
            select_element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.ID, "aaaa"))
            )
            select_aa = Select(select_element)
            select_aa.select_by_visible_text(str(self.year))
            
            # Hacer clic en el botón de consultar
            submit_button = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CLASS_NAME, "mime_bot_consultar"))
            )
            submit_button.click()
            
            # Esperar a que se cargue la tabla con filas
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//div[contains(@class,'table-responsive')]//table//tr"
                ))
            )
            
            self.logger.info("Formulario enviado y tabla cargada")
            return True
            
        except TimeoutException:
            self.logger.error("Timeout esperando la tabla de resultados")
            return False
        except NoSuchElementException as e:
            self.logger.error(f"Elemento no encontrado: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Error en selección de año y envío: {e}")
            return False
    
    def _extract_table_data(self) -> Optional[pd.DataFrame]:
        """Extraer datos de la tabla"""
        try:
            self.logger.info("Extrayendo datos de la tabla")
            
            # Esperar contenedor/tabla visible
            try:
                container = WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.XPATH, "//div[contains(@class,'table-responsive')]"))
                )
            except TimeoutException:
                container = None

            html_fragment = None
            if container:
                try:
                    # Preferir la tabla dentro del contenedor
                    table = container.find_element(By.XPATH, ".//table")
                    html_fragment = table.get_attribute("outerHTML")
                except Exception:
                    html_fragment = container.get_attribute("outerHTML")
            else:
                # Fallback: buscar cualquier tabla con cabeceras relevantes
                try:
                    table = self.driver.find_element(
                        By.XPATH,
                        "//table[.//th[contains(normalize-space(.), 'RUT')] and .//th[contains(., 'Razón')]]"
                    )
                    html_fragment = table.get_attribute("outerHTML")
                except Exception:
                    # último recurso: usar todo el page_source
                    html_fragment = self.driver.page_source

            if not html_fragment:
                self.logger.error("No se encontró la tabla de datos")
                return None

            # Procesar la tabla con pandas
            df_list = pd.read_html(StringIO(html_fragment))
            if not df_list:
                self.logger.error("No se pudieron extraer datos de la tabla")
                return None

            # Seleccionar la tabla correcta por columnas esperadas
            df = None
            for d in df_list:
                cols = [str(c) for c in d.columns]
                if ('RUT' in cols) and any('Razón' in str(c) for c in cols):
                    df = d
                    break
            if df is None:
                # tomar la primera como fallback
                df = df_list[0]

            # Validar que la tabla tiene las columnas esperadas
            if 'RUT' not in df.columns or not any('Razón' in str(c) for c in df.columns):
                self.logger.error("La tabla no contiene las columnas esperadas")
                return None

            # Normalizar nombre exacto de columna 'Razón Social' si difiere
            razon_col = next((c for c in df.columns if 'Razón' in str(c)), 'Razón Social')
            if razon_col != 'Razón Social':
                df = df.rename(columns={razon_col: 'Razón Social'})

            self.logger.info(f"Datos extraídos exitosamente: {len(df)} empresas")
            return df
            
        except Exception as e:
            self.logger.error(f"Error extrayendo datos de la tabla: {e}")
            return None
    
    def _process_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Procesar y limpiar el DataFrame"""
        try:
            self.logger.info("Procesando y limpiando datos")
            
            # Limpiar datos base
            df = df.dropna(subset=['RUT', 'Razón Social'])
            df['RUT'] = df['RUT'].astype(str).str.strip()

            # Extraer número de RUT y dígito verificador con regex robusta
            # Soporta formatos "91297000 - 0", "91.297.000-0", etc.
            rut_parts = df['RUT'].str.extract(r'^\s*([0-9\.]*)\s*-\s*([0-9Kk])\s*$', expand=True)
            df['RUT_Numero'] = rut_parts[0].str.replace(r'\.', '', regex=True)
            df['DV'] = rut_parts[1].str.upper()
            # Crear columna RUT sin guión (sólo números, sin DV)
            df['RUT_Sin_Guión'] = df['RUT_Numero']

            # Validar RUTs: sólo dígitos en RUT_Sin_Guión
            df = df[df['RUT_Sin_Guión'].fillna('').str.fullmatch(r'\d+')]
            
            # Eliminar duplicados por RUT
            df = df.drop_duplicates(subset=['RUT'], keep='first')
            
            # Ordenar por razón social
            df = df.sort_values('Razón Social')
            
            # Resetear índice
            df = df.reset_index(drop=True)
            
            self.logger.info(f"Datos procesados: {len(df)} empresas válidas")
            return df
            
        except Exception as e:
            self.logger.error(f"Error procesando DataFrame: {e}")
            return df  # Retornar DataFrame original en caso de error
    
    def _save_files(self, df: pd.DataFrame) -> Tuple[bool, bool]:
        """Guardar archivos CSV y Excel"""
        excel_success = False
        csv_success = False
        
        try:
            # Rutas de archivos
            excel_path = os.path.join(self.output_dir, "RUT_Chilean_Companies.xlsx")
            csv_path = os.path.join(self.output_dir, "RUT_Chilean_Companies.csv")
            
            # Guardar Excel
            try:
                df.to_excel(excel_path, index=False, engine='xlsxwriter')
                self.logger.info(f"Archivo Excel creado: {excel_path}")
                excel_success = True
            except Exception as e:
                self.logger.error(f"Error creando archivo Excel: {e}")
            
            # Guardar CSV
            try:
                df.to_csv(csv_path, index=False, encoding='utf-8')
                self.logger.info(f"Archivo CSV creado: {csv_path}")
                csv_success = True
            except Exception as e:
                self.logger.error(f"Error creando archivo CSV: {e}")
            
            return excel_success, csv_success
            
        except Exception as e:
            self.logger.error(f"Error general guardando archivos: {e}")
            return False, False
    
    def extract_companies(self) -> bool:
        """Ejecutar extracción completa de empresas"""
        try:
            self.logger.info("="*60)
            self.logger.info("INICIANDO EXTRACCIÓN DE EMPRESAS CMF")
            self.logger.info("="*60)
            
            # Configurar driver
            if not self._setup_driver():
                return False
            
            # Navegar a CMF
            if not self._navigate_to_cmf():
                return False
            
            # Seleccionar año y enviar
            if not self._select_year_and_submit():
                return False
            
            # Extraer datos
            df = self._extract_table_data()
            if df is None:
                return False
            
            # Procesar datos
            df = self._process_dataframe(df)
            
            # Guardar archivos
            excel_success, csv_success = self._save_files(df)
            
            # Mostrar resumen
            self.logger.info("="*60)
            self.logger.info("RESUMEN DE EXTRACCIÓN")
            self.logger.info("="*60)
            self.logger.info(f"Año consultado: {self.year}")
            self.logger.info(f"Empresas encontradas: {len(df)}")
            self.logger.info(f"Archivo Excel: {'✓' if excel_success else '✗'}")
            self.logger.info(f"Archivo CSV: {'✓' if csv_success else '✗'}")
            
            return excel_success or csv_success
            
        except Exception as e:
            self.logger.error(f"Error general en extracción: {e}")
            return False
        
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver cerrado")


def main():
    """Función principal"""
    try:
        # Permitir especificar año como argumento
        year = 2025
        if len(sys.argv) > 1:
            try:
                year = int(sys.argv[1])
            except ValueError:
                print(f"Error: '{sys.argv[1]}' no es un año válido")
                sys.exit(1)
        
        # Crear extractor y ejecutar
        extractor = CMFCompanyExtractor(year=year)
        success = extractor.extract_companies()
        
        if success:
            print("\n🎉 Extracción completada exitosamente!")
            sys.exit(0)
        else:
            print("\n❌ Error en la extracción")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n⚠️ Extracción interrumpida por el usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 Error inesperado: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
