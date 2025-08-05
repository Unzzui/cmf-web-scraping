#%%
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
import time
import re

# Configura el WebDriver (en este caso, Chrome)
driver = webdriver.Chrome()
# Cambia el RUT según la empresa que quieras recopilar "sin el guión" y "sin el digito verificador" (Ejemplo: 96505760)
rut = "91041000"  # Los datos de los RUT se encuentran en la ruta RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx

# Abre la URL
driver.get(
    f"https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
)


# Espera hasta que el formulario esté presente
wait = WebDriverWait(driver, 15)
form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

# Busca el name de la company con el class ntg-page-header
company_name = driver.find_element(By.ID, "datos_ent").text[0:]
lines = company_name.split("\n")  # Divide el texto en líneas
company_name = lines[1]  # El nombre de la empresa es la segunda línea

# Crea un escritor de Excel
writer = pd.ExcelWriter(
    f"./data/Reports/{company_name}_Financials.xlsx", engine="xlsxwriter"
)

# Define los códigos de taxonomía IFRS que queremos extraer
taxonomy_codes = {
    "[210000]": "Balance General",           # Estado de situación financiera
    "[220000]": "Balance General (Liquidez)", # Estado de situación financiera por liquidez
    "[310000]": "Estado de Resultados",      # Estado del resultado por función
    "[320000]": "Estado de Resultados",      # Estado del resultado por naturaleza
    "[420000]": "Estado de Resultados Integral", # Estado de Resultados Integral
    "[510000]": "Estado de Flujo de Efectivo",   # Flujo de efectivo método directo
    "[520000]": "Estado de Flujo de Efectivo",   # Flujo de efectivo método indirecto
    "[610000]": "Estado de Cambio en el Patrimonio" # Cambio en el Patrimonio
}

# Crea un DataFrame vacío para cada código de taxonomía
dataframes = {code: pd.DataFrame() for code in taxonomy_codes.keys()}

def safe_click_submit_button(driver, wait):
    """Función para hacer clic en el botón de envío de forma segura"""
    try:
        # Esperar a que el botón esté presente y sea clickeable
        submit_button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".arriba")))
        
        # Scroll hasta el elemento para asegurarse de que esté visible
        driver.execute_script("arguments[0].scrollIntoView(true);", submit_button)
        time.sleep(1)  # Pequeña pausa después del scroll
        
        # Intentar clic normal primero
        submit_button.click()
        
    except ElementClickInterceptedException:
        print("Clic normal falló, intentando con JavaScript...")
        try:
            # Si el clic normal falla, usar JavaScript
            submit_button = driver.find_element(By.CSS_SELECTOR, ".arriba")
            driver.execute_script("arguments[0].click();", submit_button)
        except Exception as e:
            print(f"Error en JavaScript click: {e}")
            # Último recurso: buscar botón por texto o tipo
            try:
                submit_button = driver.find_element(By.XPATH, "//input[@type='submit' or @value='Consultar' or contains(@class, 'arriba')]")
                driver.execute_script("arguments[0].click();", submit_button)
            except Exception as final_e:
                print(f"Error final: {final_e}")
                raise

def extract_table_by_taxonomy_code(soup, code):
    """Extrae una tabla basándose en el código de taxonomía en el header"""
    try:
        # Buscar el header que contiene el código de taxonomía
        header = soup.find('th', string=re.compile(re.escape(code)))
        if not header:
            print(f"No se encontró header con código {code}")
            return None
        
        # Obtener la tabla que contiene este header
        table = header.find_parent('table')
        if not table:
            print(f"No se encontró tabla para el código {code}")
            return None
        
        # Convertir la tabla a DataFrame
        table_str = str(table).replace(',', '.')
        dfs = pd.read_html(StringIO(table_str))
        
        if dfs:
            df = dfs[0]
            print(f"Tabla {code} extraída con {df.shape[0]} filas y {df.shape[1]} columnas")
            return df
        else:
            print(f"No se pudo parsear la tabla para {code}")
            return None
            
    except Exception as e:
        print(f"Error extrayendo tabla {code}: {e}")
        return None

