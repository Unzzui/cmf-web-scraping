"""Clasificación de época del plan de cuentas y unidad monetaria por período.

El nuevo Compendio de Normas Contables para Bancos rige desde enero 2022: cambia
el plan de cuentas (códigos y glosas) y las cifras pasan de millones de pesos a pesos.
"""

_COMPENDIO_YEAR = 2022


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
