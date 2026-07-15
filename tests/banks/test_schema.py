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
