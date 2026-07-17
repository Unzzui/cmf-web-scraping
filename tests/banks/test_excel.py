from src.banks import excel


def test_normalizar_rut_quita_puntos():
    """bank_profiles trae '97.004.000-5'; los productos IFRS usan '97004000-5'."""
    assert excel.normalizar_rut("97.004.000-5") == "97004000-5"
    assert excel.normalizar_rut("97004000-k") == "97004000-K"
    assert excel.normalizar_rut(None) is None
    assert excel.normalizar_rut("") is None


def test_nombre_archivo_sigue_el_formato_que_parsea_findatachile():
    """FinDataChile deduce empresa/RUT/años del NOMBRE (ver parse_file_info)."""
    n = excel.nombre_archivo("BANCO DE CHILE", "97.004.000-5", [(2014, 1), (2026, 5)])
    assert n == "BANCO DE CHILE - 97004000-5 - Análisis Financiero 2014-2026 [ES].xlsx"


def test_nombre_archivo_sin_rut_no_revienta():
    n = excel.nombre_archivo("BANCO X", None, [(2020, 1), (2021, 3)])
    assert "SIN-RUT" in n


def test_etiqueta_periodo_es_mensual():
    """Los bancos son mensuales, no trimestrales como los productos IFRS."""
    assert excel.etiqueta_periodo(2026, 5) == "2026-05"
    assert excel.etiqueta_periodo(2014, 12) == "2014-12"


class _CursorFalso:
    """Cursor mínimo que devuelve filas fijas por tipo de consulta."""

    def __init__(self, filas):
        self._filas = filas
        self._ult = []

    def execute(self, sql, params=None):
        if "bank_financial_data f" in sql and "JOIN bank_accounts" in sql:
            self._ult = self._filas
        else:
            self._ult = []

    def fetchall(self):
        return self._ult

    def fetchone(self):
        return self._ult[0] if self._ult else None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _ConnFalsa:
    def __init__(self, filas):
        self._filas = filas

    def cursor(self):
        return _CursorFalso(self._filas)


def test_fetch_matriz_arma_cuentas_y_valores():
    filas = [
        ("100000000", "TOTAL ACTIVOS", 2025, 5, 100.0),
        ("100000000", "TOTAL ACTIVOS", 2025, 6, 110.0),
        ("300000000", "PATRIMONIO", 2025, 5, 10.0),
    ]
    cuentas, valores = excel.fetch_matriz(_ConnFalsa(filas), "001", "balance",
                                          "compendio_2022")
    assert cuentas == [("100000000", "TOTAL ACTIVOS"), ("300000000", "PATRIMONIO")]
    assert valores[("100000000", (2025, 6))] == 110.0
    assert ("300000000", (2025, 6)) not in valores


def test_eje_temporal_unico_por_epoca():
    """El bug que esto previene
    -------------------------
    La CMF tiene huecos de un report suelto: el resultado de 2023-07 de Banco de Chile da
    500 mientras su balance del mismo mes da 200. Si cada hoja usa sólo SUS períodos, la
    hoja con el hueco corre todas sus columnas una posición — y como los ratios usan la
    misma letra de columna en ambas hojas, terminan cruzando el balance de un mes con el
    resultado de OTRO. Números plausibles y falsos.

    Se replica el cálculo del eje que hace construir_libro: la unión, no cada uno.
    """
    periodos = [(2023, 6), (2023, 7), (2023, 8)]
    val_balance = {("100000000", p): 1.0 for p in periodos}          # los tres meses
    val_resultado = {("590000000", p): 1.0 for p in [(2023, 6), (2023, 8)]}  # falta julio

    datos = {
        "Balance 2022+": ("Balance", [("100000000", "x")], val_balance),
        "Estado de Resultados 2022+": ("ER", [("590000000", "y")], val_resultado),
    }
    eje = [p for p in periodos
           if any((c, p) in vals for _, cuentas, vals in datos.values() for c, _ in cuentas)]

    assert eje == periodos, "el eje debe ser la UNIÓN: julio existe en balance"
    assert (2023, 7) in eje
