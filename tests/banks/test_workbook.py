"""Tests del generador de workbook bancario, sin BD (BankData sintetico)."""

from cmf_extract import excel_style as est
from cmf_extract.analisis_bancos import workbook
from cmf_extract.analisis_bancos.db_reader import Account, BankData

BAL = ["100000000", "200000000", "380000000", "500000000", "241000000", "242000000",
       "149000000"]
RES = ["411000000", "412000000", "520000000", "525000000", "550000000", "560000000",
       "470000000", "580000000", "590000000"]


def _sample(market=None):
    periods = [(2023, 12), (2024, 12)]
    bal_acc = [Account(c, f"cuenta {c}") for c in BAL]
    res_acc = [Account(c, f"cuenta {c}") for c in RES]
    bv, rv = {}, {}
    for (y, m) in periods:
        for a in bal_acc:
            bv[(a.codigo, (y, m))] = 1000.0
        for a in res_acc:
            rv[(a.codigo, (y, m))] = -100.0 if a.codigo.startswith(("412", "560", "470")) else 200.0
    return BankData(
        codigo_institucion="001", nombre="BANCO TEST", rut="99-9", swift=None,
        periods=periods, balance_accounts=bal_acc, resultado_accounts=res_acc,
        balance_values=bv, resultado_values=rv, capital={}, profile={},
        market=market or {},
    )


def _ratio_cell(ws, label):
    for r in range(4, 40):
        if ws[f"A{r}"].value == label:
            # segunda columna de periodo = C (primer periodo B, segundo C)
            return ws[f"C{r}"].value, ws[f"B{r}"].value
    raise AssertionError(f"ratio no encontrado: {label}")


def test_hojas_esperadas():
    wb = workbook.build_workbook(_sample())
    assert wb.sheetnames[0] == workbook.SHEET_INICIO
    for s in (workbook.SHEET_BALANCE, workbook.SHEET_RESULTADO, workbook.SHEET_CAPITAL,
              workbook.SHEET_RATIOS, workbook.SHEET_VALUACION, workbook.SHEET_FICHA,
              workbook.SHEET_METODO):
        assert s in wb.sheetnames


def test_contraste_limpio():
    wb = workbook.build_workbook(_sample())
    assert est.verificar_contraste(wb) == []


def test_formula_roe_referencia_estados_y_anualiza():
    wb = workbook.build_workbook(_sample())
    ws = wb[workbook.SHEET_RATIOS]
    ult, _ = _ratio_cell(ws, "ROE (anualizado)")
    assert ult.startswith("=IFERROR(")
    assert workbook.SHEET_RESULTADO in ult and workbook.SHEET_BALANCE in ult
    assert "*12/12" in ult  # anualizacion del mes 12


def test_yoy_vacio_primer_anho_lleno_segundo():
    wb = workbook.build_workbook(_sample())
    ws = wb[workbook.SHEET_RATIOS]
    ult, primero = _ratio_cell(ws, "Colocaciones YoY")
    assert primero is None            # 2023-12 no tiene anho previo cargado
    assert isinstance(ult, str) and ult.startswith("=IFERROR(")  # 2024-12 vs 2023-12


def test_ninguna_formula_referencia_none():
    # un ref roto se colaria como el literal "None" dentro de la formula
    wb = workbook.build_workbook(_sample())
    ws = wb[workbook.SHEET_RATIOS]
    for fila in ws.iter_rows():
        for celda in fila:
            if isinstance(celda.value, str) and celda.value.startswith("="):
                assert "None" not in celda.value


def test_formato_producto_cabecera_bandas_y_resumen():
    wb = workbook.build_workbook(_sample())
    ws = wb[workbook.SHEET_RATIOS]
    # cabecera de tabla en fila 4 con columnas de resumen
    hdr = [ws.cell(4, c).value for c in range(1, ws.max_column + 1)]
    assert hdr[0] == "Indicador"
    assert hdr[-3:] == ["Ultimo", "Promedio", "Tendencia"]
    # banda de seccion con fill SOFT
    band = None
    for r in range(5, 12):
        if ws.cell(r, 1).value == "RENTABILIDAD":
            band = ws.cell(r, 1)
            break
    assert band is not None
    assert band.fill.start_color.rgb == est.SOFT
    # columna Tendencia con formula de flecha
    last_row = None
    for r in range(5, 40):
        if ws.cell(r, 1).value == "ROE (anualizado)":
            last_row = r
            break
    trend = ws.cell(last_row, ws.max_column).value
    assert isinstance(trend, str) and "IFERROR(IF(" in trend


def test_inicio_tiene_hyperlinks_de_navegacion():
    wb = workbook.build_workbook(_sample())
    ws = wb[workbook.SHEET_INICIO]
    destinos = [c.hyperlink.target if c.hyperlink else None
                for row in ws.iter_rows() for c in row if c.hyperlink]
    assert any(workbook.SHEET_RATIOS in (d or "") for d in destinos)


def test_valuacion_mercado_solo_si_listado():
    wb_no = workbook.build_workbook(_sample())
    labels_no = [wb_no[workbook.SHEET_VALUACION][f"A{r}"].value for r in range(1, 25)]
    assert "MERCADO (banco listado)" not in labels_no

    wb_si = workbook.build_workbook(_sample(market={"beta": 1.0, "market_cap": 5000.0}))
    labels_si = [wb_si[workbook.SHEET_VALUACION][f"A{r}"].value for r in range(1, 25)]
    assert "MERCADO (banco listado)" in labels_si
