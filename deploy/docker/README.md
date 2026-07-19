# findata-updater — actualización automática en un contenedor

Orquestador que corre en tu server (miniserver x86 o Asahi/ARM) y mantiene FindData al día
**sin intervención**: detecta qué empresas publicaron resultados nuevos (según el calendario
CMF/EDGAR) y corre solo para ellas el pipeline completo — bajar/ingerir → regenerar estados y
Excel → publicar en FinData → backup.

## Cómo funciona

`scripts/auto_update.py` es el corazón. Cada ciclo:

1. **Refresca calendarios** — `scrape_report_dates.py` (fechas CMF) + `ingest_us_calendar.py`
   (10-K/10-Q de EDGAR).
2. **Gate incremental** (la pieza nueva — los calendarios ya existían pero nadie los leía):
   - **CL**: empresas con publicación reciente (últimos 120 días, fecha ≤ hoy) cuyo período
     todavía NO está en `financial_data`, y que ya procesamos.
   - **US**: empresas cuyo calendario tiene un filing de período MÁS NUEVO que el último dato
     ingerido. Tras la ingesta EDGAR, sólo se regenera Excel/publica para las que REALMENTE
     avanzaron de período (si companyfacts aún no reflejó el filing, no se re-genera nada caro).
3. **Corre el pipeline solo de las que cambiaron** (CL: `run_pipeline_cli.py`; US: la secuencia
   ingest → enrich → Kd → estados → análisis → publicar → ratios/DCF).
4. **Backup** a Google Drive (rclone) + log.

En días sin publicaciones nuevas, los gates devuelven cero y el ciclo termina en **segundos**.

## Deploy

```bash
# 1. En el server, cloná los dos repos y dejá sus .env con las credenciales:
git clone <cmf-web-scraping>   /srv/cmf
git clone <FinDataChile>       /srv/fdc
#    cmf/.env  y  fdc/.env  necesitan: ver "Secrets" abajo.

# 2. Rutas del compose (o exportá CMF_REPO / FDC_REPO):
export CMF_REPO=/srv/cmf FDC_REPO=/srv/fdc

# 3. Levantar (build multi-arch automático según la arch del host):
docker compose -f deploy/docker/docker-compose.yml up -d --build

# 4. Ver que corre:
docker compose -f deploy/docker/docker-compose.yml logs -f
```

Queda corriendo con `restart: unless-stopped` (sobrevive reinicios del server).

## Probar sin publicar (dry-run)

Antes de dejarlo en `--live`, verificá el plan sin escribir nada:

```bash
docker compose -f deploy/docker/docker-compose.yml run --rm findata-updater \
    python /app/cmf/scripts/auto_update.py            # dry-run, un ciclo
```

Muestra cuántas CL y US se actualizarían, sin tocar producción.

## Secrets (en los `.env` de los repos montados)

| Variable | Para qué | En qué .env |
|---|---|---|
| `PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD` | BD Supabase (prod) | cmf y/o fdc |
| `EDGAR_USER_AGENT` | la SEC exige contacto real (403 sin él) | cmf |
| `CMF_API_KEY` | API de la CMF (bancos) | cmf |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | publicar en FinData (leg 3A) | fdc |
| `FDC_ADMIN_USER` / `FDC_ADMIN_PASS` | idem para el uploader US | cmf o fdc |
| `FDC_URL` | URL de FinData (default prod) | env del compose |

**No van en el contenedor** (siguen en Vercel): `MARKET_STACK_API_KEY`, `FMP_API_KEY`,
`BLOB_READ_WRITE_TOKEN`, `SMTP_*`, `CRON_SECRET` — el Blob y los precios los maneja el Next
app desplegado; este contenedor sólo hace el POST HTTP de publicación.

## Runtime del contenedor

Python 3.12 + Arelle (puro Python, sin Java) + Chromium/chromedriver (descarga CMF) + rclone.
**Sin Node, sin LibreOffice** (verificado: no se invocan). Los dos repos y sus datos viven en
el host (montados), así el XBRL descargado y el cache persisten entre actualizaciones.

## Ajustes

- **Cadencia**: `--loop 24` (un ciclo/día). Cambiá el número de horas en el `command` del
  compose, o corré `--loop 0` (una sola vez) desde un cron/systemd del host.
- **Solo un mercado**: `--only-cl` / `--only-us`.
- **Ventana del gate**: los gates miran los últimos 120 días; se ajusta en `auto_update.py`.
- **Publicación US**: necesita `FDC_ADMIN_USER`/`FDC_ADMIN_PASS` para el `upload_us_products`.
