#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funciones para formateo y exportación a Excel con estilos corporativos.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from datetime import datetime
import pandas as pd


class ExcelStyleManager:
    """Gestor de estilos para Excel con formato corporativo."""
    
    def __init__(self, workbook, lang: str = "es"):
        self.workbook = workbook
        self.lang = lang
        self._setup_colors()
        self._setup_formats()
    
    def _setup_colors(self):
        """Define la paleta de colores corporativa."""
        self.brand_primary = '#0F172A'   # Navy oscuro
        self.brand_secondary = '#1F2937' # Gris azulado oscuro
        self.brand_accent = '#2563EB'    # Azul acento sobrio
        self.brand_gray_100 = '#F7F7F7'
        self.brand_gray_150 = '#F0F0F0'
        self.brand_gray_200 = '#E5E7EB'
        self.base_font = 'Calibri'
    
    def _setup_formats(self):
        """Crea todos los formatos necesarios."""
        self.title_format = self.workbook.add_format({
            'bold': True,
            'font_size': 16,
            'font_name': self.base_font,
            'font_color': '#FFFFFF',
            'bg_color': self.brand_primary,
            'align': 'center',
            'valign': 'vcenter'
        })

        self.subtitle_format = self.workbook.add_format({
            'font_size': 11,
            'font_name': self.base_font,
            'font_color': '#111827',
            'align': 'center',
            'valign': 'vcenter'
        })

        self.header_format = self.workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_name': self.base_font,
            'bg_color': self.brand_secondary,
            'font_color': '#FFFFFF',
            'border': 0,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True
        })

        self.number_format = self.workbook.add_format({
            'num_format': '#,##0',
            'align': 'right',
            'border': 0,
            'font_size': 10,
            'font_name': self.base_font
        })

        self.negative_number_format = self.workbook.add_format({
            'num_format': '#,##0_);[Red](#,##0)',
            'align': 'right',
            'border': 0,
            'font_size': 10,
            'font_name': self.base_font,
            'font_color': '#CC0000'
        })

        self.concept_format = self.workbook.add_format({
            'border': 0,
            'align': 'left',
            'valign': 'vcenter',
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': self.brand_gray_100
        })

        self.concept_format_alt = self.workbook.add_format({
            'border': 0,
            'align': 'left',
            'valign': 'vcenter',
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': self.brand_gray_150
        })

        self.category_format = self.workbook.add_format({
            'bold': True,
            'font_size': 11,
            'font_name': self.base_font,
            'bg_color': self.brand_primary,
            'font_color': '#FFFFFF',
            'align': 'left',
            'valign': 'vcenter'
        })

        self.empty_category_format = self.workbook.add_format({
            'bg_color': self.brand_primary,
            'align': 'center'
        })

        self.subcategory_format = self.workbook.add_format({
            'border': 0,
            'align': 'left',
            'valign': 'vcenter',
            'indent': 1,
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': '#FAFAFA'
        })

        self.subcategory_format_alt = self.workbook.add_format({
            'border': 0,
            'align': 'left',
            'valign': 'vcenter',
            'indent': 1,
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': '#F5F5F5'
        })

        self.total_format = self.workbook.add_format({
            'bold': True,
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': '#E0E7FF',
            'align': 'left',
            'valign': 'vcenter'
        })

        self.total_number_format = self.workbook.add_format({
            'bold': True,
            'num_format': '#,##0',
            'align': 'right',
            'font_size': 10,
            'font_name': self.base_font,
            'bg_color': '#E0E7FF'
        })


def setup_worksheet_properties(worksheet, brand_accent: str):
    """Configura propiedades básicas de la hoja."""
    worksheet.set_tab_color(brand_accent)
    worksheet.hide_gridlines(2)
    worksheet.set_landscape()
    worksheet.set_paper(9)  # A4
    worksheet.set_margins(left=0.5, right=0.5, top=0.6, bottom=0.6)
    worksheet.set_zoom(110)
    worksheet.set_default_row(15)


def setup_column_widths(worksheet, df: pd.DataFrame):
    """Configura anchos de columnas apropiados."""
    for i, col in enumerate(df.columns):
        if i == 0:
            max_len = min(max(12, df[col].astype(str).str.len().max() + 5), 65)
            worksheet.set_column(i, i, max_len)
        else:
            # Asegurar al menos 12 de ancho para evitar "columna casi oculta"
            worksheet.set_column(i, i, 18 if i > 0 else 12)


