# Roadmap: enriquecer el análisis XBRL + DCF (FCFF) profesional

> ESTADO DE IMPLEMENTACIÓN (actualizado):
> - ✅ WACC profesional en el DCF: bloque visible "WACC (CAPM + COSTO DE DEUDA REAL)"
>   con Ke=Rf+β·ERP, **Kd real = Costos financieros / Deuda financiera** (de los estados
>   XBRL), pesos D/E del balance, t=27%. El supuesto "WACC (%)" referencia ese cálculo.
>   Validado en SQM: Ke 11.0%, Kd 4.11%, WACC 8.05% (antes 10% fijo).
>   Código: `dcf_patch.py::create_wacc_terminal_block` (se llama tras el tornado).
> - ✅ Contraste de valor terminal: múltiplo de salida (EV/EBITDA), TV como % del EV y
>   alerta si el terminal > 75% del EV.
> - ✅ Formato chileno (coma) en TODOS los supuestos y en la hoja Escenarios; tasa de
>   impuesto fija 27% como número.
> - ⏳ Pendiente: filas RATIOS de deuda (Kd, % deuda <12m), normalización del terminal
>   (CapEx=D&A), convención de mitad de año, sensibilidad 2-vías WACC×g, 4º estado,
>   EPS/segmentos/biológicos.


> Documento de contexto para revisar e implementar. Reúne (A) qué datos del XBRL
> podemos agregar al producto —con foco en **deuda financiera, tasas y
> vencimientos**— y (B) cómo profesionalizar el modelo DCF (FCFF), incluyendo
> usar tasas REALES del XBRL para el WACC.
>
> Caso de referencia: SQM (RUT 93007000-9). Los `qname` son IFRS estándar y
> aplican a todas las empresas; los valores de ejemplo hay que validarlos por
> empresa/período (algunos derivados son aproximados y están marcados).

---

## Dónde se implementa (mapa de código)

- Extracción de facts → filas de RATIOS:
  `cmf_extract/analisis_excel/processor/formula_processor.py`
  - patrón ya usado: `_extract_shares` / `_extract_da` → `*_values_map` → se
    escribe por período en la hoja RATIOS. **Replicar ese patrón** para deuda/tasas.
  - `_xbrl_search_root()` resuelve la carpeta de facts vía `CMF_XBRL_BASE_DIR`
    (no usar rutas relativas al cwd).
- Modelo DCF:
  `cmf_extract/dcf_patch.py`
  - Tabla de supuestos: ~línea 935 (`inputs = [...]`).
  - Proyección FCFF (5 años): ~línea 1011.
  - Valuación / valor terminal: ~línea 1057 (`blocks = [...]`).
  - Hoja "Escenarios": ~línea 1340 (hoy usa un FCFF aproximado).
- Facts consolidados (wide por fecha, lo que leen los extractores):
  `data/XBRL/Total/<RUT>_<EMPRESA>/out_consolidated_<RUT>_<rango>/facts_<RUT>_<rango>_es.csv`

---

# PARTE A — Datos del XBRL para enriquecer el producto

## A1. Deuda financiera, tasas de interés y vencimientos  ⭐ PRIORIDAD

El XBRL trae el detalle de la deuda con **tasas reales por préstamo** y el
desglose del gasto financiero. Hoy el producto sólo usa una "Deuda neta" agregada.

### A1.1 Estructura de deuda (stocks) — qnames
```
ifrs-full:Borrowings                              Préstamos (total)
ifrs-full:ShorttermBorrowings                     Préstamos a corto plazo
ifrs-full:LongtermBorrowings                      Préstamos a largo plazo
ifrs-full:CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings
ifrs-full:OtherFinancialLiabilitiesCurrent        Otros pasivos financieros corrientes
ifrs-full:OtherFinancialLiabilitiesNoncurrent     ... no corrientes
ifrs-full:FinancialLiabilitiesAtAmortizedCost     Pasivos financieros a costo amortizado
```
Ejemplo SQM 2026-03-31: préstamos bancarios ~USD 534M (CP 240M + LP 294M),
bonos/obligaciones ~USD 4.549M → **los bonos son ~80% de la deuda** (clave: el
costo de deuda NO se puede aproximar sólo con tasas de préstamos bancarios).

