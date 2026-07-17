"""Cliente HTTP fino para la API de Bancos de la CMF."""

import time
from urllib.parse import urlencode

from src.banks.endpoints import BASE_URL


class NoDataError(Exception):
    """La API respondió que no hay datos para los parámetros (CodigoError 80)."""


class ApiError(Exception):
    """Fallo de transporte tras agotar los reintentos."""


class CMFApiClient:
    def __init__(
        self,
        apikey: str,
        session=None,
        base_url: str = BASE_URL,
        max_retries: int = 3,
        pause: float = 0.0,
        backoff: float = 1.0,
    ):
        if session is None:
            import requests

            session = requests.Session()
            session.headers.update({"User-Agent": "cmf-extract-banks/1.0"})
        self.apikey = apikey
        self.session = session
        self.base_url = base_url
        self.max_retries = max_retries
        self.pause = pause
        self.backoff = backoff

    def _build_url(self, path: str) -> str:
        query = urlencode({"apikey": self.apikey, "formato": "json"})
        return f"{self.base_url}/{path}?{query}"

    def get(self, path: str) -> dict:
        if self.pause:
            time.sleep(self.pause)
        url = self._build_url(path)
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=30)
                if response.status_code == 404:
                    raise NoDataError(f"404 sin datos para {path}")
                response.raise_for_status()
                data = response.json()
            except NoDataError:
                raise
            except Exception as exc:  # noqa: BLE001 - se reintenta cualquier fallo de transporte
                last_exc = exc
                if attempt < self.max_retries:
                    # Backoff exponencial y no lineal sobre self.pause: la CMF frena por
                    # ráfagas devolviendo 500 o cortando la conexión, y con los 0.3s/0.6s
                    # de antes los 3 intentos caían dentro de la misma ventana de bloqueo
                    # y el dato se marcaba 'failed' aunque existiera.
                    time.sleep(self.backoff * (2 ** (attempt - 1)))
                    continue
                raise ApiError(f"GET {path} falló tras {self.max_retries} intentos: {exc}")
            if isinstance(data, dict) and data.get("CodigoError") == 80:
                raise NoDataError(data.get("Mensaje", "Sin datos"))
            return data
        raise ApiError(f"GET {path} falló: {last_exc}")
