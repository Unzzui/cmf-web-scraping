# Ingesta de estados financieros de EEUU (SEC EDGAR)

> Spec de lo que necesita `FinDataChile` de este repo. Escrito 2026-07-16.
> Contraparte: `~/Proyectos/FinDataChile/docs/us-expansion-blueprint.md`.
>
> **Estado: implementado en `src/edgar/` (2026-07-17), sin cargar a producción.**
> Las decisiones que el spec dejaba abiertas están tomadas y documentadas en §10.
> El CÓMO vive en `src/edgar/`; el CLI es `scripts/ingest_edgar.py` (dry-run por defecto).

---

## 1) Por qué este repo y no el otro

`FinDataChile` es la web y la BD; este repo es el pipeline de datos. Esa división ya
existe: `companies` y `financial_*` las escribe **este** repo (vía
`scripts/upload_to_supabase.py`) y la web sólo las consume.

La ingesta de EEUU es exactamente el mismo trabajo que ya hace `src/xbrl/` para la
CMF —bajar XBRL, normalizar, subir— sobre otra fuente. Ponerla en la web significaría
tener dos pipelines de datos en dos repos. Va acá.

**Lo que NO entra en este spec:** los precios de las acciones de EEUU. Ya están
resueltos y viven en la web (Marketstack, `lib/market-data/providers/marketstack.ts`,
cron `/api/cron/us-eod`). Este repo no toca precios.

---

## 2) Qué hay que traer

Estados financieros de empresas de EEUU desde **SEC EDGAR**, normalizados al mismo
modelo que ya usan las chilenas, para que la web los renderice con los componentes
que ya existen y el motor de ratios los calcule sin saber de qué país vienen.

### La fuente

| Recurso | URL |
|---|---|
| Facts XBRL por empresa | `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json` |
| Un concepto puntual | `https://data.sec.gov/api/xbrl/companyconcept/CIK##########/us-gaap/{tag}.json` |
| Metadata de filings | `https://data.sec.gov/submissions/CIK##########.json` |
| Bulk (todas las empresas) | `https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip` (~1 GB, se recompila cada noche ~3am ET) |
| Mapeo ticker → CIK | `https://www.sec.gov/files/company_tickers.json` |

**Sin API key.** Requisitos operativos:

- **Header `User-Agent` obligatorio** con nombre y contacto real, ej.
  `FindataChile contacto@findatachile.com`. Sin él, la SEC responde 403.
- **Límite: 10 requests/segundo** por IP. Excederlo bloquea temporalmente. Reutilizar
  el patrón de `src/xbrl/http_throttle.py`.
- Latencia de publicación: *"the xbrl APIs are updated with a typical processing delay
  of under a minute"* tras el filing.

### Licencia — no hay restricción

Textual de sec.gov: *"Information presented on sec.gov is considered public
information and may be copied or further distributed by users of the web site without
the SEC's permission."* Atribución sugerida, no exigida. Sin límite de uso comercial.

Única restricción: **marcaria**. No usar "SEC" ni "EDGAR" como marca del producto.

Esto contrasta con los proveedores comerciales (FMP, Twelve Data), cuyos free tiers
prohíben por contrato mostrar datos a terceros. Por eso los fundamentales van por
EDGAR y no por una API de pago.

---

## 3) La identidad ya está resuelta: usar el CIK

**No hay que descubrir nada.** Las 49 empresas ya están sembradas en `companies` con
su CIK cargado desde el archivo oficial de la SEC:

```sql
SELECT id, ticker, cik, razon_social FROM companies WHERE market = 'US';
-- 523 | AAPL | 0000320193 | Apple Inc.
```

- `companies.market = 'US'` discrimina el universo. **Filtrar siempre por acá**: una
  query sin ese filtro mezcla emisores chilenos y gringos.
- `companies.cik` es TEXT con **10 dígitos y ceros a la izquierda** (`0000320193`),
  que es el formato que quiere la API de EDGAR. No es un entero.
- `companies.rut` es **NULL** para las gringas (Apple no tiene RUT). El
  `CHECK companies_rut_required_cl` sólo lo exige para `market='CL'`.
- Hay un índice único parcial sobre `cik`.

Si hay que sembrar más empresas, el script es
`FinDataChile/scripts/seed-us-companies.mjs --apply --tickers=...` — resuelve CIK y
razón social desde la SEC. **No inventar filas en `companies` desde este repo sin
coordinar**, porque el ticker tiene un UNIQUE global (ver §7).

