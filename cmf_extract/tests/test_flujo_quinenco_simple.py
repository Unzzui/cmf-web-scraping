#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
from pathlib import Path
import re
import math
import pytest
import pandas as pd


EXCEL_PATH = Path('/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total/91705000-7_QUIÑENCO_SA/out_consolidated_2025-2014/estados_91705000-7_201403-202503_es.xlsx')


@pytest.mark.skipif(not EXCEL_PATH.exists(), reason='Excel final de Quiñenco no está presente')
def test_flujo_quinenco_q1_2025_values_and_order():
    # Cargar hoja "Flujo Efectivo" con encabezado en fila 3
    xls = pd.read_excel(EXCEL_PATH, sheet_name=None, engine='openpyxl', header=2)
    assert 'Flujo Efectivo' in xls, 'Hoja "Flujo Efectivo" no encontrada en el Excel final'
    df = xls['Flujo Efectivo']
    assert not df.empty, 'Hoja vacía'

    # Verificar que exista la columna 2025Q1
    target_col = None
    for c in df.columns:
        if isinstance(c, str) and c.strip() == '2025Q1':
            target_col = c
            break
    assert target_col is not None, 'No se encontró columna 2025Q1 en el Excel'

    # Secuencia esperada (orden) y valores para 2025Q1 cuando aplique
