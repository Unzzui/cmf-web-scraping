# Ingesta de bancos vía API oficial CMF → base de datos

Fecha: 2026-07-15
Estado: aprobado (diseño), pendiente plan de implementación

## Contexto

El pipeline actual toma XBRL de empresas chilenas y produce estados financieros, ratios y
DCF que carga a Supabase. Los **bancos no presentan ese XBRL**: reportan a la CMF bajo el
Compendio de Normas Contables para Bancos. Por eso existe un scraper HTML aparte
(`src/scrapers/cmf_bank_scraper.py`) que baja CSV desde `datosbanco.cmfchile.cl`.

Ahora tenemos acceso a la **API oficial de Bancos de la CMF** (`api.cmfchile.cl`), que entrega
la misma información en JSON limpio y estable. Este proyecto reemplaza el scraping HTML por
ingesta vía API y carga la data de bancos a la base, en tablas propias.

La API key vive en `.env` como `CMF_API_KEY` (ya agregada; el `.env` no se versiona).

## Objetivo de esta fase

Ingerir data de bancos desde la API oficial y cargarla a la base en tablas dedicadas.

**Dentro de alcance:**
- Cliente de la API y capa de ingesta que reemplaza al scraper HTML.
- Seis recursos por-banco: `balances`, `resultados`, `adecuacion` (componentes + indicadores),
  `perfil`, `accionistas`, `integrantes`.
- Tablas nuevas `bank_*` y log de corridas.
- Historia completa (2010+) con marca de época del plan de cuentas.
- Granularidad mensual (nativa del banco).

**Fuera de alcance (fases posteriores):**
- Excel producto estilo `Product_v1`.
- Ratios / DCF bancarios.
- Publicación a la tienda FinDataChile.
- Indicadores macro de la API (UF, UTM, Dólar, Euro, IPC, TMC, TIP, TAB): descartados; el
  foco es 100% data por-banco.

## La API

Base: `https://api.cmfchile.cl/api-sbifv3/recursos_api`. Todos los recursos aceptan
`?apikey=<CMF_API_KEY>&formato=json`. "Sin datos" se devuelve en el body como
`{"CodigoHTTP":404,"CodigoError":80,"Mensaje":"No hay datos disponibles..."}`, no como error
de transporte.

Recursos usados (verificados con llamadas reales):

| Recurso | URL (una institución, un período) | Forma |
|---|---|---|
| Balance | `/balances/<anho>/<mes>/instituciones/<cod>` | filas: cuenta + 5 columnas de moneda |
| Resultados | `/resultados/<anho>/<mes>/instituciones/<cod>` | filas: cuenta + monedas (menos columnas) |
| Adecuación componentes | `/adecuacion/anhos/<anho>/meses/<mes>/instituciones/<cod>/componentes` | árbol anidado |
| Adecuación indicadores | `/adecuacion/anhos/<anho>/meses/<mes>/instituciones/<cod>/indicadores/<ind>` | valor por indicador (irs, ire, capbas) |
| Perfil | `/perfil/instituciones/<cod>/<anho>/<mes>` | ficha institucional |
| Accionistas | `/accionistas/instituciones/<cod>/anhos/<anho>/meses/<mes>/ficha` | lista de accionistas |
| Integrantes | `/integrantes/instituciones/<cod>/anhos/<anho>/meses/<mes>` | ejecutivos clave |

Catálogo de instituciones: `/balances/<anho>/<mes>/instituciones` (lista los códigos vigentes
en ese período). Códigos: `001` Banco de Chile, `009` Internacional, `012` Estado, etc. El
código `999` es "SISTEMA FINANCIERO" (agregado).

### Campos de balances / resultados

`CodigoCuenta`, `DescripcionCuenta`, `CodigoInstitucion`, `NombreInstitucion`, `Anho`, `Mes`,
`MonedaChilenaNoReajustable`, `MonedaReajustablePorIPC`, `MonedaReajustablePorTipoDeCambio`,
`MonedaExtranjera`, `MonedaTotal`. Resultados trae menos columnas de moneda (típicamente solo
`MonedaChilenaNoReajustable` y `MonedaTotal`).

Los valores vienen como string con formato español: `"59878091792,00"`, `"40.844,79"`
(punto de miles, coma decimal). Requiere parser dedicado.

### Quiebres históricos

