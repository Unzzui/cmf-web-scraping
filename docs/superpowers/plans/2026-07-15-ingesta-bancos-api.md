# Ingesta de bancos vía API CMF - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingerir data de bancos desde la API oficial de la CMF (`api.cmfchile.cl`) y cargarla a Supabase en tablas dedicadas `bank_*`, reemplazando el scraper HTML.

**Architecture:** Paquete nuevo `src/banks/` con capas puras y testeables (parser de números, endpoints, cliente HTTP, modelos, parsers de JSON, loader a Postgres) y un orquestador + CLI encima. Cada capa se prueba aislada; la data de la API vive solo en tablas `bank_*`, sin tocar la data XBRL existente.

**Tech Stack:** Python 3.12, `requests`, `psycopg2-binary`, `pytest`. Postgres/Supabase (pooler transaction mode).

## Global Constraints

- Sin emojis en ningún lado: código, logs, comentarios, docstrings. (verbatim del spec y memoria del usuario)
- Python `>=3.12`; ruff `line-length = 100`.
- Los tests importan el paquete como `src.banks.<modulo>` (pytest usa `pythonpath = ["."]`).
- La API key sale de `.env` como `CMF_API_KEY`; el `.env` no se versiona.
- Ningún cambio a tablas existentes; solo se crean tablas con prefijo `bank_`.
- Los valores se guardan tal cual con marca `unit`; no se convierten de unidad en esta fase.
- Números en formato español: punto de miles, coma decimal (`"40.844,79"` -> `40844.79`).
- Base de la API: `https://api.cmfchile.cl/api-sbifv3/recursos_api`. "Sin datos" llega en el body como `{"CodigoHTTP":404,"CodigoError":80,...}`, no como error de transporte.

## File Structure

- `src/banks/__init__.py` — marca el paquete.
- `src/banks/numbers.py` — parser de números español. Responsabilidad única: string ES -> float.
- `src/banks/taxonomy.py` — clasifica época del plan de cuentas y unidad por período.
- `src/banks/endpoints.py` — construye los paths de los recursos de la API (sin apikey).
- `src/banks/api_client.py` — cliente HTTP: auth, reintentos, detección de "sin datos".
- `src/banks/models.py` — dataclasses de las filas parseadas.
- `src/banks/ingest.py` — parsers puros: JSON de la API -> modelos.
- `src/banks/loader.py` — upserts a las tablas `bank_*` (psycopg2).
- `src/banks/runner.py` — orquestación por institución/período.
- `sql/bank_schema.sql` — DDL idempotente de las tablas `bank_*`.
- `scripts/ingest_banks.py` — CLI.
- `tests/banks/conftest.py` — fixture de conexión a la BD con rollback.
- `tests/banks/test_*.py` — tests por capa.

---

### Task 1: Paquete + parser de números español

**Files:**
- Create: `src/banks/__init__.py`
- Create: `src/banks/numbers.py`
- Test: `tests/banks/test_numbers.py`

**Interfaces:**
- Consumes: nada.
- Produces: `parse_spanish_number(raw: str | None) -> float | None`.

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_numbers.py`:

```python
from src.banks.numbers import parse_spanish_number


def test_entero_con_decimales_cero():
    assert parse_spanish_number("59878091792,00") == 59878091792.0


def test_miles_y_decimales():
    assert parse_spanish_number("40.844,79") == 40844.79


def test_negativo():
    assert parse_spanish_number("-1.234,50") == -1234.5


def test_cero():
    assert parse_spanish_number("0,00") == 0.0


def test_vacio_es_none():
    assert parse_spanish_number("") is None
    assert parse_spanish_number("   ") is None


def test_none_es_none():
    assert parse_spanish_number(None) is None


def test_basura_es_none():
    assert parse_spanish_number("N/A") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_numbers.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.banks'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/__init__.py` (vacío):

```python
```

Create `src/banks/numbers.py`:

```python
"""Parser de números en formato español (punto de miles, coma decimal)."""


def parse_spanish_number(raw: str | None) -> float | None:
    """Convierte un número con formato español a float.

    '59878091792,00' -> 59878091792.0
    '40.844,79'      -> 40844.79
    ''/None/'N/A'    -> None
    """
    if raw is None:
        return None
    s = raw.strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_numbers.py -v`
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/__init__.py src/banks/numbers.py tests/banks/test_numbers.py
git commit -m "feat(banks): parser de numeros en formato espanol"
```

---

### Task 2: Clasificador de época y unidad

**Files:**
- Create: `src/banks/taxonomy.py`
- Test: `tests/banks/test_taxonomy.py`

**Interfaces:**
- Consumes: nada.
- Produces:
  - `classify_epoch(year: int, month: int) -> str` (`'pre_2022'` | `'compendio_2022'`)
  - `classify_unit(year: int, month: int) -> str` (`'MMCLP'` | `'CLP'`)

El corte es enero 2022 (nuevo Compendio de Normas Contables). Antes: plan viejo y cifras en millones de pesos; desde 2022: plan nuevo y cifras en pesos.

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_taxonomy.py`:

```python
from src.banks.taxonomy import classify_epoch, classify_unit


def test_epoch_antes_de_2022():
    assert classify_epoch(2021, 12) == "pre_2022"
    assert classify_epoch(2009, 12) == "pre_2022"


def test_epoch_desde_2022():
    assert classify_epoch(2022, 1) == "compendio_2022"
    assert classify_epoch(2025, 5) == "compendio_2022"


def test_unit_sigue_a_la_epoca():
    assert classify_unit(2021, 12) == "MMCLP"
    assert classify_unit(2022, 1) == "CLP"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_taxonomy.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/taxonomy.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_taxonomy.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/taxonomy.py tests/banks/test_taxonomy.py
git commit -m "feat(banks): clasificador de epoca y unidad por periodo"
```

---

### Task 3: Constructores de paths de la API

**Files:**
- Create: `src/banks/endpoints.py`
- Test: `tests/banks/test_endpoints.py`

**Interfaces:**
- Consumes: nada.
- Produces (todas devuelven el path relativo a la base, sin apikey ni formato):
  - `instituciones_path(year: int, month: int) -> str`
  - `balance_path(year: int, month: int, cod: str) -> str`
  - `resultado_path(year: int, month: int, cod: str) -> str`
  - `adecuacion_componentes_path(year: int, month: int, cod: str) -> str`
  - `adecuacion_indicador_path(year: int, month: int, cod: str, indicador: str) -> str`
  - `perfil_path(cod: str, year: int, month: int) -> str`
  - `accionistas_path(cod: str, year: int, month: int) -> str`
  - `integrantes_path(cod: str, year: int, month: int) -> str`
- También exporta `BASE_URL = "https://api.cmfchile.cl/api-sbifv3/recursos_api"`.

Los meses van sin cero a la izquierda: la API acepta `5` y `05` (verificado con llamadas reales).

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_endpoints.py`:

```python
from src.banks import endpoints as ep


def test_instituciones():
    assert ep.instituciones_path(2025, 5) == "balances/2025/5/instituciones"


def test_balance():
    assert ep.balance_path(2025, 5, "001") == "balances/2025/5/instituciones/001"


def test_resultado():
    assert ep.resultado_path(2025, 5, "001") == "resultados/2025/5/instituciones/001"


def test_adecuacion_componentes():
    assert ep.adecuacion_componentes_path(2018, 12, "001") == (
        "adecuacion/anhos/2018/meses/12/instituciones/001/componentes"
    )


def test_adecuacion_indicador():
    assert ep.adecuacion_indicador_path(2018, 12, "001", "irs") == (
        "adecuacion/anhos/2018/meses/12/instituciones/001/indicadores/irs"
    )


def test_perfil():
    assert ep.perfil_path("001", 2024, 12) == "perfil/instituciones/001/2024/12"


def test_accionistas():
    assert ep.accionistas_path("001", 2024, 12) == (
        "accionistas/instituciones/001/anhos/2024/meses/12/ficha"
    )


