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

CATEGORY_BY_ROLE = {
    ROLE_BALANCE: "balance_sheet",
    ROLE_INCOME: "income_statement",
    ROLE_CASHFLOW: "cash_flow",
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
    # Ausente en JPM y BAC: un banco no presenta balance clasificado (no hay corriente /
    # no corriente). Queda hueco y los ratios de liquidez no aplican, que es lo correcto.
    Concept("AC", ("AssetsCurrent",),
            "Activos corrientes totales", "Total current assets",
            ROLE_BALANCE, "Activos corrientes", 50),
    Concept("PPE", ("PropertyPlantAndEquipmentNet",),
            "Propiedades, planta y equipo", "Property, plant and equipment, net",
            ROLE_BALANCE, "Activos no corrientes", 60),
    Concept("Good", ("Goodwill",),
            "Plusvalía", "Goodwill", ROLE_BALANCE, "Activos no corrientes", 70),
    Concept("Intang", ("IntangibleAssetsNetExcludingGoodwill", "FiniteLivedIntangibleAssetsNet"),
            "Activos intangibles distintos de la plusvalía",
            "Intangible assets, net", ROLE_BALANCE, "Activos no corrientes", 80),
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
    Concept("PC", ("LiabilitiesCurrent",),
            "Pasivos corrientes totales", "Total current liabilities",
            ROLE_BALANCE, "Pasivos corrientes", 130),
    Concept("DeudaLP", ("LongTermDebtNoncurrent", "LongTermDebt"),
            "Otros pasivos financieros no corrientes",
            "Long-term debt", ROLE_BALANCE, "Pasivos no corrientes", 140),
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
    Concept("CostFin", ("InterestExpense", "InterestExpenseDebt",
                        "InterestIncomeExpenseNet"),
            "Costos financieros", "Interest expense", ROLE_INCOME, None, 380),
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
