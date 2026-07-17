import json

from src.banks.loader import BankLoader
from src.banks.models import CapitalAdequacy, Executive, Profile, Shareholder


def _inst(loader):
    from src.banks.models import Institution
    loader.upsert_institution(Institution("000", "BANCO SINTETICO TEST"))


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
    loader.upsert_capital_adequacy("000", 2018, 12, ca)
    cur = db_conn.cursor()
    cur.execute(
        "select capital_basico, indice_irs, raw from bank_capital_adequacy "
        "where codigo_institucion='000' and period_year=2018 and period_month=12"
    )
    cap, irs, raw = cur.fetchone()
    assert float(cap) == 3304152.13
    assert float(irs) == 13.5
    assert (raw if isinstance(raw, dict) else json.loads(raw)) == {"k": 1}


def test_replace_shareholders_reemplaza(db_conn):
    loader = BankLoader(db_conn)
    loader.apply_schema()
    _inst(loader)
    loader.replace_shareholders("000", 2024, 12, [
        Shareholder("U", "96929880", "LQ INV", 46.344, 46815289329.0),
        Shareholder("U", "111", "OTRO", 10.0, 1000.0),
    ])
    loader.replace_shareholders("000", 2024, 12, [
        Shareholder("U", "96929880", "LQ INV", 46.344, 46815289329.0),
    ])
    cur = db_conn.cursor()
    cur.execute(
        "select count(*) from bank_shareholders where codigo_institucion='000' "
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
    loader.upsert_profile("000", 2024, 12, p)
    loader.replace_executives("000", 2024, 12, [
        Executive("EBENSPERGER", "Gerente General", "2016-05-01", "1"),
    ])
    loader.log_import("000", "balance", 2025, 5, "completed", rows_total=100, rows_ok=100)

    cur = db_conn.cursor()
    cur.execute("select empleados from bank_profiles where codigo_institucion='000'")
    assert cur.fetchone()[0] == 9919
    cur.execute("select count(*) from bank_executives where codigo_institucion='000'")
    assert cur.fetchone()[0] == 1
    cur.execute(
        "select status from bank_data_imports where report='balance' "
        "and codigo_institucion='000'"
    )
    assert cur.fetchone()[0] == "completed"
