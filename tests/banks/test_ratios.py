from src.banks import ratios as R


def _ref(cuenta):
    """ref falso: mapea cada cuenta a una celda distinta y predecible."""
    statement, codigo = cuenta
    hoja = "Balance 2022+" if statement == "balance" else "Estado de Resultados 2022+"
    return f"'{hoja}'!B{int(codigo) // 1000000}"


def _formula(nombre, mes):
    ratio = next(r for r in R.RATIOS if r.nombre == nombre)
    return R.construir_formula(ratio, _ref, mes)


def test_factor_anualizacion():
    assert R.factor_anualizacion(12) == 1.0
    assert R.factor_anualizacion(6) == 2.0
    assert R.factor_anualizacion(1) == 12.0


def test_diciembre_no_anualiza():
    """El resultado es YTD: en diciembre ya es el año completo, multiplicar sería erróneo."""
    assert "*12" not in _formula("ROE", 12)


def test_mes_parcial_anualiza():
    """A mayo la utilidad son 5 meses; sin el x12/5 el ROE queda 2,4x subestimado."""
    assert "*2.4" in _formula("ROE", 5)


def test_ratio_de_dos_flujos_no_anualiza():
    """Eficiencia = gastos/ingresos: ambos YTD del mismo período, el factor se cancela."""
    f = _formula("Índice de Eficiencia", 5)
    assert "*2.4" not in f


def test_gastos_van_en_valor_absoluto():
    """Los gastos se publican en negativo; sin ABS el índice sale con el signo invertido."""
    assert "ABS(" in _formula("Índice de Eficiencia", 12)
    assert "ABS(" in _formula("Provisiones / Colocaciones", 12)


def test_guarda_countblank_en_toda_formula():
    """Una celda vacía vale 0 en Excel: sin la guarda, un hueco publica un 0,00% creíble."""
    for ratio in R.RATIOS:
        f = R.construir_formula(ratio, _ref, 5)
        assert f.startswith("=IF(COUNTBLANK("), f"{ratio.nombre} sin guarda: {f}"
        assert '>0,""' in f


def test_toda_formula_lleva_iferror():
    for ratio in R.RATIOS:
        assert "IFERROR(" in R.construir_formula(ratio, _ref, 12)


def test_cuenta_faltante_no_rompe_la_formula():
    """Si una cuenta no está en la hoja, ref devuelve NA() y la fórmula sigue siendo válida."""
    ratio = next(r for r in R.RATIOS if r.nombre == "ROE")
    f = R.construir_formula(ratio, lambda c: "NA()", 12)
    assert f.startswith("=")


def test_todas_las_categorias_tienen_ratios():
    for cat in R.CATEGORIAS:
        assert any(r.categoria == cat for r in R.RATIOS), cat


def test_todo_ratio_esta_en_una_categoria_conocida():
    for r in R.RATIOS:
        assert r.categoria in R.CATEGORIAS, r.nombre


def test_todo_ratio_documenta_su_formula():
    """La hoja METODOLOGÍA se arma con esto: un ratio sin texto sale en blanco al cliente."""
    for r in R.RATIOS:
        assert r.formula_texto.strip()
        assert r.formato in ("pct", "mult")
