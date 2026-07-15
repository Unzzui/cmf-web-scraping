"""Arma el workbook de analisis bancario a partir de un BankData.

Reutiliza cmf_extract/excel_style.py para todo el lenguaje visual (tipografia Inter, paleta
INK/EMBER, formatos, bordes, guardas de contraste). Los ratios se escriben como formulas
Excel vivas que referencian las celdas de los estados.
"""

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from cmf_extract import excel_style as est
from cmf_extract.analisis_bancos import concept_map as cm

SHEET_BALANCE = "Estado de Situacion"
SHEET_RESULTADO = "Estado de Resultados"
SHEET_CAPITAL = "Adecuacion de Capital"
SHEET_RATIOS = "RATIOS & KPIs"
SHEET_VALUACION = "Valuacion"
SHEET_FICHA = "Ficha Tecnica"
SHEET_METODO = "Metodologia"
SHEET_INICIO = "Inicio"

# Parametros de valuacion (editables en la hoja)
RF_DEFAULT = 0.055        # tasa libre de riesgo
ERP_DEFAULT = 0.065       # premio por riesgo de mercado
BETA_DEFAULT = 0.9        # beta sectorial para bancos no listados
G_DEFAULT = 0.03          # crecimiento nominal de largo plazo


def _period_label(y: int, m: int) -> str:
    return f"{y}-{m:02d}"


def _assign_columns(data) -> None:
    """Asigna una letra de columna por periodo (compartida entre todas las hojas)."""
    for i, (y, m) in enumerate(data.periods):
        data.col_of[(y, m)] = get_column_letter(2 + i)


def _header(ws, data, title: str) -> None:
    est.preparar_hoja(ws, congelar="B4")
    ws["A1"] = title
    ws["A1"].font = est.SECCION
    ws["A2"] = f"{data.nombre}  -  RUT {data.rut or '-'}  -  cifras en $ (moneda total)"
    ws["A2"].font = est.NOTA
    hc = ws["A3"]
    hc.value = "Cuenta"
    hc.font = est.CABECERA
    hc.fill = est.RELLENO_TINTA
    for (y, m), col in data.col_of.items():
        c = ws[f"{col}3"]
        c.value = _period_label(y, m)
        c.font = est.CABECERA
        c.fill = est.RELLENO_TINTA
        c.alignment = est.DER
    ws.column_dimensions["A"].width = 62
    for col in data.col_of.values():
        ws.column_dimensions[col].width = 15


def _write_statement(ws, data, accounts, values, statement, title) -> None:
    _header(ws, data, title)
    for r, acc in enumerate(accounts, start=4):
        label = ws[f"A{r}"]
        label.value = f"{acc.codigo}  {acc.descripcion}"
        label.font = est.CUERPO_FUERTE if acc.codigo.endswith("000000") else est.CUERPO
        data.row_of[(statement, acc.codigo)] = r
        for (y, m), col in data.col_of.items():
            cell = ws[f"{col}{r}"]
            cell.value = values.get((acc.codigo, (y, m)))
            cell.number_format = est.FMT_NUM
            cell.font = est.CUERPO


def _write_capital(ws, data) -> dict:
    _header(ws, data, "Adecuacion de Capital (Basilea)")
    filas = [
        ("irs", "IRS - Indice de solvencia"),
        ("ire", "IRE - Indice de endeudamiento"),
        ("capital_basico", "Capital basico"),
        ("patrimonio_efectivo", "Patrimonio efectivo"),
        ("apr", "Activos ponderados por riesgo (APR)"),
    ]
    cap_row_of: dict[str, int] = {}
    for r, (key, label) in enumerate(filas, start=4):
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = est.CUERPO
        cap_row_of[key] = r
        for (y, m), col in data.col_of.items():
            v = data.capital.get((y, m), {}).get(key)
            cell = ws[f"{col}{r}"]
            cell.value = v
            cell.number_format = est.FMT_NUM
            cell.font = est.CUERPO
    return cap_row_of


