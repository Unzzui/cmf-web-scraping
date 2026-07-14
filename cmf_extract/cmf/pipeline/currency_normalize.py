"""Deja toda la serie de una empresa en UNA sola moneda.

EL PROBLEMA
-----------
Ocho empresas cambiaron su moneda de presentación a mitad de la serie:

    AGROSUPER (CLP->USD 2021), ENEL CHILE (2025), ENEL GENERACIÓN (2025),
    ENEL AMÉRICAS (2017), PEHUENCHE (2025), MARÍTIMA (USD->CLP 2016),
    NAVARINO (2016), QUEMCHI (2016)

El pipeline lo detectaba y lo anotaba en una nota, pero no convertía nada. En el Excel de
ENEL CHILE los ingresos iban de 3.904.732.890 (2024, CLP) a 4.509.547 (2025, USD): un
factor de 866x presentado como si la empresa se hubiera desplomado 99,9%. Todo lo que
cruzara esa frontera -- el CAGR de ventas, los márgenes, los ratios, el DCF entero -- era
basura, y llegaba a la base de datos y al cliente.

HACIA QUÉ MONEDA
----------------
Hacia la ACTUAL de la empresa: la del período más reciente. Es lo que hace la propia
empresa cuando cambia de moneda -- reexpresa sus comparativos hacia la nueva -- y deja los
años recientes, que son los que más pesan en cualquier valuación, exactamente como fueron
reportados.

CÓMO (NIC 21)
-------------
  · FLUJOS (estado de resultados, flujo de efectivo) -> tipo de cambio PROMEDIO del período
  · STOCKS (balance)                                 -> tipo de cambio de CIERRE

No es una interpretación: se verificó contra la reexpresión que ENEL CHILE misma publicó
en su filing de 2025. Ver el encabezado de `cmf_extract/fx.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _columnas_de_fecha(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if isinstance(c, str) and _FECHA.match(c)]


def _a_numero(serie: pd.Series) -> pd.Series:
    """Las cifras del CSV primario, como numeros.

    Vienen como texto con separador de miles ("3,904,732,890"). Pasarlas por
    `pd.to_numeric` a secas devuelve NaN y BORRA el dato -- silenciosamente, porque el
    resto del pipeline trata el NaN como "esta empresa no reporto esta cuenta".
    """
    if pd.api.types.is_numeric_dtype(serie):
        return serie
    return pd.to_numeric(
        serie.astype(str).str.replace(",", "", regex=False).str.strip(),
        errors="coerce",
    )


def normalizar_moneda(df: pd.DataFrame, company_dir: Path,
                      enable_log: bool = False) -> pd.DataFrame:
    """Convierte las columnas cuya moneda no sea la actual de la empresa.

    Si la empresa nunca cambió de moneda -- 223 de las 231 -- devuelve el DataFrame tal
    cual, sin tocar nada.
    """
    try:
        from cmf_extract import fx
        from cmf_extract.currency_detect import monedas_por_anio
    except ImportError:
        import fx
        from currency_detect import monedas_por_anio

    fechas = _columnas_de_fecha(df)
    if not fechas or "RoleCode" not in df.columns:
        return df

    try:
        por_anio = monedas_por_anio(company_dir)
    except Exception:
        return df

    if not por_anio or len(set(por_anio.values())) < 2:
        return df  # una sola moneda: nada que hacer

    # La moneda actual: la del año más reciente que la empresa reportó.
    destino = por_anio[max(por_anio)]

    if not fx.disponible():
        print(f"[moneda] {company_dir.name}: cambió de moneda "
              f"({sorted(set(por_anio.values()))}) pero no hay serie de tipo de cambio en "
              f"{fx.SERIE}. La serie queda MEZCLADA -- los ratios y el DCF no son fiables.")
        return df

    if not fx.es_diaria():
        print(f"[moneda] {company_dir.name}: la serie de tipo de cambio es mensual; el "
              f"balance convertido arrastra ~1,4% de error (los flujos son exactos). "
              f"Con la serie diaria del Banco Central queda exacto.")

    convertidas = 0
    for col in fechas:
        anio = int(col[:4])
        origen = por_anio.get(anio)
        if origen is None or origen == destino:
            continue

        cierre = pd.Timestamp(col)

        # Un factor por ROL, porque el balance y el estado de resultados no usan el mismo
        # tipo de cambio. Aplicar uno solo a toda la columna desviaría uno de los dos.
        for rol in df["RoleCode"].astype(str).unique():
            f = fx.factor(cierre, rol)
            if not f:
                continue

            # `fx.factor` devuelve CLP por 1 USD. Si vamos de CLP a USD hay que dividir.
            if origen == "CLP" and destino == "USD":
                mult = 1.0 / f
            elif origen == "USD" and destino == "CLP":
                mult = f
            else:
                continue  # otra moneda: no hay serie para convertirla

            mask = df["RoleCode"].astype(str) == rol
            crudo = _a_numero(df.loc[mask, col])
            # Solo se toca lo que ES un numero. Una celda vacia sigue vacia: convertirla la
            # volveria un 0, y un 0 no es lo mismo que "la empresa no reporto esta cuenta".
            df.loc[mask, col] = crudo.where(crudo.isna(), crudo * mult)

        convertidas += 1

    if convertidas and enable_log:
        print(f"[moneda] {company_dir.name}: {convertidas} período(s) convertidos a "
              f"{destino} (flujos al promedio, balance al cierre)")

    return df