---

## 4) Esquema destino (existente — no hay que crear tablas)

Las mismas dos tablas que usan las chilenas. Son un **EAV genérico**: no tienen nada
de CMF ni de IFRS en las columnas, la atadura estaba sólo en el pipeline que las
llenaba.

```sql
financial_line_items (
  id            SERIAL PRIMARY KEY,
  company_id    INTEGER NOT NULL,   -- FK companies, CASCADE
  label         TEXT    NOT NULL,   -- nombre de la línea, como se muestra
  role_code     TEXT    NOT NULL,   -- código del estado (ver abajo)
  category      TEXT,               -- balance_sheet | income_statement | cash_flow | miscellaneous
  subcategory   TEXT,
  display_order INTEGER NOT NULL,   -- orden de presentación
  is_active     BOOLEAN DEFAULT true,
  UNIQUE (company_id, display_order)
)

financial_data (
  id             SERIAL PRIMARY KEY,
  company_id     INTEGER NOT NULL,
  line_item_id   INTEGER NOT NULL,   -- FK financial_line_items
  period_year    INTEGER NOT NULL,
  period_quarter INTEGER,
  value          NUMERIC,
  currency       VARCHAR DEFAULT 'CLP',
  UNIQUE (company_id, line_item_id, period_year, period_quarter)
)
```

**Las line items son POR EMPRESA**, no un catálogo global. Cada empresa tiene su
propio set con su propio `display_order`. Es así porque la presentación de la CMF
varía por empresa; para EEUU aplica igual (cada emisor usa su subconjunto de us-gaap).

### La escala: `financial_data` guarda la plata EN MILES

No está declarado en el esquema y no lo dice ninguna columna, pero es la convención real
y hay que respetarla: **EDGAR publica en unidades y esta tabla guarda en miles.**

| Evidencia | Guardado | Real |
|---|---|---|
| Falabella, ingresos 2024 | `10.322.104.478` | ~10,3 **billones** de pesos |
| Enel Américas (chilena en USD), activos 2024 | `31.484.337` | ~US$31,5 **mil millones** |
| Cencosud, acciones emitidas | `2.805.870.127` | 2.805.870.127 (unidades reales) |

La tercera fila importa: **las acciones NO van en miles**. Y el motor de ratios lo
confirma en su propia fórmula — calcula el EPS como `(Neta * 1000) / TotalAcciones`, o
sea que asume plata en miles y acciones en unidades. Esa fórmula es el contrato.

**Cuidado con este error porque no lo agarra ninguna validación de §8.** Un ratio es plata
sobre plata, así que el factor 1000 se cancela: la cuadratura contable y la acumulación
pasan igual de verdes. Aparece sólo en el EPS (daba 6.200 en vez de 6,11) y en la UI,
mostrando US$365 billones de activos para Apple.

Implementado en `loader.escalar_para_guardar()`, que se apoya en `Concept.unit`
(`USD` -> /1000, `shares` -> tal cual, `USD/shares` -> tal cual).

### `currency`: poner `'USD'` explícito

El default de la columna es `'CLP'` por herencia. **Hay que pasar `'USD'` siempre**, o
los estados de Apple quedan etiquetados en pesos chilenos.

No es un caso nuevo: ya hay **182.062 filas en USD** de empresas chilenas que reportan
en dólares. El modelo es multi-moneda y funciona.

### `category` y `role_code`

`category` tiene 4 valores en uso, y hay que respetarlos porque la web ramifica sobre
ellos: `balance_sheet`, `income_statement`, `cash_flow`, `miscellaneous`.

`role_code` hoy lleva los códigos de rol de la taxonomía de la CMF (`210000` balance,
`310000`/`320000` resultados, `510000` flujo, `000000` misceláneos).

> Corrección (2026-07-17): la primera versión de este párrafo decía "`510000`
> resultados, `310000`/`320000` flujo". Está al revés. Verificado contra la BD:
> `510000` cuelga "Intereses pagados" y "Otras entradas (salidas) de efectivo" y está
> mapeado a `cash_flow`; `310000`/`320000` cuelgan "Ganancia (pérdida)" y están mapeados
> a `income_statement`. Coincide con la taxonomía IFRS real (510000 = estado de flujos
> de efectivo). El dato de la BD manda.

