"""Clasificación de época del plan de cuentas y unidad monetaria por período.

El nuevo Compendio de Normas Contables para Bancos rige desde enero 2022: cambia
el plan de cuentas (códigos y glosas) y las cifras pasan de millones de pesos a pesos.
"""

_COMPENDIO_YEAR = 2022

# La adecuación de capital del api-sbifv3 (IRS/IRE, Basilea I/II) deja de publicarse en
# 2020-12, cuando la CMF pasa a Basilea III. Desde ese mes el recurso `adecuacion` y sus
# 9 sub-recursos responden 500/404 para todos los bancos: no es un fallo nuestro ni un
# endpoint nuevo que falte, la serie Basilea III vive en el portal de estadísticas, fuera
# de esta API. Verificado banco a banco hasta 2026-05.
_ADECUACION_ULTIMO = (2020, 11)


def adecuacion_disponible(year: int, month: int) -> bool:
    """False desde 2020-12: el API ya no publica adecuación (quiebre Basilea III)."""
    return (year, month) <= _ADECUACION_ULTIMO


def classify_epoch(year: int, month: int) -> str:
    """'pre_2022' para períodos anteriores a enero 2022; 'compendio_2022' desde ahí."""
    if year < _COMPENDIO_YEAR:
        return "pre_2022"
    return "compendio_2022"


def classify_unit(year: int, month: int) -> str:
    """'MMCLP' (millones de pesos) en la época vieja; 'CLP' (pesos) desde 2022."""
    if classify_epoch(year, month) == "pre_2022":
        return "MMCLP"
    return "CLP"
