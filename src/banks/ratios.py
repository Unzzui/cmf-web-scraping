"""Ratios de banco: definiciones y construcción de fórmulas de Excel.

Por qué no se reutiliza la hoja de ratios de Product_v1
-------------------------------------------------------
La hoja RATIOS & KPIs del pipeline IFRS calcula Liquidez Corriente, Prueba Ácida,
Rotación de Inventarios, Ciclo de Conversión de Efectivo, Deuda/EBITDA... Nada de eso
existe en un banco: no tiene inventario, no separa activo corriente de no corriente, y su
EBITDA no significa nada. La deuda de un banco es su materia prima, no su financiamiento.
Los ratios de acá son los del negocio bancario y no tienen contraparte allá.

Dos cosas que definen las fórmulas
----------------------------------
1. **El resultado es YTD.** El API acumula el ejercicio: la utilidad de 2025-05 son cinco
   meses, no uno. Todo ratio que cruce un flujo (resultado) con un stock (balance) se
   anualiza por ``12/mes``; un ROE de mayo sin anualizar queda 2,4x subestimado. Los que
   cruzan dos flujos del mismo período (eficiencia = gastos/ingresos) **no** se anualizan:
   el factor se cancela.
2. **Los gastos vienen negativos.** ``TOTAL GASTOS OPERACIONALES`` y las provisiones son
   negativos en el origen (verificado: ingresos + gastos + pérdidas crediticias da exacto
   el resultado operacional). De ahí el ABS(): sin él, el índice de eficiencia sale con el
   signo invertido.

Sólo se calculan para la época ``compendio_2022``: el plan nuevo publica los subtotales ya
hechos (ingreso neto por intereses, ingresos/gastos operacionales), mientras que el plan
pre-2022 usa otros códigos y no los trae, así que habría que reconstruirlos a mano.
"""

from dataclasses import dataclass
from typing import Callable

# ── Cuentas del plan Compendio 2022 que alimentan los ratios ──────────────────
AT = ("balance", "100000000")          # TOTAL ACTIVOS
PT = ("balance", "200000000")          # TOTAL PASIVOS
PAT = ("balance", "300000000")         # PATRIMONIO
COL = ("balance", "500000000")         # TOTAL COLOCACIONES
PROV = ("balance", "149000000")        # Provisiones constituidas por riesgo de crédito
DEP_VISTA = ("balance", "241000000")   # Depósitos y otras obligaciones a la vista
DEP_PLAZO = ("balance", "242000000")   # Depósitos y otras captaciones a plazo

ING_NETO_INT = ("resultado", "520000000")  # INGRESO NETO POR INTERESES
ING_OP = ("resultado", "550000000")        # TOTAL INGRESOS OPERACIONALES
GTO_OP = ("resultado", "560000000")        # TOTAL GASTOS OPERACIONALES  (negativo)
GTO_CRED = ("resultado", "470000000")      # GASTO POR PÉRDIDAS CREDITICIAS (negativo)
UTIL = ("resultado", "590000000")          # UTILIDAD (PÉRDIDA) DEL EJERCICIO

CUENTAS_REQUERIDAS = (
    AT, PT, PAT, COL, PROV, DEP_VISTA, DEP_PLAZO,
    ING_NETO_INT, ING_OP, GTO_OP, GTO_CRED, UTIL,
)


@dataclass(frozen=True)
class Ratio:
    nombre: str
    categoria: str
    formula_texto: str          # para la hoja METODOLOGÍA
    formato: str                # 'pct' | 'mult'
    construir: Callable         # (ref, anual) -> str  (cuerpo de la fórmula)


def _pct(x: str) -> str:
    return x


