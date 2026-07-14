# CMF Extract

Pipeline que toma los XBRL que las empresas chilenas presentan a la CMF y produce estados
financieros consolidados, análisis con ratios y DCF, y los carga a Supabase.

## Cómo funciona

El pipeline son cuatro fases. Cada una lee lo que dejó la anterior en disco, así que se
pueden correr por separado y reanudar donde se cortó.

| Fase | Qué hace | Entrada → Salida |
|---|---|---|
| 1. Consolidación | Arelle lee cada XBRL y exporta los hechos y el árbol de presentación | `data/XBRL/Total/<empresa>/` → `out_consolidated_*/` |
| 2. Excel primario | Arma balance, estado de resultados y flujo de efectivo | CSV consolidado → `estados_*_from_primary.xlsx` |
| 3. Análisis | Agrega ratios, KPIs y DCF con fórmulas trazables | Excel primario → `Product_v1/Total/` |
| 4. Export a SQL | Aplana los Excel a CSV para la base | `Product_v1/Total/` → `Product_v1/Total/TO_SQL/` |

## La estructura de las cuentas sale del XBRL, no de una lista

Cada empresa declara en su XBRL un *linkbase de presentación*: qué cuentas tiene, en qué
orden y con qué jerarquía. `cmf_extract/presentation_order.py` lo lee y **fusiona todos los
períodos** de la empresa.

Fusionar importa: QUIÑENCO consolidaba Banco de Chile hasta 2021, y esas cuentas bancarias
tienen 35 períodos con cifras reales pero desaparecen de la presentación en 2022. Leer solo
el período más reciente las borraría del histórico.

De ahí sale también si el estado de resultados va por función (rol 310000) o por naturaleza
(320000): lo dice la empresa, no lo adivina el pipeline.

## Uso

```bash
./setup.sh                          # instala dependencias y clona Arelle en tools/

# Todo: pipeline completo + carga a Supabase + ratios + DCF
scripts/regenerate_all.sh

# Una empresa
scripts/regenerate_all.sh --only 61808000-5

# Sin tocar la base (corre el pipeline y muestra el diff)
scripts/regenerate_all.sh --dry-run

# Interfaz gráfica
python run_pipeline_gui.py
```

## Taxonomías (no van en el repo: hay que bajarlas)

La CMF publica una taxonomía **por año y por tipo de emisor**: `cl-ci` (comercial e
industrial), `cl-hb` (holding bancario), `cl-bs`, `cl-cc`, `cl-hs`, `cl-ei`. Cada XBRL declara
contra cuál se validó, y una empresa cambia de versión con los años.

Son ~180 MB en 5.940 archivos, así que **no se versionan**: son un insumo que se descarga del
sitio de la CMF, no código. Hay que dejarlas en `docs/taxonomias_cmf/`, una carpeta por
familia y versión:

```
docs/taxonomias_cmf/
  cl-ci/CMF_CLCI_2014 ... CMF_CLCI_2026      (16 versiones)
  cl-hb/CMF_CLHB_2014 ... CMF_CLHB_2026      (13)
  cl-cc/  cl-bs/  cl-hs/  cl-ei/
```

Después:

```bash
python scripts/build_taxonomy_catalogs.py
```

Eso les genera el `META-INF/catalog.xml` que Arelle necesita para resolverlas **sin salir a
internet** — y eso importa: cmfchile.cl responde 403 y hace throttling, y cuando una taxonomía
no resuelve, Arelle **no falla**. Exporta cero hechos y termina con exit 0. El hueco aparece
recién en el Excel.

Los catálogos declaran también `www.svs.cl`, el organismo anterior a la CMF, al que apuntan
los XBRL previos a 2018. El catálogo oficial de la CMF sólo declara `cmfchile.cl`, así que por
sí solo no resuelve nada anterior a esa fecha.

## Tipo de cambio

`cmf_extract/public/DOLAR_OBS_ADO.xlsx` es la serie diaria del dólar observado del Banco
Central (serie `F073.TCO.PRE.Z.D`). Sí va en el repo: pesa 272 KB y el pipeline no funciona
sin ella para las 8 empresas que cambiaron de moneda de presentación a mitad de su historia.

La regla de conversión (NIC 21) está verificada contra las reexpresiones que publicaron esas
mismas empresas: **flujos al tipo de cambio promedio del período, stocks al de cierre**. Ver
`cmf_extract/fx.py` y `cmf_extract/tests/test_fx.py`.

## Estructura

```
cmf_extract/          Motor del pipeline (las 4 fases viven en cmf/pipeline/)
src/                  GUI, scraping y descarga desde el sitio de la CMF
scripts/              Entrypoints: regenerate_all.sh, upload_to_supabase.py
tests/                Tests del scraper
docs/                 Arquitectura, metodología y taxonomías CMF
data/                 XBRL descargados (no versionado)
tools/Arelle/         Procesador XBRL (se clona con setup.sh, no versionado)
```

## Tests

```bash
pytest                                  # todo
pytest -m "not validation"              # sin los que exigen Excel ya generados
```