# ---- referencias de celdas para las formulas de ratios ----

def _ref(data, concept: str, col: str):
    """Expresion Excel para un concepto en una columna, o None si falta alguna cuenta."""
    codes = cm.codes_for(concept)
    stmt = cm.statement_for(concept)
    sheet = SHEET_BALANCE if stmt == "balance" else SHEET_RESULTADO
    parts = []
    for code in codes:
        row = data.row_of.get((stmt, code))
        if row is None:
            return None
        parts.append(f"'{sheet}'!{col}{row}")
    return "(" + "+".join(parts) + ")"


def _ann(ref: str, m: int) -> str:
    """Anualiza un acumulado YTD del mes m."""
    return f"({ref}*12/{m})"


def _cap(cap_row_of, field: str, col: str) -> str:
    return f"'{SHEET_CAPITAL}'!{col}{cap_row_of[field]}"


def _ratio_defs():
    """Lista de (categoria, etiqueta, formato, builder). El builder devuelve el cuerpo de la
    formula (sin '=') o None si no se puede construir en esa columna."""
    P, MULT, NUM = est.FMT_PCT, est.FMT_MULT, est.FMT_NUM

    def roe(d, col, y, m, cr):
        ni, pat = _ref(d, "resultado_ejercicio", col), _ref(d, "patrimonio", col)
        return f"{_ann(ni, m)}/{pat}" if ni and pat else None

    def roa(d, col, y, m, cr):
        ni, act = _ref(d, "resultado_ejercicio", col), _ref(d, "activos_total", col)
        return f"{_ann(ni, m)}/{act}" if ni and act else None

    def nim(d, col, y, m, cr):
        nii, nir = _ref(d, "ingreso_neto_intereses", col), _ref(d, "ingreso_neto_reajustes", col)
        act = _ref(d, "activos_total", col)
        return f"(({nii}+{nir})*12/{m})/{act}" if nii and nir and act else None

    def margen_op(d, col, y, m, cr):
        ro, ing = _ref(d, "resultado_operacional", col), _ref(d, "total_ingresos_operacionales", col)
        return f"{ro}/{ing}" if ro and ing else None

    def eficiencia(d, col, y, m, cr):
        g, ing = _ref(d, "total_gastos_operacionales", col), _ref(d, "total_ingresos_operacionales", col)
        return f"ABS({g})/{ing}" if g and ing else None

    def costo_riesgo(d, col, y, m, cr):
        gp, colo = _ref(d, "gasto_perdidas_crediticias", col), _ref(d, "colocaciones", col)
        return f"ABS({_ann(gp, m)})/{colo}" if gp and colo else None

    def prov_col(d, col, y, m, cr):
        pr, colo = _ref(d, "provisiones_colocaciones", col), _ref(d, "colocaciones", col)
        return f"ABS({pr})/{colo}" if pr and colo else None

    def ldr(d, col, y, m, cr):
        colo, dep = _ref(d, "colocaciones", col), _ref(d, "depositos_clientes", col)
        return f"{colo}/{dep}" if colo and dep else None

    def col_act(d, col, y, m, cr):
        colo, act = _ref(d, "colocaciones", col), _ref(d, "activos_total", col)
        return f"{colo}/{act}" if colo and act else None

    def dep_pas(d, col, y, m, cr):
        dep, pas = _ref(d, "depositos_clientes", col), _ref(d, "pasivos_total", col)
        return f"{dep}/{pas}" if dep and pas else None

    def apalancamiento(d, col, y, m, cr):
        act, pat = _ref(d, "activos_total", col), _ref(d, "patrimonio", col)
        return f"{act}/{pat}" if act and pat else None

    def irs(d, col, y, m, cr):
        return _cap(cr, "irs", col)

    def ire(d, col, y, m, cr):
        return _cap(cr, "ire", col)

    def cap_apr(d, col, y, m, cr):
        return f"{_cap(cr, 'capital_basico', col)}/{_cap(cr, 'apr', col)}"

    def _yoy(concept):
        def f(d, col, y, m, cr):
            prev = d.col_of.get((y - 1, m))
            if not prev:
                return None
            cur_ref, prev_ref = _ref(d, concept, col), _ref(d, concept, prev)
            return f"{cur_ref}/{prev_ref}-1" if cur_ref and prev_ref else None
        return f

    return [
        ("RENTABILIDAD", "ROE (anualizado)", P, roe),
        ("RENTABILIDAD", "ROA (anualizado)", P, roa),
        ("RENTABILIDAD", "Margen de interes neto (NIM)", P, nim),
        ("RENTABILIDAD", "Margen operacional", P, margen_op),
        ("EFICIENCIA", "Indice de eficiencia (gastos/ingresos)", P, eficiencia),
        ("RIESGO DE CREDITO", "Costo de riesgo (anualizado)", P, costo_riesgo),
        ("RIESGO DE CREDITO", "Provisiones / colocaciones", P, prov_col),
        ("ESTRUCTURA", "Colocaciones / depositos (LDR)", P, ldr),
        ("ESTRUCTURA", "Colocaciones / activos", P, col_act),
        ("ESTRUCTURA", "Depositos / pasivos", P, dep_pas),
        ("ESTRUCTURA", "Apalancamiento (activos / patrimonio)", MULT, apalancamiento),
        ("CAPITAL (BASILEA)", "IRS - Indice de solvencia", NUM, irs),
        ("CAPITAL (BASILEA)", "IRE - Indice de endeudamiento", NUM, ire),
        ("CAPITAL (BASILEA)", "Capital basico / APR", P, cap_apr),
        ("CRECIMIENTO", "Colocaciones YoY", P, _yoy("colocaciones")),
        ("CRECIMIENTO", "Depositos YoY", P, _yoy("depositos_clientes")),
        ("CRECIMIENTO", "Resultado del ejercicio YoY", P, _yoy("resultado_ejercicio")),
    ]


