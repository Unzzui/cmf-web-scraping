"""Tests del cliente HTTP y de los constructores de URL."""

import time

import pytest

from src.edgar import endpoints
from src.edgar.api_client import EdgarClient, RateLimiter


def test_pad_cik_deja_el_formato_que_quiere_la_sec():
    assert endpoints.pad_cik("320193") == "0000320193"
    assert endpoints.pad_cik(320193) == "0000320193"
    assert endpoints.pad_cik("0000320193") == "0000320193"  # el de companies.cik, tal cual


def test_urls():
    assert endpoints.companyfacts_url("320193") == (
        "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"
    )
    assert endpoints.companyconcept_url("320193", "Assets").endswith(
        "/CIK0000320193/us-gaap/Assets.json"
    )


def test_exige_user_agent_con_contacto():
    """Sin User-Agent con contacto real la SEC responde 403 a todo. Fallar en el
    constructor es mucho más barato que descubrirlo a mitad de un backfill."""
    with pytest.raises(ValueError, match="User-Agent"):
        EdgarClient("")
    with pytest.raises(ValueError, match="User-Agent"):
        EdgarClient("python-requests/2.31")
    EdgarClient("FindataChile contacto@findatachile.com")  # no explota


def test_rate_limiter_respeta_la_tasa():
    limiter = RateLimiter(rate_per_sec=50)
    inicio = time.monotonic()
    for _ in range(5):
        limiter.acquire()
    # 5 slots a 50/s = 4 intervalos de 20ms >= 80ms
    assert time.monotonic() - inicio >= 0.075


class _FakeResponse:
    def __init__(self, status_code, data=None):
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        return self._data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.headers = {}
        self.calls = 0

    def get(self, url, timeout=None):
        self.calls += 1
        return self.responses.pop(0)


def test_404_es_no_data_y_no_se_reintenta():
    from src.edgar.api_client import NoDataError

    session = _FakeSession([_FakeResponse(404)])
    client = EdgarClient("FindataChile contacto@findatachile.com", session=session)
    with pytest.raises(NoDataError):
        client.get_json("https://data.sec.gov/x.json")
    assert session.calls == 1


def test_403_no_se_reintenta_porque_insistir_alarga_el_bloqueo():
    from src.edgar.api_client import ApiError

    session = _FakeSession([_FakeResponse(403)])
    client = EdgarClient("FindataChile contacto@findatachile.com", session=session)
    with pytest.raises(ApiError, match="User-Agent"):
        client.get_json("https://data.sec.gov/x.json")
    assert session.calls == 1


def test_get_json_ok():
    session = _FakeSession([_FakeResponse(200, {"facts": {}})])
    client = EdgarClient("FindataChile contacto@findatachile.com", session=session)
    assert client.get_json("https://data.sec.gov/x.json") == {"facts": {}}