- **Plan de cuentas**: cambió con el nuevo Compendio en **enero 2022**. Antes los códigos son
  cortos (`1000000` = ACTIVOS, descripciones en mayúsculas); desde 2022 son de 9 dígitos con
  otra jerarquía. Se marca cada fila con `taxonomy_epoch` ∈ {`pre_2022`, `compendio_2022`}.
- **Unidad**: la época vieja parece venir en millones de pesos (MM$) y la nueva en pesos ($).
  Se marca con `unit` ∈ {`MMCLP`, `CLP`}. No se convierte: se guarda tal cual con su marca.
- **Adecuación**: `componentes` responde para períodos viejos (ej. 2018) pero da 404 en
  recientes (ej. 2024/12) — la cobertura Basilea III es irregular. Se tolera como hueco, no
  como fallo.

## Arquitectura del módulo

Paquete nuevo `src/banks/`. El scraper HTML (`src/scrapers/cmf_bank_scraper.py`) queda intacto
como fallback y no se toca.

- `api_client.py` — cliente HTTP fino. Inyecta `CMF_API_KEY` y `formato=json`, reintentos con
  backoff, rate-limiting suave (pausa entre llamadas), y distingue "sin datos"
  (`CodigoError 80`) de errores reales. Expone el parser de números español.
- `endpoints.py` — constructores de URL para los seis recursos y el catálogo de instituciones.
- `taxonomy.py` — clasifica `taxonomy_epoch` y `unit` según el período.
- `models.py` — dataclasses de las filas parseadas (una por recurso).
- `ingest.py` — orquesta por banco / período / recurso; normaliza a las dataclasses.
- `loader.py` — upsert a las tablas `bank_*` vía psycopg2. Reusa `load_env_file` y
  `resolve_pg_conn` de `src/gui/pipeline/supabase_uploader.py`.
- CLI `scripts/ingest_banks.py` — flags `--banks`, `--from MM/YYYY`, `--to MM/YYYY`,
  `--reports`, `--dry-run`, `--only <cod>`. Mismo estilo que `run_pipeline_cli.py`.

## Esquema de base de datos

DDL idempotente (`CREATE TABLE IF NOT EXISTS`) en `sql/bank_schema.sql`. Todas las tablas con
prefijo `bank_`. Ningún cambio a tablas existentes: la data XBRL de los 3 bancos que ya están
en `companies` (Banco de Chile, BCI, Banco Falabella) no se toca. La relación con `companies`
queda como columna `rut` en `bank_institutions`, sin FK dura.