def _write_ratios(ws, data, cap_row_of) -> None:
    _header(ws, data, "RATIOS & KPIs")
    ws["A2"] = (f"{data.nombre}  -  ratios como formulas trazables sobre los estados  "
                f"-  resultado anualizado = YTD / mes * 12")
    ws["A2"].font = est.NOTA
    r = 4
    cat_actual = None
    for cat, label, fmt, build in _ratio_defs():
        if cat != cat_actual:
            ws[f"A{r}"] = cat
            ws[f"A{r}"].font = est.ETIQUETA
            r += 1
            cat_actual = cat
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = est.CUERPO
        for (y, m), col in data.col_of.items():
            body = build(data, col, y, m, cap_row_of)
            cell = ws[f"{col}{r}"]
            if body:
                cell.value = f'=IFERROR({body},"")'
                cell.number_format = fmt
            cell.font = est.CUERPO
        r += 1


def _write_valuacion(ws, data) -> None:
    est.preparar_hoja(ws, congelar=None)
    ws["A1"] = "Valuacion - Exceso de retorno / P-B garantizado"
    ws["A1"].font = est.SECCION
    ws["A2"] = (f"{data.nombre}. Modelo residual: P/B = (ROE - g)/(Ke - g); "
                f"valor patrimonial = P/B * patrimonio contable.")
    ws["A2"].font = est.NOTA
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 22
    if not data.periods:
        return
    y, m = data.periods[-1]
    col = data.col_of[(y, m)]
    pat_row = data.row_of.get(("balance", "380000000")) or data.row_of.get(("balance", "300000000"))
    ni_row = data.row_of.get(("resultado", "590000000"))
    pat_ref = f"'{SHEET_BALANCE}'!{col}{pat_row}" if pat_row else None
    ni_ref = f"'{SHEET_RESULTADO}'!{col}{ni_row}" if ni_row else None
    beta = data.market.get("beta") or BETA_DEFAULT

    rows: dict[str, int] = {}
    state = {"row": 4}

    def section(label: str) -> None:
        ws[f"A{state['row']}"] = label
        ws[f"A{state['row']}"].font = est.ETIQUETA
        state["row"] += 1

    def put(label, value, fmt=None, font=est.CUERPO, key=None) -> None:
        r = state["row"]
        ws[f"A{r}"] = label
        ws[f"A{r}"].font = font
        if value is not None:
            c = ws[f"B{r}"]
            c.value = value
            if fmt:
                c.number_format = fmt
            c.font = font
        if key:
            rows[key] = r
        state["row"] += 1

    section("PARAMETROS")
    put("Tasa libre de riesgo (Rf)", RF_DEFAULT, est.FMT_PCT, key="rf")
    put("Premio por riesgo (ERP)", ERP_DEFAULT, est.FMT_PCT, key="erp")
    put("Beta", beta, "0.00", key="beta")
    put("Crecimiento largo plazo (g)", G_DEFAULT, est.FMT_PCT, key="g")
    put("Costo de capital (Ke = Rf + Beta*ERP)",
        f"=B{rows['rf']}+B{rows['beta']}*B{rows['erp']}", est.FMT_PCT, est.CUERPO_FUERTE, key="ke")
    section("BASE CONTABLE")
    put("Patrimonio contable", f"={pat_ref}" if pat_ref else None, est.FMT_NUM, key="pat")
    put("Resultado anualizado", f"={_ann(ni_ref, m)}" if ni_ref else None, est.FMT_NUM, key="ni")
    put("ROE sostenible", f"=IFERROR(B{rows['ni']}/B{rows['pat']},\"\")", est.FMT_PCT,
        est.CUERPO_FUERTE, key="roe")
    section("VALUACION")
    put("P/B garantizado = (ROE-g)/(Ke-g)",
        f"=IFERROR((B{rows['roe']}-B{rows['g']})/(B{rows['ke']}-B{rows['g']}),\"\")",
        est.FMT_MULT, est.CUERPO_FUERTE, key="pb")
    put("Valor patrimonial intrinseco", f"=IFERROR(B{rows['pb']}*B{rows['pat']},\"\")",
        est.FMT_NUM, est.CUERPO_FUERTE, key="vi")

    mc = data.market.get("market_cap")
    if mc:
        section("MERCADO (banco listado)")
        put("Capitalizacion de mercado", mc, est.FMT_NUM, key="mc")
        put("P/B de mercado", f"=IFERROR(B{rows['mc']}/B{rows['pat']},\"\")", est.FMT_MULT,
            key="pbm")
        put("Prima (+) / Descuento (-) vs intrinseco",
            f"=IFERROR(B{rows['vi']}/B{rows['mc']}-1,\"\")", est.FMT_PCT, est.CUERPO_FUERTE)


