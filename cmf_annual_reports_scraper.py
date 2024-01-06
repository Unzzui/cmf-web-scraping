from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd
from selenium.common.exceptions import TimeoutException

# Configura el WebDriver (en este caso, Chrome)
driver = webdriver.Chrome()

rut = "96505760"  # Cambia el RUT según la empresa que quieras recopilar "sin el guión"
# Abre la URL
driver.get(
    f"https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=AAAwy2ACTAAABy2AAC&vig=VI&control=svs&pestania=3"
)


# Espera hasta que el formulario esté presente
wait = WebDriverWait(driver, 10)
form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

# Busca el name de la company con el class ntg-page-header
company_name = driver.find_element(By.ID, "datos_ent").text[0:]
lines = company_name.split("\n")  # Divide el texto en líneas
company_name = lines[1]  # El nombre de la empresa es la segunda línea

# Crea un escritor de Excel
writer = pd.ExcelWriter(
    f"./data/Reports/{company_name}_Financials.xlsx", engine="xlsxwriter"
)

# Encuentra las tablas dentro de los divs con los ids especificados
ids = ["ESFC", "ERF", "ERN", "EFEMD"]

# Crea un DataFrame vacío para cada id
dataframes = {id: pd.DataFrame() for id in ids}

# Bucle para recopilar datos de varios años en este caso 10 años
# el -2 se utiliza por el hecho de que la página de la CMF brinda información cada 2 años.
for year in range(2022, 2012, -2):
    form = wait.until(EC.presence_of_element_located((By.ID, "fm")))

    select_aa = Select(driver.find_element(By.ID, "aa"))
    select_aa.select_by_visible_text(str(year))

    select_mm = Select(driver.find_element(By.ID, "mm"))
    select_mm.select_by_visible_text("12")

    select_tipo = Select(driver.find_element(By.NAME, "tipo"))
    select_tipo.select_by_visible_text("Consolidado")

    select_tipo_norma = Select(driver.find_element(By.NAME, "tipo_norma"))
    select_tipo_norma.select_by_visible_text("Estándar IFRS")

    # Haz clic en el botón para enviar el formulario
    driver.find_element(By.CSS_SELECTOR, ".arriba").click()

    # Espera para que se cargue la tabla después de la interacción
    try:
        # Espera para que se cargue la tabla después de la interacción
        wait.until(EC.presence_of_element_located((By.ID, "ESFC")))
    except TimeoutException:
        print(f"No se encontró la tabla para el año {year}. Deteniendo el ciclo.")
        continue
    # Extrae la información de la tabla con BeautifulSoup
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

    for id in ids:
        tabla = soup.find(id=id)
        if tabla:
            tabla_str = str(tabla).replace(",", ".")
            df = pd.read_html(StringIO(tabla_str))[0]  # Lee la tabla

            # Maneja cada ID de manera diferente
            if id == "ESFC":
                # Código para manejar el balance (ESFC)
                pass
            elif id in ["ERF", "ERN"]:
                # Código para manejar el estado de resultados (ERF y ERN)
                pass
            elif id == "EFEMD":
                # Código para manejar EFEMD
                pass

            # Crea una copia del DataFrame antes de modificarlo
            df = df.copy()
            # Elimina las filas que contienen la palabra "sinopsis" en la primera columna
            df = df[~df[df.columns[0]].str.contains("sinopsis")]
            # Reemplaza los guiones que están solos por ceros, pero mantiene la primera columna
            df.iloc[:, 1:] = df.iloc[:, 1:].replace("^-$", "0", regex=True)

            # Reemplaza los nombres antiguos de los conceptos por los nuevos
            df[df.columns[0]] = df[df.columns[0]].replace(concept_name_mapping)

            # Si dataframes[id] no está vacío, solo agrega las filas cuyo nombre de concepto ya existe en dataframes[id]
            if not dataframes[id].empty:
                # Renombra la primera columna para que coincida con la de dataframes[id]
                df = df.rename(columns={df.columns[0]: dataframes[id].columns[0]})
                # Realiza un merge en el nombre del concepto
                dataframes[id] = pd.merge(
                    dataframes[id], df, on=dataframes[id].columns[0], how="outer"
                )
                # Elimina duplicados basados en la primera columna (nombre del concepto)
                dataframes[id] = dataframes[id].drop_duplicates(
                    subset=dataframes[id].columns[0]
                )
            else:
                # Si dataframes[id] está vacío, agrega df tal como está
                dataframes[id] = df
    driver.back()

# Escribe cada DataFrame en una hoja diferente

Names_Sheet = {
    "ESFC": "Balance General",
    "ERF": "Estado de Resultados",
    "ERN": "Estado de Resultados",
    "EFEMD": "Estado de Flujo de Efectivo",
}

for id in ids:
    if not dataframes[id].empty:
        dataframes[id].to_excel(writer, sheet_name=Names_Sheet[id], index=False)

writer.close()

# Cierra el navegador
driver.quit()
