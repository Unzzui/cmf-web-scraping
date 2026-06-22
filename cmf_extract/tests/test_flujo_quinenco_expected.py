#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
import re
import math
import pytest
import pandas as pd


@pytest.mark.skipif(
    not Path('/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/91705000-7_QUIÑENCO_SA').exists(),
    reason='Dataset de Quiñenco no está presente en esta máquina'
)
def test_flujo_quinenco_key_lines_match_latest_period():
    """
    Verifica que, para QUIÑENCO (Total), el flujo de efectivo contenga los valores
    clave en el último período, con el contexto correcto (no bancarios vs bancarios).

    Nota: La verificación permite que los valores estén en unidades o en miles.
    """
    project_root = Path(__file__).resolve().parents[1]
    company_dir = Path('/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/91705000-7_QUIÑENCO_SA')

    # Importar funciones necesarias del pipeline
    import importlib
    import sys as _sys
    if str(project_root) not in _sys.path:
        _sys.path.insert(0, str(project_root))

    bx = importlib.import_module('batch_xbrl_to_excel')
    x2e = importlib.import_module('xbrl_to_excel')

    # Reunir datasets solo de esta empresa
    all_ds = bx.find_datasets(company_dir)
    assert all_ds, 'No se encontraron datasets para Quiñenco'

    # Agregar facts consolidados
    facts_df = bx._aggregate_facts_for_company(all_ds, 'es', project_root)
    assert not facts_df.empty, 'Facts consolidados están vacíos'

    # Determinar último dataset y cargar presentation en ES
    latest = max(all_ds, key=lambda d: d.yyyyymm)
    pres_path = latest.dataset_dir / f"out_{latest.stem}" / f"presentation_{latest.stem}_es.csv"
    assert pres_path.exists(), f'Presentation no encontrado: {pres_path}'
    try:
        pres_df = pd.read_csv(pres_path, engine='pyarrow')
    except Exception:
        pres_df = pd.read_csv(pres_path, engine='python')

    # Seleccionar árbol FLUJO
    p_tree = x2e.build_tree_and_order(pres_df)
    flujo_tree = x2e.select_role_tree(p_tree, 'FLUJO')

    # Normalizar facts y componer estado de FLUJO
    facts_norm = x2e.normalize_facts(facts_df, 'es')
    flujo_df = x2e.compose_statement(
        facts_norm,
        flujo_tree,
        lang='es',
        max_dates=16,
        statement_kind='FLUJO',
        allowed_months=None,
        presentation_data=pres_df,
        output_dir=project_root / 'data'  # no escribe nada aquí
    )

    assert not flujo_df.empty, 'Compose de FLUJO devolvió vacío'

    # Encontrar la última columna de fecha (YYYY-MM-DD)
    date_cols = [c for c in flujo_df.columns if isinstance(c, str) and re.match(r'^\d{4}-\d{2}-\d{2}$', c)]
    assert date_cols, 'No hay columnas de fecha en el FLUJO'
    last_col = sorted(date_cols)[-1]

    # Valores esperados (último período). Formato: etiqueta → valor (como string con puntos)
    expected = {
        # Operación - Negocios no bancarios
        'Cobros procedentes de las ventas de bienes y prestación de servicios': '1.525.301.578',
        'Cobros procedentes de regalías, cuotas, comisiones y otros ingresos de actividades ordinarias': '1.040.225',
        'Cobros derivados de contratos mantenidos para intermediación o para negociar con ellos': '-',
        'Cobros derivados de arrendamiento y posterior venta de esos activos': '-',
        'Recuperaciones activadas préstamos anteriormente anulados desactivados': '-',
        'Otros cobros por actividades de operación': '8.189.017',
        'Pagos a proveedores por el suministro de bienes y servicios': '1.385.396.048',
        'Pagos relacionados con regalías tasas y comisiones': '-',
        'Pagos procedentes de contratos mantenidos para intermediación o para negociar': '-',
        'Pagos a y por cuenta de los empleados': '79.308.372',
        'Pagos por fabricar o adquirir activos mantenidos para arrendar a otros y posteriormente para vender': '-',
        'Otros pagos por actividades de operación': '24.560.732',
        'Flujos de efectivo netos procedentes de (utilizados en) operaciones': '45.265.668',
        'Dividendos pagados': '-',
        'Dividendos recibidos': '-',
        'Intereses pagados': '-',
        'Interés pagado en depósito pasivos clasificado como actividades operativas': '-',
        'Intereses recibidos': '-',
        'Intereses recibidos de préstamos y anticipos clasificados como actividades operativas': '-',
        'Interés recibido de deuda instrumentos retenidos clasificado como actividades operativas': '-',
        'Impuestos a las ganancias pagados (reembolsados)': '4.476.310',
        'Otras entradas (salidas) de efectivo': '-2.480.921',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de operación de negocios no bancarios': '38.308.437',

        # Operación - Servicios bancarios
        'Utilidad (pérdida) consolidada del período': '330.618.111',
        'Depreciaciones y amortizaciones': '23.656.574',
        'Provisiones por riesgo de crédito': '106.923.732',
        'Ajuste a valor de mercado de instrumentos para negociación': '-2.016.462',
        'Utilidad neta por inversiones en sociedades con influencia significativa': '1.733.563',
        'Utilidad neta en venta de activos recibidos en pago': '303.301',
        'Utilidad neta en venta de activos fijos': '2.110.898',
        'Castigos de activos recibidos en pago': '5.459.857',
        'Otros cargos (abonos) que no significan movimiento de efectivo': '4.940.681',
        'Variación neta de intereses, reajustes y comisiones devengadas sobre activos y pasivos': '53.937.497',
        '(Aumento) disminución neta en adeudado por bancos': '1.029.784.232',
        '(Aumento) disminución en créditos y cuentas por cobrar a clientes': '441.777.109',
        '(Aumento) disminución neta de instrumentos para negociación': '-108.393.605',
        'Aumento (disminución) de depósitos y otras obligaciones a la vista': '230.385.051',
        'Aumento (disminución) de contratos de retrocompra y préstamos de valores': '41.663.367',
        'Aumento (disminución) de depósitos y otras captaciones a plazo': '1.332.842.146',
        'Aumento (disminución) de obligaciones con bancos': '1.746.161',
        'Aumento (disminución) de otras obligaciones financieras': '36.229.975',
        'Préstamos obtenidos del Banco Central de Chile (largo plazo)': '-',
        'Pago préstamos obtenidos del Banco Central de Chile (largo plazo)': '-',
        'Préstamos obtenidos del exterior a largo plazo': '-198.804.357',
        'Pago de préstamos del exterior a largo plazo': '-399.441.143',
        'Otros préstamos obtenidos a largo plazo': '-',
        'Pago de otros préstamos obtenidos a largo plazo': '-',
        'Provisión para pago de Obligación Subordinada al Banco Central': '-',
        'Otros': '4.861.519',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de la operación servicios bancarios': '1.004.569.497',
        'Flujos de efectivo netos procedentes de (utilizados en) actividades de operación': '1.042.877.934',

        # Inversión - No bancarios
        'Flujos de efectivo procedentes de la pérdida de control de subsidiarias u otros negocios': '-',
        'Flujos de efectivo utilizados para obtener el control de subsidiarias u otros negocios': '-',
        'Flujos de efectivo utilizados en la compra de participaciones no controladoras': '-',
        'Otros cobros por la venta de patrimonio o instrumentos de deuda de otras entidades': '-',
        'Otros pagos para adquirir patrimonio o instrumentos de deuda de otras entidades': '-',
        'Otros cobros por la venta de participaciones en negocios conjuntos': '-',
        'Otros pagos para adquirir participaciones en negocios conjuntos': '-',
        'Préstamos a entidades relacionadas': '-',
        'Importes procedentes de la venta de propiedades, planta y equipo': '100.745',
        'Compras de propiedades, planta y equipo': '28.883.524',
        'Importes procedentes de ventas de activos intangibles': '-',
        'Compras de activos intangibles': '265.777',
        'Importes procedentes de otros activos a largo plazo': '-',
        'Compras de otros activos a largo plazo': '-',
        'Importes procedentes de subvenciones del gobierno': '-',
        'Anticipos de efectivo y préstamos concedidos a terceros': '-',
        'Cobros procedentes del reembolso de anticipos y préstamos concedidos a terceros': '-',
        'Pagos derivados de contratos de futuro, a término, de opciones y de permuta financiera': '-',
        'Cobros procedentes de contratos de futuro, a término, de opciones y de permuta financiera': '-',
        'Cobros a entidades relacionadas': '-',
        'Dividendos recibidos': '345.135',
        'Intereses pagados': '-',
        'Intereses recibidos': '25.612.670',
        'Impuestos a las ganancias pagados (reembolsados)': '-',
        'Flujos de efectivo procedentes de la venta de participaciones no controladoras': '-',
        'Otras entradas (salidas) de efectivo': '-333.444.823',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de inversión de negocios no bancarios': '-336.535.574',

        # Inversión - Servicios bancarios
        '(Aumento) disminución neta de instrumentos de inversión disponibles para la venta': '142.190.135',
        'Compras de activos fijos': '4.482.867',
        'Ventas de activos fijos': '2.778.939',
        'Inversiones en sociedades': '-',
        'Dividendos recibidos de inversiones en sociedades': '-',
        'Venta de bienes recibidos en pago o adjudicados': '4.756.325',
        '(Aumento) disminución neta de otros activos y pasivos': '83.740.891',
        'Otros (inversión bancaria)': '-3.022.183',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de inversión servicios bancarios': '225.961.240',
        'Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión': '-110.574.334',

        # Financiación - No bancarios
        'Cobros por cambios en las participaciones en la propiedad de subsidiarias que no resulta en una pérdida de control': '-',
        'Pagos por cambios en las participaciones en la propiedad en subsidiarias que no dan lugar a la pérdida de control': '-',
        'Importes procedentes de la emisión de acciones': '-',
        'Importes procedentes de la emisión de otros instrumentos de patrimonio': '-',
        'Pagos por adquirir o rescatar las acciones de la entidad': '-',
        'Pagos por otras participaciones en el patrimonio': '-',
        'Importes procedentes de préstamos': '36.517.951',
        'Importes procedentes de préstamos de largo plazo': '28.500.303',
        'Importes procedentes de préstamos de corto plazo': '8.017.648',
        'Préstamos de entidades relacionadas': '-',
        'Reembolsos de préstamos': '-',
        'Pagos de pasivos por arrendamientos': '11.581.597',
        'Pagos de préstamos de entidades relacionadas': '-',
        'Importes procedentes de subvenciones del gobierno': '-',
        'Dividendos pagados': '-',
        'Intereses pagados': '10.956.192',
        'Impuestos a las ganancias pagados (reembolsados)': '-',
        'Otras entradas (salidas) de efectivo': '-20.090.261',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de financiación de negocios no bancarios': '-6.110.099',

        # Financiación - Servicios bancarios
        'Emisión de letras de crédito': '-',
        'Rescate de letras de crédito': '141.486',
        'Emisión de bonos': '373.284.159',
        'Pago de bonos': '175.746.027',
        'Otros préstamos obtenidos a largo plazo': '-',
        'Pago obligacion subordinada con el Banco Central de Chile': '-',
        'Emisión de acciones de pago': '-',
        'Dividendos pagados': '485.150.243',
        'Otros (financiación bancaria)': '-',
        'Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de financiación servicios bancarios': '-287.753.597',
        'Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación': '-293.863.696',

        # Totales
        'Incremento (disminución) neto de efectivo y equivalentes al efectivo, antes del efecto de los cambios en la tasa de cambio': '638.439.904',
        'Efectos de la variación en la tasa de cambio sobre el efectivo y equivalentes al efectivo': '-78.004.986',
        'Incremento (disminución) neto de efectivo y equivalentes al efectivo': '560.434.918',
        'Efectivo y equivalentes al efectivo al principio del periodo': '5.819.131.737',
        'Efectivo y equivalentes al efectivo al final del periodo': '6.379.566.655',
    }


    def _to_int(s: str) -> int:
        s = str(s).replace('.', '').replace(',', '').strip()
        if s == '-' or s == '':
            return 0
        return int(s)

    def _matches_units_or_thousands(got_val: float | int | str, expected_int: int) -> bool:
        try:
            if got_val is None or (isinstance(got_val, float) and math.isnan(got_val)):
                return expected_int == 0
            gv = float(str(got_val).replace(',', ''))
        except Exception:
            return False
        # Aceptar exacto o por miles
        return abs(gv - expected_int) < 1.0 or abs(gv - (expected_int * 1000)) < 1.0

    # Primero, asegurar que el bloque de contexto principal exista en el DF
    context_headers = flujo_df[flujo_df['Cuenta'].str.contains('Negocios no bancarios|Servicios bancarios', case=False, na=False)]
    assert not context_headers.empty, 'No se encontraron encabezados de contexto (bancarios / no bancarios) en FLUJO'

    # Verificar valores puntuales en la última fecha
    missing = []
    wrong = []
    for label, value_str in expected.items():
        exp = _to_int(value_str)
        row = flujo_df[flujo_df['Cuenta'].astype(str).str.strip().str.lower() == label.lower()]
        if row.empty:
            missing.append(label)
            continue
        got = row.iloc[0].get(last_col)
        if not _matches_units_or_thousands(got, exp):
            wrong.append((label, exp, got))

    assert not missing, f"Faltan líneas esperadas en FLUJO: {missing[:8]}"
    assert not wrong, (
        "Valores distintos al esperado (última fecha):\n" +
        "\n".join(f"- {lbl}: esperado ~{exp} (o x1000) vs obtuvo {got}" for (lbl, exp, got) in wrong[:10])
    )