### A1.2 Tasas de interés por préstamo — qnames / contextos
El XBRL detalla cada préstamo con tasa **nominal** y **efectiva** (tabla de
detalle de préstamos, contextos tipo `C8224a...Item###`):
```
TasaNominal / TasaEfectiva                         tasa por préstamo (Unit_pure, %)
Hasta90DiasPrestamosNominales
MasDe90DiasHasta1AñoPrestamosNominales
MasDe1AñoHasta3AñosPrestamosNominales
MasDe3AñosHasta5AñosPrestamosNominales
MontosNominalesPrestamos                            monto por tramo/préstamo
```
Ejemplo SQM (6 préstamos): nominal 3.62%–4.79%, efectiva 4.64%–4.82%.
**Promedio ponderado ~4.7% efectiva (préstamos)**. Bonos ~5.2% (ver A1.3).

> Nota: las tasas vienen como fracción/porcentaje con `Unit_pure`. Validar
> escala (0.0362 vs 3.62) al parsear.

### A1.3 Gasto financiero desglosado (flujos) — qnames
```
ifrs-full:InterestExpense                          Gasto por intereses (total)
ifrs-full:InterestExpenseOnBankLoansAndOverdrafts  ... préstamos bancarios
ifrs-full:InterestExpenseOnBonds                   ... bonos
ifrs-full:InterestExpenseOnBorrowings              ... otros préstamos
ifrs-full:InterestExpenseOnDebtInstrumentsIssued   ... instrumentos de deuda
ifrs-full:FinanceCosts                             Costos financieros (consolidado)
ifrs-full:InterestPaidClassifiedAsOperatingActivities    intereses pagados (caja)
ifrs-full:InterestReceivedClassifiedAsOperatingActivities
```
Permite calcular el **costo de deuda implícito real**:
```
Kd_bonos      = InterestExpenseOnBonds × (4 si es trimestral) / saldo_bonos
Kd_prestamos  = InterestExpenseOnBankLoansAndOverdrafts × 4 / (ST+LT Borrowings)
Kd_efectivo   = FinanceCosts(anualizado) / Deuda_financiera_total
```
Ejemplo SQM: Kd_bonos ≈ 5.2%, ponderado total ≈ 5.1%.
**Preferir la tasa efectiva del XBRL (A1.2) cuando exista; usar el implícito como
validación/fallback.** Cuidado con outliers trimestrales (one-offs de
refinanciamiento) — usar mediana/rango, no un solo trimestre.

### A1.4 Flujos de financiamiento y perfil de vencimientos
```
ifrs-full:ProceedsFromBorrowingsClassifiedAsFinancingActivities   nuevos préstamos
ifrs-full:RepaymentsOfBorrowingsClassifiedAsFinancingActivities   reembolsos
MaturityAnalysisForNonderivativeFinancialLiabilities (tramos <1, 1-3, 3-5, >5 años)
```
Uso: **perfil de vencimientos → riesgo de liquidez** (% de deuda < 12 meses) y
endeudamiento neto del período (proceeds − repayments).

### A1.5 Qué agregar al producto (A1)
1. Hoja nueva **"DEUDA Y FINANCIAMIENTO"**: estructura (CP/LP, bancos/bonos),
   tabla de préstamos con tasa nominal/efectiva, perfil de vencimientos, gasto
   de interés desglosado, intereses pagados.
2. Fila RATIOS **"Costo de deuda (Kd efectivo, %)"** por período (de A1.2/A1.3).
3. KPI **"% deuda < 12 meses"** (riesgo de liquidez) y **cobertura de intereses**
   (EBIT/Intereses) — ya hay EBIT.
4. Alimentar el **WACC del DCF** con Kd real (ver Parte B3).

---

## A2. Cuarto estado: Estado de Cambios en el Patrimonio  [610000]
Hoy faltan 4º estado completo. Aporta dividendos y resultado integral:
```
ifrs-full:Dividends / DividendsPaid                dividendos
ifrs-full:ComprehensiveIncome                      resultado integral
ifrs-full:OtherComprehensiveIncome                 ORI (conversión moneda, etc.)
ifrs-full:IssueOfEquity / ChangesInEquity
```
Valor: política de distribución (payout), y conciliación de patrimonio.