# Bucle para recopilar datos de varios años en este caso 10 años
# el -2 se utiliza por el hecho de que la página de la CMF brinda información cada 2 años.
for year in range(2022, 2012, -2):
    print(f"Procesando año: {year}")
    
    # Esperar a que el formulario esté presente
    form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

    # Seleccionar año
    select_aa = Select(driver.find_element(By.ID, "aa"))
    select_aa.select_by_visible_text(str(year))
    time.sleep(0.5)  # Pequeña pausa entre selecciones

    # Seleccionar mes
    select_mm = Select(driver.find_element(By.ID, "mm"))
    select_mm.select_by_visible_text("12")
    time.sleep(0.5)

    # Seleccionar tipo
    select_tipo = Select(driver.find_element(By.NAME, "tipo"))
    select_tipo.select_by_visible_text("Consolidado")
    time.sleep(0.5)

    # Seleccionar norma
    select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
    select_tipo_norma.select_by_visible_text("Estándar IFRS")
    time.sleep(0.5)

    # Haz clic en el botón para enviar el formulario usando la función segura
    safe_click_submit_button(driver, wait)

    # Espera para que se carguen las tablas después de la interacción
    try:
        # Esperar un poco más para que se cargue completamente
        time.sleep(3)
        # Verificar que hay contenido financiero en la página
        wait.until(EC.presence_of_element_located((By.XPATH, "//h3[contains(text(), 'VISUALIZACION ESTADOS FINANCIEROS')]")))
        time.sleep(2)  # Tiempo adicional para carga completa
    except TimeoutException:
        print(f"No se encontraron estados financieros para el año {year}. Continuando...")
        driver.back()
        time.sleep(2)
        continue
    
    # Extrae la información de las tablas con BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

    concept_name_mapping = {
        # Nombre Antiguo --- Nombre Nuevo
        "Capital emitido": "Capital emitido y pagado",
        "Diferencias de cambio": "Ganancias (pérdidas) de cambio en moneda extranjera",
        "Flujos de efectivo netos procedentes de (utilizados en) la operación": "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
        "Pagos de préstamos a entidades relacionadas": "Pagos de préstamos de entidades relacionadas",
        "Pagos de pasivos por arrendamientos financieros": "Pagos de pasivos por arrendamientos",
        "Pagos por cambios en las participaciones en la propiedad en subsidiarias que no resulta en una pérdida de control": "Pagos por cambios en las participaciones en la propiedad en subsidiarias que no dan lugar a la pérdida de control",
        # Agrega más mapeos según sea necesario
    }

    # Extraer tablas basándose en códigos de taxonomía
    for code in taxonomy_codes.keys():
        df = extract_table_by_taxonomy_code(soup, code)
        if df is not None and not df.empty:
            # Limpiar y procesar el DataFrame
            df = df.copy()
            
            # Elimina las filas que contienen la palabra "sinopsis" en la primera columna
            if len(df.columns) > 0:
                df = df[~df[df.columns[0]].astype(str).str.contains("sinopsis", na=False)]
            
            # Reemplaza los guiones que están solos por ceros, pero mantiene la primera columna
            if len(df.columns) > 1:
                df.iloc[:, 1:] = df.iloc[:, 1:].replace("^-$", "0", regex=True)

            # Reemplaza los nombres antiguos de los conceptos por los nuevos
            if len(df.columns) > 0:
                df[df.columns[0]] = df[df.columns[0]].replace(concept_name_mapping)

            # Merge inteligente con datos existentes
            if not dataframes[code].empty:
                # Renombrar columnas del nuevo df para incluir el año
                new_columns = {df.columns[i]: f"{col}_{year}" if i > 0 else col 
                              for i, col in enumerate(df.columns)}
                df = df.rename(columns=new_columns)
                
                # Realiza un merge en el nombre del concepto (primera columna)
                try:
                    dataframes[code] = pd.merge(
                        dataframes[code], df, on=dataframes[code].columns[0], how="outer"
                    )
                    # Elimina duplicados basados en la primera columna (nombre del concepto)
                    dataframes[code] = dataframes[code].drop_duplicates(
                        subset=dataframes[code].columns[0]
                    )
                except Exception as e:
                    print(f"Error en merge para {code}: {e}")
                    # Si falla el merge, simplemente concatenar
                    dataframes[code] = pd.concat([dataframes[code], df], ignore_index=True)
            else:
                # Si dataframes[code] está vacío, agrega df tal como está
                dataframes[code] = df
    
    # Volver a la página anterior para el siguiente año
    driver.back()
    time.sleep(2)  # Esperar a que se cargue la página anterior

# Escribe cada DataFrame en una hoja diferente
print("Guardando resultados en Excel...")

for code in taxonomy_codes.keys():
    if not dataframes[code].empty:
        sheet_name = taxonomy_codes[code]
        dataframes[code].to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"Guardada hoja: {sheet_name} con {dataframes[code].shape[0]} filas")

writer.close()

# Cierra el navegador
driver.quit()
print("Proceso completado exitosamente!")