```sql
CREATE TABLE IF NOT EXISTS bank_institutions (
  codigo_institucion  text PRIMARY KEY,
  nombre_institucion  text NOT NULL,
  rut                 text,
  codigo_swift        text,
  is_aggregate        boolean NOT NULL DEFAULT false,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

-- Plan de cuentas (dimensión). Un código puede tener descripción distinta por época.
CREATE TABLE IF NOT EXISTS bank_accounts (
  id                  bigserial PRIMARY KEY,
  statement           text NOT NULL,          -- 'balance' | 'resultado'
  codigo_cuenta       text NOT NULL,
  descripcion_cuenta  text NOT NULL,
  taxonomy_epoch      text NOT NULL,          -- 'pre_2022' | 'compendio_2022'
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (statement, codigo_cuenta, taxonomy_epoch)
);

-- Hecho mensual, multi-moneda.
CREATE TABLE IF NOT EXISTS bank_financial_data (
  id                       bigserial PRIMARY KEY,
  codigo_institucion       text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  account_id               bigint NOT NULL REFERENCES bank_accounts(id),
  period_year              int NOT NULL,
  period_month             int NOT NULL,
  moneda_no_reajustable    numeric,
  moneda_reajustable_ipc   numeric,
  moneda_reajustable_tc    numeric,
  moneda_extranjera        numeric,
  moneda_total             numeric,
  taxonomy_epoch           text NOT NULL,
  unit                     text NOT NULL DEFAULT 'CLP',   -- 'CLP' | 'MMCLP'
  created_at               timestamptz NOT NULL DEFAULT now(),
  updated_at               timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, account_id, period_year, period_month)
);
CREATE INDEX IF NOT EXISTS ix_bank_fd_inst_period
  ON bank_financial_data (codigo_institucion, period_year, period_month);

-- Adecuación de capital: componentes (aplanados) + indicadores (IRS/IRE/capital básico)
-- fusionados en una fila por institución/período. raw preserva lo no modelado.
CREATE TABLE IF NOT EXISTS bank_capital_adequacy (
  id                        bigserial PRIMARY KEY,
  codigo_institucion        text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year               int NOT NULL,
  period_month              int NOT NULL,
  activos_ponderados_riesgo numeric,
  activos_totales           numeric,
  capital_basico            numeric,
  patrimonio_efectivo       numeric,
  provisiones_voluntarias   numeric,
  bonos_subordinados        numeric,
  interes_minoritario       numeric,
  indice_irs                numeric,   -- índice de solvencia
  indice_ire                numeric,
  raw                       jsonb,
  created_at                timestamptz NOT NULL DEFAULT now(),
  updated_at                timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month)
);

-- Ficha / perfil: snapshot mensual.
CREATE TABLE IF NOT EXISTS bank_profiles (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  codigo_swift        text,
  rut                 text,
  direccion           text,
  telefono            text,
  sitio_web           text,
  sucursales          int,
  oficinas            int,
  cajeros             int,
  empleados           int,
  emp_hombres_perm    int,
  emp_mujeres_perm    int,
  emp_hombres_ext     int,
  emp_mujeres_ext     int,
  fecha_publicacion   date,
  raw                 jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month)
);

CREATE TABLE IF NOT EXISTS bank_shareholders (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  serie               text,
  rut                 text,
  nombre              text,
  participacion       numeric,
  numero_acciones     numeric,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month, rut, serie)
);

CREATE TABLE IF NOT EXISTS bank_executives (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text NOT NULL REFERENCES bank_institutions(codigo_institucion),
  period_year         int NOT NULL,
  period_month        int NOT NULL,
  nombre              text NOT NULL,
  cargo               text,
  fecha_asuncion      date,
  tipo                text,
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (codigo_institucion, period_year, period_month, nombre, cargo)
);

-- Log de corridas. Un renglón por (institución, recurso, período) intentado.
CREATE TABLE IF NOT EXISTS bank_data_imports (
  id                  bigserial PRIMARY KEY,
  codigo_institucion  text,
  report              text NOT NULL,   -- balance|resultado|adecuacion|perfil|accionistas|integrantes
  period_year         int,
  period_month        int,
  status              text NOT NULL,   -- running|completed|no_data|failed
  rows_total          int DEFAULT 0,
  rows_ok             int DEFAULT 0,
  rows_failed         int DEFAULT 0,
  message             text,
  started_at          timestamptz NOT NULL DEFAULT now(),
  finished_at         timestamptz
);
```

## Flujo de datos

1. Poblar `bank_institutions` desde el catálogo `/balances/<anho>/<mes>/instituciones`.
2. Por cada banco y período (mes) en el rango:
   - Bajar cada recurso pedido, parsear números ES, clasificar época/unidad.
   - Upsert de las cuentas nuevas a `bank_accounts`, luego de los hechos a
     `bank_financial_data` (y las demás tablas según recurso).
   - Registrar el resultado en `bank_data_imports`.
3. Re-correr un período no duplica: todo va con `ON CONFLICT (<clave única>) DO UPDATE`.

## Manejo de errores

- "Sin datos" (`CodigoError 80` / 404 en body) es estado normal: `status = no_data`, no aborta.
- Solo errores de transporte reales (5xx, timeout tras reintentos) cuentan como `failed`.
- La adecuación reciente que da 404 se registra como `no_data` y se sigue.
- `--dry-run` corre todo sin escribir a la base y muestra el resumen.

## Testing

- Fixtures JSON reales ya capturados de la API (balance, resultado, adecuación componentes,
  perfil, accionistas, integrantes; épocas 2009/2018/2025).
- Tests unitarios sin red: parser de números español, clasificación de época y unidad,
  normalización de filas por recurso, y el upsert contra una base/tabla temporal.

## Riesgos y notas

- **Volumen**: ~21 bancos x ~15 años x 12 meses x 6 recursos son muchas llamadas. La primera
  carga histórica es larga; el CLI debe permitir acotar por banco/rango y reanudar.
- **Cobertura irregular** de adecuación e instituciones que entran/salen del sistema en el
  tiempo (bancos que se fusionan o cierran). El catálogo por período lo maneja.
- **Unidades mixtas** (MM$ vs $) entre épocas: se preserva con marca, no se convierte en esta
  fase; cualquier consumidor debe respetar `unit`.
