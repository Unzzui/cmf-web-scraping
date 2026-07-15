# Generador de Excel de análisis bancario

Fecha: 2026-07-15
Estado: aprobado (diseño), pendiente plan de implementación

## Contexto

El pipeline de empresas IFRS produce un Excel `Product_v1` por empresa: estados financieros
(Balance, Estado de Resultados, Flujo), una hoja **RATIOS & KPIs** con fórmulas Excel vivas
que referencian las celdas de los estados, un **DCF (FCFF)**, y hojas de portada, ficha y
metodología. Todo el estilo visual sale de una fuente única, `cmf_extract/excel_style.py`.

Los bancos quedan fuera de ese pipeline (reportan bajo el plan de cuentas de la CMF, no XBRL
IFRS). Ya tenemos su data en la base, en tablas `bank_*` (ver
[ingesta de bancos](2026-07-15-ingesta-bancos-api-cmf-design.md)). Falta el equivalente de
`Product_v1` para bancos: un Excel de análisis con **el mismo formato y estilo**, pero con los
estados, ratios y valuación propios de un banco.

Este proyecto construye ese generador.

## Objetivo de esta fase

Generar, por institución bancaria, un Excel de análisis con el look de `Product_v1`,
leyendo de las tablas `bank_*`.

**Dentro de alcance:**
- Módulo `cmf_extract/analisis_bancos/` + CLI `scripts/generate_bank_excel.py`.
- Lee de la base (`bank_financial_data`, `bank_capital_adequacy`, `bank_profiles`,
  `bank_accounts`, `bank_institutions`).
- Cobertura **2022+** (`taxonomy_epoch = 'compendio_2022'`), columnas **mensuales**.
- Hojas: Inicio, Estado de Situación, Estado de Resultados, Adecuación de Capital,
  RATIOS & KPIs, Valuación, Ficha Técnica, Metodología.
- Ratios bancarios como **fórmulas Excel vivas** (trazables), no valores pegados.
- Valuación bancaria por **exceso de retorno / P-B garantizado (residual income)**.
- **Solo ES**.
- Reutiliza `cmf_extract/excel_style.py` sin modificar.

**Fuera de alcance (fases posteriores):**
- Variante EN.
- Publicación a la tienda (`product_versions`).
- Historia pre-2022 (plan de cuentas viejo, unidad MM$): requiere mapear cuentas viejas a
  nuevas; se difiere.
- Flujo de efectivo (la API de bancos no lo entrega).

## Fuente de datos y períodos

- Entrada: la base, no un Excel primario. Por institución se leen:
  - `bank_financial_data` join `bank_accounts` para los estados (statement `balance` y
    `resultado`), filtrando `taxonomy_epoch = 'compendio_2022'`.
  - `bank_capital_adequacy` para la hoja de capital (IRS/IRE/capital básico/APR).
  - `bank_profiles` (último período) para la Ficha Técnica.
  - `bank_institutions` para nombre/rut/swift.
- Valor del estado: la columna **`moneda_total`** (el desglose por 5 monedas queda disponible
  pero el estado principal va en Total, como un estado de una sola cifra por período).
- Períodos: **mensuales**, de 2022-01 al último mes disponible. Columnas en orden ascendente.

### Metodología (notas que van en la hoja Metodología)

- El **estado de resultados de bancos es acumulado del ejercicio (YTD)**: el valor de un mes es
  el acumulado enero→ese mes. Para ratios anualizados se anualiza: `valor_YTD / mes * 12`.
  (A verificar contra la data en implementación; si resultara mensual-flujo, se ajusta la
  fórmula de anualización.)
- Los saldos de balance son **instantáneos** (fin de mes).
- Los ratios de capital (IRS/IRE) son de fin de período y de cobertura irregular; los meses sin
  dato quedan en blanco, no en cero.

## Arquitectura

Módulo nuevo `cmf_extract/analisis_bancos/`, que espeja la estructura de `analisis_excel/`
pero con fuente BD y plan de cuentas bancario:

