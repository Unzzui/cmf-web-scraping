"""Tests del runner: sobre todo, que un fallo se pueda LEER."""

import pytest

from src.edgar.api_client import NoDataError
from src.edgar.loader import EdgarLoader
from src.edgar.runner import ingest_company
from tests.edgar.conftest import FY24_END, FY24_START, fact, payload


class _FakeClient:
    def __init__(self, result):
        self.result = result

    def get_companyfacts(self, cik):
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _FakeLoader:
    """Loader en memoria que imita lo que importa: que log_import puede fallar."""

    def __init__(self, log_explota=False):
        self.dry_run = False
        self.log_explota = log_explota
        self.rollbacks = 0
        self.logs = []

    def company_by_cik(self, cik):
        return (523, "AAPL")

    def rollback(self):
        self.rollbacks += 1

    def log_import(self, company_id, source, total, ok, status, error=None):
        if self.log_explota:
            raise RuntimeError("current transaction is aborted")
        self.logs.append((status, error))

    def upsert_line_items(self, company_id, values, tags):
        return {v.display_order: v.display_order for v in values}

    def upsert_financial_data(self, company_id, values, ids):
        return len(values)


def test_no_data_no_revienta_el_lote():
    """El caso XOM: companyfacts responde 200 pero sin us-gaap (sólo `ffd`)."""
    p = payload({})
    p["facts"] = {"ffd": {"TtlFeeAmt": {"label": "x", "units": {"USD": []}}}}
    loader = _FakeLoader()
    result = ingest_company(_FakeClient(p), loader, "0002115436")
    assert result.status == "no_data"
    assert "ffd" in result.message  # dice QUÉ trajo, no adivina el motivo
    assert loader.logs == [("no_data", result.message)]


def test_si_log_import_falla_no_tapa_el_error_original():
    """El bug real: `import_status` tenía un CHECK que rechazaba 'no_data', el log moría,
    y la excepción del log ('current transaction is aborted') tapaba la causa. El lote
    entero se caía por no poder registrar un no_data."""
    loader = _FakeLoader(log_explota=True)
    p = payload({})
    p["facts"] = {"ffd": {}}
    result = ingest_company(_FakeClient(p), loader, "0002115436")
    assert result.status == "no_data"
    assert "us-gaap" in result.message  # sobrevive el motivo real
    assert loader.rollbacks >= 1


def test_error_de_red_se_reporta_y_no_lanza():
    loader = _FakeLoader()
    result = ingest_company(_FakeClient(NoDataError("404")), loader, "0000320193")
    assert result.status == "no_data"
    assert loader.rollbacks >= 1


def test_cik_que_no_esta_en_companies_se_saltea():
    class _SinEmpresa(_FakeLoader):
        def company_by_cik(self, cik):
            return None

    result = ingest_company(_FakeClient({}), _SinEmpresa(), "0000000001")
    assert result.status == "skipped"
    assert "market='US'" in result.message


def test_empresa_ok():
    tag = "RevenueFromContractWithCustomerExcludingAssessedTax"
    p = payload({
        tag: [fact(391_035, FY24_END, FY24_START, "10-K", "2024-11-01")],
        "Assets": [fact(364_980, FY24_END, None, "10-K", "2024-11-01")],
        "LiabilitiesAndStockholdersEquity": [
            fact(364_980, FY24_END, None, "10-K", "2024-11-01")
        ],
    })
    loader = _FakeLoader()
    result = ingest_company(_FakeClient(p), loader, "0000320193")
    assert result.status == "completed"
    assert result.identity_errors == 0
    assert result.cells > 0
    assert loader.logs[0][0] == "completed"


@pytest.mark.parametrize("status,esperado", [
    ("completed", "completed"), ("no_data", "failed"),
    ("failed", "failed"), ("skipped", "failed"),
])
def test_status_se_mapea_a_los_4_valores_que_admite_el_check(status, esperado):
    """`financial_data_imports.import_status` sólo admite pending/processing/completed/
    failed. El vocabulario del runner es más fino y se mapea al escribir."""
    assert EdgarLoader._IMPORT_STATUS[status] == esperado