def write_headers(worksheet, df: pd.DataFrame, style_manager: ExcelStyleManager, 
                 entity_name: str, sheet_name: str, lang: str):
    """Escribe encabezados de la hoja con formato corporativo."""
    ncols = len(df.columns)
    header_row = 2
    title_text = f"{sheet_name} — {entity_name}"
    
    # Construir subtítulo con unidad y períodos
    date_cols = [str(c) for c in df.columns[1:]]
    unit_header_note = 'Miles CLP' if lang == 'es' else 'Thousands CLP'
    
    if lang == 'es':
        periods_label = 'Períodos'
        unit_label = 'Unidad'
    else:
        periods_label = 'Periods'
        unit_label = 'Unit'
    
    # Rango estético AAAA - AAAA
    if date_cols:
        try:
            years = sorted({str(c)[:4] for c in date_cols})
            periods_text = f"{years[0]} - {years[-1]}" if years else '-'
        except Exception:
            periods_text = ', '.join(date_cols[:4])
    else:
        periods_text = '-'
    
    subtitle_text = f"{unit_label}: {unit_header_note}    •    {periods_label}: {periods_text}"
    
    # Escribir títulos
    worksheet.merge_range(0, 0, 0, ncols - 1, title_text, style_manager.title_format)
    worksheet.merge_range(1, 0, 1, ncols - 1, subtitle_text, style_manager.subtitle_format)
    worksheet.set_row(0, 26)
    worksheet.set_row(1, 18)
    
    # Escribir encabezados de columna
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(header_row, col_num, value, style_manager.header_format)
    worksheet.set_row(header_row, 22)
    
    return header_row


def setup_quarterly_grouping(worksheet, df: pd.DataFrame):
    """Configura agrupación trimestral si está habilitada."""
    if os.getenv('X2E_COMBINED', '0') != '1':
        return
    
    try:
        # Map year → {quarter_num: col_index}
        year_quarter_cols: dict[str, dict[int, int]] = {}

        for c_idx, lbl in enumerate(df.columns):
            if c_idx == 0:
                continue  # 'Cuenta'
            s = str(lbl).strip().split("\n", 1)[0]
            m_q = re.match(r"^(\d{4})Q([1-4])$", s)
            if m_q:
                y = m_q.group(1)
                q = int(m_q.group(2))
                year_quarter_cols.setdefault(y, {})[q] = c_idx
            elif re.match(r"^(\d{4})$", s):
                # Bare year → treat as Q4 summary
                year_quarter_cols.setdefault(s, {})[4] = c_idx

        latest_year = None
        try:
            latest_year = max(int(y) for y in year_quarter_cols.keys()) if year_quarter_cols else None
        except Exception:
            latest_year = None

        # Group Q1-Q3 under Q4 (Q4 is the summary, always visible)
        for y, qmap in year_quarter_cols.items():
            is_latest_year = (latest_year is not None and int(y) == int(latest_year))
            inner_cols = sorted([ci for q, ci in qmap.items() if q != 4])
            q4_col = qmap.get(4)

            if not inner_cols:
                continue

            start_ci = min(inner_cols)
            end_ci = max(inner_cols)
            worksheet.set_column(start_ci, end_ci, None, None, {
                'level': 1,
                'hidden': (not is_latest_year)
            })

            if q4_col is not None:
                worksheet.set_column(q4_col, q4_col, None, None, {
                    'collapsed': (not is_latest_year)
                })

        # Summary to the RIGHT (Q4 is after Q1-Q3)
        try:
            worksheet.outline_settings(visible=True, symbols_below=False, symbols_right=True, show_outline_symbols=True)
        except Exception:
            pass
    except Exception:
        pass