# ``ref(cuenta)`` devuelve la referencia a la celda ("'Balance 2022+'!B10").
# ``anual(x)`` envuelve un flujo YTD para anualizarlo (x * 12/mes).
RATIOS: tuple[Ratio, ...] = (
    Ratio("ROE", "Rentabilidad",
          "Utilidad del ejercicio (anualizada) / Patrimonio", "pct",
          lambda ref, anual: f"{anual(ref(UTIL))}/{ref(PAT)}"),
    Ratio("ROA", "Rentabilidad",
          "Utilidad del ejercicio (anualizada) / Total activos", "pct",
          lambda ref, anual: f"{anual(ref(UTIL))}/{ref(AT)}"),
    Ratio("Margen de Interés Neto (NIM)", "Rentabilidad",
          "Ingreso neto por intereses (anualizado) / Total activos", "pct",
          lambda ref, anual: f"{anual(ref(ING_NETO_INT))}/{ref(AT)}"),
    Ratio("Margen Neto", "Rentabilidad",
          "Utilidad del ejercicio / Total ingresos operacionales", "pct",
          lambda ref, anual: f"{ref(UTIL)}/{ref(ING_OP)}"),

    Ratio("Índice de Eficiencia", "Eficiencia",
          "|Total gastos operacionales| / Total ingresos operacionales", "pct",
          lambda ref, anual: f"ABS({ref(GTO_OP)})/{ref(ING_OP)}"),
    Ratio("Gastos Operacionales / Activos", "Eficiencia",
          "|Total gastos operacionales| (anualizado) / Total activos", "pct",
          lambda ref, anual: f"{anual('ABS(' + ref(GTO_OP) + ')')}/{ref(AT)}"),

    Ratio("Provisiones / Colocaciones", "Riesgo de crédito",
          "|Provisiones por riesgo de crédito| / Total colocaciones", "pct",
          lambda ref, anual: f"ABS({ref(PROV)})/{ref(COL)}"),
    Ratio("Costo del Riesgo", "Riesgo de crédito",
          "|Gasto por pérdidas crediticias| (anualizado) / Total colocaciones", "pct",
          lambda ref, anual: f"{anual('ABS(' + ref(GTO_CRED) + ')')}/{ref(COL)}"),

    Ratio("Colocaciones / Depósitos", "Estructura y fondeo",
          "Total colocaciones / (Depósitos a la vista + a plazo)", "pct",
          lambda ref, anual: f"{ref(COL)}/({ref(DEP_VISTA)}+{ref(DEP_PLAZO)})"),
    Ratio("Colocaciones / Activos", "Estructura y fondeo",
          "Total colocaciones / Total activos", "pct",
          lambda ref, anual: f"{ref(COL)}/{ref(AT)}"),
    Ratio("Depósitos / Pasivos", "Estructura y fondeo",
          "(Depósitos a la vista + a plazo) / Total pasivos", "pct",
          lambda ref, anual: f"({ref(DEP_VISTA)}+{ref(DEP_PLAZO)})/{ref(PT)}"),
    Ratio("Patrimonio / Activos", "Estructura y fondeo",
          "Patrimonio / Total activos", "pct",
          lambda ref, anual: f"{ref(PAT)}/{ref(AT)}"),
    Ratio("Apalancamiento (Activos / Patrimonio)", "Estructura y fondeo",
          "Total activos / Patrimonio", "mult",
          lambda ref, anual: f"{ref(AT)}/{ref(PAT)}"),
)

CATEGORIAS = ("Rentabilidad", "Eficiencia", "Riesgo de crédito", "Estructura y fondeo")


def factor_anualizacion(mes: int) -> float:
    """12/mes: convierte un acumulado YTD a base anual. Diciembre -> 1.0."""
    return 12.0 / mes


def construir_formula(ratio: Ratio, ref: Callable, mes: int) -> str:
    """Fórmula de Excel completa, envuelta en IFERROR como las de Product_v1.

    Antepone una guarda ISBLANK sobre cada celda que la fórmula toca. Sin ella, un hueco
    del origen se convierte en un número creíble y falso: Excel evalúa la celda vacía como
    0, así que ``0/patrimonio`` da 0 sin lanzar error, el IFERROR no lo atrapa y el ratio
    publica un ROE de 0,00% — que se lee como "el banco no ganó nada" en vez de "no hay
    dato". La CMF tiene huecos de un report suelto (p.ej. el resultado de 2023-07 de Banco
    de Chile), así que el caso es real, no teórico.
    """
    f = factor_anualizacion(mes)
    tocadas: list[str] = []

    def ref_reg(cuenta):
        celda = ref(cuenta)
        if celda != "NA()":
            tocadas.append(celda)
        return celda

    def anual(x: str) -> str:
        return x if f == 1.0 else f"({x}*{f:.6g})"

    cuerpo = ratio.construir(ref_reg, anual)
    if not tocadas:
        return '=""'
    guarda = "+".join(f"COUNTBLANK({c})" for c in tocadas)
    return f'=IF({guarda}>0,"",IFERROR({cuerpo},""))'
