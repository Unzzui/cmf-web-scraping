# Pipeline CMF unificado (GUI)

Una sola interfaz para llevar, de punta a punta y sin intervención, el flujo:

```
①  Descargar XBRL desde la CMF        (este repo · selenium)
②  Consolidar a Excel de análisis     (CMF_EXTRACT · Arelle)
③  Subir a FinDataChile               (DIFERIDO — se hará aparte)
```

> La etapa ③ está implementada pero **desactivada por ahora**. El flujo por
> defecto termina en el paso ②, dejando los Excel listos para revisar y subir
> manualmente.

## Todo en un solo repo (portable)

Este repo es **autocontenido**: CMF_EXTRACT está vendorizado en `cmf_extract/` y
Arelle vive en `tools/Arelle/`. No depende de repos externos ni de rutas
absolutas; todas las rutas se derivan del propio repo, así funciona igual en
otro PC.

## Instalación en un PC nuevo

```bash
git clone <este-repo> && cd cmf-web-scraping
./setup.sh
```

`setup.sh` deja todo listo (no requiere intervención):
1. `.venv` — GUI + descarga (tkinter, selenium, pandas…).
2. `cmf_extract/.venv` — consolidación (pandas 2.3.x, etc.).
3. `tools/Arelle` — clona Arelle y le crea su propio `.venv`.
4. Genera `config/pipeline_settings.json` con rutas in-repo y verifica el entorno.

Necesita un Python ≥ 3.11 con `tkinter` (p. ej. `sudo apt install python3-tk`,
o pyenv 3.12). `setup.sh` lo detecta solo.

## Cómo se ejecuta

```bash
.venv/bin/python run_pipeline_gui.py
```

o `source .venv/bin/activate && python run_pipeline_gui.py`.

> Tres entornos aislados a propósito (la GUI, CMF_EXTRACT y Arelle tienen
> dependencias incompatibles entre sí). La GUI los orquesta; no hay que activarlos
> a mano. Si una ruta guardada no existe (config traída de otro PC), se repara
> sola al default in-repo.

## Primera vez: configurar el entorno

Abrí **⚙ Configuración** y revisá / ajustá:

- **Repo CMF_EXTRACT** — ruta al proyecto CMF_EXTRACT.
- **Python CMF_EXTRACT** — intérprete con el que importa `cmf.pipeline`
  (su `.venv` si existe, o el python del sistema).
- **Directorio Arelle** — instalación de Arelle (necesaria para consolidar).
- **Carpeta XBRL base / Products / Product_v1** — auto-detectadas; cambialas
  sólo si hace falta.

Pulsá **🔍 Verificar entorno**: muestra ✔/✖ por cada requisito (repo, import de
`cmf.pipeline`, Arelle, etc.). Si algo está en ✖, la consolidación fallará.

La configuración se guarda en `config/pipeline_settings.json`.

## Descarga rápida (HTTP, sin navegador)

La descarga ya NO usa Selenium/Chrome. Se descubrió que la CMF entrega el XBRL
por HTTP directo:

1. `GET entidad.php?...&pestania=3` abre la sesión.
2. `POST` del formulario (`forma=P, aa, mm, tipo=C, tipo_norma=IFRS`) devuelve el
   enlace "Estados financieros (XBRL)".
3. `GET safec_ifrs_verarchivo.php?auth=..&send=..` baja el ZIP.

Con peticiones concurrentes (`requests`, sin browser): **~16 períodos en ~11 s**
frente a **~4 min** del navegador (~22x). Implementado en
`src/xbrl/cmf_xbrl_http_downloader.py`; Selenium queda solo como fallback.

## Qué lo hace rápido

- **Pipelining real**: cada empresa es un worker independiente. Mientras una se
  consolida (Arelle, CPU), otra ya está descargando (red). No se espera a que
  termine "todo el lote" de una etapa para empezar la siguiente.
- **Concurrencia por etapa** (configurable en *Rendimiento*): nº de descargas,
  consolidaciones y workers de Arelle en paralelo.
- **Omitir lo ya hecho** (`skip_existing`): no re-descarga períodos presentes ni
  re-consolida empresas cuyo Excel de análisis ya existe. Re-correr es barato.
- **Sin duplicar XBRL**: CMF_EXTRACT lee directo la carpeta que produce la
  descarga; no se copian gigabytes.

## La vista de pipeline

Una fila por empresa con el estado vivo de cada etapa
(`· Pendiente / ● En curso / ✔ Listo / ✖ Error / » Omitido`), progreso, ETA y
detalle, más contadores globales y cronómetro. El log completo se conserva
abajo: nada de información se pierde, sólo queda mejor organizada.

## Arquitectura (resumen)

```
src/gui/unified_window.py        Ventana principal (toolbar, config, vista, log)
src/gui/settings_dialog.py       Configuración + verificación de entorno
src/gui/components/pipeline_view.py   Tabla viva por empresa/etapa
src/gui/pipeline/
  settings.py                    Config persistida + auto-detección
  models.py                      Stage / StageStatus / CompanyState / eventos
  orchestrator.py                Workers por empresa + semáforos por etapa
  cmf_extract_bridge.py          Lanza CMF_EXTRACT (subprocess) y lee su JSONL
  cmf_extract_runner.py          Se ejecuta DENTRO de CMF_EXTRACT; emite JSONL
  findatachile_uploader.py       Subida (lista, desactivada por ahora)
```

La GUI y CMF_EXTRACT viven en intérpretes distintos y se comunican por un
protocolo de líneas JSON sobre stdout (los logs de las librerías van a stderr y
se muestran en el panel de log).