**Para EEUU hay que definir una convención propia y documentarla acá.** Propuesta: usar
un prefijo distinguible (ej. `US-BS`, `US-IS`, `US-CF`) en vez de reciclar los números de
la CMF, que significan otra cosa. Decidir antes de cargar: cambiarlo después obliga a
reprocesar. **Decidido: se adoptó la propuesta. Ver §10.**

---

## 5) LA CONVENCIÓN QUE MÁS IMPORTA: los flujos van ACUMULADOS (YTD)

Si de este documento se lee una sola sección, que sea esta.

**En `financial_data`, `period_quarter` va de 1 a 4 y los flujos son acumulados desde
el inicio del año fiscal.** No es el trimestre suelto. Verificado sobre datos reales:

```
Falabella, "Ingresos de actividades ordinarias", 2024:
  period_quarter = 1  ->   2.392.525.649    (3 meses)
  period_quarter = 2  ->   4.837.813.810    (6 meses acumulados)
  period_quarter = 3  ->   7.240.767.681    (9 meses acumulados)
  period_quarter = 4  ->  10.322.104.478    (12 meses = AÑO COMPLETO)
```

Consecuencias, las tres:

1. **`period_quarter = 4` ES el dato anual.** No existe `period_quarter = 0` en esta
   tabla. (El `quarter=0 = anual` que menciona el `CLAUDE.md` de la web es de
   `product_versions`, otra tabla, otro dominio. No confundir.)
2. **El balance NO se acumula**: es un stock a una fecha, no un flujo. `period_quarter
   = 2` del balance es la foto al cierre del Q2, no una suma.
3. **Un 10-Q publica AMBAS duraciones.** El 10-Q del Q3 de Apple trae "three months
   ended" y "nine months ended" para cada línea de resultados. **Hay que tomar la
   acumulada (nine months).** Tomar la de tres meses es el error más fácil de cometer
   y el más difícil de ver: no falla nada, no hay excepción, simplemente los estados
   de EEUU quedan discretos mientras los chilenos son acumulados, y todo ratio o
   comparación entre mercados da mal en silencio.

Mapeo, entonces:

| Filing | `fp` en EDGAR | Duración a tomar | `period_quarter` |
|---|---|---|---|
| 10-Q | `Q1` | 3 meses (= YTD) | 1 |
| 10-Q | `Q2` | **6 meses** | 2 |
| 10-Q | `Q3` | **9 meses** | 3 |
| 10-K | `FY` | 12 meses | **4** |

**No hay que derivar el Q4.** El 10-K da el año completo y eso es `period_quarter=4`.
(La tentación de calcular "Q4 = FY − Q1 − Q2 − Q3" surge sólo si uno asume trimestres
discretos, que no es el caso acá.)

---

## 6) Gotchas de EDGAR

Los que van a morder. Cada uno es una decisión que hay que tomar explícitamente.

### 6.1 El mismo hecho aparece en varios filings
Un concepto de un período dado se repite en el 10-K original, en los 10-Q siguientes
como comparativo, y en las enmiendas. `companyfacts` los devuelve **todos**, cada uno
con su `accn` (número de accession), `filed` y `form`.

Hay que **deduplicar**. Criterio sugerido: quedarse con el `filed` más reciente para
cada `(tag, period, form-type)` — así una reexpresión pisa al original, que es lo que
uno quiere ver. Documentar la decisión, porque cambia los números.

### 6.2 `instant` vs `duration`
Los hechos de balance tienen sólo `end` (instant). Los de resultados y flujo tienen
`start` y `end` (duration). Es lo que permite distinguir un stock de un flujo, y lo
que hay que mirar para aplicar §5.

### 6.3 Año fiscal ≠ año calendario
El FY2024 de Apple **cierra el 28 de septiembre de 2024**. Los datos chilenos son
calendario (la CMF cierra al 31 de diciembre).

Decisión a tomar y documentar: ¿`period_year` es el año fiscal (`fy` de EDGAR) o el
calendario? Recomendación: **el fiscal**, que es como la empresa reporta y como lo
muestran todas las fuentes financieras. Pero implica que "2024" cubre ventanas
distintas según la empresa, y la UI debería decir la fecha de cierre.

### 6.4 `fy`/`fp` no siempre son lo que parecen
En los facts, `fy` y `fp` identifican **el filing donde apareció el hecho**, no el
período del hecho. Un 10-K FY2024 contiene comparativos de 2023 y 2022 con `fy=2024`.
**Hay que derivar el período de `start`/`end`, no de `fy`/`fp`.** Este es el error
clásico del que se arrepiente todo el que ingesta EDGAR.

