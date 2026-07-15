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