## A3. EPS y número de acciones  [838000 / 861200]  (parcial ✅)
Acciones ya se extraen (`NumberOfSharesIssued` → fila RATIOS). Falta:
```
ifrs-full:BasicEarningsLossPerShare                EPS básico
ifrs-full:DilutedEarningsPerShare                  EPS diluido
ifrs-full:NumberOfSharesOutstanding                acciones en circulación (vs emitidas)
```
Valor: base de P/E y del valor por acción del DCF (usar circulación, no tesorería).

## A4. Segmentos operativos  [871100]
```
ifrs-full:Revenue / ProfitLoss / Assets  por dimensión IdentificarSegmentoOperacion
```
Valor: ingresos/margen/activos por línea de negocio (hoy se colapsa a total).

## A5. Activos biológicos  [824180]  (crítico para agro, p.ej. Agrosuper)
```
ifrs-full:BiologicalAssets
ifrs-full:GainsLossesOnFairValueAdjustmentBiologicalAssets   (precio vs físico)
```
Valor: separa eficiencia operativa de volatilidad de commodities; no se ve en el
EE.RR. plano.

## A6. Otros desgloses de valor medio
- Arrendamientos IFRS-16 [832610] (`LeaseLiabilities`, current/noncurrent) → deuda real.
- Impuestos diferidos [835110] (`DeferredTaxLiabilityAsset`) → caja futura.
- Partes relacionadas [818000] → gobernanza.
- PP&E / CAPEX y depreciación [822100] → para FCF.
- Inversiones en subsidiarias [825700] → exposición de moneda.

---

# PARTE B — DCF (FCFF) profesional

## B1. Estado actual (lo que ya hace bien)
Proyección a 5 años en la hoja `DCF <período>`:
```
Ventas_k = Ventas_base × Π(1+g_i)
EBIT     = Ventas × Margen EBIT
NOPAT    = EBIT × (1 − tax)
D&A      = Ventas × (D&A/Ventas)
CapEx    = Ventas × (CapEx/Ventas)
ΔNWC     = ΔVentas × (ΔNWC/ΔVentas)
FCFF     = NOPAT + D&A − CapEx − ΔNWC            ✅ fórmula correcta
PV       = FCFF / (1+WACC)^k
TV       = FCFF_5 × (1+g)/(WACC − g)            (Gordon)
EV       = ΣPV(FCFF) + PV(TV)
Equity   = EV − Deuda neta;  Valor/acción = Equity/Acciones
```

## B2. Brechas y mejoras (a implementar)

| # | Brecha actual | Mejora profesional |
|---|---------------|--------------------|
| 1 | **WACC fijo (10%)**, input manual | Construir WACC = E/V·Ke + D/V·Kd·(1−t). Ke por **CAPM** (Rf + β·ERP). Kd **real del XBRL** (Parte A1). Pesos D/E del balance. |
| 2 | **Valor terminal con FCFF₅ sin normalizar** (CapEx≠D&A, ΔNWC no estacionario) → distorsiona perpetuidad | **Normalizar terminal**: CapEx = D&A, ΔNWC = g·NWC (o ΔNWC→0), EBIT margin normalizado. FCFF_normal = EBIT_n·(1−t). |
| 3 | Descuento **fin de año** | Opción **convención de mitad de año** (factor `(1+WACC)^(k−0.5)`). |
| 4 | Sólo Gordon para TV | Agregar **múltiplo de salida** (EV/EBITDA terminal) como contraste y mostrar **TV como % del EV** (alerta si > ~75%). |
| 5 | Sin sensibilidad estructurada | **Tabla 2-vías WACC × g** sobre valor/acción + **tornado** de drivers. |
| 6 | Hoja "Escenarios" usa **FCFF aproximado** (crecimiento promedio × factor terminal × descuento ~3 años) | Recalcular cada escenario con el **mismo motor multi-año** (bear/base/bull cambian g, margen, WACC). |
| 7 | **Tax fija 27%**, g fija 2% | Tax = **efectiva histórica** (ImpGanan/AntesImp, con piso/techo); g ≤ inflación/PIB largo plazo (configurable). |
| 8 | Sin chequeos de sanidad | Flags: **ROIC vs WACC**, crecimiento implícito, FCFF negativo, TV%EV, deuda/EBITDA. |
| 9 | Deuda neta como número único | Usar **deuda del XBRL** (A1) y, opcional, **WACC dinámico** por año si cambia la estructura. |

