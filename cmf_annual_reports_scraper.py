from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
import time
import logging
import re
import calendar

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [THREAD %(thread)d] %(message)s'
)
logger = logging.getLogger(__name__)

def scrape_cmf_data(rut, start_year=2024, end_year=2014, step=-2, headless=True, quarterly=False):
    """
    Función principal para scraping de datos CMF
    Extrae solo [210000], [320000] y [510000]
    Mantiene el orden original de las filas como aparecen en la CMF
    INCLUYE categorías [sinopsis] para estructura jerárquica
    
    Args:
        rut: RUT de la empresa sin guión ni dígito verificador
        start_year: Año inicial
        end_year: Año final
        step: Incremento entre años (por defecto -2)
        headless: Si True, ejecuta Chrome sin ventana visible (por defecto True)
        quarterly: Si True, extrae datos trimestrales (3,6,9,12), si False solo anuales (12)
    """
    
    # Función para obtener DV desde el CSV
    def get_dv_from_csv(rut_numero):
        """Obtener el DV del RUT desde el archivo CSV"""
        try:
            import pandas as pd
            import os
            csv_path = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
            if os.path.exists(csv_path):
                df = pd.read_csv(csv_path)
                # Buscar el RUT en la columna RUT_Numero
                match = df[df['RUT_Numero'].astype(str) == str(rut_numero)]
                if not match.empty:
                    dv = str(match.iloc[0]['DV']).strip()
                    if dv and dv != 'nan':
                        logger.info(f"DV encontrado para RUT {rut_numero}: {dv}")
                        return dv
                logger.warning(f"No se encontró DV para RUT {rut_numero} en el CSV")
            else:
                logger.warning(f"No se encontró archivo CSV: {csv_path}")
        except Exception as e:
            logger.warning(f"Error obteniendo DV para RUT {rut_numero}: {e}")
        return None
    
    # TAXONOMÍAS PRINCIPALES Y ALTERNATIVAS
    TAXONOMY_MAPPING = {
        # Balance General
        "[210000]": {
            "name": "Balance General",
            "description": "Estado de situación financiera, corriente/no corriente",
            "alternative": "[220000]"  # Orden de liquidez como alternativa
        },
        "[220000]": {
            "name": "Balance General (Liquidez)",
            "description": "Estado de situación financiera, orden de liquidez",
            "alternative": None
        },
        
        # Estado de Resultados
        "[320000]": {
            "name": "Estado Resultados",
            "description": "Estado del resultado, por naturaleza de gasto",
            "alternative": "[310000]"  # Por función de gasto como alternativa
        },
        "[310000]": {
            "name": "Estado Resultados (Función)",
            "description": "Estado del resultado, por función de gasto",
            "alternative": None
        },
        
        # Flujo de Efectivo
        "[510000]": {
            "name": "Flujo Efectivo",
            "description": "Estado de flujos de efectivo, método directo",
            "alternative": "[520000]"  # Método indirecto como alternativa
        },
        "[520000]": {
            "name": "Flujo Efectivo (Indirecto)",
            "description": "Estado de flujos de efectivo, método indirecto",
            "alternative": None
        }
    }
    
    # Mapeo de taxonomías principales (las que preferimos)
    PRIMARY_TAXONOMIES = {
        "balance": "[210000]",
        "resultados": "[320000]", 
        "flujo": "[510000]"
    }
    
    # Mapeo de nombres de conceptos
    concept_name_mapping = {
        "Capital emitido": "Capital emitido y pagado",
        "Diferencias de cambio": "Ganancias (pérdidas) de cambio en moneda extranjera",
        "Flujos de efectivo netos procedentes de (utilizados en) la operación": 
            "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
        "Pagos de préstamos a entidades relacionadas": 
            "Pagos de préstamos de entidades relacionadas",
        "Pagos de pasivos por arrendamientos financieros": 
            "Pagos de pasivos por arrendamientos",
        "Pagos por cambios en las participaciones en la propiedad en subsidiarias que no resulta en una pérdida de control": 
            "Pagos por cambios en las participaciones en la propiedad en subsidiarias que no dan lugar a la pérdida de control",
    }
    
    # Configura el WebDriver con modo headless opcional
    chrome_options = Options()
    
    if headless:
        # Configuración para modo headless (sin ventana)
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        
        # Configuraciones adicionales para estabilidad
        chrome_options.add_argument("--disable-background-timer-throttling")
        chrome_options.add_argument("--disable-backgrounding-occluded-windows")
        chrome_options.add_argument("--disable-renderer-backgrounding")
        chrome_options.add_argument("--disable-features=TranslateUI")
        chrome_options.add_argument("--disable-ipc-flooding-protection")
        chrome_options.add_argument("--disable-crash-reporter")
        chrome_options.add_argument("--disable-logging")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--allow-running-insecure-content")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Desactivar notificaciones y popups
        prefs = {
            "profile.default_content_setting_values": {
                "notifications": 2,
                "popups": 2
            },
            "profile.managed_default_content_settings": {
                "images": 2  # Bloquear imágenes para mayor velocidad
            }
        }
        chrome_options.add_experimental_option("prefs", prefs)
        
        # User agent para evitar detección
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (Linux; x86_64) AppleWebKit/537.36")
        
        logger.info("Iniciando Chrome en modo headless (sin ventana)")
    else:
        logger.info("Iniciando Chrome con ventana visible")
    
    driver = webdriver.Chrome(options=chrome_options)
    
    try:
        # Abre la URL
        url = f"https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
        logger.info(f"Accediendo a: {url}")
        driver.get(url)
        
        # Espera hasta que el formulario esté presente
        wait = WebDriverWait(driver, 10)
        form = wait.until(EC.presence_of_element_located((By.ID, "fm")))
        
        # Obtener nombre de la empresa
        try:
            company_element = driver.find_element(By.ID, "datos_ent")
            company_name = company_element.text.split("\n")[1]
        except:
            company_name = f"Empresa_RUT_{rut}"
        
        logger.info(f"Procesando: {company_name}")
        
        # Inicializar dataframes vacíos para cada taxonomía
        # Usaremos listas para mantener el orden
        data_by_taxonomy = {code: {} for code in TAXONOMY_MAPPING.keys()}
        
        # Lista para mantener el orden de los conceptos
        concept_order = {code: [] for code in TAXONOMY_MAPPING.keys()}
        
        # Set para trackear años ya procesados
        years_collected = {code: set() for code in TAXONOMY_MAPPING.keys()}
        
        # Diccionario para almacenar headers originales de CMF por taxonomía
        original_headers = {code: {} for code in TAXONOMY_MAPPING.keys()}
        
        # Set para trackear taxonomías encontradas
        found_taxonomies = set()
        
        # Función para detectar taxonomías disponibles
        def detect_available_taxonomies(soup):
            """Detectar qué taxonomías están disponibles en la página"""
            available = set()
            tables = soup.find_all("table")
            for table in tables:
                first_th = table.find("th")
                if first_th:
                    header_text = first_th.get_text()
                    match = re.search(r'\[(\d{6})\]', header_text)
                    if match:
                        taxonomy_code = f"[{match.group(1)}]"
                        if taxonomy_code in TAXONOMY_MAPPING:
                            available.add(taxonomy_code)
            return available
        
        # Función para seleccionar la mejor taxonomía disponible para cada tipo
        def select_best_taxonomies(available_taxonomies):
            """Seleccionar las mejores taxonomías disponibles"""
            selected = {}
            
            # Para Balance General
            if PRIMARY_TAXONOMIES["balance"] in available_taxonomies:
                selected["balance"] = PRIMARY_TAXONOMIES["balance"]
            elif TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["balance"]]["alternative"] in available_taxonomies:
                selected["balance"] = TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["balance"]]["alternative"]
            
            # Para Estado de Resultados
            if PRIMARY_TAXONOMIES["resultados"] in available_taxonomies:
                selected["resultados"] = PRIMARY_TAXONOMIES["resultados"]
            elif TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["resultados"]]["alternative"] in available_taxonomies:
                selected["resultados"] = TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["resultados"]]["alternative"]
            
            # Para Flujo de Efectivo
            if PRIMARY_TAXONOMIES["flujo"] in available_taxonomies:
                selected["flujo"] = PRIMARY_TAXONOMIES["flujo"]
            elif TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["flujo"]]["alternative"] in available_taxonomies:
                selected["flujo"] = TAXONOMY_MAPPING[PRIMARY_TAXONOMIES["flujo"]]["alternative"]
            
            return selected
        
        # Variable para almacenar las taxonomías seleccionadas
        selected_taxonomies = None
        
        # Función para verificar si hay información disponible
        def check_no_data_message(soup):
            """Verificar si aparece el mensaje de 'No existe información'"""
            page_text = soup.get_text().lower()
            no_data_messages = [
                "no existe información de la entidad para el periodo señalado",
                "no existe información",
                "verifique que los parámetros de búsqueda"
            ]
            return any(msg in page_text for msg in no_data_messages)
        
        # Función para buscar el año más reciente disponible
        def find_latest_available_year(driver, wait, base_year, months_to_try):
            """Buscar el año más reciente con información disponible"""
            max_attempts = 5  # Intentar hasta 5 años hacia atrás
            
            for year_offset in range(max_attempts):
                test_year = base_year - year_offset
                
                logger.info(f"  🔍 Verificando disponibilidad para año {test_year}")
                
                # Intentar cada mes para este año
                for month in months_to_try:
                    try:
                        # Volver al formulario
                        form = wait.until(EC.presence_of_element_located((By.ID, "fm")))
                        
                        # Seleccionar año
                        select_aa = Select(driver.find_element(By.ID, "aa"))
                        select_aa.select_by_visible_text(str(test_year))
                        
                        # Seleccionar mes - usar formato de 2 dígitos
                        select_mm = Select(driver.find_element(By.ID, "mm"))
                        month_str = f"{month:02d}"  # Formato 03, 06, 09, 12
                        select_mm.select_by_visible_text(month_str)
                        
                        # Seleccionar tipo
                        try:
                            select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                            select_tipo.select_by_visible_text("Consolidado")
                        except:
                            logger.warning("No se pudo seleccionar 'Consolidado'")
                        
                        # Seleccionar norma
                        try:
                            select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                            select_tipo_norma.select_by_visible_text("Estándar IFRS")
                        except:
                            logger.warning("No se pudo seleccionar 'Estándar IFRS'")
                        
                        # Click en submit
                        submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                        try:
                            submit_button.click()
                        except ElementClickInterceptedException:
                            driver.execute_script("arguments[0].click();", submit_button)
                        
                        # Esperar carga
                        time.sleep(3)
                        
                        # Verificar si hay información
                        soup = BeautifulSoup(driver.page_source, "html.parser")
                        
                        if not check_no_data_message(soup):
                            # Verificar que hay tablas
                            tables = soup.find_all("table")
                            if len(tables) > 0:
                                logger.info(f"  ✅ Información encontrada para {test_year}-{month:02d}")
                                return test_year, month
                        
                        # Volver atrás para el siguiente intento
                        driver.back()
                        time.sleep(1)
                        
                    except Exception as e:
                        logger.warning(f"  ❌ Error verificando {test_year}-{month:02d}: {e}")
                        try:
                            driver.back()
                            time.sleep(1)
                        except:
                            # Si no puede volver atrás, recargar la página
                            driver.get(url)
                            time.sleep(2)
                        continue
            
            logger.warning(f"  ⚠️ No se encontró información disponible en los últimos {max_attempts} años")
            return None, None
        
        # Determinar meses a procesar según el modo
        if quarterly:
            months_to_process = [3, 6, 9, 12]  # Trimestres
            period_type = "trimestral"
            logger.info(f"📅 Modo de extracción: {period_type}")
            logger.info(f"📋 Meses a procesar: {months_to_process}")
            logger.info(f"🔄 Lógica: Trimestral acumulativo - Columna 1: período actual acumulado, Columna 2: período anterior comparativo")
        else:
            months_to_process = [12]  # Solo anual
            period_type = "anual"
            logger.info(f"📅 Modo de extracción: {period_type}")
            logger.info(f"📋 Meses a procesar: {months_to_process}")
            logger.info(f"🔄 Lógica: Procesamiento anual normal, tomando todas las columnas")
        
        # Procesar cada año
        for year in range(start_year, end_year - 1, step):
            logger.info(f"\n{'='*50}")
            logger.info(f"Consultando año {year} - Modo {period_type}")
            
            year_processed = False
            
            # Procesar cada mes para este año
            for month in months_to_process:
                logger.info(f"\n🗓️ Procesando período {year}-{month:02d}")
                
                try:
                    # Esperar a que el formulario esté presente
                    form = wait.until(EC.presence_of_element_located((By.ID, "fm")))
                    
                    # Seleccionar año
                    select_aa = Select(driver.find_element(By.ID, "aa"))
                    select_aa.select_by_visible_text(str(year))
                    
                    # Seleccionar mes - usar formato de 2 dígitos
                    select_mm = Select(driver.find_element(By.ID, "mm"))
                    month_str = f"{month:02d}"  # Formato 03, 06, 09, 12
                    logger.info(f"Seleccionando mes: {month_str}")
                    select_mm.select_by_visible_text(month_str)
                    
                    # Seleccionar tipo
                    try:
                        select_tipo = Select(driver.find_element(By.NAME, "tipo"))
                        select_tipo.select_by_visible_text("Consolidado")
                    except:
                        logger.warning("No se pudo seleccionar 'Consolidado'")
                    
                    # Seleccionar norma
                    try:
                        select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
                        select_tipo_norma.select_by_visible_text("Estándar IFRS")
                    except:
                        logger.warning("No se pudo seleccionar 'Estándar IFRS'")
                    
                    # Click en submit
                    submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
                    try:
                        submit_button.click()
                    except ElementClickInterceptedException:
                        driver.execute_script("arguments[0].click();", submit_button)
                    
                    # Esperar carga
                    time.sleep(3)
                    
                    # Parsear HTML y verificar si hay información
                    soup = BeautifulSoup(driver.page_source, "html.parser")
                    
                    # Verificar mensaje de "no hay información"
                    if check_no_data_message(soup):
                        logger.warning(f"❌ No hay información para {year}-{month:02d}")
                        
                        # Si es el primer período que intentamos y no hay info, buscar año disponible
                        if not year_processed and month == months_to_process[0]:
                            logger.info(f"🔍 Buscando año más reciente con información disponible...")
                            driver.back()
                            time.sleep(1)
                            
                            available_year, available_month = find_latest_available_year(
                                driver, wait, year, months_to_process
                            )
                            
                            if available_year and available_month:
                                logger.info(f"✅ Redirigiendo a {available_year}-{available_month:02d}")
                                # Actualizar el año actual al encontrado
                                year = available_year
                                # Continuar con el procesamiento normal
                                continue
                            else:
                                # No se encontró información, saltar este año completo
                                driver.back()
                                break
                        else:
                            # Solo saltar este período específico
                            driver.back()
                            time.sleep(1)
                            continue
                    
                    # Verificar que hay tablas
                    try:
                        wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                    except TimeoutException:
                        logger.warning(f"❌ No se encontraron tablas para {year}-{month:02d}")
                        driver.back()
                        continue
                    
                    # En el primer año, detectar taxonomías disponibles y seleccionar las mejores
                    if selected_taxonomies is None:
                        available_taxonomies = detect_available_taxonomies(soup)
                        selected_taxonomies = select_best_taxonomies(available_taxonomies)
                        
                        logger.info(f"📊 Taxonomías disponibles: {sorted(available_taxonomies)}")
                        logger.info(f"🎯 Taxonomías seleccionadas: {selected_taxonomies}")
                        
                        # Actualizar los diccionarios para usar solo las taxonomías seleccionadas
                        selected_codes = list(selected_taxonomies.values())
                        data_by_taxonomy = {code: {} for code in selected_codes}
                        concept_order = {code: [] for code in selected_codes}
                        years_collected = {code: set() for code in selected_codes}
                        original_headers = {code: {} for code in selected_codes}
                    
                    # Buscar todas las tablas
                    all_tables = soup.find_all("table")
                    logger.info(f"Se encontraron {len(all_tables)} tablas para {year}-{month:02d}")
                    
                    # Procesar cada tabla
                    for table in all_tables:
                        try:
                            # Buscar código de taxonomía en el header
                            taxonomy_code = None
                            first_th = table.find("th")
                            
                            if first_th:
                                header_text = first_th.get_text()
                                match = re.search(r'\[(\d{6})\]', header_text)
                                if match:
                                    taxonomy_code = f"[{match.group(1)}]"
                            
                            # Solo procesar si es una de las taxonomías seleccionadas
                            if taxonomy_code and taxonomy_code in data_by_taxonomy:
                                logger.info(f"Procesando tabla {taxonomy_code} - {TAXONOMY_MAPPING[taxonomy_code]['description']}")
                                
                                # Extraer fechas de las columnas del header
                                column_dates = []
                                column_headers_raw = []  # Nuevo: guardar headers originales de CMF
                                ths = table.find_all("th")
                                for th in ths[1:]:  # Skip first header (descripción)
                                    date_text = th.get_text().strip()
                                    # Guardar el texto completo del header original
                                    column_headers_raw.append(date_text)
                                    
                                    # Extraer fecha para identificación interna
                                    date_match = re.search(r'(\d{4})-(\d{2})-\d{2}', date_text)
                                    if date_match:
                                        year_col = date_match.group(1)
                                        month_col = date_match.group(2)
                                        period_key = f"{year_col}-{month_col}"
                                        column_dates.append(period_key)
                                
                                logger.info(f"  Columnas de períodos encontradas: {column_dates}")
                                logger.info(f"  Headers originales CMF: {column_headers_raw}")
                                
                                # En modo trimestral, tomar ambas columnas (actual y comparativo)
                                if quarterly:
                                    if len(column_dates) >= 2:
                                        # Ambas columnas: actual y comparativo
                                        column_dates_to_process = column_dates[:2]
                                        column_headers_to_process = column_headers_raw[:2]
                                        logger.info(f"  🎯 Modo trimestral: Procesando período actual ({column_dates[0]}) y comparativo ({column_dates[1]})")
                                    elif len(column_dates) == 1:
                                        # Solo hay una columna disponible
                                        column_dates_to_process = [column_dates[0]]
                                        column_headers_to_process = [column_headers_raw[0]]
                                        logger.info(f"  🎯 Modo trimestral: Solo una columna disponible ({column_dates[0]})")
                                    else:
                                        column_dates_to_process = []
                                        column_headers_to_process = []
                                        logger.warning(f"  ⚠️ No se encontraron columnas de datos")
                                else:
                                    # En modo anual, procesar todas las columnas
                                    column_dates_to_process = column_dates
                                    column_headers_to_process = column_headers_raw
                                
                                # Guardar los headers originales de CMF para esta taxonomía
                                for i, period_key in enumerate(column_dates_to_process):
                                    if i < len(column_headers_to_process):
                                        original_headers[taxonomy_code][period_key] = column_headers_to_process[i]
                                
                                # Procesar filas manualmente para mantener el orden
                                rows = table.find_all("tr")
                                
                                for row in rows[1:]:  # Skip header row
                                    cells = row.find_all(["td", "th"])
                                    
                                    if len(cells) > 0:
                                        # Debug: Mostrar información de la primera celda
                                        first_cell = cells[0]
                                        colspan_value = first_cell.get('colspan')
                                        cell_classes = first_cell.get('class', [])
                                        cell_text = first_cell.get_text().strip()
                                        
                                        # Verificar si es una fila de categoría (con colspan="3" y nowrap)
                                        is_category_row = (
                                            colspan_value == '3' and 
                                            'nowrap' in cell_classes
                                        )
                                        
                                        if is_category_row:
                                            # Es una categoría [sinopsis]
                                            concept_text = cell_text.replace("\n", " ").strip()
                                            
                                            logger.info(f"    📁 CATEGORÍA encontrada: '{concept_text}'")
                                            
                                            # Si es la primera vez que vemos este concepto, agregarlo al orden
                                            if concept_text and concept_text not in data_by_taxonomy[taxonomy_code]:
                                                data_by_taxonomy[taxonomy_code][concept_text] = {}
                                                concept_order[taxonomy_code].append(concept_text)
                                            
                                            # Para categorías, agregar valores vacíos para todos los períodos
                                            for period_key in column_dates_to_process:
                                                if period_key not in years_collected[taxonomy_code]:
                                                    if concept_text:
                                                        data_by_taxonomy[taxonomy_code][concept_text][period_key] = None
                                        
                                        elif len(cells) > 1:
                                            # Es una fila normal de datos
                                            # Obtener el concepto (primera celda)
                                            concept_text = cells[0].get_text().strip()
                                            
                                            # Limpiar el concepto
                                            concept_text = concept_text.replace("\n", " ").strip()
                                            
                                            # Aplicar mapeo de conceptos si existe
                                            if concept_text in concept_name_mapping:
                                                concept_text = concept_name_mapping[concept_text]
                                            
                                            # Si es la primera vez que vemos este concepto, agregarlo al orden
                                            if concept_text and concept_text not in data_by_taxonomy[taxonomy_code]:
                                                data_by_taxonomy[taxonomy_code][concept_text] = {}
                                                concept_order[taxonomy_code].append(concept_text)
                                            
                                            # Procesar valores de las celdas
                                            for i, cell in enumerate(cells[1:]):
                                                if i < len(column_dates):
                                                    period_key = column_dates[i]
                                                    
                                                    # En modo trimestral, procesar hasta 2 columnas (actual y comparativo)
                                                    if quarterly and i >= 2:
                                                        continue  # Saltar columnas adicionales más allá de las 2 primeras
                                                    
                                                    # Solo agregar si no hemos procesado este período antes
                                                    if period_key not in years_collected[taxonomy_code]:
                                                        value_text = cell.get_text().strip()
                                                        
                                                        # Limpiar valor
                                                        value_text = value_text.replace(".", "")  # Quitar separador de miles
                                                        value_text = value_text.replace(",", ".")  # Cambiar coma decimal por punto
                                                        
                                                        # Convertir guiones a 0
                                                        if value_text in ["-", "−", ""]:
                                                            value_text = "0"
                                                        
                                                        # Intentar convertir a número
                                                        try:
                                                            value = float(value_text)
                                                        except:
                                                            value = 0
                                                        
                                                        # Guardar valor
                                                        if concept_text:
                                                            data_by_taxonomy[taxonomy_code][concept_text][period_key] = value
                                
                                # Marcar períodos como procesados
                                for period_key in column_dates_to_process:
                                    years_collected[taxonomy_code].add(period_key)
                                
                                logger.info(f"  Procesados {len(concept_order[taxonomy_code])} conceptos")
                        
                        except Exception as e:
                            logger.error(f"Error procesando tabla: {e}")
                            continue
                    
                    year_processed = True
                    logger.info(f"✅ Período {year}-{month:02d} procesado exitosamente")
                    
                    # Volver atrás para el siguiente período
                    driver.back()
                    time.sleep(1)
                    
                except Exception as e:
                    logger.error(f"❌ Error procesando período {year}-{month:02d}: {e}")
                    
                    # Intentar recuperarse del error
                    try:
                        # Verificar si el driver aún está funcionando
                        driver.current_url
                        
                        # Intentar volver atrás
                        driver.back()
                        time.sleep(2)
                    except Exception as recovery_error:
                        logger.error(f"Error de driver detectado, reiniciando navegación: {recovery_error}")
                        try:
                            # Recargar la página principal
                            driver.get(url)
                            time.sleep(3)
                        except Exception as reload_error:
                            logger.error(f"No se pudo recuperar el driver: {reload_error}")
                            # Si no se puede recuperar, saltar este año completo
                            break
                    
                    continue
            
            # Si no se procesó ningún período para este año, intentar siguiente año
            if not year_processed:
                logger.warning(f"⚠️ No se pudo procesar ningún período para el año {year}")
        
        # Convertir datos a DataFrames manteniendo el orden
        dataframes = {}
        
        # Verificar que tenemos taxonomías seleccionadas
        if selected_taxonomies is None:
            logger.warning("No se detectaron taxonomías válidas")
            return None
        
        for taxonomy_code in data_by_taxonomy.keys():
            if data_by_taxonomy[taxonomy_code]:
                # Obtener lista de todos los períodos y ordenarlos correctamente
                all_periods = sorted(years_collected[taxonomy_code], reverse=True)
                
                # Para modo trimestral, ordenar por año y luego por mes
                if quarterly:
                    # Separar año y mes para ordenamiento correcto
                    periods_with_sort_key = []
                    for period in all_periods:
                        year_str, month_str = period.split('-')
                        year_int = int(year_str)
                        month_int = int(month_str)
                        # Crear clave de ordenamiento: primero año (desc), luego mes (desc)
                        sort_key = (year_int * -1, month_int * -1)
                        periods_with_sort_key.append((sort_key, period))
                    
                    # Ordenar y extraer solo los períodos
                    periods_with_sort_key.sort()
                    all_periods = [period for _, period in periods_with_sort_key]
                    
                    logger.info(f"🗓️ Períodos trimestrales ordenados: {all_periods}")
                
                if all_periods and concept_order[taxonomy_code]:
                    # Crear lista de diccionarios manteniendo el orden original
                    rows = []
                    for concept in concept_order[taxonomy_code]:
                        row = {"Concepto": concept}
                        for period in all_periods:
                            value = data_by_taxonomy[taxonomy_code][concept].get(period, 0)
                            # Para categorías (sinopsis), mostrar como texto vacío en lugar de 0
                            if value is None:
                                row[period] = ""
                            else:
                                row[period] = value
                        rows.append(row)
                    
                    # Crear DataFrame con nombres de columna mejorados
                    if quarterly:
                        # Para trimestral, usar los headers EXACTOS de la CMF
                        column_headers = ["Concepto"]
                        for period in all_periods:
                            # Usar el header original de CMF si está disponible
                            if period in original_headers[taxonomy_code]:
                                cmf_header = original_headers[taxonomy_code][period]
                                # Limpiar el header de CMF y mejorar legibilidad
                                cleaned_header = ' '.join(cmf_header.split())
                                # Agregar espacios alrededor de "Hasta" para mejor legibilidad
                                cleaned_header = cleaned_header.replace('Hasta', ' Hasta ')
                                # Limpiar espacios dobles
                                cleaned_header = ' '.join(cleaned_header.split())
                                column_headers.append(cleaned_header)
                            else:
                                # Fallback al formato manual si no tenemos el header original
                                year_str, month_str = period.split('-')
                                quarter_end_dates = {
                                    "03": "03-31", "06": "06-30", "09": "09-30", "12": "12-31"
                                }
                                
                                if month_str in quarter_end_dates:
                                    end_date = quarter_end_dates[month_str]
                                    if taxonomy_code in ["[320000]", "[310000]", "[510000]", "[520000]"]:
                                        column_header = f"Desde {year_str}-01-01\nHasta {year_str}-{end_date}"
                                    else:
                                        column_header = f"Al {year_str}-{end_date}"
                                else:
                                    if taxonomy_code in ["[320000]", "[310000]", "[510000]", "[520000]"]:
                                        month_int = int(month_str)
                                        if month_int <= 12:
                                            last_day = calendar.monthrange(int(year_str), month_int)[1]
                                            column_header = f"Desde {year_str}-01-01\nHasta {year_str}-{month_str}-{last_day:02d}"
                                        else:
                                            column_header = f"{year_str}-{month_str}"
                                    else:
                                        column_header = f"Al {year_str}-{month_str}"
                                
                                column_headers.append(column_header)
                        
                        # Crear DataFrame con headers personalizados
                        df_data = []
                        for row in rows:
                            new_row = [row["Concepto"]]
                            for period in all_periods:
                                new_row.append(row[period])
                            df_data.append(new_row)
                        
                        dataframes[taxonomy_code] = pd.DataFrame(df_data, columns=column_headers)
                    else:
                        # Para anual, usar formato normal
                        columns = ["Concepto"] + all_periods
                        dataframes[taxonomy_code] = pd.DataFrame(rows, columns=columns)
                    
                    logger.info(f"\n{taxonomy_code}: {len(rows)} filas, {len(all_periods)} períodos")
                    logger.info(f"  Períodos: {all_periods}")
                    logger.info(f"  Primeros 5 conceptos: {concept_order[taxonomy_code][:5]}")
        
        # Guardar en Excel con nomenclatura clara para comercialización
        # Determinar rango de años procesados
        all_years = set()
        for taxonomy_code in data_by_taxonomy.keys():
            if taxonomy_code in years_collected:
                for period in years_collected[taxonomy_code]:
                    year = period.split('-')[0]
                    all_years.add(int(year))
        
        if all_years:
            min_year = min(all_years)
            max_year = max(all_years)
            year_range = f"{min_year}-{max_year}" if min_year != max_year else str(min_year)
        else:
            year_range = f"{start_year}-{end_year}"
        
        # Crear nombre descriptivo para comercialización
        period_type_name = "Trimestral" if quarterly else "Anual"
        
        # Determinar qué estados financieros se incluyeron
        estados_incluidos = []
        if selected_taxonomies:
            for tipo, codigo in selected_taxonomies.items():
                if codigo in dataframes and not dataframes[codigo].empty:
                    if tipo == "balance":
                        estados_incluidos.append("Balance")
                    elif tipo == "resultados":
                        estados_incluidos.append("Resultados")
                    elif tipo == "flujo":
                        estados_incluidos.append("Flujos")
        
        estados_text = "_".join(estados_incluidos) if estados_incluidos else "Completos"
        
        # Limpiar nombre de empresa para nombre de archivo
        safe_company_name = "".join(c for c in company_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_company_name = safe_company_name.replace(' ', '_')
        
        # Obtener DV desde el CSV
        dv = get_dv_from_csv(rut)
        
        # Nomenclatura comercial clara y completa con RUT-DV al inicio
        if dv:
            rut_completo = f"{rut}-{dv}"
        else:
            rut_completo = rut
        
        import os
        base_reports_dir = "./data/Reports"
        period_dir_name = "Trimestral" if quarterly else "Anual"
        company_dir = os.path.join(base_reports_dir, period_dir_name, f"{rut_completo}_{safe_company_name}")
        os.makedirs(company_dir, exist_ok=True)
        output_file = os.path.join(
            company_dir,
            f"{rut_completo}_{safe_company_name}_EEFF_{estados_text}_{period_type_name}_{year_range}.xlsx"
        )
        
        with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
            for taxonomy_code in data_by_taxonomy.keys():
                if taxonomy_code in dataframes and not dataframes[taxonomy_code].empty:
                    sheet_name = TAXONOMY_MAPPING[taxonomy_code]["name"][:31]
                    dataframes[taxonomy_code].to_excel(
                        writer,
                        sheet_name=sheet_name,
                        index=False
                    )
                    
                    # Formato
                    workbook = writer.book
                    worksheet = writer.sheets[sheet_name]
                    
                    # Formato para números
                    number_format = workbook.add_format({
                        'num_format': '#,##0',
                        'align': 'right'
                    })
                    
                    # Formato para headers
                    header_format = workbook.add_format({
                        'bold': True,
                        'bg_color': '#D7E4BD',
                        'border': 1,
                        'align': 'center',
                        'valign': 'vcenter',
                        'text_wrap': True  # Permitir salto de línea en headers largos
                    })
                    
                    # Formato para conceptos (primera columna)
                    concept_format = workbook.add_format({
                        'border': 1,
                        'align': 'left',
                        'valign': 'vcenter'
                    })
                    
                    # Formato especial para categorías (sinopsis)
                    category_format = workbook.add_format({
                        'bold': True,
                        'bg_color': '#E8F4FD',
                        'border': 1,
                        'align': 'left',
                        'valign': 'vcenter'
                    })
                    
                    # Formato para subcategorías (indentación visual)
                    subcategory_format = workbook.add_format({
                        'border': 1,
                        'align': 'left',
                        'valign': 'vcenter',
                        'indent': 1
                    })
                    
                    # Aplicar formatos
                    for i, col in enumerate(dataframes[taxonomy_code].columns):
                        if i == 0:  # Columna de conceptos
                            max_len = dataframes[taxonomy_code][col].astype(str).str.len().max()
                            worksheet.set_column(i, i, min(max_len + 2, 60))
                        else:  # Columnas numéricas
                            # Para headers largos de períodos acumulativos, usar ancho mayor
                            if quarterly and "Desde" in str(col):
                                worksheet.set_column(i, i, 25, number_format)  # Más ancho para fechas descriptivas
                            else:
                                worksheet.set_column(i, i, 15, number_format)
                    
                    # Formato de headers
                    for col_num, value in enumerate(dataframes[taxonomy_code].columns.values):
                        worksheet.write(0, col_num, value, header_format)
                    
                    # Ajustar altura de la fila de headers para texto largo
                    if quarterly:
                        worksheet.set_row(0, 30)  # Más alto para headers descriptivos
                    
                    # Aplicar formato específico a cada fila según su tipo
                    for row_num, (index, row) in enumerate(dataframes[taxonomy_code].iterrows(), start=1):
                        concept = row['Concepto']
                        # Identificar categorías por la presencia de [sinopsis]
                        is_category = "[sinopsis]" in concept.lower()
                        
                        # Aplicar formato a la columna de conceptos
                        if is_category:
                            worksheet.write(row_num, 0, concept, category_format)
                        else:
                            worksheet.write(row_num, 0, concept, subcategory_format)
                        
                        # Escribir valores numéricos con formato apropiado
                        for col_num in range(1, len(dataframes[taxonomy_code].columns)):
                            value = row.iloc[col_num]
                            if is_category:
                                # Para categorías, dejar celdas vacías con formato de categoría
                                cell_format = workbook.add_format({
                                    'bg_color': '#E8F4FD',
                                    'border': 1,
                                    'align': 'center'
                                })
                                worksheet.write(row_num, col_num, "", cell_format)
                            else:
                                # Para subcategorías, usar formato numérico normal
                                worksheet.write(row_num, col_num, value, number_format)
                    
                    logger.info(f"Guardada hoja '{sheet_name}' con {len(dataframes[taxonomy_code])} filas")
        
        logger.info(f"\n{'='*50}")
        logger.info(f"PROCESO COMPLETADO")
        logger.info(f"Empresa: {company_name}")
        logger.info(f"Período: {year_range} ({period_type_name})")
        logger.info(f"Estados: {estados_text}")
        logger.info(f"Archivo: {output_file}")
        logger.info(f"{'='*50}")
        
        # Resumen final
        for taxonomy_code in data_by_taxonomy.keys():
            if taxonomy_code in dataframes:
                periodos = [col for col in dataframes[taxonomy_code].columns if col != "Concepto"]
                logger.info(f"{taxonomy_code}: {len(periodos)} períodos extraídos: {periodos}")
                
                # Mostrar primeros conceptos para verificación
                if not dataframes[taxonomy_code].empty:
                    primeros_conceptos = dataframes[taxonomy_code]["Concepto"].head(10).tolist()
                    logger.info(f"  Primeros conceptos: {primeros_conceptos[:3]}...")
        
        # Mostrar resumen de headers originales capturados
        logger.info(f"\n📋 HEADERS ORIGINALES CAPTURADOS DE CMF:")
        for taxonomy_code in data_by_taxonomy.keys():
            if taxonomy_code in original_headers and original_headers[taxonomy_code]:
                logger.info(f"  {taxonomy_code}:")
                for period_key, header_text in original_headers[taxonomy_code].items():
                    logger.info(f"    {period_key} → '{header_text}'")
        
        # Mostrar resumen de taxonomías utilizadas
        if selected_taxonomies:
            logger.info(f"\n🎯 TAXONOMÍAS UTILIZADAS:")
            for tipo, codigo in selected_taxonomies.items():
                descripcion = TAXONOMY_MAPPING[codigo]["description"]
                logger.info(f"  {tipo.upper()}: {codigo} - {descripcion}")
        
        return output_file
        
    except Exception as e:
        logger.error(f"Error fatal: {e}")
        raise
    
    finally:
        driver.quit()
        logger.info("Driver cerrado correctamente")


# Función para verificar el orden de los datos
def verify_data_order(file_path):
    """
    Verificar el orden de los conceptos en el archivo Excel generado
    Incluye análisis de categorías y subcategorías
    """
    try:
        # Leer el archivo Excel
        excel_data = pd.read_excel(file_path, sheet_name=None)
        
        print(f"\n{'='*60}")
        print("VERIFICACIÓN DEL ORDEN DE DATOS")
        print(f"{'='*60}")
        
        for sheet_name, df in excel_data.items():
            print(f"\n📊 Hoja: {sheet_name}")
            print(f"   Dimensiones: {df.shape[0]} filas x {df.shape[1]} columnas")
            
            if not df.empty and "Concepto" in df.columns:
                print(f"   Primeros 15 conceptos:")
                for i, concepto in enumerate(df["Concepto"].head(15), 1):
                    is_category = "[sinopsis]" in concepto.lower()
                    prefix = "📁" if is_category else "  →"
                    print(f"      {i:2d}. {prefix} {concepto}")
                
                # Contar categorías y subcategorías
                categorias = df[df["Concepto"].str.contains(r"\[sinopsis\]", case=False, na=False)]
                subcategorias = df[~df["Concepto"].str.contains(r"\[sinopsis\]", case=False, na=False)]
                print(f"   📊 Estadísticas: {len(categorias)} categorías, {len(subcategorias)} subcategorías")
                
                # Mostrar todas las categorías encontradas
                if len(categorias) > 0:
                    print(f"   📁 Categorías encontradas:")
                    for i, (idx, row) in enumerate(categorias.iterrows(), 1):
                        print(f"      {i}. {row['Concepto']}")
                else:
                    print(f"   ⚠ No se encontraron categorías con [sinopsis]")
                
                # Verificar específicamente para Balance General
                if "Balance" in sheet_name:
                    # Buscar "Efectivo y equivalentes al efectivo"
                    efectivo_pos = df[df["Concepto"].str.contains("Efectivo", na=False)].index
                    if len(efectivo_pos) > 0:
                        print(f"   ✓ 'Efectivo y equivalentes al efectivo' encontrado en posición: {efectivo_pos[0] + 1}")
                    else:
                        print(f"   ⚠ 'Efectivo y equivalentes al efectivo' NO encontrado")
                    
                    # Buscar categorías importantes
                    activos_corrientes = df[df["Concepto"].str.contains(r"Activos corrientes.*\[sinopsis\]", case=False, na=False)]
                    if len(activos_corrientes) > 0:
                        print(f"   ✓ 'Activos corrientes [sinopsis]' encontrado en posición: {activos_corrientes.index[0] + 1}")
                    
                    # Buscar también "Activos [sinopsis]"
                    activos = df[df["Concepto"].str.contains(r"^Activos \[sinopsis\]", case=False, na=False)]
                    if len(activos) > 0:
                        print(f"   ✓ 'Activos [sinopsis]' encontrado en posición: {activos.index[0] + 1}")
                
                # Verificar para Estado de Resultados
                elif "Resultado" in sheet_name:
                    # Buscar "Ingresos de actividades ordinarias"
                    ingresos_pos = df[df["Concepto"].str.contains("Ingresos de actividades ordinarias", na=False)].index
                    if len(ingresos_pos) > 0:
                        print(f"   ✓ 'Ingresos de actividades ordinarias' encontrado en posición: {ingresos_pos[0] + 1}")
                    else:
                        print(f"   ⚠ 'Ingresos de actividades ordinarias' NO encontrado")
        
    except Exception as e:
        print(f"Error verificando archivo: {e}")


# Función para procesar múltiples empresas
def process_multiple_companies(ruts, start_year=2024, end_year=2014, headless=True, quarterly=False):
    """
    Procesar múltiples empresas
    
    Args:
        ruts: Lista de RUTs de empresas
        start_year: Año inicial
        end_year: Año final
        headless: Si True, ejecuta en modo headless (por defecto True)
        quarterly: Si True, extrae datos trimestrales (por defecto False)
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    results = []
    # Nuevo parámetro: max_workers
    import inspect
    # Detectar si se pasó max_workers como argumento
    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    max_workers = values.get('max_workers', min(8, len(ruts)))

    def worker(rut, idx):
        logger.info(f"\n{'#'*60}")
        logger.info(f"PROCESANDO EMPRESA {idx+1}/{len(ruts)}: RUT {rut}")
        logger.info(f"{'#'*60}")
        try:
            file_path = scrape_cmf_data(rut, start_year, end_year, headless=headless, quarterly=quarterly)
            logger.info(f"✓ Empresa {idx+1}/{len(ruts)} completada exitosamente")
            verify_data_order(file_path)
            return (rut, file_path, "SUCCESS")
        except Exception as e:
            logger.error(f"✗ Error procesando RUT {rut}: {e}")
            return (rut, None, f"ERROR: {str(e)}")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_rut = {executor.submit(worker, rut, idx): rut for idx, rut in enumerate(ruts)}
        for future in as_completed(future_to_rut):
            result = future.result()
            results.append(result)

    # Resumen final
    logger.info(f"\n{'='*60}")
    logger.info("RESUMEN DE PROCESAMIENTO")
    logger.info(f"{'='*60}")

    successful = sum(1 for _, _, status in results if status == "SUCCESS")
    logger.info(f"Empresas procesadas exitosamente: {successful}/{len(ruts)}")

    for rut, file, status in results:
        if status == "SUCCESS":
            logger.info(f"✓ RUT {rut}: {file}")
        else:
            logger.info(f"✗ RUT {rut}: {status}")

    return results


def main():
    """
    Función principal para ejecutar el scraper de manera independiente
    """
    # Configuración
    rut = "91041000"  # VIÑA SAN PEDRO TARAPACA S.A.
    
    # Procesar una empresa en modo anual
    try:
        logger.info("INICIANDO EXTRACCIÓN DE DATOS CMF - MODO ANUAL")
        logger.info(f"RUT: {rut}")
        logger.info(f"Período: 2024-2020")
        logger.info(f"Estados financieros: Detección automática de taxonomías disponibles")
        logger.info(f"Modo: Headless (sin ventana de navegador)")
        logger.info(f"Frecuencia: Anual (solo diciembre)")
        
        output_file = scrape_cmf_data(
            rut=rut,
            start_year=2024,
            end_year=2020,
            step=-2,
            headless=True,  # Modo headless por defecto
            quarterly=False  # Solo anual
        )
        
        if output_file:
            print(f"\nProceso completado exitosamente")
            print(f"Archivo generado: {output_file}")
            print(f"Modo: Anual (diciembre de cada año)")
            
            # Verificar el orden de los datos
            print("\nVerificando orden de los datos...")
            verify_data_order(output_file)
        else:
            print(f"\nNo se pudieron extraer datos para esta empresa")
        
    except Exception as e:
        print(f"\nError en el procesamiento: {e}")


def main_quarterly():
    """
    Función para ejecutar el scraper en modo trimestral
    """
    rut = "91041000"  # VIÑA SAN PEDRO TARAPACA S.A.
    
    try:
        logger.info("INICIANDO EXTRACCIÓN DE DATOS CMF - MODO TRIMESTRAL")
        logger.info(f"RUT: {rut}")
        logger.info(f"Período: 2024-2022")
        logger.info(f"Estados financieros: Detección automática de taxonomías disponibles")
        logger.info(f"Modo: Headless (sin ventana de navegador)")
        logger.info(f"Frecuencia: Trimestral (marzo, junio, septiembre, diciembre)")
        
        output_file = scrape_cmf_data(
            rut=rut,
            start_year=2024,
            end_year=2022,
            step=-1,  # Cada año para tener más datos trimestrales
            headless=True,
            quarterly=True  # Modo trimestral
        )
        
        if output_file:
            print(f"\nProceso completado exitosamente")
            print(f"Archivo generado: {output_file}")
            print(f"Modo: Trimestral (4 períodos por año)")
            
            # Verificar el orden de los datos
            print("\nVerificando orden de los datos...")
            verify_data_order(output_file)
        else:
            print(f"\nNo se pudieron extraer datos para esta empresa")
        
    except Exception as e:
        print(f"\nError en el procesamiento: {e}")


# Función para ejecutar con ventana visible (solo para debugging)
def main_with_window():
    """
    Función para ejecutar el scraper con ventana visible (para debugging)
    """
    rut = "91041000"  # VIÑA SAN PEDRO TARAPACA S.A.
    
    try:
        logger.info("INICIANDO EXTRACCIÓN DE DATOS CMF - MODO CON VENTANA")
        logger.info("ADVERTENCIA: No use otras aplicaciones durante la extracción")
        
        output_file = scrape_cmf_data(
            rut=rut,
            start_year=2024,
            end_year=2020,
            step=-2,
            headless=False,  # Mostrar ventana para debugging
            quarterly=False  # Solo anual
        )
        
        if output_file:
            print(f"\nProceso completado exitosamente")
            print(f"Archivo generado: {output_file}")
        else:
            print(f"\nNo se pudieron extraer datos para esta empresa")
        
    except Exception as e:
        print(f"\nError en el procesamiento: {e}")


if __name__ == "__main__":
    # Por defecto ejecutar en modo anual
    main()
    
    # Para ejecutar en modo trimestral, usar:
    # main_quarterly()
    
    # Para ejecutar con ventana visible (solo para debugging), usar:
    # main_with_window()
    
    # Para múltiples empresas (ejemplo comentado):
    """
    # Modo anual
    ruts = ["76536353", "96505760", "96509660"]
    results = process_multiple_companies(ruts, start_year=2024, end_year=2014, headless=True, quarterly=False)
    
    # Modo trimestral
    ruts = ["91041000"]
    results = process_multiple_companies(ruts, start_year=2024, end_year=2022, headless=True, quarterly=True)
    """
