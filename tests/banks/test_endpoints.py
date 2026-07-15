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