def test_integrantes():
    assert ep.integrantes_path("001", 2024, 12) == (
        "integrantes/instituciones/001/anhos/2024/meses/12"
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_endpoints.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/endpoints.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_endpoints.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/endpoints.py tests/banks/test_endpoints.py
git commit -m "feat(banks): constructores de paths de la API CMF"
```

---

### Task 4: Cliente HTTP de la API

**Files:**
- Create: `src/banks/api_client.py`
- Test: `tests/banks/test_api_client.py`

**Interfaces:**
- Consumes: `endpoints.BASE_URL`.
- Produces:
  - `class NoDataError(Exception)` — la API respondió "sin datos" (CodigoError 80 / CodigoHTTP 404 en el body).
  - `class ApiError(Exception)` — fallo de transporte tras reintentos.
  - `class CMFApiClient` con:
    - `__init__(self, apikey: str, session=None, base_url: str = BASE_URL, max_retries: int = 3, pause: float = 0.0)`
    - `get(self, path: str) -> dict` — hace GET a `base_url/path?apikey=...&formato=json`; devuelve el JSON parseado; levanta `NoDataError` o `ApiError`.

El cliente recibe una `session` inyectable (objeto con `.get(url, timeout)`), para testear sin red. `session.get` devuelve un objeto con `.status_code`, `.json()` y `.raise_for_status()`.

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_api_client.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_api_client.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/api_client.py`:

```python
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

    def _build_url(self, path: str) -> str:
        query = urlencode({"apikey": self.apikey, "formato": "json"})
        return f"{self.base_url}/{path}?{query}"

    def get(self, path: str) -> dict:
        url = self._build_url(path)
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                data = response.json()
            except Exception as exc:  # noqa: BLE001 - se reintenta cualquier fallo de transporte
                last_exc = exc
                if attempt < self.max_retries:
                    if self.pause:
                        time.sleep(self.pause * attempt)
                    continue
                raise ApiError(f"GET {path} falló tras {self.max_retries} intentos: {exc}")
            if isinstance(data, dict) and data.get("CodigoError") == 80:
                raise NoDataError(data.get("Mensaje", "Sin datos"))
            return data
        raise ApiError(f"GET {path} falló: {last_exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_api_client.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/api_client.py tests/banks/test_api_client.py
git commit -m "feat(banks): cliente HTTP con reintentos y deteccion de sin-datos"
```

---

### Task 5: Modelos (dataclasses)

**Files:**
- Create: `src/banks/models.py`
- Test: `tests/banks/test_models.py`

**Interfaces:**
- Consumes: nada.
- Produces dataclasses:
  - `Institution(codigo_institucion: str, nombre_institucion: str)`
  - `AccountRow(statement, codigo_cuenta, descripcion_cuenta, moneda_no_reajustable, moneda_reajustable_ipc, moneda_reajustable_tc, moneda_extranjera, moneda_total)` (los 5 montos son `float | None`)
  - `CapitalAdequacy(activos_ponderados_riesgo, activos_totales, capital_basico, patrimonio_efectivo, provisiones_voluntarias, bonos_subordinados, interes_minoritario, indice_irs, indice_ire, raw)` (montos `float | None`, `raw: dict`)
  - `Profile(codigo_swift, rut, direccion, telefono, sitio_web, sucursales, oficinas, cajeros, empleados, emp_hombres_perm, emp_mujeres_perm, emp_hombres_ext, emp_mujeres_ext, fecha_publicacion, raw)`
  - `Shareholder(serie, rut, nombre, participacion, numero_acciones)`
  - `Executive(nombre, cargo, fecha_asuncion, tipo)`

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_models.py`:

```python
from src.banks.models import (
    AccountRow,
    CapitalAdequacy,
    Executive,
    Institution,
    Profile,
    Shareholder,
)


def test_account_row_admite_montos_none():
    row = AccountRow(
        statement="resultado",
        codigo_cuenta="434000000",
        descripcion_cuenta="RESULTADO",
        moneda_no_reajustable=0.0,
        moneda_reajustable_ipc=None,
        moneda_reajustable_tc=None,
        moneda_extranjera=None,
        moneda_total=0.0,
    )
    assert row.statement == "resultado"
    assert row.moneda_reajustable_ipc is None


def test_institution():
    inst = Institution(codigo_institucion="001", nombre_institucion="BANCO DE CHILE")
    assert inst.codigo_institucion == "001"


def test_capital_adequacy_guarda_raw():
    ca = CapitalAdequacy(
        activos_ponderados_riesgo=1.0,
        activos_totales=2.0,
        capital_basico=3.0,
        patrimonio_efectivo=None,
        provisiones_voluntarias=None,
        bonos_subordinados=None,
        interes_minoritario=None,
        indice_irs=None,
        indice_ire=None,
        raw={"x": 1},
    )
    assert ca.raw == {"x": 1}


def test_profile_shareholder_executive_existen():
    Profile(
        codigo_swift="BCHI", rut="97.004.000-5", direccion="AHUMADA 251", telefono="1",
        sitio_web="www", sucursales=222, oficinas=227, cajeros=1839, empleados=9919,
        emp_hombres_perm=4842, emp_mujeres_perm=5077, emp_hombres_ext=0, emp_mujeres_ext=0,
        fecha_publicacion="2024-12-01", raw={},
    )
    Shareholder(serie="U", rut="96929880", nombre="LQ INV", participacion=46.344,
                numero_acciones=46815289329.0)
    Executive(nombre="EBENSPERGER", cargo="Gerente General",
              fecha_asuncion="2016-05-01", tipo="1")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_models.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/models.py`:

```python
"""Dataclasses de las filas parseadas desde la API de bancos."""

from dataclasses import dataclass


@dataclass
class Institution:
    codigo_institucion: str
    nombre_institucion: str


@dataclass
class AccountRow:
    statement: str  # 'balance' | 'resultado'
    codigo_cuenta: str
    descripcion_cuenta: str
    moneda_no_reajustable: float | None
    moneda_reajustable_ipc: float | None
    moneda_reajustable_tc: float | None
    moneda_extranjera: float | None
    moneda_total: float | None


@dataclass
class CapitalAdequacy:
    activos_ponderados_riesgo: float | None
    activos_totales: float | None
    capital_basico: float | None
    patrimonio_efectivo: float | None
    provisiones_voluntarias: float | None
    bonos_subordinados: float | None
    interes_minoritario: float | None
    indice_irs: float | None
    indice_ire: float | None
    raw: dict


@dataclass
class Profile:
    codigo_swift: str | None
    rut: str | None
    direccion: str | None
    telefono: str | None
    sitio_web: str | None
    sucursales: int | None
    oficinas: int | None
    cajeros: int | None
    empleados: int | None
    emp_hombres_perm: int | None
    emp_mujeres_perm: int | None
    emp_hombres_ext: int | None
    emp_mujeres_ext: int | None
    fecha_publicacion: str | None
    raw: dict


@dataclass
class Shareholder:
    serie: str | None
    rut: str | None
    nombre: str | None
    participacion: float | None
    numero_acciones: float | None


@dataclass
class Executive:
    nombre: str
    cargo: str | None
    fecha_asuncion: str | None
    tipo: str | None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_models.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/models.py tests/banks/test_models.py
git commit -m "feat(banks): dataclasses de los modelos de datos"
```

---

### Task 6: Parsers de JSON de la API

**Files:**
- Create: `src/banks/ingest.py`
- Test: `tests/banks/test_ingest.py`

**Interfaces:**
- Consumes: `numbers.parse_spanish_number`, todos los modelos de `models.py`.
- Produces (funciones puras JSON -> modelos):
  - `parse_instituciones(payload: dict) -> list[Institution]`
  - `parse_accounts(payload: dict, statement: str) -> list[AccountRow]` (sirve para balances y resultados)
  - `parse_adecuacion_componentes(payload: dict) -> CapitalAdequacy`
  - `parse_adecuacion_indicador(payload: dict) -> float | None`
  - `parse_perfil(payload: dict) -> Profile | None`
  - `parse_accionistas(payload: dict) -> list[Shareholder]`
  - `parse_integrantes(payload: dict) -> list[Executive]`

Claves de nivel superior (verificadas): balances -> `CodigosBalances`; resultados -> `CodigosEstadosDeResultado`; instituciones -> `DescripcionesCodigosDeInstituciones`; adecuación componentes -> `AdecuacionDeCapital`; perfil -> `Perfiles` (lista con clave `Perfil`); accionistas -> `Accionistas` (cada item con `DescripcionAccionista`); integrantes -> `Integrantes` (cada item con `DescripcionIntegrante`).

`parse_adecuacion_indicador` es best-effort (no capturamos un sample real por 404 en períodos recientes): busca una clave `Valor`/`valor` numérica en el payload y la parsea; si no la halla, devuelve `None`.

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_ingest.py`:

```python
from src.banks import ingest


def test_parse_instituciones():
    payload = {
        "DescripcionesCodigosDeInstituciones": [
            {"CodigoInstitucion": "001", "NombreInstitucion": "BANCO DE CHILE"},
            {"CodigoInstitucion": "037", "NombreInstitucion": "BANCO SANTANDER-CHILE"},
        ]
    }
    insts = ingest.parse_instituciones(payload)
    assert len(insts) == 2
    assert insts[0].codigo_institucion == "001"
    assert insts[1].nombre_institucion == "BANCO SANTANDER-CHILE"


def test_parse_accounts_balance():
    payload = {
        "CodigosBalances": [
            {
                "CodigoCuenta": "145400401",
                "DescripcionCuenta": "Créditos por tarjetas de crédito",
                "Anho": 2025, "Mes": 5,
                "MonedaChilenaNoReajustable": "59878091792,00",
                "MonedaReajustablePorIPC": "0,00",
                "MonedaReajustablePorTipoDeCambio": "0,00",
                "MonedaExtranjera": "12004962095,00",
                "MonedaTotal": "71883053887,00",
            }
        ]
    }
    rows = ingest.parse_accounts(payload, "balance")
    assert len(rows) == 1
    r = rows[0]
    assert r.statement == "balance"
    assert r.codigo_cuenta == "145400401"
    assert r.moneda_no_reajustable == 59878091792.0
    assert r.moneda_total == 71883053887.0


def test_parse_accounts_resultado_sin_columnas_reajustables():
    payload = {
        "CodigosEstadosDeResultado": [
            {
                "CodigoCuenta": "434000000",
                "DescripcionCuenta": "RESULTADO FINANCIERO",
                "Anho": 2025, "Mes": 5,
                "MonedaChilenaNoReajustable": "0,00",
                "MonedaTotal": "0,00",
            }
        ]
    }
    rows = ingest.parse_accounts(payload, "resultado")
    r = rows[0]
    assert r.statement == "resultado"
    assert r.moneda_no_reajustable == 0.0
    assert r.moneda_reajustable_ipc is None
    assert r.moneda_extranjera is None


def test_parse_adecuacion_componentes():
    payload = {
        "AdecuacionDeCapital": [
            {
                "Componentes": {
                    "Activos": {
                        "PonderadosPorRiesgo": "29695297,67999566",
                        "Totales": "39989599,179371",
                    },
                    "PatrimonioEfectivo": {
                        "CapitalBasico": "3304152,128812",
                        "ProvisionesVoluntarias": "213251,877138",
                        "BonosSubordinados": "612594,382255",
                    },
                }
            }
        ]
    }
    ca = ingest.parse_adecuacion_componentes(payload)
    assert ca.activos_ponderados_riesgo == 29695297.67999566
    assert ca.capital_basico == 3304152.128812
    assert ca.bonos_subordinados == 612594.382255
    assert ca.raw == payload


def test_parse_adecuacion_indicador_best_effort():
    assert ingest.parse_adecuacion_indicador({"Indicador": [{"Valor": "12,34"}]}) == 12.34
    assert ingest.parse_adecuacion_indicador({"nada": 1}) is None


def test_parse_perfil():
    payload = {
        "Perfiles": [
            {
                "Perfil": {
                    "codigoSWIFT": "BCHI CL RM",
                    "rut": "97.004.000-5",
                    "direccionPrincipal": "AHUMADA 251",
                    "telefono": "(56-2) 653 11 11",
                    "direccionWeb": "www.bancochile.cl",
                    "sucursales": 222, "oficinas": 227, "cajeros": 1839, "empleados": 9919,
                    "emp_hombres_perm": 4842, "emp_mujereres_perm": 5077,
                    "fechaPublicacion": "2024-12-01",
                }
            }
        ]
    }
    p = ingest.parse_perfil(payload)
    assert p.codigo_swift == "BCHI CL RM"
    assert p.sucursales == 222
    assert p.empleados == 9919
    assert p.emp_mujeres_perm == 5077  # ojo: la API escribe 'emp_mujereres_perm'


def test_parse_accionistas():
    payload = {
        "Accionistas": [
            {
                "DescripcionAccionista": {
                    "Serie": "U", "Rut": "96929880", "Nombre": "LQ INV FINANCIERAS S.A.",
                    "Participacion": 46.344, "NumeroAcciones": "46815289329",
                }
            }
        ]
    }
    accs = ingest.parse_accionistas(payload)
    assert accs[0].serie == "U"
    assert accs[0].participacion == 46.344
    assert accs[0].numero_acciones == 46815289329.0


def test_parse_integrantes():
    payload = {
        "Integrantes": [
            {
                "DescripcionIntegrante": {
                    "Nombre": "EBENSPERGER ORREGO EDUARDO",
                    "Cargo": "Gerente General",
                    "FechaAsuncion": "2016-05-01",
                    "Tipo": "1",
                }
            }
        ]
    }
    ints = ingest.parse_integrantes(payload)
    assert ints[0].nombre == "EBENSPERGER ORREGO EDUARDO"
    assert ints[0].cargo == "Gerente General"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_ingest.py -v`
Expected: FAIL con `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/ingest.py`:

```python
"""Parsers puros: JSON de la API de bancos -> modelos."""

from src.banks.models import (
    AccountRow,
    CapitalAdequacy,
    Executive,
    Institution,
    Profile,
    Shareholder,
)
from src.banks.numbers import parse_spanish_number


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_instituciones(payload: dict) -> list[Institution]:
    items = payload.get("DescripcionesCodigosDeInstituciones", []) or []
    return [
        Institution(
            codigo_institucion=str(it.get("CodigoInstitucion")),
            nombre_institucion=it.get("NombreInstitucion", ""),
        )
        for it in items
    ]


def parse_accounts(payload: dict, statement: str) -> list[AccountRow]:
    key = "CodigosBalances" if statement == "balance" else "CodigosEstadosDeResultado"
    items = payload.get(key, []) or []
    rows: list[AccountRow] = []
    for it in items:
        rows.append(
            AccountRow(
                statement=statement,
                codigo_cuenta=str(it.get("CodigoCuenta")),
                descripcion_cuenta=it.get("DescripcionCuenta", ""),
                moneda_no_reajustable=parse_spanish_number(it.get("MonedaChilenaNoReajustable")),
                moneda_reajustable_ipc=parse_spanish_number(it.get("MonedaReajustablePorIPC")),
                moneda_reajustable_tc=parse_spanish_number(
                    it.get("MonedaReajustablePorTipoDeCambio")
                ),
                moneda_extranjera=parse_spanish_number(it.get("MonedaExtranjera")),
                moneda_total=parse_spanish_number(it.get("MonedaTotal")),
            )
        )
    return rows


def parse_adecuacion_componentes(payload: dict) -> CapitalAdequacy:
    items = payload.get("AdecuacionDeCapital", []) or []
    comp = (items[0].get("Componentes", {}) if items else {}) or {}
    activos = comp.get("Activos", {}) or {}
    patrimonio = comp.get("PatrimonioEfectivo", {}) or {}
    return CapitalAdequacy(
        activos_ponderados_riesgo=parse_spanish_number(activos.get("PonderadosPorRiesgo")),
        activos_totales=parse_spanish_number(activos.get("Totales")),
        capital_basico=parse_spanish_number(patrimonio.get("CapitalBasico")),
        patrimonio_efectivo=parse_spanish_number(patrimonio.get("Total")),
        provisiones_voluntarias=parse_spanish_number(patrimonio.get("ProvisionesVoluntarias")),
        bonos_subordinados=parse_spanish_number(patrimonio.get("BonosSubordinados")),
        interes_minoritario=parse_spanish_number(patrimonio.get("InteresMinoritario")),
        indice_irs=None,
        indice_ire=None,
        raw=payload,
    )


def parse_adecuacion_indicador(payload: dict) -> float | None:
    """Best-effort: busca una clave 'Valor'/'valor' numérica en el payload."""
    def _search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "valor":
                    parsed = parse_spanish_number(v) if isinstance(v, str) else v
                    if isinstance(parsed, (int, float)):
                        return float(parsed)
                found = _search(v)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _search(item)
                if found is not None:
                    return found
        return None

    return _search(payload)


def parse_perfil(payload: dict) -> Profile | None:
    items = payload.get("Perfiles", []) or []
    if not items:
        return None
    p = items[0].get("Perfil", {}) or {}
    return Profile(
        codigo_swift=(p.get("codigoSWIFT") or "").strip() or None,
        rut=(p.get("rut") or "").strip() or None,
        direccion=(p.get("direccionPrincipal") or "").strip() or None,
        telefono=(p.get("telefono") or "").strip() or None,
        sitio_web=(p.get("direccionWeb") or "").strip() or None,
        sucursales=_to_int(p.get("sucursales")),
        oficinas=_to_int(p.get("oficinas")),
        cajeros=_to_int(p.get("cajeros")),
        empleados=_to_int(p.get("empleados")),
        emp_hombres_perm=_to_int(p.get("emp_hombres_perm")),
        # La API escribe la clave con typo: 'emp_mujereres_perm'.
        emp_mujeres_perm=_to_int(p.get("emp_mujereres_perm", p.get("emp_mujeres_perm"))),
        emp_hombres_ext=_to_int(p.get("emp_hombres_ext")),
        emp_mujeres_ext=_to_int(p.get("emp_mujeres_ext")),
        fecha_publicacion=(p.get("fechaPublicacion") or "").strip() or None,
        raw=p,
    )


def parse_accionistas(payload: dict) -> list[Shareholder]:
    items = payload.get("Accionistas", []) or []
    out: list[Shareholder] = []
    for it in items:
        d = it.get("DescripcionAccionista", {}) or {}
        out.append(
            Shareholder(
                serie=d.get("Serie"),
                rut=d.get("Rut"),
                nombre=d.get("Nombre"),
                participacion=d.get("Participacion")
                if isinstance(d.get("Participacion"), (int, float))
                else parse_spanish_number(d.get("Participacion")),
                numero_acciones=parse_spanish_number(str(d.get("NumeroAcciones")))
                if d.get("NumeroAcciones") is not None
                else None,
            )
        )
    return out


def parse_integrantes(payload: dict) -> list[Executive]:
    items = payload.get("Integrantes", []) or []
    out: list[Executive] = []
    for it in items:
        d = it.get("DescripcionIntegrante", {}) or {}
        out.append(
            Executive(
                nombre=d.get("Nombre", ""),
                cargo=d.get("Cargo"),
                fecha_asuncion=d.get("FechaAsuncion"),
                tipo=d.get("Tipo"),
            )
        )
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_ingest.py -v`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
git add src/banks/ingest.py tests/banks/test_ingest.py
git commit -m "feat(banks): parsers de JSON de la API a modelos"
```

---

### Task 7: Esquema SQL + fixture de BD + apply_schema

**Files:**
- Create: `sql/bank_schema.sql`
- Create: `src/banks/loader.py`
- Create: `tests/banks/conftest.py`
- Test: `tests/banks/test_schema.py`

**Interfaces:**
- Consumes: `.env` (credenciales PG).
- Produces:
  - `sql/bank_schema.sql` con el DDL idempotente completo (todas las tablas `bank_*` del spec).
  - `class BankLoader` en `src/banks/loader.py` con `__init__(self, conn)` y `apply_schema(self, sql_path: str = "sql/bank_schema.sql") -> None`.
  - Fixture pytest `db_conn` en `tests/banks/conftest.py`: conecta con `.env`, hace `apply_schema` dentro de la transacción, cede la conexión, y al final hace `ROLLBACK` (no persiste nada). Hace `skip` si no hay `.env` o no conecta.

- [ ] **Step 1: Write the failing test**

Create `sql/bank_schema.sql` con el DDL completo (copiar verbatim del spec, sección "Esquema de base de datos": las 8 tablas `bank_institutions`, `bank_accounts`, `bank_financial_data` con su índice, `bank_capital_adequacy`, `bank_profiles`, `bank_shareholders`, `bank_executives`, `bank_data_imports`, todas con `CREATE TABLE IF NOT EXISTS` y `CREATE INDEX IF NOT EXISTS`).

Create `tests/banks/conftest.py`:

```python
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k] = v
    return env


