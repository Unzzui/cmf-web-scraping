# Deploy headless en servidor Linux

Guía de instalación del pipeline autónomo (sin GUI) con systemd + respaldo a
Google Drive. Todo lo de esta carpeta asume la instalación en
`/opt/cmf-web-scraping` con el usuario `findata`; ajusta rutas/usuario en los
`.service` si difieren.

## 1. Instalación base

```bash
sudo useradd -r -m -s /bin/bash findata          # usuario de servicio
sudo git clone <repo> /opt/cmf-web-scraping
sudo chown -R findata:findata /opt/cmf-web-scraping
sudo -iu findata
cd /opt/cmf-web-scraping

# venv del host (descarga + orquestación; NO necesita tkinter)
python -m venv .venv
.venv/bin/pip install -r src/config/requirements_pipeline.txt

# venv de cmf_extract (consolidación + análisis; aislado del host)
cd cmf_extract
python -m venv venv
venv/bin/pip install -r requirements.txt
cd ..

# Arelle (checkout fuente + su propio venv, igual que en desarrollo)
git clone https://github.com/Arelle/Arelle ~/Documents/Arelle
cd ~/Documents/Arelle && python -m venv .venv && .venv/bin/pip install -r requirements.txt
```

`src/gui/pipeline/settings.py` auto-detecta Arelle en `tools/Arelle`,
`~/Documents/Arelle` o `~/Arelle`; también puedes fijar `CMF_ARELLE_DIR`.

## 2. Clasificación de empresas (una vez, y al agregar empresas)

```bash
python scripts/classify_companies.py --dry-run   # revisar
python scripts/classify_companies.py             # escribe columna Categoria
```

Bancos, AFPs y aseguradoras quedan marcados y el CLI los omite por defecto
(reportan en formatos no-XBRL y romperían la corrida). Correcciones manuales:
edita la celda `Categoria` en el CSV; el clasificador las respeta.

## 3. Probar el CLI a mano

```bash
.venv/bin/python run_pipeline_cli.py --dry-run                  # plan
.venv/bin/python run_pipeline_cli.py --limit 2 --stages download --end-year 2024
.venv/bin/python run_pipeline_cli.py                            # corrida completa
```

Salidas: `--json` para eventos JSONL (journald-friendly); código de salida 0
ok / 1 errores por empresa / 2 preflight.

## 4. Optimización Arelle (cuello de botella de consolidación)

La fusión facts+pre (una corrida de Arelle por dataset en vez de dos) ya es el
comportamiento por defecto. El worker persistente (amortiza el arranque de
Python+Arelle entre datasets) se valida y activa así:

```bash
cd cmf_extract
venv/bin/python bench_arelle.py --base-dir ../data/XBRL/Total \
    --arelle-dir ~/Documents/Arelle
# si "worker" gana con claridad:
# añade Environment=CMF_ARELLE_WORKER=1 en findata-pipeline.service
```

Variables relevantes: `CMF_ARELLE_PARALLEL` (workers, default 6),
`CMF_ARELLE_TIMEOUT` (segundos por export, default 180).

## 5. Respaldo a Google Drive (rclone)

```bash
sudo pacman -S rclone            # o apt install rclone
rclone config                    # nuevo remote: nombre "gdrive", tipo "drive"
./scripts/backup_to_drive.sh --dry-run
./scripts/backup_to_drive.sh     # primer sync (tarda; luego es incremental)
```

Respalda `data/XBRL` (crudo, lo irreemplazable), `Products`, `Product_v1` y el
CSV maestro, excluyendo los `out_*/` regenerables. Nada se borra jamás del
Drive: lo eliminado localmente se mueve a `_papelera/<fecha>` en el remoto.

Para el `rclone config` en un servidor sin navegador: usa
`rclone authorize "drive"` desde tu máquina de escritorio y pega el token.

## 6. systemd

```bash
sudo cp deploy/systemd/findata-*.{service,timer} /etc/systemd/system/
# editar User= y rutas si difieren
sudo systemctl daemon-reload
sudo systemctl enable --now findata-pipeline.timer findata-backup.timer

systemctl list-timers findata-\*          # próximas ejecuciones
journalctl -u findata-pipeline -f        # logs en vivo
sudo systemctl start findata-pipeline    # corrida manual inmediata
```

El timer del pipeline corre diario a las 06:00 en los meses de publicación
CMF; con `skip_existing` las corridas sin datos nuevos terminan en minutos.
El pipeline invoca el respaldo al terminar (`--backup`) y además hay un timer
de respaldo diario independiente como red de seguridad.

## 7. Monitoreo (opcional, recomendado)

Crea un check en https://healthchecks.io y descomenta en
`findata-backup.service`:

```ini
Environment=HEALTHCHECK_URL=https://hc-ping.com/<uuid>
```

Si el pipeline falla del todo, `systemctl status findata-pipeline` y
`journalctl -u findata-pipeline --since today` tienen el detalle; el código de
salida distinto de 0 deja la unidad en estado `failed` (visible en cualquier
monitoreo de systemd).