## B3. WACC con costo de deuda real (conecta A1 ↔ DCF)
```
Kd      = tasa efectiva ponderada del XBRL (A1.2/A1.3); fallback implícito FinanceCosts/Deuda
Ke      = Rf + β × ERP            (CAPM)
            Rf  = tasa libre de riesgo CLP (BCU/BTP 10a) — parámetro/config
            ERP = prima de mercado Chile (~5–6%) — parámetro
            β   = beta sectorial o configurable
D, E    = deuda financiera (A1) y patrimonio (market cap si hay precio, si no, libros)
t       = tasa efectiva
WACC    = E/(D+E)·Ke + D/(D+E)·Kd·(1−t)
```
Mostrar el desglose del WACC en el DCF (no como número mágico): celdas para Rf,
ERP, β, Ke, Kd, pesos, t → WACC. Esto **es** la diferencia entre un DCF de juguete
y uno profesional, y aprovecha directamente las tasas reales del XBRL.

## B4. Mejoras de presentación
- Bloque "SUPUESTOS DEL WACC" arriba del DCF (Rf, ERP, β, Ke, Kd, D/E, t).
- "VALOR TERMINAL" mostrando ambos métodos (Gordon vs múltiplo) y TV%EV.
- "SENSIBILIDAD" con tabla WACC×g y rango de valor/acción.
- Todos los supuestos como **números** (no texto) para que es-CL muestre coma
  (ya corregido en el escritor de supuestos).

---

# PARTE C — Plan de implementación priorizado

**Fase 1 (alto valor, base de datos):** extraer deuda y tasas del XBRL
- Nuevos extractores en `formula_processor.py` siguiendo el patrón
  `_extract_shares`/`_extract_da` (`_extract_borrowings`, `_extract_rates`,
  `_extract_finance_costs`), usando `_xbrl_search_root()`.
- Nueva hoja "DEUDA Y FINANCIAMIENTO" + filas RATIOS (Kd efectivo, % deuda <12m,
  cobertura de intereses).

**Fase 2 (DCF profesional):** en `dcf_patch.py`
- Bloque WACC (CAPM + Kd real) con celdas visibles.
- Terminal normalizado + múltiplo de salida + TV%EV.
- Convención mitad de año (toggle).
- Tabla de sensibilidad 2-vías y escenarios con motor único.
- Tax efectiva histórica.

**Fase 3 (estados/datos adicionales):**
- 4º estado [610000], EPS/acciones en circulación, segmentos, biológicos.

**Riesgos / cuidado:**
- Validar escala de tasas (`Unit_pure`) y outliers trimestrales (refinanciamientos).
- Los `qname` de detalle de préstamos pueden variar por empresa/taxonomía; tener
  fallback por label y por rol [822xxx].
- Mantener todo dependiente de `CMF_XBRL_BASE_DIR` (portabilidad).

---

## Apéndice — fórmulas de cálculo desde XBRL (resumen)
```
Kd_bonos        = InterestExpenseOnBonds × f / saldo_bonos           (f=4 si trimestral)
Kd_prestamos    = InterestExpenseOnBankLoansAndOverdrafts × f / (ST+LT Borrowings)
Kd_efectivo     = FinanceCosts_anualizado / Deuda_financiera_total
% deuda <12m    = (deuda corriente) / deuda_total
Cobertura int.  = EBIT / InterestExpense
Endeud. neto    = Proceeds − Repayments (del período)
WACC            = E/(D+E)·(Rf+β·ERP) + D/(D+E)·Kd·(1−t)
FCFF_terminal_n = EBIT_n·(1−t)            (CapEx=D&A, ΔNWC=g·NWC)
TV_gordon       = FCFF_terminal_n·(1+g)/(WACC−g)
TV_multiplo     = EBITDA_terminal × (EV/EBITDA salida)
```
