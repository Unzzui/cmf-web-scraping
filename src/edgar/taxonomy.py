"""Catálogo de conceptos us-gaap y su traducción al modelo de FindataChile.

Cada concepto declara **una cadena de tags candidatos en orden de prioridad**: gana el
primero que la empresa reporte. No es un lujo — se midió sobre 8 emisores y ninguna
cadena de un solo tag cubre el universo:

    Ingresos   -> RevenueFromContractWithCustomerExcludingAssessedTax (AAPL, MSFT, GOOGL,
                  TSLA, WMT, XOM) pero `Revenues` en JPM y UNH.
    Cuentas x cobrar -> AccountsReceivableNetCurrent salvo WMT, que usa ReceivablesNetCurrent.
    Costo de ventas  -> CostOfRevenue salvo AAPL/UNH, que usan CostOfGoodsAndServicesSold.
    D&A        -> DepreciationDepletionAndAmortization en XOM/WMT/TSLA, pero GOOGL y MSFT
                  sólo publican `Depreciation` (amortizan aparte).

`label_es` reutiliza **a propósito los mismos strings que usan las chilenas**. No es
cosmética: `ratio_calculator_postgresql.py` resuelve conceptos matcheando texto de label
en español (`"AT": ["Total de activos"]`). Con estos labels el motor de ratios toma las
gringas sin que haya que tocarlo. Cambiar un label de acá desconecta silenciosamente el
ratio correspondiente — cualquier cambio se verifica contra `concept_mappings`.

Lo que NO se hace acá: derivar ni calcular. Si un emisor no publica el tag, la línea
queda como hueco. XOM y JPM no publican `OperatingIncomeLoss`; WMT no publica
`Liabilities`. Rellenar eso con un 0 o con una resta es exactamente el error que el spec
(§7) prohíbe: un dato faltante es un hueco, no un cero.
"""

from dataclasses import dataclass

# Convención propia de EEUU. NO se reciclan los códigos de la CMF (210000/310000/510000):
# significan roles de la taxonomía IFRS y mezclarlos haría ilegible el origen de una fila.
ROLE_BALANCE = "US-BS"
ROLE_INCOME = "US-IS"
ROLE_CASHFLOW = "US-CF"
# NOTAS AL PIE. No es un cuarto estado: es lo que el emisor revela en las notas y que no
# aparece en la cara de ninguno de los tres (tasa efectiva de impuesto, desglose de
# arrendamientos, vencimientos de deuda, componentes del OCI…).
#
# Va aparte y no repartido entre los otros roles POR UNA RAZÓN CONCRETA: si estas líneas
# entraran al balance o a resultados, quien sume las cuentas dejaría de llegar al
# subtotal y leería un descuadre donde no lo hay. Una nota no es una cuenta del estado.
#
# Nada de lo que hoy lee la BD las va a mostrar por accidente: la web pide siempre por
# categoría explícita (`?category=income_statement`…), el export filtra
# `category IN ('income_statement','balance_sheet','cash_flow')` y `build_us_estados.py`
# mapea categorías fijas a hojas. La categoría 'notes' queda guardada e invisible hasta
# que exista una superficie que la muestre — que es exactamente la intención.
ROLE_NOTES = "US-NOTE"

CATEGORY_BY_ROLE = {
    ROLE_BALANCE: "balance_sheet",
    ROLE_INCOME: "income_statement",
    ROLE_CASHFLOW: "cash_flow",
    ROLE_NOTES: "notes",
}


@dataclass(frozen=True)
class Concept:
    """Un concepto del catálogo: cómo encontrarlo en EDGAR y cómo guardarlo."""

    key: str
    tags: tuple[str, ...]  # candidatos, en orden de prioridad
    label_es: str
    label_en: str
    role_code: str
    subcategory: str | None
    display_order: int
    unit: str = "USD"

    @property
    def category(self) -> str:
        return CATEGORY_BY_ROLE[self.role_code]