def _write_ficha(ws, data) -> None:
    est.preparar_hoja(ws, congelar=None)
    ws["A1"] = "Ficha Tecnica"
    ws["A1"].font = est.SECCION
    ws.column_dimensions["A"].width = 30
    ws.column_dimensions["B"].width = 50
    p = data.profile
    filas = [
        ("Institucion", data.nombre),
        ("Codigo CMF", data.codigo_institucion),
        ("RUT", data.rut or "-"),
        ("SWIFT", p.get("swift") or data.swift or "-"),
        ("Sitio web", p.get("sitio_web") or "-"),
        ("Direccion", p.get("direccion") or "-"),
        ("Empleados", p.get("empleados")),
        ("Sucursales", p.get("sucursales")),
        ("Oficinas", p.get("oficinas")),
        ("Cajeros", p.get("cajeros")),
        ("Ficha al", str(p.get("fecha_publicacion") or "-")),
    ]
    for i, (label, val) in enumerate(filas, start=3):
        ws[f"A{i}"] = label
        ws[f"A{i}"].font = est.ETIQUETA
        ws[f"B{i}"] = val
        ws[f"B{i}"].font = est.CUERPO


def _write_metodologia(ws, data) -> None:
    est.preparar_hoja(ws, congelar=None)
    ws["A1"] = "Metodologia"
    ws["A1"].font = est.SECCION
    ws.column_dimensions["A"].width = 110
    notas = [
        "Fuente: API oficial de Bancos de la CMF (api.cmfchile.cl), tablas bank_*.",
        "Cobertura: plan de cuentas del Compendio de Normas Contables (desde enero 2022).",
        "Periodicidad: mensual. Los saldos de balance son de fin de mes (instantaneos).",
        "El estado de resultados es ACUMULADO del ejercicio (YTD): el valor de un mes es el",
        "   acumulado enero-mes. Los ratios anualizan el resultado: valor YTD / mes * 12.",
        "Los ratios se escriben como formulas Excel que referencian las celdas de los estados",
        "   (trazables y recalculables si se editan los estados).",
        "Adecuacion de capital (IRS/IRE): de la CMF; cobertura irregular, los meses sin dato",
        "   quedan en blanco.",
        "Valuacion: modelo de exceso de retorno. P/B garantizado = (ROE - g)/(Ke - g); Ke por",
        "   CAPM. La comparacion con mercado solo aplica a bancos listados.",
    ]
    for i, n in enumerate(notas, start=3):
        ws[f"A{i}"] = n
        ws[f"A{i}"].font = est.NOTA if not n.endswith(".") or i > 3 else est.CUERPO


