#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones de traducción y localización para etiquetas XBRL.
"""

from __future__ import annotations


def translate_label_to_english(spanish_label: str) -> str:
    """Traduce etiquetas del español al inglés usando diccionario específico IFRS."""
    # Diccionario completo de traducciones IFRS español -> inglés
    translations = {
        # Activos
        "Activos": "Assets",
        "Activos corrientes": "Current assets", 
        "Activos no corrientes": "Non-current assets",
        "Efectivo y equivalentes al efectivo": "Cash and cash equivalents",
        "Otros activos financieros": "Other financial assets",
        "Otros activos no financieros": "Other non-financial assets",
        "Deudores comerciales y otras cuentas por cobrar": "Trade and other current receivables",
        "Cuentas por cobrar a entidades relacionadas": "Current accounts receivable from related entities",
        "Inventarios": "Inventories",
        "Activos biológicos": "Biological assets",
        "Activos por impuestos": "Tax assets",
        "Propiedades, planta y equipo": "Property, plant and equipment",
        "Propiedades de inversión": "Investment property",
        "Activos intangibles distintos de la plusvalía": "Intangible assets other than goodwill",
        "Plusvalía": "Goodwill",
        "Inversiones en subsidiarias, negocios conjuntos y asociadas": "Investments in subsidiaries, joint ventures and associates",
        
        # Pasivos y Patrimonio
        "Pasivos": "Liabilities",
        "Pasivos corrientes": "Current liabilities",
        "Pasivos no corrientes": "Non-current liabilities",
        "Otros pasivos financieros": "Other financial liabilities",
        "Cuentas por pagar comerciales y otras cuentas por pagar": "Trade and other current payables",
        "Cuentas por pagar a entidades relacionadas": "Current accounts payable to related entities",
        "Otras provisiones": "Other provisions",
        "Pasivos por impuestos corrientes": "Current tax liabilities",
        "Provisiones por beneficios a los empleados": "Employee benefits provisions",
        "Otros pasivos no financieros": "Other non-financial liabilities",
        "Patrimonio": "Equity",
        "Capital emitido": "Issued capital",
        "Ganancias (pérdidas) acumuladas": "Retained earnings (accumulated losses)",
        "Otras reservas": "Other reserves",
        "Patrimonio atribuible a los propietarios de la controladora": "Equity attributable to owners of the parent",
        "Participaciones no controladoras": "Non-controlling interests",
        
        # Estado de Resultados
        "Ingresos de actividades ordinarias": "Revenue",
        "Costo de ventas": "Cost of sales",
        "Ganancia bruta": "Gross profit",
        "Otros ingresos": "Other income",
        "Costos de distribución": "Distribution costs",
        "Gastos de administración": "Administrative expenses",
        "Otros gastos, por función": "Other expenses, by function",
        "Otras ganancias (pérdidas)": "Other gains (losses)",
        "Ganancias (pérdidas) de actividades operacionales": "Profit (loss) from operating activities",
        "Ingresos financieros": "Finance income",
        "Costos financieros": "Finance costs",
        "Participación en las ganancias (pérdidas) de asociadas y negocios conjuntos": "Share of profit (loss) of associates and joint ventures",
        "Diferencias de cambio": "Foreign currency translation differences",
        "Resultado por unidades de reajuste": "Indexation units result",
        "Ganancia (pérdida), antes de impuestos": "Profit (loss) before tax",
        "Gasto por impuestos a las ganancias": "Income tax expense",
        "Ganancia (pérdida)": "Profit (loss)",
        "Ganancia (pérdida), atribuible a:": "Profit (loss) attributable to:",
        "Ganancia (pérdida) atribuible a los propietarios de la controladora": "Profit (loss) attributable to owners of the parent",
        "Ganancia (pérdida) atribuible a participaciones no controladoras": "Profit (loss) attributable to non-controlling interests",
        
        # Flujo de Efectivo
        "Flujos de efectivo procedentes de (utilizados en) actividades de operación": "Cash flows from (used in) operating activities",
        "Flujos de efectivo netos procedentes de (utilizados en) actividades de operación": "Net cash flows from (used in) operating activities",
        "Flujos de efectivo procedentes de (utilizados en) actividades de inversión": "Cash flows from (used in) investing activities",
        "Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión": "Net cash flows from (used in) investing activities",
        "Flujos de efectivo procedentes de (utilizados en) actividades de financiación": "Cash flows from (used in) financing activities",
        "Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación": "Net cash flows from (used in) financing activities",
        "Cobros procedentes de las ventas de bienes y prestación de servicios": "Cash receipts from sales of goods and rendering of services",
        "Pagos a proveedores por el suministro de bienes y servicios": "Cash payments to suppliers for goods and services",
        "Pagos a y por cuenta de los empleados": "Cash payments to and on behalf of employees",
        "Pagos por primas y prestaciones, anualidades y otras obligaciones derivadas de las pólizas suscritas": "Cash payments for and on behalf of employees",
        "Otros pagos por actividades de operación": "Other cash payments for operating activities",
        "Dividendos pagados": "Dividends paid",
        "Intereses pagados": "Interest paid",
        "Intereses recibidos": "Interest received",
        "Impuestos a las ganancias reembolsados (pagados)": "Income taxes refunded (paid)",
        "Otras entradas (salidas) de efectivo": "Other cash inflows (outflows)",
        "Compras de propiedades, planta y equipo": "Purchases of property, plant and equipment",
        "Compras de activos intangibles": "Purchases of intangible assets",
        "Compras de otros activos de largo plazo": "Purchases of other long-term assets",
        "Préstamos a entidades relacionadas": "Loans to related entities",
        "Obtención de préstamos": "Proceeds from borrowings",
        "Reembolsos de préstamos": "Repayments of borrowings",
        "Pagos de pasivos por arrendamientos financieros": "Payments of finance lease liabilities",
        "Importes procedentes de emisión de acciones": "Proceeds from issuing shares",
        "Compra de acciones propias": "Purchase of treasury shares",
        "Incremento (disminución) neto de efectivo y equivalentes al efectivo": "Net increase (decrease) in cash and cash equivalents",
        "Efectivo y equivalentes al efectivo al principio del periodo": "Cash and cash equivalents at beginning of period",
        "Efectivo y equivalentes al efectivo al final del periodo": "Cash and cash equivalents at end of period",
        
        # Términos comunes
        "Total": "Total",
        "Subtotal": "Subtotal",
        "Neto": "Net",
        "Bruto": "Gross",
        "Corriente": "Current",
        "No corriente": "Non-current",
        "Atribuible": "Attributable",
        "Consolidado": "Consolidated",
        
        # Conceptos de tiempo
        "Al": "At",
        "Por el período": "For the period",
        "Por el año": "For the year",
        "terminado": "ended",
        
        # Monedas y unidades
        "Miles de pesos": "Thousands of pesos",
        "Miles CLP": "Thousands CLP",
        "M$": "M$",
        
        # Participaciones
        "ordinarias": "ordinary",
        "preferentes": "preference",
        "por acción": "per share",
        "básica": "basic",
        "diluida": "diluted",
        
        # Otros términos financieros
        "depreciación": "depreciation",
        "amortización": "amortisation",
        "deterioro": "impairment",
        "provisión": "provision",
        "reserva": "reserve",
        "resultado": "result",
        "ganancia": "profit",
        "pérdida": "loss",
        "ingreso": "income",
        "gasto": "expense",
        "costo": "cost",
    }
    
    # Buscar traducción exacta primero
    if spanish_label in translations:
        return translations[spanish_label]
    
    # Si no hay traducción exacta, buscar por palabras clave
    label_lower = spanish_label.lower()
    result = spanish_label
    
    # Aplicar traducciones parciales para términos compuestos
    for spanish_term, english_term in translations.items():
        if spanish_term.lower() in label_lower:
            result = result.replace(spanish_term, english_term)
    
    return result