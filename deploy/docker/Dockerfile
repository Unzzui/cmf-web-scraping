# findata-updater — orquestador de actualización automática (CL + EEUU).
#
# Multi-arch: python:3.12-slim tiene arm64 (Asahi / Apple Silicon) y amd64 (miniserver).
# Chromium, chromium-driver y rclone salen de Debian para las dos arquitecturas.
#
# Build (multi-arch, requiere buildx):
#   docker buildx build --platform linux/arm64,linux/amd64 -t findata-updater \
#       -f deploy/docker/Dockerfile . --load
# Correr: ver deploy/docker/docker-compose.yml (monta los dos repos + el .env).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    # La descarga de la CMF usa Selenium/Chromium headless.
    CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

# Runtime del sistema: Chromium + driver (descarga CMF), rclone (backup a Drive), y las
# libs nativas de psycopg2/lxml. NO se instala Java (Arelle es puro Python), ni Node
# (la publicación es un POST HTTP al Next ya desplegado), ni LibreOffice (las fórmulas
# se escriben como strings y el comprador recalcula al abrir el Excel).
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium chromium-driver \
        rclone \
        libpq-dev libxml2 libxslt1.1 \
        curl ca-certificates tzdata bash \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=America/Santiago

# Dependencias Python del pipeline (baked en la imagen; el CÓDIGO se monta en runtime).
# arelle-release = el motor XBRL, puro Python. El resto son las deps de pyproject.toml.
RUN pip install \
        pandas numpy openpyxl xlsxwriter requests psycopg2-binary rich \
        beautifulsoup4 lxml selenium webdriver-manager \
        arelle-release

WORKDIR /app

# Los dos repos y los .env se MONTAN en runtime (docker-compose), no se copian a la imagen:
#   /app/cmf  = cmf-web-scraping   (pipeline + orquestador)
#   /app/fdc  = FinDataChile       (scripts de ratios/DCF + .env)
# Así la imagen es sólo runtime y el código/datos viven en el host (persisten entre updates).

# Por defecto: un ciclo diario, live, refrescando calendarios. El gate hace que las noches
# sin publicaciones nuevas terminen en segundos. Override en compose si se quiere otro modo.
ENV FINDATACHILE_REPO=/app/fdc
CMD ["python", "/app/cmf/scripts/auto_update.py", "--live", "--refresh-calendars", "--loop", "24"]
