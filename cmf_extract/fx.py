"""El dólar observado del Banco Central, y la conversión de estados que cambiaron de moneda.

POR QUÉ EXISTE
--------------
Ocho empresas cambiaron su moneda de presentación a mitad de la serie histórica:

    AGROSUPER, ENEL CHILE, ENEL GENERACIÓN, ENEL AMÉRICAS, PEHUENCHE,
    MARÍTIMA DE INVERSIONES, NAVARINO, QUEMCHI

El pipeline las detectaba y lo anotaba en una nota al pie, pero NO CONVERTÍA NADA. En el
Excel de ENEL CHILE los ingresos pasaban de 3.904.732.890 (2024, CLP) a 4.509.547 (2025,
USD): un salto de 866x que el Excel presentaba como si la empresa se hubiera desplomado
99,9%. Todo lo que cruzaba esa frontera -- CAGR, márgenes, ratios, el DCF entero -- era
basura, y esos valores mezclados llegaban a la base de datos y al cliente.

LA REGLA (NIC 21), VERIFICADA CONTRA LA PROPIA EMPRESA
-------------------------------------------------------
No hay que adivinarla. Cuando ENEL CHILE cambió a dólares en 2025, reexpresó su 2024 --
y de ahí sale el tipo de cambio que ella misma usó:

    Ingresos 2024:  3.904.732.890 CLP / 4.137.511 USD  = 943,74
        promedio anual 2024 del Banco Central          = 943,74   (error 0,00%)
        cierre de diciembre 2024                       = 982,30   (error 4,09%)

    Activos 2024:  12.719.897.584 CLP / 12.765.086 USD = 996,46
        dólar observado del 31-dic-2024                = 996,46   (exacto)

Es decir, exactamente lo que manda la norma:

  · FLUJOS (estado de resultados, flujo de efectivo) -> tipo de cambio PROMEDIO del período
  · STOCKS (balance)                                 -> tipo de cambio de CIERRE, el del día

PRECISIÓN DEL BALANCE
---------------------
El cierre exige el valor del DÍA. Si la serie que hay en disco es mensual (promedios), se
usa el promedio del mes de cierre y se acepta ~1,4% de error en el balance; el módulo lo
advierte. Con la serie DIARIA del Banco Central (la misma, `F073.TCO.PRE.Z.D`, exportada
en frecuencia diaria) el balance queda exacto.
"""

from __future__ import annotations

import functools
from pathlib import Path

import pandas as pd

SERIE = Path(__file__).resolve().parent / "public" / "DOLAR_OBS_ADO.xlsx"

# Los estados primarios que son FLUJOS (se acumulan durante el período) y los que son
# STOCKS (una foto a la fecha de cierre). La distinción decide qué tipo de cambio usar.
ROLES_FLUJO = {"310000", "320000", "510000"}
ROLES_STOCK = {"210000", "220000"}


@functools.lru_cache(maxsize=1)
def _serie() -> pd.DataFrame:
    """El dólar observado: una fila por fecha, ordenada. Vacío si no está en disco."""
    if not SERIE.is_file():
        return pd.DataFrame(columns=["fecha", "clp_por_usd"])

    df = pd.read_excel(SERIE, sheet_name="Cuadro")
    df = df.iloc[:, :2]
    df.columns = ["fecha", "clp_por_usd"]
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df["clp_por_usd"] = pd.to_numeric(df["clp_por_usd"], errors="coerce")
    return df.dropna().sort_values("fecha").reset_index(drop=True)


@functools.lru_cache(maxsize=1)
def es_diaria() -> bool:
    """¿La serie tiene resolución diaria?

    Con datos mensuales el tipo de cambio de CIERRE es una aproximación (el promedio del
    mes de cierre en vez del valor del día), y el balance de las empresas convertidas
    arrastra ~1,4% de error. Con datos diarios es exacto.
    """
    s = _serie()
    if len(s) < 3:
        return False
    # Mensual: una observación por mes, siempre el día 1.
    return not (s["fecha"].dt.day == 1).all()


def disponible() -> bool:
    return not _serie().empty


def cierre(fecha: pd.Timestamp | str) -> float | None:
    """El tipo de cambio a la FECHA DE CIERRE. Para el balance (stocks).

    Se toma la PRIMERA observación en o DESPUÉS del cierre, no la última anterior.
    Suena al revés, y no lo es: el dólar observado que el Banco Central publica el día D
    refleja las operaciones del día hábil anterior. El que corresponde al cierre del 31 de
    diciembre es entonces el publicado el siguiente día hábil -- y el 31 de diciembre suele
    ni siquiera tener observación, porque es feriado bancario.

    No es teoría. Contrastado contra la reexpresión que publicaron cuatro empresas al
    cambiar de moneda:

        cierre 2024-12-31   implícito   última previa   primera posterior
        ENEL CHILE             996,46      992,12 (0,44%)    996,46 (0,00%)
        ENEL GENERACIÓN        996,46      992,12 (0,44%)    996,46 (0,00%)
        PEHUENCHE              996,46      992,12 (0,44%)    996,46 (0,00%)
        AGROSUPER (2020)       710,95      711,24 (0,04%)    710,95 (0,00%)
    """
    s = _serie()
    if s.empty:
        return None
    f = pd.Timestamp(fecha)

    if es_diaria():
        posteriores = s[s["fecha"] >= f]
        return float(posteriores.iloc[0]["clp_por_usd"]) if len(posteriores) else None

    # Serie mensual: no hay resolución de día, así que el cierre es una aproximación (el
    # promedio del mes). Arrastra ~1,4% de error en el balance; `es_diaria()` lo advierte.
    mes = s[(s["fecha"].dt.year == f.year) & (s["fecha"].dt.month == f.month)]
    return float(mes.iloc[0]["clp_por_usd"]) if len(mes) else None


def promedio(desde: pd.Timestamp | str, hasta: pd.Timestamp | str) -> float | None:
    """El tipo de cambio PROMEDIO del período. Para el estado de resultados y el flujo.

    Es lo que la propia empresa aplica al reexpresar sus comparativos: verificado contra
    la reexpresión de ENEL CHILE con 0,00% de error.
    """
    s = _serie()
    if s.empty:
        return None
    a, b = pd.Timestamp(desde), pd.Timestamp(hasta)
    tramo = s[(s["fecha"] >= a) & (s["fecha"] <= b)]
    return float(tramo["clp_por_usd"].mean()) if len(tramo) else None


def factor(fecha_cierre: pd.Timestamp | str, rol: str,
           desde: pd.Timestamp | str | None = None) -> float | None:
    """CLP por 1 USD que corresponde a este período y este estado.

    `rol` es el código del estado primario: los flujos (310000/320000/510000) usan el
    promedio del período; los stocks (210000/220000) usan el cierre.
    """
    f = pd.Timestamp(fecha_cierre)
    if str(rol) in ROLES_STOCK:
        return cierre(f)

    # El período de un flujo acumulado: desde el inicio del ejercicio hasta el cierre.
    inicio = pd.Timestamp(desde) if desde is not None else pd.Timestamp(f.year, 1, 1)
    return promedio(inicio, f)
