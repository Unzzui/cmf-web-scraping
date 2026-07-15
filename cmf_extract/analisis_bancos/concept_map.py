"""Mapa de conceptos bancarios -> codigos de cuenta del plan CMF (compendio 2022).

El plan de cuentas bancario expone subtotales agregados limpios, asi que casi todos los
conceptos mapean a un unico codigo. Un concepto que necesita sumar varias cuentas (p.ej.
depositos de clientes = vista + plazo) lista varios codigos.

Los valores se guardan con su signo natural (los gastos vienen negativos). Los ratios
que necesiten magnitudes usan valor absoluto en la formula, no aca.
"""

# Balance (Estado de Situacion) -- statement 'balance'
BALANCE = {
    "activos_total": ["100000000"],            # TOTAL ACTIVOS
    "pasivos_total": ["200000000"],            # TOTAL PASIVOS
    "patrimonio": ["380000000"],               # PATRIMONIO DE LOS PROPIETARIOS
    "patrimonio_total": ["300000000"],         # PATRIMONIO (incluye interes no controlador)
    "capital": ["310000000"],                  # CAPITAL
    "colocaciones": ["500000000"],             # TOTAL COLOCACIONES (memorandum)
    "provisiones_colocaciones": ["149000000"],  # Provisiones por riesgo de credito (negativo)
    "depositos_vista": ["241000000"],          # Depositos y otras obligaciones a la vista
    "depositos_plazo": ["242000000"],          # Depositos y otras captaciones a plazo
    "depositos_clientes": ["241000000", "242000000"],  # captaciones de clientes (funding)
}

# Estado de Resultados -- statement 'resultado' (acumulado del ejercicio / YTD)
RESULTADO = {
    "ingresos_intereses": ["411000000"],       # INGRESOS POR INTERESES
    "gastos_intereses": ["412000000"],         # GASTOS POR INTERESES (negativo)
    "ingreso_neto_intereses": ["520000000"],   # INGRESO NETO POR INTERESES
    "ingreso_neto_reajustes": ["525000000"],   # INGRESO NETO POR REAJUSTES
    "ingreso_neto_comisiones": ["530000000"],  # INGRESO NETO POR COMISIONES
    "resultado_financiero_neto": ["540000000"],  # RESULTADO FINANCIERO NETO
    "total_ingresos_operacionales": ["550000000"],  # TOTAL INGRESOS OPERACIONALES
    "total_gastos_operacionales": ["560000000"],   # TOTAL GASTOS OPERACIONALES (gastos de apoyo)
    "resultado_antes_perdidas": ["570000000"],  # RESULTADO OPER. ANTES DE PERDIDAS CREDITICIAS
    "gasto_perdidas_crediticias": ["470000000"],  # GASTO POR PERDIDAS CREDITICIAS (negativo)
    "resultado_operacional": ["580000000"],    # RESULTADO OPERACIONAL
    "impuesto": ["480000000"],                 # IMPUESTO A LA RENTA (negativo)
    "resultado_ejercicio": ["590000000"],      # UTILIDAD (PERDIDA) DEL EJERCICIO
    "resultado_propietarios": ["594000000"],   # RESULTADO DE LOS PROPIETARIOS
}


def codes_for(concept: str) -> list[str]:
    """Codigos de cuenta que componen un concepto. Levanta KeyError si no existe."""
    if concept in BALANCE:
        return BALANCE[concept]
    if concept in RESULTADO:
        return RESULTADO[concept]
    raise KeyError(f"Concepto bancario desconocido: {concept}")


def statement_for(concept: str) -> str:
    """'balance' o 'resultado' segun donde vive el concepto."""
    if concept in BALANCE:
        return "balance"
    if concept in RESULTADO:
        return "resultado"
    raise KeyError(f"Concepto bancario desconocido: {concept}")


def all_concepts() -> list[str]:
    return list(BALANCE) + list(RESULTADO)