# `display_order` va de 10 en 10 y es fijo por concepto: es parte de la unique
# (company_id, display_order), así que reordenar acá reescribe filas ya cargadas. Los
# huecos entre números son para poder insertar conceptos nuevos sin renumerar.
CONCEPTS: tuple[Concept, ...] = (
    # ------------------------------------------------------------------ BALANCE
    Concept("Efec", ("CashAndCashEquivalentsAtCarryingValue",),
            "Efectivo y equivalentes al efectivo", "Cash and cash equivalents",
            ROLE_BALANCE, "Activos corrientes", 10),
    Concept("OAF", ("ShortTermInvestments", "MarketableSecuritiesCurrent"),
            "Otros activos financieros corrientes", "Short-term investments",
            ROLE_BALANCE, "Activos corrientes", 20),
    Concept("CxC", ("AccountsReceivableNetCurrent", "ReceivablesNetCurrent"),
            "Deudores comerciales y otras cuentas por cobrar corrientes",
            "Accounts receivable, net", ROLE_BALANCE, "Activos corrientes", 30),
    Concept("Inv", ("InventoryNet",),
            "Inventarios corrientes", "Inventories",
            ROLE_BALANCE, "Activos corrientes", 40),
    Concept("OtrAC", ("OtherAssetsCurrent", "PrepaidExpenseAndOtherAssetsCurrent"),
            "Otros activos no financieros, corrientes", "Other current assets",
            ROLE_BALANCE, "Activos corrientes", 45),
    # Ausente en JPM y BAC: un banco no presenta balance clasificado (no hay corriente /
    # no corriente). Queda hueco y los ratios de liquidez no aplican, que es lo correcto.
    Concept("AC", ("AssetsCurrent",),
            "Activos corrientes totales", "Total current assets",
            ROLE_BALANCE, "Activos corrientes", 50),
    Concept("PPE", ("PropertyPlantAndEquipmentNet",),
            "Propiedades, planta y equipo", "Property, plant and equipment, net",
            ROLE_BALANCE, "Activos no corrientes", 60),
    # Bruto y depreciación acumulada. Con los tres el lector ve la EDAD del activo fijo
    # —cuánto de la planta ya se depreció—, que el neto solo esconde: dos empresas con el
    # mismo PPE neto pueden tener una la planta recién estrenada y la otra casi agotada.
    # El display_order los deja después del neto y no antes porque estos números son
    # nuevos y renumerar el 60 reescribiría filas ya cargadas (la unique con company_id).
    Concept("PPEBruto", ("PropertyPlantAndEquipmentGross",),
            "Propiedades, planta y equipo, bruto", "Property, plant and equipment, gross",
            ROLE_BALANCE, "Activos no corrientes", 61),
    # Activo por derecho de uso: universal desde 2019 (ASC 842). Antes de esa norma la
    # línea no existe y queda hueca, que es lo correcto —no es un dato faltante, es que la
    # cuenta no existía—.
    Concept("ROU", ("OperatingLeaseRightOfUseAsset",),
            "Activos por derecho de uso", "Operating lease right-of-use assets",
            ROLE_BALANCE, "Activos no corrientes", 62),
    Concept("InvLP", ("LongTermInvestments", "MarketableSecuritiesNoncurrent"),
            "Otros activos financieros no corrientes", "Long-term investments",
            ROLE_BALANCE, "Activos no corrientes", 64),
    Concept("Good", ("Goodwill",),
            "Plusvalía", "Goodwill", ROLE_BALANCE, "Activos no corrientes", 70),
    Concept("Intang", ("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
            "Activos intangibles distintos de la plusvalía",
            "Intangible assets, net", ROLE_BALANCE, "Activos no corrientes", 80),
    Concept("DTA", ("DeferredIncomeTaxAssetsNet", "DeferredTaxAssetsNet"),
            "Activos por impuestos diferidos", "Deferred tax assets",
            ROLE_BALANCE, "Activos no corrientes", 84),
    Concept("OANC", ("OtherAssetsNoncurrent",),
            "Otros activos no corrientes", "Other non-current assets",
            ROLE_BALANCE, "Activos no corrientes", 86),
    Concept("ANC", ("AssetsNoncurrent",),
            "Total de activos no corrientes", "Total non-current assets",
            ROLE_BALANCE, "Activos no corrientes", 90),
    Concept("AT", ("Assets",),
            "Total de activos", "Total assets", ROLE_BALANCE, None, 100),
    Concept("CxP", ("AccountsPayableCurrent", "AccountsPayableAndAccruedLiabilitiesCurrent"),
            "Cuentas por pagar comerciales y otras cuentas por pagar",
            "Accounts payable", ROLE_BALANCE, "Pasivos corrientes", 110),
    Concept("DeudaCP", ("LongTermDebtCurrent", "DebtCurrent"),
            "Otros pasivos financieros corrientes",
            "Short-term debt", ROLE_BALANCE, "Pasivos corrientes", 120),
    Concept("DefRevCP", ("ContractWithCustomerLiabilityCurrent", "DeferredRevenueCurrent"),
            "Pasivos por ingresos diferidos, corrientes", "Deferred revenue, current",
            ROLE_BALANCE, "Pasivos corrientes", 122),
    Concept("LeaseCP", ("OperatingLeaseLiabilityCurrent",),
            "Pasivos por arrendamientos, corrientes",
            "Operating lease liabilities, current", ROLE_BALANCE, "Pasivos corrientes", 124),
    # Arrendamiento FINANCIERO: es deuda y va aparte del operativo (124/142). Sin estas
    # líneas el apalancamiento de una empresa con flota o locales propios se subestima.
    Concept("LeaseFinCP", ("FinanceLeaseLiabilityCurrent",),
            "Pasivos por arrendamientos financieros, corrientes",
            "Finance lease liabilities, current", ROLE_BALANCE, "Pasivos corrientes", 125),
    # Papel comercial: deuda de cortísimo plazo que 18 de 36 emisores presentan separada.
    Concept("PapelCom", ("CommercialPaper",),
            "Papel comercial", "Commercial paper",
            ROLE_BALANCE, "Pasivos corrientes", 121),
    Concept("RemunPorPagar", ("EmployeeRelatedLiabilitiesCurrent",),
            "Cuentas por pagar al personal", "Employee-related liabilities, current",
            ROLE_BALANCE, "Pasivos corrientes", 123),
    Concept("ImpPorPagar", ("AccruedIncomeTaxesCurrent",),
            "Pasivos por impuestos corrientes", "Accrued income taxes, current",
            ROLE_BALANCE, "Pasivos corrientes", 127),
    Concept("OtrPasCP", ("OtherLiabilitiesCurrent",),
            "Otros pasivos corrientes", "Other current liabilities",
            ROLE_BALANCE, "Pasivos corrientes", 126),
    Concept("PC", ("LiabilitiesCurrent",),
            "Pasivos corrientes totales", "Total current liabilities",
            ROLE_BALANCE, "Pasivos corrientes", 130),
    Concept("DeudaLP", ("LongTermDebtNoncurrent", "LongTermDebt"),
            "Otros pasivos financieros no corrientes",
            "Long-term debt", ROLE_BALANCE, "Pasivos no corrientes", 140),
    Concept("LeaseLP", ("OperatingLeaseLiabilityNoncurrent",),
            "Pasivos por arrendamientos, no corrientes",
            "Operating lease liabilities, non-current", ROLE_BALANCE, "Pasivos no corrientes", 142),
    Concept("LeaseTotal", ("OperatingLeaseLiability",),
            "Pasivos por arrendamientos, total", "Operating lease liability, total",
            ROLE_BALANCE, "Pasivos no corrientes", 141),
    Concept("LeaseFinLP", ("FinanceLeaseLiabilityNoncurrent",),
            "Pasivos por arrendamientos financieros, no corrientes",
            "Finance lease liabilities, non-current", ROLE_BALANCE, "Pasivos no corrientes", 143),
    Concept("ImpPorPagarLP", ("AccruedIncomeTaxesNoncurrent",),
            "Pasivos por impuestos no corrientes", "Accrued income taxes, non-current",
            ROLE_BALANCE, "Pasivos no corrientes", 145),
    Concept("DTL", ("DeferredTaxLiabilitiesNoncurrent", "DeferredIncomeTaxLiabilitiesNet"),
            "Pasivos por impuestos diferidos", "Deferred tax liabilities",
            ROLE_BALANCE, "Pasivos no corrientes", 144),
    Concept("OtrPasLP", ("OtherLiabilitiesNoncurrent",),
            "Otros pasivos no corrientes", "Other non-current liabilities",
            ROLE_BALANCE, "Pasivos no corrientes", 146),
    Concept("PNC", ("LiabilitiesNoncurrent",),
            "Total de pasivos no corrientes", "Total non-current liabilities",
            ROLE_BALANCE, "Pasivos no corrientes", 150),
    # WMT no publica `Liabilities`. Queda hueco a propósito: restar
    # LiabilitiesAndStockholdersEquity - equity sería inventar un dato que el emisor no
    # declaró. La identidad contable se verifica con `PatPas` (abajo), que sí es universal.
    Concept("PT", ("Liabilities",),
            "Total de pasivos", "Total liabilities", ROLE_BALANCE, None, 160),
    # El orden de la cadena importa y replica la decisión de las chilenas: el patrimonio
    # ATRIBUIBLE A LA CONTROLADORA manda sobre el total. Si se invierte, el ROE y el D/E
    # de las empresas con interés minoritario salen distintos del producto que se vende.
    Concept("Patr", ("StockholdersEquity",),
            "Patrimonio atribuible a los propietarios de la controladora",
            "Stockholders' equity attributable to parent",
            ROLE_BALANCE, "Patrimonio", 170),
    Concept("CapEmit", ("CommonStockValue",),
            "Capital emitido", "Common stock", ROLE_BALANCE, "Patrimonio", 172),
    Concept("AccPref", ("PreferredStockValue",),
            "Acciones preferentes", "Preferred stock, value",
            ROLE_BALANCE, "Patrimonio", 173),
    Concept("Primas", ("AdditionalPaidInCapital",),
            "Primas de emisión", "Additional paid-in capital",
            ROLE_BALANCE, "Patrimonio", 174),
    Concept("AOCI", ("AccumulatedOtherComprehensiveIncomeLossNetOfTax",),
            "Otras reservas", "Accumulated other comprehensive income (loss)",
            ROLE_BALANCE, "Patrimonio", 176),
    # Signo negativo por definición (contra-patrimonio). Se guarda tal cual lo publica el
    # emisor —EDGAR ya lo trae negativo— para que la suma de componentes cierre con `Patr`.
    Concept("Treasury", ("TreasuryStockValue", "TreasuryStockCommonValue"),
            "Acciones propias en cartera", "Treasury stock",
            ROLE_BALANCE, "Patrimonio", 178),
    Concept("TreasuryAcc", ("TreasuryStockCommonShares",),
            "Número de acciones propias en cartera", "Treasury stock, shares",
            ROLE_BALANCE, "Patrimonio", 179, unit="shares"),
    Concept("Minor", ("MinorityInterest",),
            "Participaciones no controladoras", "Noncontrolling interest",
            ROLE_BALANCE, "Patrimonio", 180),
    Concept("PatrTot", ("StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",),
            "Patrimonio total", "Total equity", ROLE_BALANCE, "Patrimonio", 190),
    Concept("RE", ("RetainedEarningsAccumulatedDeficit",),
            "Ganancias (pérdidas) acumuladas", "Retained earnings (accumulated deficit)",
            ROLE_BALANCE, "Patrimonio", 195),
    # Va en el balance y no en resultados porque es un instant (un saldo a una fecha), no
    # un flujo. Y NO puede quedar en 'miscellaneous': el motor de ratios descarta esa
    # categoría entera, y sin acciones no hay métricas por acción.
    Concept("Acciones", ("CommonStockSharesOutstanding", "CommonStockSharesIssued"),
            "Total número de acciones emitidas", "Common shares outstanding",
            ROLE_BALANCE, "Patrimonio", 198, unit="shares"),
    # Universal (lo publican hasta JPM y WMT) y por eso es el ancla del chequeo de
    # cuadratura del §8.1: Assets debe igualar esto.
    Concept("PatPas", ("LiabilitiesAndStockholdersEquity",),
            "Total de patrimonio y pasivos", "Total liabilities and equity",
            ROLE_BALANCE, None, 200),

    # ------------------------------------------------------- ESTADO DE RESULTADOS
    # `RevenuesNetOfInterestExpense` va al final y es para los bancos (JPM, BAC): en sus
    # 10-Q no publican `Revenues` —sólo lo tagean en el 10-K anual— así que sin este
    # candidato JPM queda con los 3 trimestres vacíos y sólo el dato del ejercicio.
    # Mezclar dos tags en una misma serie sólo es legítimo si miden lo mismo: se comparó
    # tag contra tag en los 18 períodos donde JPM publica ambos y coinciden al peso en
    # todos (2018-2025).
    Concept("Ventas", ("RevenueFromContractWithCustomerExcludingAssessedTax",
                       "Revenues",
                       "RevenueFromContractWithCustomerIncludingAssessedTax",
                       "RevenuesNetOfInterestExpense"),
            "Ingresos de actividades ordinarias", "Revenues",
            ROLE_INCOME, None, 300),
    Concept("COGS", ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfServices",
                     "CostOfGoodsSold"),
            "Costo de ventas", "Cost of revenue", ROLE_INCOME, None, 310),
    # Ausente en GOOGL, WMT, XOM, JPM y UNH: no lo presentan. Hueco, no resta.
    Concept("GProfit", ("GrossProfit",),
            "Ganancia bruta", "Gross profit", ROLE_INCOME, None, 320),
    Concept("RyD", ("ResearchAndDevelopmentExpense",),
            "Gastos de investigación y desarrollo", "Research and development",
            ROLE_INCOME, "Gastos operacionales", 330),
    Concept("GAV", ("SellingGeneralAndAdministrativeExpense",
                    "GeneralAndAdministrativeExpense"),
            "Gastos de administración", "Selling, general and administrative",
            ROLE_INCOME, "Gastos operacionales", 340),
    Concept("OpEx", ("OperatingExpenses", "CostsAndExpenses"),
            "Gastos de operación", "Total operating expenses",
            ROLE_INCOME, "Gastos operacionales", 350),
    # XOM y JPM no lo publican.
    # El label va en PLURAL ("Ganancias (pérdidas)") porque es el string exacto que usan
    # las 218 chilenas y el que busca concept_mappings["EBIT"]. En singular el motor de
    # ratios no lo resuelve ni por 'contiene', y el EBIT de las gringas saldría vacío.
    Concept("OpInc", ("OperatingIncomeLoss",),
            "Ganancias (pérdidas) de actividades operacionales", "Operating income",
            ROLE_INCOME, None, 360),
    Concept("IngFin", ("InvestmentIncomeInterest", "InterestAndDividendIncomeOperating"),
            "Ingresos financieros", "Interest and investment income",
            ROLE_INCOME, None, 370),
    # `InterestExpenseNonoperating` va al final de la cadena y no es un detalle: emisores
    # que antes publicaban `InterestExpense` DEJARON DE HACERLO. Apple lo taggeó hasta
    # FY2023 y desde FY2024 no, así que su línea de costos financieros aparecía vacía en
    # los dos últimos ejercicios — no por un fallo nuestro, sino porque el tag que
    # buscábamos ya no está en el filing. Lo reportan 18 de 36 emisores medidos.
    #
    # Al FINAL, nunca al principio: la cadena resuelve por prioridad, así que agregar
    # atrás sólo puede rellenar huecos y jamás cambia un valor ya cargado.
    Concept("CostFin", ("InterestExpense", "InterestExpenseDebt",
                        "InterestIncomeExpenseNet", "InterestExpenseNonoperating"),
            "Costos financieros", "Interest expense", ROLE_INCOME, None, 380),
    # Neto de partidas no operacionales (resultado por inversiones, tipo de cambio, otros).
    # Label neutro a propósito para NO chocar con "Otras ganancias (pérdidas)", que el motor
    # de ratios matchea por texto — este concepto no es un input de ratio.
    Concept("NoOp", ("NonoperatingIncomeExpense", "OtherNonoperatingIncomeExpense"),
            "Otros ingresos (gastos) no operacionales, netos",
            "Non-operating income (expense), net", ROLE_INCOME, None, 385),
    Concept("EBT", ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"),
            "Ganancia (pérdida), antes de impuestos", "Income before income taxes",
            ROLE_INCOME, None, 390),
    Concept("Tax", ("IncomeTaxExpenseBenefit",),
            "Gasto por impuestos a las ganancias", "Income tax expense",
            ROLE_INCOME, None, 400),
    Concept("NetInc", ("NetIncomeLoss",),
            "Ganancia (pérdida)", "Net income", ROLE_INCOME, None, 410),
    Concept("EPS", ("EarningsPerShareBasic",),
            "Ganancias por acción básica", "Earnings per share, basic",
            ROLE_INCOME, "Por acción", 420, unit="USD/shares"),
    Concept("EPSDil", ("EarningsPerShareDiluted",),
            "Ganancias por acción diluida", "Earnings per share, diluted",
            ROLE_INCOME, "Por acción", 430, unit="USD/shares"),

    # Resultado ANTES de repartir con los minoritarios, y la parte que se van ellos.
    # `NetIncomeLoss` (410) es lo atribuible al controlador, que es lo que el accionista
    # cobra; pero para medir el negocio COMPLETO hace falta el total, y sin él una filial
    # consolidada al 60% parece rendir menos de lo que rinde.
    Concept("ResultadoTotal", ("ProfitLoss",),
            "Resultado del período, incluyendo participaciones no controladoras",
            "Net income (loss), including noncontrolling interest",
            ROLE_INCOME, None, 405),
    Concept("ResultadoMinor", ("NetIncomeLossAttributableToNoncontrollingInterest",),
            "Resultado atribuible a participaciones no controladoras",
            "Net income (loss) attributable to noncontrolling interest",
            ROLE_INCOME, None, 408),
    # Impuesto CORRIENTE: lo que de verdad se paga este año, contra el gasto contable de
    # 400 que incluye diferidos. La brecha entre ambos es una señal de calidad de utilidad.
    Concept("ImpCorriente", ("CurrentIncomeTaxExpenseBenefit",),
            "Gasto por impuestos corrientes", "Current income tax expense (benefit)",
            ROLE_INCOME, None, 402),
    Concept("DeterioroPlus", ("GoodwillImpairmentLoss",),
            "Pérdidas por deterioro de plusvalía", "Goodwill impairment loss",
            ROLE_INCOME, None, 367),
    Concept("Publicidad", ("AdvertisingExpense",),
            "Gastos de publicidad", "Advertising expense",
            ROLE_INCOME, None, 343),
    Concept("Deterioro", ("AssetImpairmentCharges",),
            "Pérdidas por deterioro de valor", "Asset impairment charges",
            ROLE_INCOME, None, 365),

    # Los DENOMINADORES del BPA. Se agregan porque sin ellos hay empresas que quedan sin
    # ninguna cuenta de acciones: `CommonStockSharesOutstanding` (el tag del concepto
    # "Acciones", en el balance) NO es universal. Medido el 2026-07-26 sobre 12 emisores:
    # AAPL, NVDA, BAC y MSFT lo publican; ACN, MA, META, NKE, UPS y V no publican ese ni
    # `CommonStockSharesIssued` ni el `dei:EntityCommonStockSharesOutstanding` de la
    # portada — sólo estos promedios ponderados.
    #
    # Y sin acciones se cae toda la cadena por acción: el pipeline no puede dividir el
    # equity value, `dcf_analysis.base_price` queda NULL y la web no publica valor justo
    # (hacen falta ≥2 métodos y se pierde el DCF). Eso es exactamente lo que dejaba a
    # META y otras cinco con «—» en el portafolio.
    #
    # Van en resultados y NO en el balance, con su propio label: son un promedio DEL
    # PERÍODO, no un saldo a una fecha. Meterlos en el concepto "Acciones" los rotularía
    # «Total número de acciones emitidas», que es otra cosa y mentiría en el balance.
    Concept("AccBasicas", ("WeightedAverageNumberOfSharesOutstandingBasic",
                           "WeightedAverageNumberOfSharesOutstanding"),
            "Número de acciones básico (promedio del período)",
            "Weighted average shares outstanding, basic",
            ROLE_INCOME, "Por acción", 440, unit="shares"),
    Concept("AccDiluidas", ("WeightedAverageNumberOfDilutedSharesOutstanding",),
            "Número de acciones diluido (promedio del período)",
            "Weighted average shares outstanding, diluted",
            ROLE_INCOME, "Por acción", 450, unit="shares"),

    # Dividendo por acción DECLARADO. Lo publican 8 de 10 emisores y no lo teníamos: el
    # eje Dividendo y el DDM tenían que deducirlo del flujo de caja (`PaymentsOfDividends`
    # ÷ acciones), que mezcla el momento del pago con el de la declaración.
    Concept("DPA", ("CommonStockDividendsPerShareDeclared",
                    "CommonStockDividendsPerShareCashPaid"),
            "Dividendos por acción declarados", "Dividends declared per share",
            ROLE_INCOME, "Por acción", 460, unit="USD/shares"),

    # Resultado integral: la utilidad más lo que pasó por patrimonio sin tocar resultados
    # (traducción de moneda, coberturas). Cierra contra el AOCI del balance, que sí
    # teníamos, y hasta ahora no tenía contraparte en el estado de resultados.
    Concept("RIntegral", ("ComprehensiveIncomeNetOfTax",
                          "ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest"),
            "Resultado integral total", "Comprehensive income, net of tax",
            ROLE_INCOME, None, 470),
    Concept("OCI", ("OtherComprehensiveIncomeLossNetOfTaxPortionAttributableToParent",
                    "OtherComprehensiveIncomeLossNetOfTax"),
            "Otro resultado integral del período",
            "Other comprehensive income (loss), net of tax",
            ROLE_INCOME, None, 465),

    # ------------------------------------------------------------ FLUJO DE EFECTIVO
    Concept("CFO", ("NetCashProvidedByUsedInOperatingActivities",
                    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"),
            "Flujos de efectivo netos procedentes de (utilizados en) actividades de operación",
            "Net cash from operating activities", ROLE_CASHFLOW, None, 500),
    Concept("CFI", ("NetCashProvidedByUsedInInvestingActivities",
                    "NetCashProvidedByUsedInInvestingActivitiesContinuingOperations"),
            "Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión",
            "Net cash from investing activities", ROLE_CASHFLOW, None, 510),
    Concept("CFF", ("NetCashProvidedByUsedInFinancingActivities",
                    "NetCashProvidedByUsedInFinancingActivitiesContinuingOperations"),
            "Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación",
            "Net cash from financing activities", ROLE_CASHFLOW, None, 520),
    # GOOGL y MSFT sólo publican `Depreciation` (amortizan en un tag aparte); el resto usa
    # el combinado. La cadena cubre ambos, pero ojo: para esos dos el valor es sólo
    # depreciación, no D&A completo.
    Concept("DA", ("DepreciationDepletionAndAmortization",
                   "DepreciationAmortizationAndAccretionNet",
                   "DepreciationAndAmortization",
                   "Depreciation"),
            "Depreciación y amortización", "Depreciation and amortization",
            ROLE_CASHFLOW, None, 530),
    Concept("Capex", ("PaymentsToAcquirePropertyPlantAndEquipment",
                      "PaymentsToAcquireProductiveAssets"),
            "Compras de propiedades, planta y equipo",
            "Purchases of property, plant and equipment", ROLE_CASHFLOW, None, 540),
    Concept("Div", ("PaymentsOfDividends", "PaymentsOfDividendsCommonStock"),
            "Dividendos pagados", "Dividends paid", ROLE_CASHFLOW, None, 550),
    # --- Ajustes no monetarios al resultado (van DESPUÉS de los subtotales, igual que D&A) ---
    Concept("SBC", ("ShareBasedCompensation", "AllocatedShareBasedCompensationExpense"),
            "Gasto por compensación basada en acciones", "Share-based compensation",
            ROLE_CASHFLOW, "Ajustes al resultado", 560),
    Concept("DefTaxCF", ("DeferredIncomeTaxExpenseBenefit",),
            "Impuestos diferidos", "Deferred income taxes",
            ROLE_CASHFLOW, "Ajustes al resultado", 562),
    # --- Cambios en el capital de trabajo. EDGAR los publica con el signo del EFECTO en
    #     caja (un aumento de la cuenta por cobrar entra negativo), tal como el estado. ---
    Concept("dCxC", ("IncreaseDecreaseInAccountsReceivable",),
            "Cambios en deudores comerciales", "Change in accounts receivable",
            ROLE_CASHFLOW, "Capital de trabajo", 564),
    Concept("dInv", ("IncreaseDecreaseInInventories",),
            "Cambios en inventarios", "Change in inventories",
            ROLE_CASHFLOW, "Capital de trabajo", 566),
    Concept("dCxP", ("IncreaseDecreaseInAccountsPayable", "IncreaseDecreaseInAccountsPayableTrade"),
            "Cambios en cuentas por pagar", "Change in accounts payable",
            ROLE_CASHFLOW, "Capital de trabajo", 568),
    # --- Financiamiento en detalle ---
    Concept("Buyback", ("PaymentsForRepurchaseOfCommonStock",),
            "Recompra de acciones propias", "Repurchases of common stock",
            ROLE_CASHFLOW, "Financiamiento", 570),
    Concept("DeudaObt", ("ProceedsFromIssuanceOfLongTermDebt",),
            "Importes procedentes de préstamos de largo plazo",
            "Proceeds from issuance of long-term debt", ROLE_CASHFLOW, "Financiamiento", 572),
    Concept("DeudaPago", ("RepaymentsOfLongTermDebt",),
            "Pagos de préstamos de largo plazo", "Repayments of long-term debt",
            ROLE_CASHFLOW, "Financiamiento", 574),
    # --- Variación neta de la caja y complementos ---
    Concept("NetCashChg", ("CashAndCashEquivalentsPeriodIncreaseDecrease",
                           "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalentsPeriodIncreaseDecreaseIncludingExchangeRateEffect"),
            "Incremento (disminución) neto de efectivo y equivalentes",
            "Net change in cash and cash equivalents", ROLE_CASHFLOW, None, 580),
    Concept("TaxPaid", ("IncomeTaxesPaidNet", "IncomeTaxesPaid"),
            "Impuestos a las ganancias pagados (reembolsados)", "Income taxes paid, net",
            ROLE_CASHFLOW, "Información complementaria", 590),
    Concept("IntPaid", ("InterestPaidNet", "InterestPaid"),
            "Intereses pagados", "Interest paid",
            ROLE_CASHFLOW, "Información complementaria", 592),

    # Las líneas "otros" de inversión y financiación. Las reportan 10 de 10 emisores y
    # sin ellas el estado NO CUADRA: los subtotales CFI y CFF que sí guardábamos incluyen
    # estos montos, así que al desglosar faltaba plata sin explicación visible. Un lector
    # que suma las líneas y no llega al subtotal asume que el dato está mal.
    # Adquisiciones: la vía de crecimiento que NO se ve en el capex. Sin esta línea una
    # empresa que compra crecimiento parece no estar invirtiendo.
    Concept("Adquisiciones", ("PaymentsToAcquireBusinessesNetOfCashAcquired",),
            "Compras de negocios, netas de la caja adquirida",
            "Payments to acquire businesses, net of cash acquired",
            ROLE_CASHFLOW, "Inversión", 545),
    Concept("dOtrosAct", ("IncreaseDecreaseInOtherOperatingAssets",),
            "Cambios en otros activos de operación",
            "Increase (decrease) in other operating assets",
            ROLE_CASHFLOW, "Operación", 569),
    Concept("OtrosCFI", ("PaymentsForProceedsFromOtherInvestingActivities",),
            "Otros flujos de inversión", "Other investing activities, net",
            ROLE_CASHFLOW, "Inversión", 576),
    Concept("OtrosCFF", ("ProceedsFromPaymentsForOtherFinancingActivities",),
            "Otros flujos de financiación", "Other financing activities, net",
            ROLE_CASHFLOW, "Financiación", 578),
    Concept("AjusteNoCaja", ("OtherNoncashIncomeExpense",),
            "Otros ajustes no monetarios", "Other non-cash income (expense)",
            ROLE_CASHFLOW, "Operación", 582),

    # El puente entre el saldo inicial y el final. `NetCashChg` (580) da la variación,
    # pero sin el efecto cambiario y el saldo final la conciliación queda a medias — y en
    # una empresa con caja en varias monedas el descuadre puede ser de miles de millones.
    Concept("FXEfectivo", ("EffectOfExchangeRateOnCashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
                           "EffectOfExchangeRateOnCashAndCashEquivalents"),
            "Efecto de la variación del tipo de cambio sobre la caja",
            "Effect of exchange rate on cash",
            ROLE_CASHFLOW, "Información complementaria", 585),
    Concept("EfectivoFinal", ("CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",),
            "Saldo final de caja y equivalentes",
            "Cash, cash equivalents and restricted cash, end of period",
            ROLE_CASHFLOW, "Información complementaria", 594),

    # OJO CON LAS ETIQUETAS QUE SE AGREGUEN ACÁ. El DCF de FinDataChile
    # (`scripts/dcf/excel_aligned.py`) NO resuelve por tag ni por categoría: hace
    # `LOWER(fli.label) LIKE '%término%'` y se queda con **MAX(value)** entre todas las
    # líneas que matcheen. Una etiqueta nueva que contenga una palabra buscada entra a
    # ese MAX y puede ganarle a la cuenta correcta.
    #
    # Ya pasó, el 2026-07-26: se agregó "Depreciación acumulada" al balance y el término
    # "Depreciación" del concepto DA la tomó. Es un SALDO ACUMULADO de todos los años
    # contra un flujo anual, así que el MAX la elegía siempre: el FCF de UPS saltó de
    # 6,5 a 20,1 mil millones y su valor por acción a US$545 con la acción en US$115.
    # Se quitaron esa cuenta y "Amortización de intangibles" por el mismo motivo, y los
    # cinco flujos que decían "efectivo" se renombraron a "caja".
    #
    # Antes de agregar una etiqueta, cruzarla contra CONCEPT_MAPPINGS del DCF y contra
    # los conceptos que busca `data_extractor.py` (ése sí prioriza el match exacto).
    # -------------------------------------------------------------------- NOTAS
    # Prevalencia medida el 2026-07-26 sobre 36 emisores de todos los sectores. El
    # display_order arranca en 700 para no chocar nunca con los tres estados (máx. 594).

    # --- Impuestos ---
    Concept("TasaEfectiva", ("EffectiveIncomeTaxRateContinuingOperations",),
            "Tasa efectiva de impuesto", "Effective income tax rate",
            ROLE_NOTES, "Impuestos", 700, unit="pure"),  # 36/36
    Concept("EBTNacional", ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",),
            "Resultado antes de impuestos, nacional",
            "Income before taxes, domestic", ROLE_NOTES, "Impuestos", 702),  # 33/36
    Concept("EBTExtranjero", ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesForeign",),
            "Resultado antes de impuestos, extranjero",
            "Income before taxes, foreign", ROLE_NOTES, "Impuestos", 704),  # 34/36
    Concept("DTLBruto", ("DeferredIncomeTaxLiabilities",),
            "Pasivos por impuestos diferidos, bruto",
            "Deferred tax liabilities, gross", ROLE_NOTES, "Impuestos", 706),  # 29/36
    Concept("DTABruto", ("DeferredTaxAssetsGross",),
            "Activos por impuestos diferidos, bruto",
            "Deferred tax assets, gross", ROLE_NOTES, "Impuestos", 708),
    Concept("DTAProvision", ("DeferredTaxAssetsValuationAllowance",),
            "Provisión de valuación sobre impuestos diferidos",
            "Deferred tax assets, valuation allowance", ROLE_NOTES, "Impuestos", 710),
    Concept("ImpIncierto", ("UnrecognizedTaxBenefits",),
            "Beneficios tributarios no reconocidos",
            "Unrecognized tax benefits", ROLE_NOTES, "Impuestos", 712),
    # ASU 2023-09 desagregó los impuestos pagados por jurisdicción. Los nuevos tags ya
    # aparecen en 28 y 24 de 36 emisores, así que conviene capturarlos antes de que el
    # `IncomeTaxesPaidNet` agregado (que alimenta a TaxPaid, 590) empiece a desaparecer.
    Concept("ImpPagFederal", ("IncomeTaxPaidFederalAfterRefundReceived",),
            "Impuestos pagados, federal (neto de devoluciones)",
            "Income taxes paid, federal, net of refunds", ROLE_NOTES, "Impuestos", 714),
    Concept("ImpPagEstatal", ("IncomeTaxPaidStateAndLocalAfterRefundReceived",),
            "Impuestos pagados, estatal y local (neto de devoluciones)",
            "Income taxes paid, state and local, net of refunds", ROLE_NOTES, "Impuestos", 716),
    Concept("UtilNoRemesada", ("UndistributedEarningsOfForeignSubsidiaries",),
            "Utilidades no remesadas de filiales extranjeras",
            "Undistributed earnings of foreign subsidiaries", ROLE_NOTES, "Impuestos", 718),

    # --- Arrendamientos (ASC 842) ---
    Concept("LeaseCosto", ("OperatingLeaseCost",),
            "Costo de arrendamientos operativos", "Operating lease cost",
            ROLE_NOTES, "Arrendamientos", 730),  # 32/36
    Concept("LeasePagos", ("OperatingLeasePayments",),
            "Pagos por arrendamientos operativos", "Operating lease payments",
            ROLE_NOTES, "Arrendamientos", 732),  # 30/36
    Concept("LeaseROUNuevo", ("RightOfUseAssetObtainedInExchangeForOperatingLeaseLiability",),
            "Activos por derecho de uso incorporados en el período",
            "Right-of-use assets obtained in exchange for lease liabilities",
            ROLE_NOTES, "Arrendamientos", 734),  # 30/36
    Concept("LeaseVariable", ("VariableLeaseCost",),
            "Costo variable de arrendamientos", "Variable lease cost",
            ROLE_NOTES, "Arrendamientos", 736),
    Concept("LeaseCostoTotal", ("LeaseCost",),
            "Costo total de arrendamientos", "Total lease cost",
            ROLE_NOTES, "Arrendamientos", 738),
    Concept("LeaseTasa", ("OperatingLeaseWeightedAverageDiscountRatePercent",),
            "Tasa de descuento de arrendamientos operativos",
            "Operating lease weighted average discount rate",
            ROLE_NOTES, "Arrendamientos", 740, unit="pure"),
    Concept("LeaseFinTotal", ("FinanceLeaseLiability",),
            "Pasivo por arrendamientos financieros, total",
            "Finance lease liability, total", ROLE_NOTES, "Arrendamientos", 742),

    # --- Vencimientos de deuda: el perfil de amortización, que decide si un
    #     apalancamiento alto es manejable o es un muro a doce meses. ---
    Concept("DeudaVence1", ("LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths",),
            "Vencimientos de deuda, año 1", "Debt maturities, year 1",
            ROLE_NOTES, "Vencimientos de deuda", 750),
    Concept("DeudaVence2", ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo",),
            "Vencimientos de deuda, año 2", "Debt maturities, year 2",
            ROLE_NOTES, "Vencimientos de deuda", 752),
    Concept("DeudaVence3", ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearThree",),
            "Vencimientos de deuda, año 3", "Debt maturities, year 3",
            ROLE_NOTES, "Vencimientos de deuda", 754),
    Concept("DeudaVence4", ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFour",),
            "Vencimientos de deuda, año 4", "Debt maturities, year 4",
            ROLE_NOTES, "Vencimientos de deuda", 756),
    Concept("DeudaVence5", ("LongTermDebtMaturitiesRepaymentsOfPrincipalInYearFive",),
            "Vencimientos de deuda, año 5", "Debt maturities, year 5",
            ROLE_NOTES, "Vencimientos de deuda", 758),

    # --- Componentes del otro resultado integral ---
    Concept("OCIMoneda", ("OtherComprehensiveIncomeLossForeignCurrencyTransactionAndTranslationAdjustmentNetOfTax",),
            "Otro resultado integral: diferencias de cambio por conversión",
            "OCI, foreign currency translation adjustment",
            ROLE_NOTES, "Resultado integral", 770),  # 24/36
    Concept("OCICobertura", ("OtherComprehensiveIncomeLossCashFlowHedgeGainLossAfterReclassificationAndTax",),
            "Otro resultado integral: coberturas de flujo de caja",
            "OCI, cash flow hedges", ROLE_NOTES, "Resultado integral", 772),  # 23/36
    Concept("OCIPension", ("OtherComprehensiveIncomeLossPensionAndOtherPostretirementBenefitPlansAdjustmentNetOfTax",),
            "Otro resultado integral: planes de beneficios post-empleo",
            "OCI, pension and postretirement plans",
            ROLE_NOTES, "Resultado integral", 774),
    Concept("RIntegralMinor", ("ComprehensiveIncomeNetOfTaxAttributableToNoncontrollingInterest",),
            "Resultado integral atribuible a participaciones no controladoras",
            "Comprehensive income attributable to noncontrolling interest",
            ROLE_NOTES, "Resultado integral", 776),

    # --- Estructura accionaria: lo que hay declarado pero no emitido, que es el
    #     espacio de dilución futura. ---
    Concept("AccAutorizadas", ("CommonStockSharesAuthorized",),
            "Acciones ordinarias autorizadas", "Common stock, shares authorized",
            ROLE_NOTES, "Estructura accionaria", 790, unit="shares"),  # 30/36
    Concept("AccValorPar", ("CommonStockParOrStatedValuePerShare",),
            "Valor par por acción ordinaria", "Common stock, par value per share",
            ROLE_NOTES, "Estructura accionaria", 792, unit="USD/shares"),  # 30/36
    Concept("AccPrefAutorizadas", ("PreferredStockSharesAuthorized",),
            "Acciones preferentes autorizadas", "Preferred stock, shares authorized",
            ROLE_NOTES, "Estructura accionaria", 794, unit="shares"),
    Concept("AccPrefEmitidas", ("PreferredStockSharesIssued",),
            "Acciones preferentes emitidas", "Preferred stock, shares issued",
            ROLE_NOTES, "Estructura accionaria", 796, unit="shares"),
    Concept("AccDilucion", ("IncrementalCommonSharesAttributableToShareBasedPaymentArrangements",),
            "Acciones incrementales por compensación en acciones",
            "Incremental shares from share-based payment arrangements",
            ROLE_NOTES, "Estructura accionaria", 798, unit="shares"),  # 23/36

    # --- Otras revelaciones ---
    Concept("IntangBruto", ("IntangibleAssetsGrossExcludingGoodwill",),
            "Activos intangibles, bruto", "Intangible assets, gross",
            ROLE_NOTES, "Otras revelaciones", 810),
    Concept("PlusAdquirida", ("GoodwillAcquiredDuringPeriod",),
            "Plusvalía incorporada en el período", "Goodwill acquired during period",
            ROLE_NOTES, "Otras revelaciones", 812),  # 24/36
    Concept("ProvIncobrables", ("AllowanceForDoubtfulAccountsReceivableCurrent",),
            "Provisión por deudores incobrables",
            "Allowance for doubtful accounts", ROLE_NOTES, "Otras revelaciones", 814),
    Concept("IngresoDiferidoPend", ("RevenueRemainingPerformanceObligation",),
            "Ingresos por obligaciones de desempeño pendientes",
            "Revenue, remaining performance obligation",
            ROLE_NOTES, "Otras revelaciones", 816),
    Concept("CompromisosCompra", ("UnrecordedUnconditionalPurchaseObligationBalanceSheetAmount",),
            "Compromisos de compra no registrados",
            "Unrecorded unconditional purchase obligations",
            ROLE_NOTES, "Otras revelaciones", 818),
)

CONCEPTS_BY_KEY = {c.key: c for c in CONCEPTS}

# Todos los tags que nos interesan, para poder filtrar el companyfacts de una pasada.
ALL_TAGS = frozenset(tag for c in CONCEPTS for tag in c.tags)


def resolve_tag(concept: Concept, available: frozenset[str] | set[str]) -> str | None:
    """Primer tag de la cadena que el emisor efectivamente reporta, o None."""
    for tag in concept.tags:
        if tag in available:
            return tag
    return None
