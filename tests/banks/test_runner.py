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
    codes = runner.sync_institutions(client, loader, 2025, 5)
    assert len(codes) == 2
    assert "001" in codes
    cur = db_conn.cursor()
    cur.execute("select is_aggregate from bank_institutions where codigo_institucion='999'")
    assert cur.fetchone()[0] is True


def test_ingest_period_mezcla_completed_y_no_data(db_conn):
    from src.banks.loader import BankLoader
    loader = BankLoader(db_conn)
    loader.apply_schema()
    from src.banks.models import Institution
    loader.upsert_institution(Institution("000", "BANCO DE CHILE"))
    client = FakeClient(
        by_key={
            "balances/2025/5/instituciones/000": {
                "CodigosBalances": [{
                    "CodigoCuenta": "100000000", "DescripcionCuenta": "TOTAL ACTIVOS",
                    "MonedaChilenaNoReajustable": "1,00", "MonedaTotal": "1,00",
                }]
            },
        },
        no_data=("resultados", "adecuacion", "perfil", "accionistas", "integrantes"),
    )
    result = runner.ingest_period(client, loader, "000", 2025, 5)
    assert result["balance"] == "completed"
    assert result["resultado"] == "no_data"
    cur = db_conn.cursor()
    cur.execute("select count(*) from bank_financial_data where codigo_institucion='000'")
    assert cur.fetchone()[0] == 1
    cur.execute("select count(*) from bank_data_imports where status='no_data'")
    assert cur.fetchone()[0] >= 1
