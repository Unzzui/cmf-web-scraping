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
                    "emp_hombres_perm": 4842, "emp_mujareres_perm": 5077,
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
