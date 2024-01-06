from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select
from bs4 import BeautifulSoup
from io import StringIO
import pandas as pd

# Configura el WebDriver (en este caso, Chrome)
driver = webdriver.Chrome()

# Abre la URL
driver.get(
    "https://www.cmfchile.cl/institucional/mercados/novedades_envio_fechas_eeff.php"
)

# Espera hasta que el formulario esté presente
wait = WebDriverWait(driver, 10)
form = wait.until(EC.presence_of_element_located((By.ID, "frm_consulta")))

select_aa = Select(driver.find_element(By.ID, "aaaa"))
select_aa.select_by_visible_text(str("2023"))

driver.find_element(By.CLASS_NAME, "mime_bot_consultar").click()

# Espera para que se cargue la tabla después de la interacción
wait.until(EC.presence_of_element_located((By.CLASS_NAME, "table-responsive")))

# Extrae la información de la tabla con BeautifulSoup
soup = BeautifulSoup(driver.page_source, "html.parser")

tabla = soup.find(class_="table-responsive")

tabla_str = str(tabla).replace(",", ".")

df = pd.read_html(StringIO(tabla_str))[0]

# Cierra el navegador
driver.quit()

# agregar una nueva columna con el RUT de la empresa tomando la columna RUT pero sin el guion y el digito verificador
df["RUT_Sin_Guión"] = df["RUT"].str.replace("-", "").str[:-1]

# Creación archivo excel y csv.
df.to_excel("./data/RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx", index=False)
df.to_csv("./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv", index=False)
