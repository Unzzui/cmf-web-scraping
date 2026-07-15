import pytest

from src.banks.api_client import CMFApiClient, NoDataError, ApiError


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 500:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        # responses: lista de FakeResponse o Exception a devolver/levantar en orden
        self._responses = list(responses)
        self.calls = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_get_ok_devuelve_json():
    session = FakeSession([FakeResponse({"UFs": [{"Valor": "40.844,79"}]})])
    client = CMFApiClient("KEY", session=session)
    data = client.get("uf")
    assert data == {"UFs": [{"Valor": "40.844,79"}]}


def test_url_incluye_apikey_y_formato():
    session = FakeSession([FakeResponse({"ok": 1})])
    client = CMFApiClient("KEY", session=session)
    client.get("balances/2025/5/instituciones/001")
    url = session.calls[0]
    assert url.startswith(
        "https://api.cmfchile.cl/api-sbifv3/recursos_api/balances/2025/5/instituciones/001"
    )
    assert "apikey=KEY" in url
    assert "formato=json" in url


def test_sin_datos_levanta_nodataerror():
    session = FakeSession(
        [FakeResponse({"CodigoHTTP": 404, "CodigoError": 80, "Mensaje": "No hay datos"})]
    )
    client = CMFApiClient("KEY", session=session)
    with pytest.raises(NoDataError):
        client.get("balances/2099/1/instituciones/001")


def test_reintenta_y_luego_ok():
    session = FakeSession([RuntimeError("boom"), FakeResponse({"ok": 1})])
    client = CMFApiClient("KEY", session=session, max_retries=3)
    assert client.get("uf") == {"ok": 1}
    assert len(session.calls) == 2


def test_falla_tras_agotar_reintentos():
    session = FakeSession([RuntimeError("boom"), RuntimeError("boom"), RuntimeError("boom")])
    client = CMFApiClient("KEY", session=session, max_retries=3)
    with pytest.raises(ApiError):
        client.get("uf")


def test_http_404_es_nodataerror_sin_reintentos():
    session = FakeSession([FakeResponse({}, status_code=404)])
    client = CMFApiClient("KEY", session=session, max_retries=3)
    with pytest.raises(NoDataError):
        client.get("adecuacion/anhos/2024/meses/12/instituciones/001/componentes")
    assert len(session.calls) == 1  # no reintentos: un 404 es "sin datos", no fallo de transporte


def test_throttle_espera_antes_de_cada_llamada(monkeypatch):
    import src.banks.api_client as mod

    slept: list[float] = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    session = FakeSession([FakeResponse({"ok": 1})])
    client = CMFApiClient("KEY", session=session, pause=0.3)
    client.get("uf")
    assert slept == [0.3]  # una espera de throttle antes de la llamada exitosa


def test_sin_throttle_cuando_pause_cero(monkeypatch):
    import src.banks.api_client as mod

    slept: list[float] = []
    monkeypatch.setattr(mod.time, "sleep", lambda s: slept.append(s))
    session = FakeSession([FakeResponse({"ok": 1})])
    client = CMFApiClient("KEY", session=session, pause=0.0)
    client.get("uf")
    assert slept == []