- `db_reader.py` — lee de las tablas `bank_*` y arma, por institución, las series por concepto
  y período (balance, resultado, capital, perfil). Devuelve estructuras en memoria.
- `concept_map.py` — **el mapa de conceptos bancarios**: cada concepto de análisis
  (`activos_total`, `patrimonio`, `colocaciones`, `depositos`, `ingresos_intereses`,
  `gastos_intereses`, `comisiones`, `gastos_apoyo`, `provisiones_gasto`, `cartera_vencida`,
  `resultado_ejercicio`, `apr`, …) se resuelve a uno o varios `codigo_cuenta` (a sumar). Es el
  equivalente de `row_mappers` para el plan bancario. Se **valida contra la data real** (los
  totales deben cuadrar: p.ej. suma de colocaciones ≤ total activos).
- `ratios.py` — define los ratios bancarios como **fórmulas Excel** que referencian las celdas
  de las hojas de estados (patrón de `formula_builder`: referencia por letra de columna + fila).
- `valuation.py` — construye la hoja de Valuación (exceso de retorno).
- `workbook.py` — arma el workbook: escribe las hojas de estados, ratios, capital, valuación,
  ficha, metodología y portada; aplica `excel_style` y los saneadores de tipografía/contraste.
- CLI `scripts/generate_bank_excel.py` — flags `--banks`/`--only` (códigos; vacío = todos los
  de `bank_institutions`), `--to MM/YYYY` (último período; default el más reciente en la base),
  `--out` (default `cmf_extract/Product_v1_Banks/Total/`).

Salida: `cmf_extract/Product_v1_Banks/Total/<Nombre> - <RUT> - Análisis Bancario <rango> [ES].xlsx`.

**Estilo:** importa `cmf_extract/excel_style.py` tal cual (tipografía Inter, paleta INK/EMBER,
formatos de número, bordes finos, `preparar_hoja`, `aplicar_tipografia_base`,
`verificar_contraste`). No se inventan colores ni fuentes nuevas.

## Hojas del workbook

Mismo esqueleto y orden que `Product_v1`:

1. **Inicio** — portada/dashboard (espeja `add_start_sheet`).
2. **Estado de Situación** — cuentas de `bank_accounts` (statement `balance`, epoch nuevo) en
   orden de código; una fila por cuenta, columnas por mes. Fila título + subtítulo unidad/período
   + cabecera, igual que los estados de empresas.
3. **Estado de Resultados** — statement `resultado`, YTD mensual.
4. **Adecuación de Capital** — IRS, IRE, capital básico, patrimonio efectivo, APR por período
   (de `bank_capital_adequacy`); meses sin dato en blanco.
5. **RATIOS & KPIs** — ratios bancarios (sección siguiente) como fórmulas vivas que referencian
   las hojas de estados y de capital. Columnas: Indicador | meses | Último | Promedio | Tendencia.
6. **Valuación** — modelo de exceso de retorno (sección siguiente).
7. **Ficha Técnica** — de `bank_profiles` (SWIFT, empleados, sucursales, oficinas, cajeros).
8. **Metodología** — notas de arriba + definición de cada ratio.

## Set de ratios bancarios

Reemplaza los ratios de empresas (liquidez corriente, inventarios, COGS, Altman, etc. no
aplican). Cada uno se escribe como fórmula Excel referenciando celdas de los estados.

- **Rentabilidad:** ROE (resultado anualizado / patrimonio), ROA (resultado anualizado /
  activos), **NIM** (margen de intereses anualizado / activos productivos), margen operacional.
- **Eficiencia:** índice de eficiencia (gastos de apoyo / ingreso operacional), gastos
  operacionales / activos.
- **Riesgo de crédito:** morosidad/NPL (cartera vencida / colocaciones), cobertura de provisiones
  (provisiones / cartera vencida), costo de riesgo (gasto en provisiones anualizado /
  colocaciones).
- **Estructura / liquidez:** colocaciones / depósitos (LDR), colocaciones / activos, depósitos /
  pasivos.