# Secuencia esperada (orden) y valores para 2025Q1 cuando aplique
    expected_sequence = [
        'Flujos de efectivo procedentes de (utilizados en) actividades de operación [sinopsis]',
        'Negocios no bancarios [sinopsis]',
        'Clases de cobros por actividades de operación [sinopsis]',
        ('Cobros procedentes de las ventas de bienes y prestación de servicios', '1.525.301.578'),
        ('Cobros procedentes de regalías, cuotas, comisiones y otros ingresos de actividades ordinarias', '1.040.225'),
        ('Cobros derivados de contratos mantenidos para intermediación o para negociar con ellos', '-'),
        ('Cobros derivados de arrendamiento y posterior venta de esos activos', '-'),
        ('Recuperaciones activadas préstamos anteriormente anulados desactivados', '-'),
        ('Otros cobros por actividades de operación', '8.189.017'),
        'Clases de pagos [sinopsis]',
        ('Pagos a proveedores por el suministro de bienes y servicios', '1.385.396.048'),
        ('Pagos relacionados con regalías tasas y comisiones', '-'),
        ('Pagos procedentes de contratos mantenidos para intermediación o para negociar', '-'),
        ('Pagos a y por cuenta de los empleados', '79.308.372'),
        ('Pagos por fabricar o adquirir activos mantenidos para arrendar a otros y posteriormente para vender', '-'),
        ('Otros pagos por actividades de operación', '24.560.732'),
        ('Flujos de efectivo netos procedentes de (utilizados en) operaciones', '45.265.668'),
        ('Dividendos pagados', '-'),
        ('Dividendos recibidos', '-'),
        ('Intereses pagados', '-'),
        ('Interés pagado en depósito pasivos clasificado como actividades operativas', '-'),
        ('Intereses recibidos', '-'),
        ('Intereses recibidos de préstamos y anticipos clasificados como actividades operativas', '-'),
        ('Interés recibido de deuda instrumentos retenidos clasificado como actividades operativas', '-'),
        ('Impuestos a las ganancias pagados (reembolsados)', '4.476.310'),
        ('Otras entradas (salidas) de efectivo', '-2.480.921'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de operación de negocios no bancarios', '38.308.437'),

        'Servicios bancarios [sinopsis]',
        ('Utilidad (pérdida) consolidada del período', '330.618.111'),
        'Cargos (abonos) a resultados que no significan movimientos de efectivo [sinopsis]',
        ('Depreciaciones y amortizaciones', '23.656.574'),
        ('Provisiones por riesgo de crédito', '106.923.732'),
        ('Ajuste a valor de mercado de instrumentos para negociación', '-2.016.462'),
        ('Utilidad neta por inversiones en sociedades con influencia significativa', '1.733.563'),
        ('Utilidad neta en venta de activos recibidos en pago', '303.301'),
        ('Utilidad neta en venta de activos fijos', '2.110.898'),
        ('Castigos de activos recibidos en pago', '5.459.857'),
        ('Otros cargos (abonos) que no significan movimiento de efectivo', '4.940.681'),
        ('Variación neta de intereses, reajustes y comisiones devengadas sobre activos y pasivos', '53.937.497'),
        'Cambios en activos y pasivos que afectan al flujo operacional [sinopsis]',
        ('(Aumento) disminución neta en adeudado por bancos', '1.029.784.232'),
        ('(Aumento) disminución en créditos y cuentas por cobrar a clientes', '441.777.109'),
        ('(Aumento) disminución neta de instrumentos para negociación', '-108.393.605'),
        ('Aumento (disminución) de depósitos y otras obligaciones a la vista', '230.385.051'),
        ('Aumento (disminución) de contratos de retrocompra y préstamos de valores', '41.663.367'),
        ('Aumento (disminución) de depósitos y otras captaciones a plazo', '1.332.842.146'),
        ('Aumento (disminución) de obligaciones con bancos', '1.746.161'),
        ('Aumento (disminución) de otras obligaciones financieras', '36.229.975'),
        ('Préstamos obtenidos del Banco Central de Chile (largo plazo)', '-'),
        ('Pago préstamos obtenidos del Banco Central de Chile (largo plazo)', '-'),
        ('Préstamos obtenidos del exterior a largo plazo', '-198.804.357'),
        ('Pago de préstamos del exterior a largo plazo', '-399.441.143'),
        ('Otros préstamos obtenidos a largo plazo', '-'),
        ('Pago de otros préstamos obtenidos a largo plazo', '-'),
        ('Provisión para pago de Obligación Subordinada al Banco Central', '-'),
        ('Otros', '4.861.519'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de la operación servicios bancarios', '1.004.569.497'),
        ('Flujos de efectivo netos procedentes de (utilizados en) actividades de operación', '1.042.877.934'),

        'Flujos de efectivo procedentes de (utilizados en) actividades de inversión [sinopsis]',
        'Negocios no Bancarios [sinopsis]',
        ('Flujos de efectivo procedentes de la pérdida de control de subsidiarias u otros negocios', '-'),
        ('Flujos de efectivo utilizados para obtener el control de subsidiarias u otros negocios', '-'),
        ('Flujos de efectivo utilizados en la compra de participaciones no controladoras', '-'),
        ('Otros cobros por la venta de patrimonio o instrumentos de deuda de otras entidades', '-'),
        ('Otros pagos para adquirir patrimonio o instrumentos de deuda de otras entidades', '-'),
        ('Otros cobros por la venta de participaciones en negocios conjuntos', '-'),
        ('Otros pagos para adquirir participaciones en negocios conjuntos', '-'),
        ('Préstamos a entidades relacionadas', '-'),
        ('Importes procedentes de la venta de propiedades, planta y equipo', '100.745'),
        ('Compras de propiedades, planta y equipo', '28.883.524'),
        ('Importes procedentes de ventas de activos intangibles', '-'),
        ('Compras de activos intangibles', '265.777'),
        ('Importes procedentes de otros activos a largo plazo', '-'),
        ('Compras de otros activos a largo plazo', '-'),
        ('Importes procedentes de subvenciones del gobierno', '-'),
        ('Anticipos de efectivo y préstamos concedidos a terceros', '-'),
        ('Cobros procedentes del reembolso de anticipos y préstamos concedidos a terceros', '-'),
        ('Pagos derivados de contratos de futuro, a término, de opciones y de permuta financiera', '-'),
        ('Cobros procedentes de contratos de futuro, a término, de opciones y de permuta financiera', '-'),
        ('Cobros a entidades relacionadas', '-'),
        ('Dividendos recibidos', '345.135'),
        ('Intereses pagados', '-'),
        ('Intereses recibidos', '25.612.670'),
        ('Impuestos a las ganancias pagados (reembolsados)', '-'),
        ('Flujos de efectivo procedentes de la venta de participaciones no controladoras', '-'),
        ('Otras entradas (salidas) de efectivo', '-333.444.823'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de inversión de negocios no bancarios', '-336.535.574'),
        'Servicios Bancarios [sinopsis]',
        ('(Aumento) disminución neta de instrumentos de inversión disponibles para la venta', '142.190.135'),
        ('Compras de activos fijos', '4.482.867'),
        ('Ventas de activos fijos', '2.778.939'),
        ('Inversiones en sociedades', '-'),
        ('Dividendos recibidos de inversiones en sociedades', '-'),
        ('Venta de bienes recibidos en pago o adjudicados', '4.756.325'),
        ('(Aumento) disminución neta de otros activos y pasivos', '83.740.891'),
        ('Otros', '-3.022.183'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de inversión servicios bancarios', '225.961.240'),
        ('Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión', '-110.574.334'),

        'Flujos de efectivo procedentes de (utilizados en) actividades de financiación [sinopsis]',
        'Negocios no bancarios [sinopsis]',
        ('Cobros por cambios en las participaciones en la propiedad de subsidiarias que no resulta en una pérdida de control', '-'),
        ('Pagos por cambios en las participaciones en la propiedad en subsidiarias que no dan lugar a la pérdida de control', '-'),
        ('Importes procedentes de la emisión de acciones', '-'),
        ('Importes procedentes de la emisión de otros instrumentos de patrimonio', '-'),
        ('Pagos por adquirir o rescatar las acciones de la entidad', '-'),
        ('Pagos por otras participaciones en el patrimonio', '-'),
        ('Importes procedentes de préstamos', '36.517.951'),
        ('Importes procedentes de préstamos de largo plazo', '28.500.303'),
        ('Importes procedentes de préstamos de corto plazo', '8.017.648'),
        ('Préstamos de entidades relacionadas', '-'),
        ('Reembolsos de préstamos', '-'),
        ('Pagos de pasivos por arrendamientos', '11.581.597'),
        ('Pagos de préstamos de entidades relacionadas', '-'),
        ('Importes procedentes de subvenciones del gobierno', '-'),
        ('Dividendos pagados', '-'),
        ('Intereses pagados', '10.956.192'),
        ('Impuestos a las ganancias pagados (reembolsados)', '-'),
        ('Otras entradas (salidas) de efectivo', '-20.090.261'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de financiación de negocios no bancarios', '-6.110.099'),
        'Servicios Bancarios [sinopsis]',
        ('Emisión de letras de crédito', '-'),
        ('Rescate de letras de crédito', '141.486'),
        ('Emisión de bonos', '373.284.159'),
        ('Pago de bonos', '175.746.027'),
        ('Otros préstamos obtenidos a largo plazo', '-'),
        ('Pago obligacion subordinada con el Banco Central de Chile', '-'),
        ('Emisión de acciones de pago', '-'),
        ('Dividendos pagados', '485.150.243'),
        ('Otros', '-'),
        ('Subtotal flujos de efectivo netos procedentes de (utilizados en) actividades de financiación servicios bancarios', '-287.753.597'),
        ('Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación', '-293.863.696'),

        ('Incremento (disminución) neto de efectivo y equivalentes al efectivo, antes del efecto de los cambios en la tasa de cambio', '638.439.904'),
        'Efectos de la variación en la tasa de cambio sobre el efectivo y equivalentes al efectivo [sinopsis]',
        ('Efectos de la variación en la tasa de cambio sobre el efectivo y equivalentes al efectivo', '-78.004.986'),
        ('Incremento (disminución) neto de efectivo y equivalentes al efectivo', '560.434.918'),
        ('Efectivo y equivalentes al efectivo al principio del periodo', '5.819.131.737'),
        ('Efectivo y equivalentes al efectivo al final del periodo', '6.379.566.655'),
    ]


    # Helper para parsear el valor esperado como entero en unidades
    def _to_units(s: str) -> int:
        s = str(s).strip()
        if s == '-' or s == '—' or s == '–' or s == '' or s.upper() == 'NULL':
            return 0
        return int(s.replace('.', '').replace(',', ''))

    # Comparador tolerante a miles: acepta valor exacto o valor/1000 redondeado
    def _matches(got, expected_units: int) -> bool:
        try:
            if got is None or (isinstance(got, float) and math.isnan(got)):
                got_num = 0.0
            else:
                got_num = float(str(got).replace(',', ''))
        except Exception:
            return False
        if abs(got_num - expected_units) < 1.0:
            return True
        if abs(got_num - expected_units/1000.0) < 1.0:
            return True
        # también aceptar redondeo al entero en miles
        if abs(round(got_num) - round(expected_units/1000.0)) <= 1.0:
            return True
        return False

    # Mapear a índice para verificar el orden
    concept_col = df.columns[0]
    labels = df[concept_col].astype(str).str.strip().tolist()

    last_index = -1
    problems = []
    for item in expected_sequence:
        if isinstance(item, tuple):
            label, value = item
        else:
            label, value = item, None

        try:
            idx = labels.index(label)
        except ValueError:
            problems.append(f'No se encontró la línea "{label}"')
            continue

        # Verificar orden creciente
        if idx <= last_index:
            problems.append(f'Orden incorrecto para "{label}" (índice {idx} <= {last_index})')
        last_index = idx

        # Verificar valor si aplica
        if value is not None:
            got = df.iloc[idx][target_col]
            exp_units = _to_units(value)
            if not _matches(got, exp_units):
                problems.append(f'Valor distinto en {label} @2025Q1: esperado {value} (unidades), obtuvo {got}')

    assert not problems, "\n" + "\n".join(problems[:20])