### 6.5 Enmiendas
`10-K/A` y `10-Q/A` son correcciones. El filtro de `form` debe incluirlas y el criterio
de dedupe (§6.1) resolver cuál gana.

### 6.6 Empresas que no son `us-gaap`
Los foreign private issuers presentan 20-F/40-F y pueden usar la taxonomía `ifrs-full`
en vez de `us-gaap`. En el universo actual (49 mega caps) no debería aparecer, pero al
escalar sí. Detectar y decidir: soportar o excluir.

### 6.7 Cobertura temporal
XBRL es obligatorio por fases: grandes emisores desde jun-2009, el resto desde
jun-2011. Antes de eso no hay datos estructurados. **Los precios llegan a 2016**
(límite del plan de Marketstack), así que ~2011 de fundamentales es más que suficiente
y no vale la pena pelear por los años anteriores.

---

## 7) Reglas de este repo que aplican

Del `CLAUDE.md` de acá, y valen igual:

- **Supabase es PRODUCCIÓN.** Default `--supabase-dry-run`. No pasar `--supabase-live`
  sin que Diego lo pida.
- **Idempotente y con `--dry-run`.** El upsert nunca purga.
- Commits y comentarios **en español**, formato `tipo(scope): descripción`.
- Actualizar el ADR (`manage_adr(mode="update")`) con las decisiones que se tomen acá:
  el criterio de dedupe, la convención de `role_code`, fiscal vs calendario.

Y dos de la web:

- **`uq_companies_ticker` es UNIQUE GLOBAL sobre `ticker`**, no por mercado. Hoy no hay
  colisión (se verificaron los 120 tickers chilenos contra los 49 gringos), pero al
  escalar a 500 puede aparecer un ticker repetido entre Santiago y Nueva York. Si pasa,
  hay que coordinar el cambio de la constraint — no forzar un sufijo por las malas.
- **Nunca `Number(x)`/`float(x)` a secas sobre el payload externo.** Ya nos costó: el
  cargador de precios convirtió `close: null` en un precio de `0` (en JS `Number(null)`
  es `0`, no `NaN`) y metió 149 barras corruptas que sólo se vieron porque el mínimo
  anual de AAPL daba cero. En Python el equivalente es tratar `None` y `""` antes de
  convertir, y **rechazar valores imposibles explícitamente**. Un dato faltante debe
  quedar como hueco, no como cero.

---

## 8) Criterios de aceptación

Antes de dar la ingesta por buena:

1. **Cuadratura contable.** Para una muestra de empresas y períodos:
   `Activos = Pasivos + Patrimonio`. Si no cuadra, el mapeo de tags está mal.
2. **Acumulación (§5).** Verificar sobre una empresa que
   `valor(Q1) < valor(Q2) < valor(Q3) < valor(Q4)` en una línea de ingresos, y que
   `Q4` coincida con el 10-K. Si Q2 ≈ Q1, se tomó la duración de 3 meses: está mal.
3. **Contraste externo.** Los ingresos FY de Apple contra su 10-K publicado. Un dato
   correcto en la BD que no corresponde a la realidad no sirve.
4. **Moneda.** `SELECT DISTINCT currency FROM financial_data fd JOIN companies c ON
   c.id=fd.company_id WHERE c.market='US'` debe dar sólo `USD`.
5. **Idempotencia.** Correr dos veces no duplica filas ni cambia valores.
6. **No contaminación.** Las 521 empresas chilenas y sus 843.378 filas de
   `financial_data` intactas (baseline medido 2026-07-16, con 0 filas US). Contar
   antes y después.
7. **Ratios.** `FinDataChile/scripts/ratio_calculator_postgresql.py` debe correr sobre
   una empresa US y producir ratios plausibles. Es el consumidor final y la prueba de
   que el EAV quedó bien.

---

## 9) Sugerencia de orden

1. **Una empresa, a mano.** Bajar `companyfacts` de Apple, mapear a mano 10-15 líneas
   por estado, cargar en dry-run, y mirar los números contra el 10-K. Acá se descubre
   si el modelo aguanta us-gaap — es la pregunta abierta de verdad, no el volumen.
2. **Decidir y documentar**: `role_code`, dedupe, fiscal vs calendario. En el ADR.
3. **Las 49.** Con `--dry-run` primero. Son 49 requests: la SEC no cobra ni limita por
   día, sólo 10/s.