def write_data_rows(worksheet, df: pd.DataFrame, style_manager: ExcelStyleManager, 
                   header_row: int, lang: str):
    """Escribe las filas de datos con formato alternado."""
    data_start_row = header_row + 1
    
    # Definir listas de cuentas especiales por idioma
    if lang == "es":
        cuentas_total = [
            'Ganancia bruta',
            'Ganancias (pérdidas) de actividades operacionales',
            'Ganancia (pérdida), antes de impuestos',
            'Ganancia (pérdida)',
            'Flujos de efectivo netos procedentes de (utilizados en) operaciones',
            'Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión',
            'Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación',
            'Efectivo y equivalentes al efectivo al final del periodo'
        ]
    else:
        cuentas_total = [
            'Gross profit',
            'Profit (loss) from operating activities',
            'Profit (loss)',
            'Net cash flows from (used in) operations',
            'Net cash flows from (used in) investing activities',
            'Net cash flows from (used in) financing activities',
            'Cash and cash equivalents at end of period'
        ]
    
    cuentas_total_ifrs = [
        'ifrs-full:CashAndCashEquivalentsIfDifferentFromStatementOfFinancialPosition'
    ]
    
    totales = ['total', 'suma', 'subtotal']
    
    for r_index, (index, row) in enumerate(df.iterrows()):
        row_num = data_start_row + r_index
        cuenta = str(row['Cuenta'])
        
        # Debug para cuentas problemáticas específicas
        if 'primas' in cuenta.lower() and 'pagos' in cuenta.lower():
            if os.getenv('X2E_DEBUG') == '1':
                print(f"📝 ESCRIBIENDO CUENTA PROBLEMÁTICA AL EXCEL:")
                print(f"   r_index: {r_index}, row_num: {row_num}")
                print(f"   cuenta: {cuenta}")
                print(f"   valores: {[row.get(col) for col in df.columns[1:]]}")
        
        # Determinar tipo de fila
        is_alternate = (r_index % 2 == 1)
        is_category = (cuenta.startswith('[') and ']' in cuenta)
        
        cuenta_lower = cuenta.lower()
        is_sinopsis_cat = (
            ('[sinopsis]' in cuenta_lower) or cuenta_lower.endswith('sinopsis') or
            ('[abstract]' in cuenta_lower) or cuenta_lower.endswith('abstract') or
            ('[resumen]' in cuenta_lower) or cuenta_lower.endswith('resumen')
        )
        
        if is_sinopsis_cat:
            is_category = True
        
        is_total = (
            any(word in cuenta_lower for word in totales)
            or cuenta.strip() in cuentas_total
            or cuenta.strip() in cuentas_total_ifrs
        )
        
        # Seleccionar formato para la cuenta
        if is_category:
            concept_cell_format = style_manager.category_format
        elif is_total:
            concept_cell_format = style_manager.total_format
        elif is_alternate:
            concept_cell_format = style_manager.subcategory_format_alt
        else:
            concept_cell_format = style_manager.subcategory_format

        worksheet.write(row_num, 0, cuenta, concept_cell_format)

        # Escribir valores numéricos
        for col_num in range(1, len(df.columns)):
            value = row.iloc[col_num]

            if is_category:
                worksheet.write(row_num, col_num, "", style_manager.empty_category_format)
            else:
                if pd.notna(value) and value != '':
                    try:
                        clean_value = str(value).replace(',', '').replace(' ', '').strip()
                        numeric_value = float(clean_value)
                        numeric_value_thousands = numeric_value / 1000

                        if is_total:
                            cell_format = style_manager.total_number_format
                        elif numeric_value_thousands < 0:
                            cell_format = style_manager.negative_number_format
                        else:
                            cell_format = style_manager.number_format
                        
                        worksheet.write(row_num, col_num, numeric_value_thousands, cell_format)
                    except (ValueError, TypeError):
                        text_format = style_manager.concept_format_alt if is_alternate else style_manager.concept_format
                        worksheet.write(row_num, col_num, value, text_format)
                else:
                    empty_format = style_manager.concept_format_alt if is_alternate else style_manager.concept_format
                    worksheet.write(row_num, col_num, "", empty_format)


def setup_worksheet_final_properties(worksheet, header_row: int, df: pd.DataFrame, 
                                    sheet_name: str, entity_name: str):
    """Configura propiedades finales de la hoja (filtros, congelado, etc.)."""
    data_start_row = header_row + 1
    
    # Configurar repetición de encabezados y pie de página
    worksheet.repeat_rows(0, header_row)
    
    ts_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    worksheet.set_footer(f"&L{sheet_name}  |  {entity_name}&RGenerado: {ts_str}   Página &P de &N")
    
    # Congelar paneles y filtros
    worksheet.freeze_panes(data_start_row, 1)
    worksheet.autofilter(header_row, 0, header_row + len(df), len(df.columns) - 1)


def guess_company_name_from_path(path: Path) -> str | None:
    """Extrae el nombre de la empresa desde la estructura del path."""
    try:
        d = path
        company_dir = None
        for _ in range(6):
            if d is None:
                break
            if d.name.startswith('Estados_financieros_(XBRL)') or d.name.startswith('out_consolidated_'):
                company_dir = d.parent
                break
            d = d.parent
        
        if company_dir is None:
            company_dir = path.parent
        
        raw = company_dir.name  # p.ej. 91041000-8_VIÑA_SAN_PEDRO_TARAPACA_SA
        name_part = raw.split('_', 1)[1] if '_' in raw else raw
        human = name_part.replace('_', ' ').strip()
        return human or None
    except Exception:
        return None