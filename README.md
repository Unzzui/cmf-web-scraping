# CMF Annual Reports Scraper

## Descripción

Este proyecto ofrece una solución automatizada para la recopilación de informes anuales de la Comisión para el Mercado Financiero (CMF) de Chile. Mediante el uso de Selenium y BeautifulSoup, este scraper facilita la extracción eficiente de datos financieros desde el sitio web de la CMF. Su desarrollo surge como respuesta a la falta de plataformas en el mercado chileno que simplifiquen este proceso, proveyendo así una herramienta valiosa para el análisis financiero y la investigación de mercado.

## Características

- Automatización de la recopilación de datos financieros de múltiples años.
- Extracción de información de tablas de la página web de la CMF.
- Generación de archivos Excel con datos estructurados para análisis.

## Requisitos

Antes de ejecutar este scraper, asegúrate de tener instaladas las siguientes bibliotecas en tu entorno Python:

- selenium
- beautifulsoup4
- pandas

Puedes instalar estas bibliotecas ejecutando:

```bash
pip install -r requirements.txt
```

## Uso

Para usar este scraper, simplemente ejecuta el script `cmf_annual_reports_scraper.py` con Python:

```bash
python cmf_annual_reports_scraper.py
```

## Complemento

- En la carpeta "RUT_Chilean_Companies", se encontrarán los RUT de cada empresa Chilena, con esto se podra acceder a cualquier empresa, por ende descargar sus estados financieros.

## Contribuciones

Las contribuciones al proyecto son bienvenidas. Si tienes sugerencias para mejorar o ampliar la funcionalidad del scraper, no dudes en crear un pull request o abrir un issue.

## Contacto

Para cualquier consulta o comentario, puedes contactarme a diegobravobe@gmail.com @Unzzui