4. **Ratios y validación** (§8).
5. **Escalar** al S&P 500. Acá conviene el bulk `companyfacts.zip` en vez de 500
   requests.
6. **Incremental**: leer el feed de filings nuevos y procesar sólo lo que cambió. No
   re-bajar 500 empresas por día — son ~4 filings al año por empresa.

---

## 10) Decisiones tomadas (2026-07-17)

Las tres que el spec pedía decidir antes de cargar, más las que aparecieron al hacerlo.
Implementación en `src/edgar/`, validada contra las 49 en dry-run.

| Decisión | Resuelto | Dónde |
|---|---|---|
| `role_code` | `US-BS` / `US-IS` / `US-CF`. No se reciclan los números de la CMF. | `taxonomy.py` |
| Dedupe (§6.1) | Gana el `filed` más reciente; desempata el `accn` mayor. | `ingest.dedupe_facts` |
| Fiscal vs calendario (§6.3) | **Fiscal.** `period_year` = año calendario del CIERRE del ejercicio. | `ingest.build_fiscal_calendar` |
| Idioma del label | **Español**, reusando el string exacto de las chilenas. | `taxonomy.py` |
| Origen de la línea | `source_tag` + `source_label`, columnas nuevas. | `migrations/011` (repo web) |

### El label va en español a propósito

`ratio_calculator_postgresql.py` resuelve conceptos **matcheando texto de label en
español** (`"AT": ["Total de activos"]`). Usando esos mismos strings, el motor de ratios
toma las gringas sin que haya que tocarlo. Un label "arreglado" acá desconecta el ratio
en silencio; `tests/edgar/test_taxonomy.py` ata el contrato.

El tag us-gaap va en `source_tag` y **no en `subcategory`**: `subcategory` no está libre,
es un campo de presentación (`lib/excel-report.ts` lo usa como encabezado de grupo), y
meter ahí el tag pondría un encabezado sobre cada línea.

### Lo que la fuente obligó a corregir

- **La cadena de tags se resuelve por AÑO FISCAL**, no por empresa ni por trimestre.
  Por empresa: XOM migró de `RevenueFromContract...` a `Revenues` en 2022 y se quedaba
  sin ingresos desde ahí. Por trimestre: Mastercard tagea bruto y neto a la vez y la
  serie 2022 mezclaba ambos (el Q4 "bajaba" respecto del Q3).
- **La cuadratura (§8.1) se verifica dentro de cada filing (`accn`)**, no sobre la serie
  deduplicada. El dedupe toma cada hecho por separado, así que una reexpresión de
  `Assets` que no venga acompañada de un retagueo del total produce un descuadre falso
  (JPM 2013). Comparando dentro del filing, cuadra.
- **La ventana arranca en 2011** y el chequeo de cuadratura la respeta: el único
  descuadre real de las 49 es JPM al 2009-12-31, primer año del mandato XBRL.

### Lo que queda abierto

- **XOM no se puede cargar.** `companies.cik` apunta a `0002115436` (ExxonMobil Holdings
  Corp) — y coincide con el archivo oficial de la SEC, así que el seed no se equivocó.
  ExxonMobil está haciendo una reorganización con holding (julio 2026: `25-NSE` sobre la
  vieja, `S-8 POS` de la nueva) y el archivo de tickers ya apunta al holdco, que **no
  tiene historia XBRL** (su `companyfacts` sólo trae `ffd`). Los estados siguen bajo
  `0000034088`. Hay que corregir el CIK — es la tabla `companies`, así que se coordina.
  Va a volver a pasar con cada fusión o reorganización.
- **GE 2022 tiene la serie de ingresos inconsistente** y el validador la marca. No es un
  bug: GE reexpresó el ejercicio por los spin-offs de HealthCare y Vernova pero nunca
  reexpresó los YTD trimestrales, así que Q3 (41.272) > Q4 (29.139). Es la regla del
  §6.1 mezclando perímetros de reexpresión, y no se arregla eligiendo mejor el tag.
- **Los ratios de la web para las gringas.** Los labels ya están puestos para que el
  motor los resuelva, pero no se corrió. El Excel de producto tampoco: la ruta de
  `analisis_excel` no sirve (mapea conceptos por label chileno y lee de los CSV de
  Arelle, que para EDGAR no existen); el molde bueno es `src/banks/excel.py`, que arma el
  libro desde la BD con fórmulas vivas.
