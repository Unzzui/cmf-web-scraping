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
        codigo_swift="BCHI",
        rut="97.004.000-5",
        direccion="AHUMADA 251",
        telefono="1",
        sitio_web="www",
        sucursales=222,
        oficinas=227,
        cajeros=1839,
        empleados=9919,
        emp_hombres_perm=4842,
        emp_mujeres_perm=5077,
        emp_hombres_ext=0,
        emp_mujeres_ext=0,
        fecha_publicacion="2024-12-01",
        raw={},
    )
    Shareholder(
        serie="U",
        rut="96929880",
        nombre="LQ INV",
        participacion=46.344,
        numero_acciones=46815289329.0,
    )
    Executive(
        nombre="EBENSPERGER",
        cargo="Gerente General",
        fecha_asuncion="2016-05-01",
        tipo="1",
    )
