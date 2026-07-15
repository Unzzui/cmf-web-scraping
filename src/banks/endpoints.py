"""Constructores de paths para los recursos de la API de Bancos de la CMF.

Cada función devuelve el path relativo a BASE_URL, sin apikey ni formato (los agrega
el cliente). Los meses van sin cero a la izquierda; la API acepta ambos.
"""

BASE_URL = "https://api.cmfchile.cl/api-sbifv3/recursos_api"


def instituciones_path(year: int, month: int) -> str:
    return f"balances/{year}/{month}/instituciones"


def balance_path(year: int, month: int, cod: str) -> str:
    return f"balances/{year}/{month}/instituciones/{cod}"


def resultado_path(year: int, month: int, cod: str) -> str:
    return f"resultados/{year}/{month}/instituciones/{cod}"


def adecuacion_componentes_path(year: int, month: int, cod: str) -> str:
    return f"adecuacion/anhos/{year}/meses/{month}/instituciones/{cod}/componentes"


def adecuacion_indicador_path(year: int, month: int, cod: str, indicador: str) -> str:
    return (
        f"adecuacion/anhos/{year}/meses/{month}/instituciones/{cod}"
        f"/indicadores/{indicador}"
    )


def perfil_path(cod: str, year: int, month: int) -> str:
    return f"perfil/instituciones/{cod}/{year}/{month}"


def accionistas_path(cod: str, year: int, month: int) -> str:
    return f"accionistas/instituciones/{cod}/anhos/{year}/meses/{month}/ficha"


def integrantes_path(cod: str, year: int, month: int) -> str:
    return f"integrantes/instituciones/{cod}/anhos/{year}/meses/{month}"
