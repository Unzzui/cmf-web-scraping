from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
import time
import logging
import re

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def scrape_cmf_data(rut, start_year=2024, end_year=2014, step=-2):
    """
    Función principal para scraping de datos CMF
    Extrae solo [210000], [320000] y [510000]
    Mantiene el orden original de las filas como aparecen en la CMF
    
    Args:
        rut: RUT de la empresa sin guión ni dígito verificador
        start_year: Año inicial
        end_year: Año final
        step: Incremento entre años (por defecto -2)
    """
    
    # SOLO las taxonomías que necesitamos
    TAXONOMY_MAPPING = {
        "[210000]": {
            "name": "Balance General",
            "description": "Estado de situación financiera, corriente/no corriente"
        },
        "[320000]": {
            "name": "Estado Resultados",
            "description": "Estado del resultado, por naturaleza de gasto"
        },
        "[510000]": {
            "name": "Flujo Efectivo",
            "description": "Estado de flujos de efectivo, método directo"
        }
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
    
    # Configura el WebDriver
    driver = webdriver.Chrome()
    
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
        
        # Procesar cada año
        for year in range(start_year, end_year - 1, step):
            logger.info(f"\n{'='*50}")
            logger.info(f"Consultando año {year} (mostrará {year} y {year-1})")
            
            try:
                # Esperar a que el formulario esté presente
                form = wait.until(EC.presence_of_element_located((By.ID, "fm")))
                
                # Seleccionar año
                select_aa = Select(driver.find_element(By.ID, "aa"))
                select_aa.select_by_visible_text(str(year))
                
                # Seleccionar mes
                select_mm = Select(driver.find_element(By.ID, "mm"))
                select_mm.select_by_visible_text("12")
                
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
                
                # Verificar que hay tablas
                try:
                    wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
                except TimeoutException:
                    logger.warning(f"No se encontraron tablas para el año {year}")
                    driver.back()
                    continue
                
                # Parsear HTML
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
                # Buscar todas las tablas
                all_tables = soup.find_all("table")
                logger.info(f"Se encontraron {len(all_tables)} tablas")
                
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
                        
                        # Solo procesar si es una de las taxonomías que necesitamos
                        if taxonomy_code and taxonomy_code in TAXONOMY_MAPPING:
                            logger.info(f"Procesando tabla {taxonomy_code}")
                            
                            # Extraer fechas de las columnas del header
                            column_dates = []
                            ths = table.find_all("th")
                            for th in ths[1:]:  # Skip first header (descripción)
                                date_text = th.get_text().strip()
                                date_match = re.search(r'(\d{4})-\d{2}-\d{2}', date_text)
                                if date_match:
                                    year_col = date_match.group(1)
                                    column_dates.append(year_col)
                            
                            logger.info(f"  Columnas de años encontradas: {column_dates}")
                            
                            # Procesar filas manualmente para mantener el orden
                            rows = table.find_all("tr")
                            
                            for row in rows[1:]:  # Skip header row
                                cells = row.find_all(["td", "th"])
                                
                                if len(cells) > 1:
                                    # Obtener el concepto (primera celda)
                                    concept_text = cells[0].get_text().strip()
                                    
                                    # Limpiar el concepto
                                    concept_text = concept_text.replace("\n", " ").strip()
                                    
                                    # Skip filas con "sinopsis"
                                    if "sinopsis" in concept_text.lower():
                                        continue
                                    
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
                                            year_col = column_dates[i]
                                            
                                            # Solo agregar si no hemos procesado este año antes
                                            if year_col not in years_collected[taxonomy_code]:
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
                                                    data_by_taxonomy[taxonomy_code][concept_text][year_col] = value
                            
                            # Marcar años como procesados
                            for year_col in column_dates:
                                years_collected[taxonomy_code].add(year_col)
                            
                            logger.info(f"  Procesados {len(concept_order[taxonomy_code])} conceptos")
                    
                    except Exception as e:
                        logger.error(f"Error procesando tabla: {e}")
                        continue
                
                # Volver atrás
                driver.back()
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error procesando año {year}: {e}")
                try:
                    driver.back()
                except:
                    driver.get(url)
                continue
        
        # Convertir datos a DataFrames manteniendo el orden
        dataframes = {}
        
        for taxonomy_code in TAXONOMY_MAPPING.keys():
            if data_by_taxonomy[taxonomy_code]:
                # Obtener lista de todos los años
                all_years = sorted(years_collected[taxonomy_code], reverse=True)
                
                if all_years and concept_order[taxonomy_code]:
                    # Crear lista de diccionarios manteniendo el orden original
                    rows = []
                    for concept in concept_order[taxonomy_code]:
                        row = {"Concepto": concept}
                        for year in all_years:
                            row[year] = data_by_taxonomy[taxonomy_code][concept].get(year, 0)
                        rows.append(row)
                    
                    # Crear DataFrame
                    columns = ["Concepto"] + all_years
                    dataframes[taxonomy_code] = pd.DataFrame(rows, columns=columns)
                    
                    logger.info(f"\n{taxonomy_code}: {len(rows)} filas, {len(all_years)} años")
                    logger.info(f"  Primeros 5 conceptos: {concept_order[taxonomy_code][:5]}")
        
        # Guardar en Excel
        output_file = f"./data/Reports/{company_name}_Financials.xlsx"
        
        import os
        os.makedirs("./data/Reports", exist_ok=True)
        
        with pd.ExcelWriter(output_file, engine="xlsxwriter") as writer:
            for taxonomy_code, info in TAXONOMY_MAPPING.items():
                if taxonomy_code in dataframes and not dataframes[taxonomy_code].empty:
                    sheet_name = info["name"][:31]
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
                        'align': 'center'
                    })
                    
                    # Formato para conceptos (primera columna)
                    concept_format = workbook.add_format({
                        'border': 1,
                        'align': 'left',
                        'valign': 'vcenter'
                    })
                    
                    # Aplicar formatos
                    for i, col in enumerate(dataframes[taxonomy_code].columns):
                        if i == 0:  # Columna de conceptos
                            max_len = dataframes[taxonomy_code][col].astype(str).str.len().max()
                            worksheet.set_column(i, i, min(max_len + 2, 60))
                        else:  # Columnas numéricas
                            worksheet.set_column(i, i, 15, number_format)
                    
                    # Formato de headers
                    for col_num, value in enumerate(dataframes[taxonomy_code].columns.values):
                        worksheet.write(0, col_num, value, header_format)
                    
                    logger.info(f"Guardada hoja '{sheet_name}' con {len(dataframes[taxonomy_code])} filas")
        
        logger.info(f"\n{'='*50}")
        logger.info(f"PROCESO COMPLETADO")
        logger.info(f"Archivo guardado: {output_file}")
        logger.info(f"{'='*50}")
        
        # Resumen final
        for taxonomy_code, info in TAXONOMY_MAPPING.items():
            if taxonomy_code in dataframes:
                años = [col for col in dataframes[taxonomy_code].columns if col != "Concepto"]
                logger.info(f"{taxonomy_code}: {len(años)} años extraídos: {años}")
                
                # Mostrar primeros conceptos para verificación
                if not dataframes[taxonomy_code].empty:
                    primeros_conceptos = dataframes[taxonomy_code]["Concepto"].head(10).tolist()
                    logger.info(f"  Primeros conceptos: {primeros_conceptos[:3]}...")
        
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
                print(f"   Primeros 10 conceptos:")
                for i, concepto in enumerate(df["Concepto"].head(10), 1):
                    print(f"      {i}. {concepto}")
                
                # Verificar específicamente para Balance General
                if "Balance" in sheet_name:
                    # Buscar "Efectivo y equivalentes al efectivo"
                    efectivo_pos = df[df["Concepto"].str.contains("Efectivo", na=False)].index
                    if len(efectivo_pos) > 0:
                        print(f"   ✓ 'Efectivo y equivalentes al efectivo' encontrado en posición: {efectivo_pos[0] + 1}")
                    else:
                        print(f"   ⚠ 'Efectivo y equivalentes al efectivo' NO encontrado")
                
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
def process_multiple_companies(ruts, start_year=2024, end_year=2014):
    """
    Procesar múltiples empresas
    """
    results = []
    
    for i, rut in enumerate(ruts, 1):
        logger.info(f"\n{'#'*60}")
        logger.info(f"PROCESANDO EMPRESA {i}/{len(ruts)}: RUT {rut}")
        logger.info(f"{'#'*60}")
        
        try:
            file_path = scrape_cmf_data(rut, start_year, end_year)
            results.append((rut, file_path, "SUCCESS"))
            logger.info(f"✓ Empresa {i}/{len(ruts)} completada exitosamente")
            
            # Verificar el orden de los datos
            verify_data_order(file_path)
            
        except Exception as e:
            logger.error(f"✗ Error procesando RUT {rut}: {e}")
            results.append((rut, None, f"ERROR: {str(e)}"))
        
        # Pausa entre empresas
        if i < len(ruts):
            logger.info(f"Esperando 5 segundos antes de procesar la siguiente empresa...")
            time.sleep(5)
    
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


if __name__ == "__main__":
    # Configuración
    rut = "96505760"  # ENEL CHILE
    
    # Procesar una empresa
    try:
        logger.info("INICIANDO EXTRACCIÓN DE DATOS CMF")
        logger.info(f"RUT: {rut}")
        logger.info(f"Período: 2024-2014")
        logger.info(f"Estados financieros: [210000], [320000], [510000]")
        
        output_file = scrape_cmf_data(
            rut=rut,
            start_year=2024,
            end_year=2014,
            step=-2
        )
        
        print(f"\n✅ Proceso completado exitosamente")
        print(f"📁 Archivo generado: {output_file}")
        
        # Verificar el orden de los datos
        print("\nVerificando orden de los datos...")
        verify_data_order(output_file)
        
    except Exception as e:
        print(f"\n❌ Error en el procesamiento: {e}")
    
    # Para múltiples empresas:
    """
    ruts = ["76536353", "96505760", "96509660"]
    results = process_multiple_companies(ruts, start_year=2024, end_year=2014)
    """