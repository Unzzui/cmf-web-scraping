"""Constructores de URL para las APIs XBRL de la SEC.

El CIK va SIEMPRE con 10 dígitos y ceros a la izquierda (`CIK0000320193`). Es el formato
que quiere la API y es también como está guardado en `companies.cik` (TEXT, no entero),
así que no hay que reformatear nada al leer de la BD — pero sí al recibir un CIK escrito
a mano, para eso está `pad_cik`.
"""

BASE_DATA = "https://data.sec.gov"
BASE_WWW = "https://www.sec.gov"


def pad_cik(cik: str | int) -> str:
    """'320193' | 320193 -> '0000320193'."""
    return str(cik).strip().lstrip("CIK").zfill(10)


def companyfacts_url(cik: str | int) -> str:
    return f"{BASE_DATA}/api/xbrl/companyfacts/CIK{pad_cik(cik)}.json"


def companyconcept_url(cik: str | int, tag: str, taxonomy: str = "us-gaap") -> str:
    return f"{BASE_DATA}/api/xbrl/companyconcept/CIK{pad_cik(cik)}/{taxonomy}/{tag}.json"


def submissions_url(cik: str | int) -> str:
    return f"{BASE_DATA}/submissions/CIK{pad_cik(cik)}.json"


def company_tickers_url() -> str:
    return f"{BASE_WWW}/files/company_tickers.json"
