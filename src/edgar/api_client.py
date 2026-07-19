"""Cliente HTTP para las APIs XBRL de la SEC.

Dos requisitos operativos, y los dos son duros:

* **User-Agent con nombre y contacto reales.** Sin él la SEC responde 403 a todo. No hay
  API key ni registro: el User-Agent ES la identificación. Por eso el cliente lo exige en
  el constructor y se niega a arrancar con uno que no tenga pinta de contacto — un 403
  masivo a mitad de un backfill es mucho más caro que fallar acá.
* **Máximo 10 requests/segundo por IP.** Pasarse bloquea la IP temporalmente.

El throttle se implementa acá y no se reusa `src/xbrl/http_throttle.py`: ese módulo está
afinado para la CMF, que bloquea por ráfagas y necesita cooldowns de minutos y rotación de
User-Agent. Acá la regla es una tasa fija y explícita, y rotar el User-Agent sería
exactamente lo contrario de lo que la SEC pide.
"""

import threading
import time

import requests

from src.edgar.endpoints import companyfacts_url

# La SEC documenta 10 req/s. Se deja margen a propósito: el límite es por IP y no por
# proceso, así que si además corre el scraper de la CMF o un backfill en paralelo, ir
# pegado al techo es pedir el bloqueo.
DEFAULT_RATE_PER_SEC = 8.0


class NoDataError(Exception):
    """La SEC no tiene datos para ese CIK (404)."""


class ApiError(Exception):
    """Fallo de transporte tras agotar los reintentos."""


class RateLimiter:
    """Throttle de tasa fija, compartido entre hilos."""

    def __init__(self, rate_per_sec: float = DEFAULT_RATE_PER_SEC):
        self._min_interval = 1.0 / rate_per_sec
        self._lock = threading.Lock()
        self._next_slot = 0.0

    def acquire(self) -> None:
        # El slot se reserva DENTRO del lock y se duerme FUERA: si se durmiera adentro, los
        # hilos se serializarían contra el lock y el throttle se volvería un cuello de
        # botella en vez de un regulador de tasa.
        with self._lock:
            now = time.monotonic()
            slot = max(now, self._next_slot)
            self._next_slot = slot + self._min_interval
        wait = slot - time.monotonic()
        if wait > 0:
            time.sleep(wait)


class EdgarClient:
    def __init__(
        self,
        user_agent: str,
        session=None,
        rate_per_sec: float = DEFAULT_RATE_PER_SEC,
        max_retries: int = 3,
        backoff: float = 2.0,
        timeout: int = 60,
        limiter: RateLimiter | None = None,
    ):
        if not _looks_like_contact(user_agent):
            raise ValueError(
                "La SEC exige un User-Agent con nombre y contacto reales, ej. "
                "'FindataChile contacto@findatachile.com'. Sin eso responde 403 a todo. "
                f"Recibido: {user_agent!r}"
            )
        if session is None:
            session = requests.Session()
        session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self.session = session
        self.limiter = limiter or RateLimiter(rate_per_sec)
        self.max_retries = max_retries
        self.backoff = backoff
        self.timeout = timeout

    def get_json(self, url: str) -> dict:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 404:
                    raise NoDataError(f"404 sin datos: {url}")
                if response.status_code == 403:
                    # No se reintenta: un 403 de la SEC es el User-Agent o un bloqueo por
                    # tasa. Insistir sólo alarga el bloqueo.
                    raise ApiError(
                        f"403 de la SEC en {url}. Revisar el User-Agent y no pasar de "
                        "10 req/s."
                    )
                if response.status_code == 429:
                    raise ApiError(f"429: excedido el límite de 10 req/s en {url}")
                response.raise_for_status()
                return response.json()
            except (NoDataError, ApiError):
                raise
            except Exception as exc:  # noqa: BLE001 - se reintenta cualquier fallo de red
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff * (2 ** (attempt - 1)))
                    continue
                raise ApiError(f"GET {url} falló tras {self.max_retries} intentos: {exc}")
        raise ApiError(f"GET {url} falló: {last_exc}")

    def get_text(self, url: str) -> str:
        """GET que devuelve texto (para la instancia iXBRL del filing, no JSON).

        Mismo throttle, reintentos y política de 403/404 que ``get_json``.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            self.limiter.acquire()
            try:
                response = self.session.get(url, timeout=self.timeout)
                if response.status_code == 404:
                    raise NoDataError(f"404 sin datos: {url}")
                if response.status_code == 403:
                    raise ApiError(
                        f"403 de la SEC en {url}. Revisar el User-Agent y no pasar de "
                        "10 req/s."
                    )
                if response.status_code == 429:
                    raise ApiError(f"429: excedido el límite de 10 req/s en {url}")
                response.raise_for_status()
                return response.text
            except (NoDataError, ApiError):
                raise
            except Exception as exc:  # noqa: BLE001 - se reintenta cualquier fallo de red
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(self.backoff * (2 ** (attempt - 1)))
                    continue
                raise ApiError(f"GET {url} falló tras {self.max_retries} intentos: {exc}")
        raise ApiError(f"GET {url} falló: {last_exc}")

    def get_companyfacts(self, cik: str | int) -> dict:
        return self.get_json(companyfacts_url(cik))


def _looks_like_contact(user_agent: str) -> bool:
    return bool(user_agent) and "@" in user_agent and len(user_agent.strip()) >= 10