- **Capital (Basilea):** IRS (patrimonio efectivo / APR), IRE, capital básico / APR,
  apalancamiento (activos / patrimonio).
- **Crecimiento:** colocaciones, depósitos y resultado, variación YoY (mismo mes año anterior).

Anclas de cuentas ya verificadas en la data (compendio_2022): `100000000` TOTAL ACTIVOS,
`200000000` TOTAL PASIVOS, `300000000` PATRIMONIO (y `380000000` PATRIMONIO DE LOS PROPIETARIOS),
`411000000` INGRESOS POR INTERESES, `412000000` GASTOS POR INTERESES, `420000000` INGRESOS POR
COMISIONES. Las colocaciones y depósitos-de-clientes se componen de varias sub-cuentas; el
conjunto exacto por concepto lo fija y valida `concept_map.py` (tarea del plan).

## Valuación bancaria (exceso de retorno / P-B garantizado)

Modelo de **residual income**, elegido porque se arma con lo que ya tenemos (ROE, patrimonio
contable, costo de capital) y sirve incluso para bancos que no reparten dividendos ni cotizan.

- **Ke (costo de capital)** por CAPM: `Ke = Rf + beta * ERP`. Rf y ERP como constantes del
  módulo (mismos valores que usa el DCF de empresas). `beta` de `companies.yahoo_beta` para los
  bancos listados; para los no listados, una beta sectorial supuesta (constante configurable).
- **P/B garantizado** = `(ROE - g) / (Ke - g)`, con ROE sostenible (promedio reciente
  anualizado) y `g` supuesto (constante configurable, p.ej. crecimiento nominal de largo plazo).
- **Valor patrimonial intrínseco** = `P/B garantizado * patrimonio contable`.
- **Comparación con mercado (prima/descuento, recomendación) solo para bancos listados**
  (Banco de Chile, BCI, Santander, Itaú): usa `companies.yahoo_market_cap` / precio. Para los no
  listados (filiales), solo se muestra el valor intrínseco, sin comparación.
- Todas las celdas del modelo son fórmulas vivas (Rf, ERP, beta, g editables), como en el DCF.

## Aislamiento y reutilización

- **Reutiliza sin tocar:** `cmf_extract/excel_style.py`. Puede reutilizar helpers de
  `analisis_excel` (portada, ficha, metodología) si aplican sin modificarlos; si requieren cambios
  específicos de bancos, se hace una variante en `analisis_bancos/`, no se edita el módulo IFRS.
- **No toca** el pipeline IFRS ni las tablas existentes; solo lee `bank_*` y escribe archivos
  nuevos en `Product_v1_Banks/`.

## Testing

- Tests unitarios sin BD para `concept_map` (resolución concepto→códigos con fixtures) y para las
  fórmulas de ratios (que la cadena de fórmula generada sea la esperada).
- Test de `db_reader` contra la Supabase real con ROLLBACK (mismo patrón que la ingesta),
  usando la data ya cargada de un banco.
- Test de humo del generador: produce el .xlsx de un banco y verifica que las hojas esperadas
  existen, que `verificar_contraste` no reporta problemas, y que las fórmulas de ratios no dan
  `#REF!` (abrir con openpyxl `data_only=False` y chequear referencias).

## Riesgos

- **Mapeo de cuentas** (`concept_map`): es la parte con más trabajo y riesgo. El plan de cuentas
  bancario es granular (colocaciones por categoría de medición y tipo; depósitos de clientes en
  el pasivo). Se valida contra la data real (cuadres de totales) y es la primera tarea sustantiva.
- **YTD vs flujo** en el estado de resultados: la anualización depende de esto; se verifica con
  la data antes de fijar las fórmulas.
- **Cobertura de capital** irregular: la hoja de Adecuación tendrá huecos; es esperado.
- **Bancos no listados**: la mayoría de las ~21 instituciones son filiales sin precio de mercado;
  la valuación intrínseca aplica a todos, la comparación con mercado solo a los listados.