def _write_inicio(ws, data) -> None:
    est.preparar_hoja(ws, congelar=None)
    ws.column_dimensions["A"].width = 40
    ws.column_dimensions["B"].width = 40
    ws["A1"] = data.nombre
    ws["A1"].font = est.TITULO
    ws["A2"] = "Analisis Bancario"
    ws["A2"].font = est.ETIQUETA
    rng = ""
    if data.periods:
        y0, m0 = data.periods[0]
        y1, m1 = data.periods[-1]
        rng = f"{_period_label(y0, m0)} a {_period_label(y1, m1)}"
    ws["A4"] = "RUT"
    ws["B4"] = data.rut or "-"
    ws["A5"] = "Codigo CMF"
    ws["B5"] = data.codigo_institucion
    ws["A6"] = "Periodo"
    ws["B6"] = rng
    ws["A7"] = "Meses cubiertos"
    ws["B7"] = len(data.periods)
    for r in range(4, 8):
        ws[f"A{r}"].font = est.ETIQUETA
        ws[f"B{r}"].font = est.CUERPO


def build_workbook(data) -> Workbook:
    _assign_columns(data)
    wb = Workbook()
    wb.remove(wb.active)

    ws_bal = wb.create_sheet(SHEET_BALANCE)
    _write_statement(ws_bal, data, data.balance_accounts, data.balance_values, "balance",
                     "Estado de Situacion")
    ws_res = wb.create_sheet(SHEET_RESULTADO)
    _write_statement(ws_res, data, data.resultado_accounts, data.resultado_values, "resultado",
                     "Estado de Resultados")
    ws_cap = wb.create_sheet(SHEET_CAPITAL)
    cap_row_of = _write_capital(ws_cap, data)
    ws_rat = wb.create_sheet(SHEET_RATIOS)
    _write_ratios(ws_rat, data, cap_row_of)
    _write_valuacion(wb.create_sheet(SHEET_VALUACION), data)
    _write_ficha(wb.create_sheet(SHEET_FICHA), data)
    _write_metodologia(wb.create_sheet(SHEET_METODO), data)

    ws_ini = wb.create_sheet(SHEET_INICIO)
    _write_inicio(ws_ini, data)
    wb.move_sheet(SHEET_INICIO, -(len(wb.sheetnames) - 1))  # Inicio primero

    est.aplicar_tipografia_base(wb)
    return wb