@pytest.fixture
def db_conn():
    try:
        import psycopg2
    except ImportError:
        pytest.skip("psycopg2 no disponible")
    env = _load_env(REPO_ROOT / ".env")
    if not env.get("PGHOST"):
        pytest.skip("sin .env con credenciales PG")
    try:
        conn = psycopg2.connect(
            host=env["PGHOST"], port=env.get("PGPORT", "5432"),
            dbname=env["PGDATABASE"], user=env["PGUSER"], password=env["PGPASSWORD"],
        )
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"no se pudo conectar a la BD: {exc}")
    conn.autocommit = False
    try:
        yield conn
    finally:
        conn.rollback()
        conn.close()
```

Create `tests/banks/test_schema.py`:

```python
from src.banks.loader import BankLoader


def test_apply_schema_crea_tablas(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    cur = db_conn.cursor()
    cur.execute(
        "select table_name from information_schema.tables "
        "where table_schema='public' and table_name like 'bank_%'"
    )
    tablas = {r[0] for r in cur.fetchall()}
    esperadas = {
        "bank_institutions", "bank_accounts", "bank_financial_data",
        "bank_capital_adequacy", "bank_profiles", "bank_shareholders",
        "bank_executives", "bank_data_imports",
    }
    assert esperadas <= tablas
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_schema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.banks.loader'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/loader.py`:

```python
"""Carga de data de bancos a Postgres (tablas bank_*)."""

from pathlib import Path


class BankLoader:
    def __init__(self, conn):
        self.conn = conn

    def apply_schema(self, sql_path: str = "sql/bank_schema.sql") -> None:
        sql = Path(sql_path).read_text()
        with self.conn.cursor() as cur:
            cur.execute(sql)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_schema.py -v`
Expected: PASS (1 passed). Si no hay BD/`.env`, el test hace SKIP (aceptable).

- [ ] **Step 5: Commit**

```bash
git add sql/bank_schema.sql src/banks/loader.py tests/banks/conftest.py tests/banks/test_schema.py
git commit -m "feat(banks): esquema SQL y apply_schema con fixture de BD"
```

---

### Task 8: Upserts núcleo (instituciones, cuentas, hechos financieros)

**Files:**
- Modify: `src/banks/loader.py`
- Test: `tests/banks/test_loader_core.py`

**Interfaces:**
- Consumes: modelos `Institution`, `AccountRow`; fixture `db_conn`.
- Produces, en `BankLoader`:
  - `upsert_institution(self, inst: Institution, rut: str | None = None, is_aggregate: bool = False) -> None`
  - `upsert_account(self, statement: str, codigo_cuenta: str, descripcion: str, epoch: str) -> int` (devuelve `account_id`)
  - `upsert_financial_row(self, cod: str, account_id: int, year: int, month: int, row: AccountRow, epoch: str, unit: str) -> None`

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_loader_core.py`:

```python
from src.banks.loader import BankLoader
from src.banks.models import AccountRow, Institution


def _row():
    return AccountRow(
        statement="balance", codigo_cuenta="145400401",
        descripcion_cuenta="Créditos por tarjetas", moneda_no_reajustable=59878091792.0,
        moneda_reajustable_ipc=0.0, moneda_reajustable_tc=0.0,
        moneda_extranjera=12004962095.0, moneda_total=71883053887.0,
    )


def test_upsert_institution_y_financial_row(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    loader.upsert_institution(Institution("001", "BANCO DE CHILE"), rut="97004000-5")
    account_id = loader.upsert_account("balance", "145400401", "Créditos por tarjetas",
                                       "compendio_2022")
    assert isinstance(account_id, int)
    loader.upsert_financial_row("001", account_id, 2025, 5, _row(),
                                "compendio_2022", "CLP")

    cur = db_conn.cursor()
    cur.execute(
        "select moneda_total, unit from bank_financial_data "
        "where codigo_institucion='001' and account_id=%s and period_year=2025 "
        "and period_month=5", (account_id,),
    )
    total, unit = cur.fetchone()
    assert float(total) == 71883053887.0
    assert unit == "CLP"


def test_upsert_financial_row_es_idempotente(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    loader.upsert_institution(Institution("001", "BANCO DE CHILE"))
    account_id = loader.upsert_account("balance", "145400401", "x", "compendio_2022")
    loader.upsert_financial_row("001", account_id, 2025, 5, _row(), "compendio_2022", "CLP")
    loader.upsert_financial_row("001", account_id, 2025, 5, _row(), "compendio_2022", "CLP")
    cur = db_conn.cursor()
    cur.execute(
        "select count(*) from bank_financial_data where codigo_institucion='001' "
        "and account_id=%s", (account_id,),
    )
    assert cur.fetchone()[0] == 1


def test_upsert_account_mismo_codigo_no_duplica(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    a1 = loader.upsert_account("balance", "100000000", "TOTAL ACTIVOS", "compendio_2022")
    a2 = loader.upsert_account("balance", "100000000", "TOTAL ACTIVOS", "compendio_2022")
    assert a1 == a2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_loader_core.py -v`
Expected: FAIL con `AttributeError: 'BankLoader' object has no attribute 'upsert_institution'`.

- [ ] **Step 3: Write minimal implementation**

Añadir a `src/banks/loader.py` (importar los modelos arriba y agregar los métodos a `BankLoader`):

```python
from src.banks.models import AccountRow, Institution
```

```python
    def upsert_institution(
        self, inst: Institution, rut: str | None = None, is_aggregate: bool = False
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_institutions
                    (codigo_institucion, nombre_institucion, rut, is_aggregate)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (codigo_institucion) DO UPDATE SET
                    nombre_institucion = EXCLUDED.nombre_institucion,
                    rut = COALESCE(EXCLUDED.rut, bank_institutions.rut),
                    is_aggregate = EXCLUDED.is_aggregate,
                    updated_at = now()
                """,
                (inst.codigo_institucion, inst.nombre_institucion, rut, is_aggregate),
            )

    def upsert_account(
        self, statement: str, codigo_cuenta: str, descripcion: str, epoch: str
    ) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_accounts
                    (statement, codigo_cuenta, descripcion_cuenta, taxonomy_epoch)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (statement, codigo_cuenta, taxonomy_epoch) DO UPDATE SET
                    descripcion_cuenta = EXCLUDED.descripcion_cuenta,
                    updated_at = now()
                RETURNING id
                """,
                (statement, codigo_cuenta, descripcion, epoch),
            )
            return cur.fetchone()[0]

    def upsert_financial_row(
        self, cod: str, account_id: int, year: int, month: int,
        row: AccountRow, epoch: str, unit: str,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_financial_data
                    (codigo_institucion, account_id, period_year, period_month,
                     moneda_no_reajustable, moneda_reajustable_ipc, moneda_reajustable_tc,
                     moneda_extranjera, moneda_total, taxonomy_epoch, unit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_institucion, account_id, period_year, period_month)
                DO UPDATE SET
                    moneda_no_reajustable = EXCLUDED.moneda_no_reajustable,
                    moneda_reajustable_ipc = EXCLUDED.moneda_reajustable_ipc,
                    moneda_reajustable_tc = EXCLUDED.moneda_reajustable_tc,
                    moneda_extranjera = EXCLUDED.moneda_extranjera,
                    moneda_total = EXCLUDED.moneda_total,
                    taxonomy_epoch = EXCLUDED.taxonomy_epoch,
                    unit = EXCLUDED.unit,
                    updated_at = now()
                """,
                (cod, account_id, year, month,
                 row.moneda_no_reajustable, row.moneda_reajustable_ipc,
                 row.moneda_reajustable_tc, row.moneda_extranjera, row.moneda_total,
                 epoch, unit),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_loader_core.py -v`
Expected: PASS (3 passed) o SKIP sin BD.

- [ ] **Step 5: Commit**

```bash
git add src/banks/loader.py tests/banks/test_loader_core.py
git commit -m "feat(banks): upserts de instituciones, cuentas y hechos financieros"
```

---

### Task 9: Upserts restantes (adecuación, perfil, accionistas, integrantes, log)

**Files:**
- Modify: `src/banks/loader.py`
- Test: `tests/banks/test_loader_rest.py`

**Interfaces:**
- Consumes: modelos `CapitalAdequacy`, `Profile`, `Shareholder`, `Executive`.
- Produces, en `BankLoader`:
  - `upsert_capital_adequacy(self, cod: str, year: int, month: int, ca: CapitalAdequacy) -> None`
  - `upsert_profile(self, cod: str, year: int, month: int, p: Profile) -> None`
  - `replace_shareholders(self, cod: str, year: int, month: int, rows: list[Shareholder]) -> None`
  - `replace_executives(self, cod: str, year: int, month: int, rows: list[Executive]) -> None`
  - `log_import(self, cod: str | None, report: str, year: int | None, month: int | None, status: str, rows_total: int = 0, rows_ok: int = 0, rows_failed: int = 0, message: str | None = None) -> None`

`replace_*` borra las filas del período antes de insertar (los accionistas/integrantes de un período son un set completo, no incremental).

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_loader_rest.py`:

```python
import json

from src.banks.loader import BankLoader
from src.banks.models import CapitalAdequacy, Executive, Profile, Shareholder


def _inst(loader):
    from src.banks.models import Institution
    loader.upsert_institution(Institution("001", "BANCO DE CHILE"))


def test_upsert_capital_adequacy_guarda_raw_como_jsonb(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    _inst(loader)
    ca = CapitalAdequacy(
        activos_ponderados_riesgo=29695297.68, activos_totales=39989599.18,
        capital_basico=3304152.13, patrimonio_efectivo=None,
        provisiones_voluntarias=213251.88, bonos_subordinados=612594.38,
        interes_minoritario=None, indice_irs=13.5, indice_ire=None, raw={"k": 1},
    )
    loader.upsert_capital_adequacy("001", 2018, 12, ca)
    cur = db_conn.cursor()
    cur.execute(
        "select capital_basico, indice_irs, raw from bank_capital_adequacy "
        "where codigo_institucion='001' and period_year=2018 and period_month=12"
    )
    cap, irs, raw = cur.fetchone()
    assert float(cap) == 3304152.13
    assert float(irs) == 13.5
    assert (raw if isinstance(raw, dict) else json.loads(raw)) == {"k": 1}


def test_replace_shareholders_reemplaza(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    _inst(loader)
    loader.replace_shareholders("001", 2024, 12, [
        Shareholder("U", "96929880", "LQ INV", 46.344, 46815289329.0),
        Shareholder("U", "111", "OTRO", 10.0, 1000.0),
    ])
    loader.replace_shareholders("001", 2024, 12, [
        Shareholder("U", "96929880", "LQ INV", 46.344, 46815289329.0),
    ])
    cur = db_conn.cursor()
    cur.execute(
        "select count(*) from bank_shareholders where codigo_institucion='001' "
        "and period_year=2024 and period_month=12"
    )
    assert cur.fetchone()[0] == 1


def test_upsert_profile_y_executives_y_log(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    _inst(loader)
    p = Profile(
        codigo_swift="BCHI", rut="97.004.000-5", direccion="AHUMADA 251", telefono="1",
        sitio_web="www", sucursales=222, oficinas=227, cajeros=1839, empleados=9919,
        emp_hombres_perm=4842, emp_mujeres_perm=5077, emp_hombres_ext=0, emp_mujeres_ext=0,
        fecha_publicacion="2024-12-01", raw={},
    )
    loader.upsert_profile("001", 2024, 12, p)
    loader.replace_executives("001", 2024, 12, [
        Executive("EBENSPERGER", "Gerente General", "2016-05-01", "1"),
    ])
    loader.log_import("001", "balance", 2025, 5, "completed", rows_total=100, rows_ok=100)

    cur = db_conn.cursor()
    cur.execute("select empleados from bank_profiles where codigo_institucion='001'")
    assert cur.fetchone()[0] == 9919
    cur.execute("select count(*) from bank_executives where codigo_institucion='001'")
    assert cur.fetchone()[0] == 1
    cur.execute("select status from bank_data_imports where report='balance'")
    assert cur.fetchone()[0] == "completed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_loader_rest.py -v`
Expected: FAIL con `AttributeError: ... has no attribute 'upsert_capital_adequacy'`.

- [ ] **Step 3: Write minimal implementation**

Añadir a `src/banks/loader.py`. Ampliar el import de modelos y añadir `import json` arriba:

```python
import json
```

```python
from src.banks.models import (
    AccountRow, CapitalAdequacy, Executive, Institution, Profile, Shareholder,
)
```

Métodos nuevos en `BankLoader`:

```python
    def upsert_capital_adequacy(
        self, cod: str, year: int, month: int, ca: CapitalAdequacy
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_capital_adequacy
                    (codigo_institucion, period_year, period_month,
                     activos_ponderados_riesgo, activos_totales, capital_basico,
                     patrimonio_efectivo, provisiones_voluntarias, bonos_subordinados,
                     interes_minoritario, indice_irs, indice_ire, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_institucion, period_year, period_month) DO UPDATE SET
                    activos_ponderados_riesgo = EXCLUDED.activos_ponderados_riesgo,
                    activos_totales = EXCLUDED.activos_totales,
                    capital_basico = EXCLUDED.capital_basico,
                    patrimonio_efectivo = EXCLUDED.patrimonio_efectivo,
                    provisiones_voluntarias = EXCLUDED.provisiones_voluntarias,
                    bonos_subordinados = EXCLUDED.bonos_subordinados,
                    interes_minoritario = EXCLUDED.interes_minoritario,
                    indice_irs = EXCLUDED.indice_irs,
                    indice_ire = EXCLUDED.indice_ire,
                    raw = EXCLUDED.raw,
                    updated_at = now()
                """,
                (cod, year, month, ca.activos_ponderados_riesgo, ca.activos_totales,
                 ca.capital_basico, ca.patrimonio_efectivo, ca.provisiones_voluntarias,
                 ca.bonos_subordinados, ca.interes_minoritario, ca.indice_irs,
                 ca.indice_ire, json.dumps(ca.raw)),
            )

    def upsert_profile(self, cod: str, year: int, month: int, p: Profile) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_profiles
                    (codigo_institucion, period_year, period_month, codigo_swift, rut,
                     direccion, telefono, sitio_web, sucursales, oficinas, cajeros,
                     empleados, emp_hombres_perm, emp_mujeres_perm, emp_hombres_ext,
                     emp_mujeres_ext, fecha_publicacion, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s)
                ON CONFLICT (codigo_institucion, period_year, period_month) DO UPDATE SET
                    codigo_swift = EXCLUDED.codigo_swift, rut = EXCLUDED.rut,
                    direccion = EXCLUDED.direccion, telefono = EXCLUDED.telefono,
                    sitio_web = EXCLUDED.sitio_web, sucursales = EXCLUDED.sucursales,
                    oficinas = EXCLUDED.oficinas, cajeros = EXCLUDED.cajeros,
                    empleados = EXCLUDED.empleados,
                    emp_hombres_perm = EXCLUDED.emp_hombres_perm,
                    emp_mujeres_perm = EXCLUDED.emp_mujeres_perm,
                    emp_hombres_ext = EXCLUDED.emp_hombres_ext,
                    emp_mujeres_ext = EXCLUDED.emp_mujeres_ext,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    raw = EXCLUDED.raw, updated_at = now()
                """,
                (cod, year, month, p.codigo_swift, p.rut, p.direccion, p.telefono,
                 p.sitio_web, p.sucursales, p.oficinas, p.cajeros, p.empleados,
                 p.emp_hombres_perm, p.emp_mujeres_perm, p.emp_hombres_ext,
                 p.emp_mujeres_ext, p.fecha_publicacion or None, json.dumps(p.raw)),
            )

    def replace_shareholders(
        self, cod: str, year: int, month: int, rows: list[Shareholder]
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bank_shareholders WHERE codigo_institucion=%s "
                "AND period_year=%s AND period_month=%s", (cod, year, month),
            )
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO bank_shareholders
                        (codigo_institucion, period_year, period_month, serie, rut,
                         nombre, participacion, numero_acciones)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codigo_institucion, period_year, period_month, rut, serie)
                    DO NOTHING
                    """,
                    (cod, year, month, r.serie, r.rut, r.nombre, r.participacion,
                     r.numero_acciones),
                )

    def replace_executives(
        self, cod: str, year: int, month: int, rows: list[Executive]
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bank_executives WHERE codigo_institucion=%s "
                "AND period_year=%s AND period_month=%s", (cod, year, month),
            )
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO bank_executives
                        (codigo_institucion, period_year, period_month, nombre, cargo,
                         fecha_asuncion, tipo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codigo_institucion, period_year, period_month, nombre, cargo)
                    DO NOTHING
                    """,
                    (cod, year, month, r.nombre, r.cargo, r.fecha_asuncion or None, r.tipo),
                )

    def log_import(
        self, cod: str | None, report: str, year: int | None, month: int | None,
        status: str, rows_total: int = 0, rows_ok: int = 0, rows_failed: int = 0,
        message: str | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_data_imports
                    (codigo_institucion, report, period_year, period_month, status,
                     rows_total, rows_ok, rows_failed, message, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (cod, report, year, month, status, rows_total, rows_ok, rows_failed,
                 message),
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_loader_rest.py -v`
Expected: PASS (3 passed) o SKIP sin BD.

- [ ] **Step 5: Commit**

```bash
git add src/banks/loader.py tests/banks/test_loader_rest.py
git commit -m "feat(banks): upserts de adecuacion, perfil, accionistas, integrantes y log"
```

---

### Task 10: Orquestación por período

**Files:**
- Create: `src/banks/runner.py`
- Test: `tests/banks/test_runner.py`

**Interfaces:**
- Consumes: `CMFApiClient` (o un doble con `.get(path)`), `BankLoader`, `endpoints`, `ingest`, `taxonomy`, `NoDataError`.
- Produces:
  - `REPORTS_DEFAULT: tuple[str, ...]` = `("balance", "resultado", "adecuacion", "perfil", "accionistas", "integrantes")`
  - `ingest_period(client, loader, cod: str, year: int, month: int, reports=REPORTS_DEFAULT) -> dict[str, str]` — devuelve `{report: status}` con status ∈ {`completed`, `no_data`, `failed`}; registra cada uno en `bank_data_imports`; nunca levanta por `NoDataError`.
  - `sync_institutions(client, loader, year: int, month: int) -> int` — puebla `bank_institutions` desde el catálogo; devuelve cuántas.

`ingest_period` para cada report: llama al endpoint, parsea, hace upsert; ante `NoDataError` -> status `no_data`; ante `ApiError` u otra excepción -> status `failed` (no aborta los demás reports).

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_runner.py`:

```python
from src.banks import runner
from src.banks.api_client import NoDataError


class FakeClient:
    """Devuelve payloads por path-substring; levanta NoDataError si el path matchea no_data."""
    def __init__(self, by_key: dict, no_data=()):
        self.by_key = by_key
        self.no_data = no_data

    def get(self, path):
        for token in self.no_data:
            if token in path:
                raise NoDataError("sin datos")
        for token, payload in self.by_key.items():
            if token in path:
                return payload
        raise NoDataError("sin datos")


def test_sync_institutions(db_conn):
    from src.banks.loader import BankLoader
    loader = BankLoader(db_conn)
    loader.apply_schema()
    client = FakeClient({
        "instituciones": {
            "DescripcionesCodigosDeInstituciones": [
                {"CodigoInstitucion": "001", "NombreInstitucion": "BANCO DE CHILE"},
                {"CodigoInstitucion": "999", "NombreInstitucion": "SISTEMA FINANCIERO"},
            ]
        }
    })
    n = runner.sync_institutions(client, loader, 2025, 5)
    assert n == 2
    cur = db_conn.cursor()
    cur.execute("select is_aggregate from bank_institutions where codigo_institucion='999'")
    assert cur.fetchone()[0] is True


def test_ingest_period_mezcla_completed_y_no_data(db_conn):
    from src.banks.loader import BankLoader
    loader = BankLoader(db_conn)
    loader.apply_schema()
    loader.upsert_institution.__self__  # noop para claridad
    from src.banks.models import Institution
    loader.upsert_institution(Institution("001", "BANCO DE CHILE"))
    client = FakeClient(
        by_key={
            "balances/2025/5/instituciones/001": {
                "CodigosBalances": [{
                    "CodigoCuenta": "100000000", "DescripcionCuenta": "TOTAL ACTIVOS",
                    "MonedaChilenaNoReajustable": "1,00", "MonedaTotal": "1,00",
                }]
            },
        },
        no_data=("resultados", "adecuacion", "perfil", "accionistas", "integrantes"),
    )
    result = runner.ingest_period(client, loader, "001", 2025, 5)
    assert result["balance"] == "completed"
    assert result["resultado"] == "no_data"
    cur = db_conn.cursor()
    cur.execute("select count(*) from bank_financial_data where codigo_institucion='001'")
    assert cur.fetchone()[0] == 1
    cur.execute("select count(*) from bank_data_imports where status='no_data'")
    assert cur.fetchone()[0] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_runner.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'src.banks.runner'`.

- [ ] **Step 3: Write minimal implementation**

Create `src/banks/runner.py`:

```python
"""Orquestación: baja los recursos de un banco/período y los carga a la BD."""

from src.banks import endpoints, ingest
from src.banks.api_client import NoDataError
from src.banks.taxonomy import classify_epoch, classify_unit

REPORTS_DEFAULT = ("balance", "resultado", "adecuacion", "perfil", "accionistas",
                   "integrantes")

_AGGREGATE_CODES = {"999"}


def sync_institutions(client, loader, year: int, month: int) -> int:
    payload = client.get(endpoints.instituciones_path(year, month))
    insts = ingest.parse_instituciones(payload)
    for inst in insts:
        loader.upsert_institution(
            inst, is_aggregate=inst.codigo_institucion in _AGGREGATE_CODES
        )
    return len(insts)


def _ingest_accounts(client, loader, cod, year, month, statement, path) -> str:
    payload = client.get(path)
    rows = ingest.parse_accounts(payload, statement)
    epoch = classify_epoch(year, month)
    unit = classify_unit(year, month)
    ok = 0
    for row in rows:
        account_id = loader.upsert_account(
            statement, row.codigo_cuenta, row.descripcion_cuenta, epoch
        )
        loader.upsert_financial_row(cod, account_id, year, month, row, epoch, unit)
        ok += 1
    loader.log_import(cod, statement, year, month, "completed", rows_total=len(rows),
                      rows_ok=ok)
    return "completed"


def _ingest_adecuacion(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.adecuacion_componentes_path(year, month, cod))
    ca = ingest.parse_adecuacion_componentes(payload)
    for attr, indicador in (("indice_irs", "irs"), ("indice_ire", "ire")):
        try:
            ind_payload = client.get(
                endpoints.adecuacion_indicador_path(year, month, cod, indicador)
            )
            setattr(ca, attr, ingest.parse_adecuacion_indicador(ind_payload))
        except NoDataError:
            pass
    loader.upsert_capital_adequacy(cod, year, month, ca)
    loader.log_import(cod, "adecuacion", year, month, "completed", rows_total=1, rows_ok=1)
    return "completed"


def _ingest_perfil(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.perfil_path(cod, year, month))
    profile = ingest.parse_perfil(payload)
    if profile is None:
        raise NoDataError("perfil vacío")
    loader.upsert_profile(cod, year, month, profile)
    loader.log_import(cod, "perfil", year, month, "completed", rows_total=1, rows_ok=1)
    return "completed"


def _ingest_accionistas(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.accionistas_path(cod, year, month))
    rows = ingest.parse_accionistas(payload)
    loader.replace_shareholders(cod, year, month, rows)
    loader.log_import(cod, "accionistas", year, month, "completed", rows_total=len(rows),
                      rows_ok=len(rows))
    return "completed"


def _ingest_integrantes(client, loader, cod, year, month) -> str:
    payload = client.get(endpoints.integrantes_path(cod, year, month))
    rows = ingest.parse_integrantes(payload)
    loader.replace_executives(cod, year, month, rows)
    loader.log_import(cod, "integrantes", year, month, "completed", rows_total=len(rows),
                      rows_ok=len(rows))
    return "completed"


def ingest_period(client, loader, cod: str, year: int, month: int,
                  reports=REPORTS_DEFAULT) -> dict[str, str]:
    dispatch = {
        "balance": lambda: _ingest_accounts(
            client, loader, cod, year, month, "balance",
            endpoints.balance_path(year, month, cod)),
        "resultado": lambda: _ingest_accounts(
            client, loader, cod, year, month, "resultado",
            endpoints.resultado_path(year, month, cod)),
        "adecuacion": lambda: _ingest_adecuacion(client, loader, cod, year, month),
        "perfil": lambda: _ingest_perfil(client, loader, cod, year, month),
        "accionistas": lambda: _ingest_accionistas(client, loader, cod, year, month),
        "integrantes": lambda: _ingest_integrantes(client, loader, cod, year, month),
    }
    result: dict[str, str] = {}
    for report in reports:
        try:
            result[report] = dispatch[report]()
        except NoDataError:
            loader.log_import(cod, report, year, month, "no_data")
            result[report] = "no_data"
        except Exception as exc:  # noqa: BLE001 - un report que falla no aborta los demás
            loader.log_import(cod, report, year, month, "failed", message=str(exc))
            result[report] = "failed"
    return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_runner.py -v`
Expected: PASS (2 passed) o SKIP sin BD.

- [ ] **Step 5: Commit**

```bash
git add src/banks/runner.py tests/banks/test_runner.py
git commit -m "feat(banks): orquestacion de ingesta por periodo"
```

---

### Task 11: CLI de ingesta

**Files:**
- Create: `scripts/ingest_banks.py`
- Test: `tests/banks/test_cli.py`

**Interfaces:**
- Consumes: `runner`, `BankLoader`, `CMFApiClient`; `.env` (`CMF_API_KEY`, `PG*`).
- Produces (funciones testeables sin red ni BD):
  - `parse_period(text: str) -> tuple[int, int]` — `"MM/YYYY"` -> `(year, month)`; levanta `ValueError` si es inválido.
  - `iter_months(desde: tuple[int, int], hasta: tuple[int, int]) -> list[tuple[int, int]]` — lista inclusiva de `(year, month)`.
  - `build_arg_parser() -> argparse.ArgumentParser` con flags `--from`, `--to`, `--banks` (csv de códigos; default todos del catálogo), `--reports` (csv; default todos), `--only`, `--dry-run`.
  - `main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing test**

Create `tests/banks/test_cli.py`:

```python
import pytest

from scripts.ingest_banks import iter_months, parse_period


def test_parse_period_ok():
    assert parse_period("05/2025") == (2025, 5)
    assert parse_period("12/2010") == (2010, 12)


def test_parse_period_invalido():
    with pytest.raises(ValueError):
        parse_period("2025-05")
    with pytest.raises(ValueError):
        parse_period("13/2025")


def test_iter_months_inclusivo_y_cruza_anho():
    assert iter_months((2024, 11), (2025, 2)) == [
        (2024, 11), (2024, 12), (2025, 1), (2025, 2),
    ]


def test_iter_months_un_solo_mes():
    assert iter_months((2025, 5), (2025, 5)) == [(2025, 5)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/banks/test_cli.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'scripts.ingest_banks'` (o `scripts` sin `__init__`). Si `scripts` no es importable, crear `scripts/__init__.py` vacío como parte del Step 3.

- [ ] **Step 3: Write minimal implementation**

Create `scripts/__init__.py` si no existe (vacío):

```python
```

Create `scripts/ingest_banks.py`:

```python
#!/usr/bin/env python3
"""CLI: ingesta de bancos desde la API CMF a la base.

Ejemplos:
    python scripts/ingest_banks.py --from 01/2022 --to 05/2025
    python scripts/ingest_banks.py --from 05/2025 --to 05/2025 --only 001 --dry-run
"""

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.banks import runner  # noqa: E402
from src.banks.api_client import CMFApiClient  # noqa: E402
from src.banks.loader import BankLoader  # noqa: E402


def parse_period(text: str) -> tuple[int, int]:
    if "/" not in text:
        raise ValueError(f"Período inválido '{text}', use MM/YYYY")
    mm, yyyy = text.split("/", 1)
    month, year = int(mm), int(yyyy)
    if not (1 <= month <= 12):
        raise ValueError(f"Mes fuera de rango: {month}")
    if not (2000 <= year <= 2100):
        raise ValueError(f"Año fuera de rango: {year}")
    return (year, month)


def iter_months(desde: tuple[int, int], hasta: tuple[int, int]) -> list[tuple[int, int]]:
    (y0, m0), (y1, m1) = desde, hasta
    out: list[tuple[int, int]] = []
    y, m = y0, m0
    while (y, m) <= (y1, m1):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


def load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k] = v
    return env


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ingesta de bancos desde la API CMF")
    p.add_argument("--from", dest="desde", required=True, help="Período inicial MM/YYYY")
    p.add_argument("--to", dest="hasta", required=True, help="Período final MM/YYYY")
    p.add_argument("--banks", default="", help="Códigos separados por coma; vacío = todos")
    p.add_argument("--only", default="", help="Alias de --banks para un solo código")
    p.add_argument("--reports", default="", help="Reports separados por coma; vacío = todos")
    p.add_argument("--dry-run", action="store_true", help="No escribe a la base")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    desde = parse_period(args.desde)
    hasta = parse_period(args.hasta)
    meses = iter_months(desde, hasta)
    reports = tuple(r.strip() for r in args.reports.split(",") if r.strip()) \
        or runner.REPORTS_DEFAULT
    codes = [c.strip() for c in (args.banks or args.only).split(",") if c.strip()]

    env = load_env(REPO_ROOT / ".env")
    apikey = env.get("CMF_API_KEY")
    if not apikey:
        print("Falta CMF_API_KEY en .env", file=sys.stderr)
        return 2

    client = CMFApiClient(apikey, pause=0.2)

    if args.dry_run:
        print(f"[dry-run] meses={len(meses)} reports={reports} bancos={codes or 'todos'}")
        return 0

    import psycopg2

    conn = psycopg2.connect(
        host=env["PGHOST"], port=env.get("PGPORT", "5432"), dbname=env["PGDATABASE"],
        user=env["PGUSER"], password=env["PGPASSWORD"],
    )
    conn.autocommit = False
    loader = BankLoader(conn)
    try:
        loader.apply_schema()
        conn.commit()
        first_y, first_m = meses[0]
        runner.sync_institutions(client, loader, first_y, first_m)
        conn.commit()
        if not codes:
            with conn.cursor() as cur:
                cur.execute("SELECT codigo_institucion FROM bank_institutions ORDER BY 1")
                codes = [r[0] for r in cur.fetchall()]
        for (y, m) in meses:
            for cod in codes:
                result = runner.ingest_period(client, loader, cod, y, m, reports)
                conn.commit()
                done = sum(1 for s in result.values() if s == "completed")
                print(f"{y}-{m:02d} {cod}: {done}/{len(result)} completed")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/banks/test_cli.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Run the full suite and a real smoke test**

Run: `.venv/bin/pytest tests/banks -v`
Expected: todos PASS (o SKIP los de BD si no hay `.env`).

Smoke real (un banco, un mes, escribe a la base):
Run: `.venv/bin/python scripts/ingest_banks.py --from 05/2025 --to 05/2025 --only 001`
Expected: imprime `2025-05 001: N/6 completed` y crea filas en `bank_financial_data`.

- [ ] **Step 6: Commit**

```bash
git add scripts/__init__.py scripts/ingest_banks.py tests/banks/test_cli.py
git commit -m "feat(banks): CLI de ingesta de bancos"
```

---

## Self-Review

**Spec coverage:**
- Cliente API + auth + no-data + reintentos -> Task 4.
- Endpoints de los 6 recursos + catálogo -> Task 3.
- Parser de números ES -> Task 1.
- Época/unidad (quiebre 2022) -> Task 2.
- Modelos -> Task 5; parsers JSON -> Task 6.
- Tablas `bank_*` (DDL idempotente, sin tocar existentes) -> Task 7; upserts -> Tasks 8-9.
- Adecuación componentes + indicadores (best-effort) -> Task 6 (parse) + Task 9 (upsert) + Task 10 (fetch de indicadores).
- Perfil/accionistas/integrantes -> Tasks 6, 9, 10.
- Log de imports + manejo de huecos (no_data no aborta) -> Tasks 9, 10.
- Historia completa + mensual + idempotencia (ON CONFLICT) -> Tasks 8-10.
- CLI con --from/--to/--banks/--reports/--only/--dry-run -> Task 11.
- Sin cambios a tablas existentes -> solo se crean `bank_*` (Task 7).

**Placeholder scan:** sin TBD/TODO; todo el código está completo. La única parte marcada "best-effort" (parse_adecuacion_indicador) tiene implementación real y test.

**Type consistency:** `BankLoader` métodos y firmas usados en runner (Task 10) coinciden con los definidos en Tasks 8-9. `parse_accounts(payload, statement)` firma consistente entre Task 6 y su uso en Task 10. `REPORTS_DEFAULT` y `ingest_period` consistentes entre Task 10 y su uso en Task 11.

## Notas de ejecución

- Los tests de BD (Tasks 7-10) requieren `.env` con credenciales PG y red; si faltan, hacen SKIP. Corren contra la Supabase real pero dentro de una transacción con ROLLBACK, así que no persisten nada.
- La primera carga histórica (2010+ x 21 bancos x 12 meses x 6 reports) es larga; usar `--only` y rangos acotados para reanudar por tramos.
