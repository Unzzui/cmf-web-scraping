"""
DCF Patch Module
================

Módulo complementario para agregar funcionalidad DCF (FCFF) al generador de Excel.
Sistema dinámico de referencias: todas las fórmulas referencian DIRECTAMENTE a las hojas
existentes usando búsqueda dinámica de conceptos como en formula_builder.py.
"""

import re
from typing import Dict, List, Any, Optional
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.utils.cell import column_index_from_string

try:
    from openpyxl.worksheet.data_validation import DataValidation
except ImportError:
    DataValidation = None


class DCFBuilder:
    """
    Constructor de hojas DCF para análisis de valuación.
    """

    # ----------------------------
    # INIT - Sistema dinámico como formula_builder.py
    # ----------------------------
    def __init__(self, workbook: Workbook, financial_data: Dict[str, Any]):
        self.wb = workbook
        self.financial_data = financial_data
        self.years = financial_data.get("years", [])

        # Moneda en la que la empresa REPORTA sus estados. La inyecta formula_processor
        # desde los facts del XBRL. 18 empresas del catálogo reportan en dólares (SQM,
        # COPEC, CMPC, LATAM, ARAUCO, COLBÚN…), y el precio de su acción cotiza en PESOS.
        # Sin esto, el DCF calcula un valor intrínseco en dólares y lo compara contra un
        # precio en pesos: la "Prima/(Descuento)" y la "Recomendación" salen desviadas
        # ~900x, y siempre dicen "extremadamente sobrevalorada".
        self.reporting_currency = str(financial_data.get("reporting_currency") or "CLP").upper()

        # Estilos
        self._setup_styles()

        # Hojas existentes (nombres en español/inglés)
        def pick_sheet(wb: Workbook, names: list[str]):
            for n in names:
                if n in wb.sheetnames:
                    return wb[n]
            return None

        self.sh_bal = pick_sheet(workbook, ["Balance General", "Balance Sheet"])
        self.sh_pl = pick_sheet(workbook, ["Estado de Resultados", "Estado Resultados (Función)", "Income Statement"])
        self.sh_cfs = pick_sheet(workbook, ["Flujo Efectivo", "Cash Flow"])
        self.sh_ratios = pick_sheet(workbook, ["RATIOS & KPIs"])

        # Detectar fila de encabezados por hoja dinámicamente
        def detect_header_row(sheet) -> int:
            if sheet is None:
                return 3
            max_scan = min(10, sheet.max_row)
            for r in range(1, max_scan + 1):
                v0 = sheet.cell(row=r, column=1).value
                if isinstance(v0, str) and v0.strip().lower() in ("cuenta", "concepto", "account"):
                    return r
                for c in range(2, min(sheet.max_column, 20) + 1):
                    v = sheet.cell(row=r, column=c).value
                    if isinstance(v, str):
                        s = v.strip().split("\n", 1)[0]
                        if re.match(r"^\d{4}-(\d{2}|\d{2}-\d{2})$", s):
                            return r
                        if re.match(r"^\d{4}(?:Q[1-4])?$", s):
                            return r
            return 3

        self.HDR_BAL = detect_header_row(self.sh_bal)
        self.HDR_PL = detect_header_row(self.sh_pl)
        self.HDR_CFS = detect_header_row(self.sh_cfs)
        self.HDR_RATIOS = detect_header_row(self.sh_ratios)

        # Mapeos dinámicos de conceptos a filas
        self.rows_bal = self._map_balance_rows() if self.sh_bal else {}
        self.rows_pl = self._map_income_rows() if self.sh_pl else {}
        self.rows_cfs = self._map_cash_flow_rows() if self.sh_cfs else {}
        self.rows_ratios = self._map_ratios_rows() if self.sh_ratios else {}

    # ----------------------------
    # Utilidades dinámicas - Sistema como formula_builder.py
    # ----------------------------
    def _find_row_in_sheet(self, sheet, concept_name: str) -> Optional[int]:
        """
        Encuentra la fila de un concepto en una hoja específicamente.
        Búsqueda dinámica por contenido de celda.
        """
        if sheet is None:
            return None
        
        hdr = self._hdr_row_for_sheet(sheet)
        if hdr is None:
            return None
        
        try:
            # Normalizar el concepto de búsqueda
            concept_lower = concept_name.strip().lower()
            
            # Buscar fila que contenga el concepto
            for r in range(hdr + 1, sheet.max_row + 1):
                cell_value = sheet.cell(row=r, column=1).value
                if not isinstance(cell_value, str):
                    continue
                
                cell_lower = cell_value.strip().lower()
                
                # Evitar filas abstractas/resumen
                if any(word in cell_lower for word in ["abstract", "resumen", "sinopsis"]):
                    continue
                
                # Buscar coincidencia exacta o inclusión
                if cell_lower == concept_lower or concept_lower in cell_lower:
                    return r
                    
        except Exception:
            pass
        
        return None

    def _hdr_row_for_sheet(self, sheet):
        """Retorna la fila de headers para una hoja."""
        if sheet == self.sh_bal:
            return self.HDR_BAL
        elif sheet == self.sh_pl:
            return self.HDR_PL
        elif sheet == self.sh_cfs:
            return self.HDR_CFS
        elif sheet == self.sh_ratios:
            return self.HDR_RATIOS
        return 3

    def _get_col_letter_by_label(self, sheet, label: str) -> Optional[str]:
        """
        Encuentra la columna (letra) para un período específico.
        Sistema dinámico como formula_builder.py
        """
        if sheet is None:
            return None
        
        hdr = self._hdr_row_for_sheet(sheet)
        label_norm = label.strip().split("\n", 1)[0]
        
        for col in range(2, sheet.max_column + 1):
            val = sheet.cell(row=hdr, column=col).value
            if isinstance(val, str) and val.strip().split("\n", 1)[0] == label_norm:
                return get_column_letter(col)
        return None

    def create_cell_reference_by_label(self, sheet, row_num: Optional[int], label: str) -> Optional[str]:
        """
        Crea una referencia de celda dinámica usando fila + etiqueta de período.
        Equivalente al método de formula_builder.py
        """
        if row_num is None or sheet is None:
            return None
        
        col = self._get_col_letter_by_label(sheet, label)
        if col is None:
            return None
        
        return f"'{sheet.title}'!{col}{row_num}"
    def _map_balance_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del balance a números de fila usando búsqueda dinámica."""
        concepts = {
            "AC": "Activos corrientes totales",
            "ANC": "Total de activos no corrientes",  
            "AT": "Total de activos",
            "PC": "Pasivos corrientes totales",
            "PNC": "Total de pasivos no corrientes",
            "PT": "Total de pasivos",
            "Patr": "Patrimonio atribuible a los propietarios de la controladora",
            "PatrTotal": "Patrimonio total",
            "CxC": "Deudores comerciales y otras cuentas por cobrar corrientes",
            "Inv": "Inventarios corrientes",
            "CxP": "Cuentas por pagar comerciales y otras cuentas por pagar",
            "Efec": "Efectivo y equivalentes al efectivo",
            "DeudaFinCorr": "Otros pasivos financieros corrientes",
            "DeudaFinNC": "Otros pasivos financieros no corrientes",
            "PPE": "Propiedades, planta y equipo",
        }
        
        return {key: self._find_row_in_sheet(self.sh_bal, concept)
                for key, concept in concepts.items()}

    def _map_income_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del estado de resultados a números de fila usando búsqueda dinámica."""
        concepts = {
            "Ventas": "Ingresos de actividades ordinarias",
            "COGS": "Costo de ventas",
            "Bruta": "Ganancia bruta",
            "EBIT": "Ganancias (pérdidas) de actividades operacionales",
            "Neta": "Ganancia (pérdida)",
            "NetaControl": "Ganancia (pérdida), atribuible a los propietarios de la controladora",
            "DepAmort": "Depreciación y amortización",
            "ImpGanan": "Gasto por impuestos a las ganancias",
            "AntesImp": "Ganancia (pérdida), antes de impuestos",
        }
        
        return {key: self._find_row_in_sheet(self.sh_pl, concept)
                for key, concept in concepts.items()}

    def _map_cash_flow_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del flujo de efectivo a números de fila usando búsqueda dinámica."""
        concepts = {
            "CFO": "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
            "CFI": "Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión",
            "CFF": "Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación",
            "CapEx": "Compras de propiedades, planta y equipo",
            "CapExIntang": "Compras de activos intangibles",
        }
        
        return {key: self._find_row_in_sheet(self.sh_cfs, concept)
                for key, concept in concepts.items()}

    def _map_ratios_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos de RATIOS & KPIs a números de fila usando búsqueda dinámica."""
        if not self.sh_ratios:
            return {}
        
        concepts = {
            "MargenEBIT": "Margen Operativo (EBIT)",
            "DepAmort": "Depreciación y Amortización", 
            "Acciones": "Total número de acciones emitidas",
        }
        
        return {key: self._find_row_in_sheet(self.sh_ratios, concept)
                for key, concept in concepts.items()}

    def _iter_periods_from_sheet(self, sheet) -> List[str]:
        """Lee los labels de la fila de encabezados (fila 3 o 4) y devuelve la lista de periodos (strings)."""
        if sheet is None:
            return []
        hdr = 4 if sheet == self.sh_ratios else 3
        labels: List[str] = []
        for col in range(2, sheet.max_column + 1):
            v = sheet.cell(row=hdr, column=col).value
            if isinstance(v, str):
                s = v.strip()
                if s:
                    labels.append(s.split("\n", 1)[0])
        return labels
    
    def _find_latest_period(self) -> str:
        """
        Encuentra automáticamente el último período disponible en las hojas.
        """
        periods = self._iter_periods_from_sheet(self.sh_pl)
        if not periods:
            from datetime import datetime
            return f"{datetime.now().year}Q4"

        valid_periods = [p for p in periods if re.match(r"^\d{4}(Q[1-4])?$", p)]
        if not valid_periods:
            from datetime import datetime
            return f"{datetime.now().year}Q4"

        def period_to_number(period):
            if "Q" in period:
                year, quarter = period.split("Q")
                return int(year) * 10 + int(quarter)
            else:
                return int(period) * 10 + 4  # Bare YYYY treated as Q4

        valid_periods_sorted = sorted(valid_periods, key=period_to_number, reverse=True)
        return valid_periods_sorted[0]
    
    def _find_base_annual_period(self) -> str:
        """
        Encuentra el año base anual más reciente.
        Acepta tanto YYYY como YYYYQ4 como períodos anuales.
        Resultado cacheado para evitar recomputación.
        """
        if hasattr(self, '_cached_base_annual'):
            return self._cached_base_annual
        periods = self._iter_periods_from_sheet(self.sh_pl)
        annual_periods = []
        for p in periods:
            m = re.match(r"^(\d{4})Q4$", p)
            if m:
                annual_periods.append(p)
            elif re.match(r"^\d{4}$", p):
                annual_periods.append(f"{p}Q4")

        if annual_periods:
            annual_sorted = sorted(annual_periods, reverse=True)
            self._cached_base_annual = annual_sorted[0]
        else:
            self._cached_base_annual = self._find_latest_period()
        return self._cached_base_annual

    # ----------------------------
    # Fórmulas (todas DIRECTAS)
    # ----------------------------
    def _get_ventas_base_formula(self, base_period: str = None) -> str:
        """
        Genera fórmula dinámica para ventas año base usando sistema de referencias como formula_builder.py
        """
        if base_period is None:
            base_period = self._find_base_annual_period()
            
        if self.sh_pl and "Ventas" in self.rows_pl and self.rows_pl["Ventas"]:
            # Para períodos trimestrales, usar ratios anualizados de RATIOS & KPIs
            if "Q" in base_period and self.sh_ratios:
                # Buscar "Ventas anualizadas" en RATIOS & KPIs
                ventas_anualizadas_row = self._find_row_in_sheet(self.sh_ratios, "Ventas")
                if ventas_anualizadas_row:
                    ref = self.create_cell_reference_by_label(self.sh_ratios, ventas_anualizadas_row, base_period)
                    if ref:
                        return f"=IFERROR({ref},\"N/D\")"
            
            # Para períodos anuales, usar Estado de Resultados directamente
            ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], base_period)
            if ref:
                return f"=IFERROR({ref},\"N/D\")"
        
        return "=\"N/D\""
    def _get_margen_ebit_formula(self) -> str:
        """
        Genera fórmula dinámica para margen EBIT usando sistema de referencias como formula_builder.py
        """
        # Primero intentar desde RATIOS & KPIs  
        if self.sh_ratios and "MargenEBIT" in self.rows_ratios and self.rows_ratios["MargenEBIT"]:
            ref = self.create_cell_reference_by_label(self.sh_ratios, self.rows_ratios["MargenEBIT"], self._find_base_annual_period())
            if ref:
                return f"=IFERROR({ref},0.10)"
        
        # Fallback: calcular desde Estado de Resultados
        if (self.sh_pl and "EBIT" in self.rows_pl and self.rows_pl["EBIT"] and 
            "Ventas" in self.rows_pl and self.rows_pl["Ventas"]):
            ebit_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["EBIT"], self._find_base_annual_period())
            ventas_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], self._find_base_annual_period())
            if ebit_ref and ventas_ref:
                return f"=IFERROR({ebit_ref}/{ventas_ref},0.10)"
        
        return "0.10"


    def _get_da_ventas_formula(self) -> str:
        """
        Genera fórmula dinámica para D&A/Ventas usando sistema de referencias como formula_builder.py
        """
        # Estrategia: DepAmort de RATIOS & KPIs, Ventas de Estado de Resultados
        if (self.sh_ratios and "DepAmort" in self.rows_ratios and self.rows_ratios["DepAmort"] and
            self.sh_pl and "Ventas" in self.rows_pl and self.rows_pl["Ventas"]):
            da_ref = self.create_cell_reference_by_label(self.sh_ratios, self.rows_ratios["DepAmort"], self._find_base_annual_period())
            ventas_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], self._find_base_annual_period())
            if da_ref and ventas_ref:
                return f"=IFERROR({da_ref}/{ventas_ref},0.03)"
        
        # Fallback: solo Estado de Resultados si DepAmort existe ahí
        if (self.sh_pl and "DepAmort" in self.rows_pl and self.rows_pl["DepAmort"] and
            "Ventas" in self.rows_pl and self.rows_pl["Ventas"]):
            da_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["DepAmort"], self._find_base_annual_period())
            ventas_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], self._find_base_annual_period())
            if da_ref and ventas_ref:
                return f"=IFERROR({da_ref}/{ventas_ref},0.03)"
        
        return "0.03"

    def _get_capex_ventas_formula(self) -> str:
        """
        Genera fórmula dinámica para CapEx/Ventas usando sistema de referencias como formula_builder.py
        """
        parts = []
        
        # CapEx desde flujo de efectivo
        if self.sh_cfs and "CapEx" in self.rows_cfs and self.rows_cfs["CapEx"]:
            capex_ref = self.create_cell_reference_by_label(self.sh_cfs, self.rows_cfs["CapEx"], self._find_base_annual_period())
            if capex_ref:
                parts.append(f"ABS({capex_ref})")
        
        # CapEx intangibles desde flujo de efectivo
        if self.sh_cfs and "CapExIntang" in self.rows_cfs and self.rows_cfs["CapExIntang"]:
            capex_intang_ref = self.create_cell_reference_by_label(self.sh_cfs, self.rows_cfs["CapExIntang"], self._find_base_annual_period())
            if capex_intang_ref:
                parts.append(f"ABS({capex_intang_ref})")
        
        # Ventas desde estado de resultados
        if self.sh_pl and "Ventas" in self.rows_pl and self.rows_pl["Ventas"] and parts:
            ventas_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], self._find_base_annual_period())
            if ventas_ref:
                return f"=IFERROR(({'+'.join(parts)})/{ventas_ref},0.04)"
        
        return "0.04"

    def _get_deuda_neta_formula(self, period: str = None) -> str:
        """
        Genera fórmula dinámica para deuda neta usando sistema de referencias como formula_builder.py
        
        Args:
            period: Período específico a usar (ej: "2024", "2025Q2"). Si None, usa el más reciente disponible.
        """
        # Determinar el período a usar
        if period is None:
            period = self._find_latest_period()
        
        terms = []
        
        # Deuda financiera corriente
        if self.sh_bal and "DeudaFinCorr" in self.rows_bal and self.rows_bal["DeudaFinCorr"]:
            deuda_corr_ref = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["DeudaFinCorr"], period)
            if deuda_corr_ref:
                terms.append(deuda_corr_ref)
        
        # Deuda financiera no corriente
        if self.sh_bal and "DeudaFinNC" in self.rows_bal and self.rows_bal["DeudaFinNC"]:
            deuda_nc_ref = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["DeudaFinNC"], period)
            if deuda_nc_ref:
                terms.append(deuda_nc_ref)
        
        # Efectivo y equivalentes
        cash_ref = None
        if self.sh_bal and "Efec" in self.rows_bal and self.rows_bal["Efec"]:
            cash_ref = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Efec"], period)
        
        if terms and cash_ref:
            return f"=IFERROR(({'+'.join(terms)})-{cash_ref},0)"
        elif terms:
            return f"=IFERROR({'+'.join(terms)},0)"
        
        return "0"

    def _get_tasa_impuestos_formula(self) -> str:
        """
        Tasa de impuestos fija en 27% para todos los cálculos
        """
        return "0.27"
    
    def _get_acciones_formula(self) -> str:
        """
        Genera fórmula dinámica para acciones en circulación.

        Toma el ÚLTIMO valor no vacío de la fila de acciones en RATIOS (el más
        reciente disponible), en vez de un período fijo: las acciones suelen
        venir sólo en algunos períodos (anuales) y el período más reciente
        puede estar vacío. LOOKUP(2,1/(rango<>""),rango) devuelve el último no
        vacío, que en esta hoja (columnas de viejo a nuevo) es el más reciente.
        """
        row = self.rows_ratios.get("Acciones") if self.rows_ratios else None
        if self.sh_ratios and row:
            # Última columna de período (encabezado tipo YYYY o YYYYQn)
            hdr = getattr(self, "HDR_RATIOS", 4) or 4
            last_col = None
            for c in range(2, self.sh_ratios.max_column + 1):
                v = self.sh_ratios.cell(row=hdr, column=c).value
                if isinstance(v, str) and re.match(r"^\d{4}(Q[1-4])?$", v.strip()):
                    last_col = c
            if last_col:
                from openpyxl.utils import get_column_letter
                title = self.sh_ratios.title
                rng = f"'{title}'!B{row}:{get_column_letter(last_col)}{row}"
                return f'=IFERROR(LOOKUP(2,1/({rng}<>""),{rng}),"")'
        return '""'
    
    def _get_cagr_formula(self, years_back: int = 5) -> str:
        """
        Calcula CAGR automático de ventas basado en períodos históricos disponibles.
        Maneja correctamente el orden de columnas desde más reciente a más antiguo.
        
        Args:
            years_back: Número de años hacia atrás para calcular CAGR
        """
        if not (self.sh_pl and "Ventas" in self.rows_pl and self.rows_pl["Ventas"]):
            return "0.05"  # Default 5%
            
        # Obtener períodos disponibles en el orden que aparecen
        periods = self._iter_periods_from_sheet(self.sh_pl)
        if not periods or len(periods) < 2:
            return "0.05"
            
        # Cierres ANUALES.
        #
        # ESTE FILTRO ESTABA MUERTO. Exigía que el período NO contuviera "Q":
        #
        #     if "Q" not in period_str and len(period_str) >= 4:
        #
        # Pero TODOS los encabezados del Excel son "2026Q1", "2025Q4", "2024Q4"…
        # Ninguno pasaba jamás, así que `annual_periods` quedaba vacío y la función
        # retornaba "0.05" SIEMPRE. Verificado en 7 Excel de producción: la celda
        # "Crecimiento Ventas Y+1" contiene el literal 0.05, no una fórmula.
        #
        # O sea que TODOS los Excel vendidos proyectaban un 5% de crecimiento, igual
        # para Falabella que para SQM. Y como Y+2 a Y+5 se derivan de esa celda
        # (=MAX(B13*0.9,0.02)…), toda la proyección de cinco años colgaba de un número
        # inventado.
        #
        # El cierre anual de una empresa es su Q4. (Los formatos antiguos traían el año
        # a secas; se aceptan los dos.)
        annual_periods = []
        for p in periods:
            period_str = str(p).strip()
            if len(period_str) < 4 or not period_str[:4].isdigit():
                continue
            up = period_str.upper()
            es_anual = ("Q" not in up) or up.endswith("Q4")
            if es_anual:
                annual_periods.append((period_str[:4], period_str))

        if len(annual_periods) < 2:
            return "0.05"
        
        # Los períodos están en orden: más reciente primero
        # annual_periods = [(2024, "2024"), (2023, "2023"), (2022, "2022"), ...]
        
        # Encontrar el año más reciente y uno anterior para CAGR
        most_recent_year, most_recent_label = annual_periods[0]  # 2024
        
        # Buscar el período más lejano disponible dentro del rango solicitado
        # Priorizar períodos más largos para un CAGR más representativo
        best_start_year = None
        best_start_label = None
        best_years_diff = 0
        
        for i in range(1, len(annual_periods)):
            start_year, start_label = annual_periods[i]
            years_diff = float(most_recent_year) - float(start_year)
            
            # Solo considerar períodos dentro del rango solicitado
            if years_diff <= years_back and years_diff > best_years_diff:
                # Verificar que podemos crear las referencias
                end_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], most_recent_label)
                start_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], start_label)
                
                if end_ref and start_ref:
                    best_start_year = start_year
                    best_start_label = start_label
                    best_years_diff = years_diff
        
        # Usar el mejor período encontrado
        if best_start_year and best_years_diff > 0:
            end_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], most_recent_label)
            start_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], best_start_label)
            
            # CAGR calculado
            # Referencias CAGR identificadas
            # Tope 15% y piso 2%: los mismos que aplica el DCF que se guarda en la BD
            # (scripts/dcf/excel_aligned.py). Sin ellos, una empresa que dobló ventas en
            # un año proyectaría 100% anual durante cinco años.
            return f"=IFERROR(MAX(MIN(POWER({end_ref}/{start_ref},1/{best_years_diff})-1,0.15),0.02),0.05)"
        
        # Fallback: usar los dos períodos más recientes si están disponibles
        if len(annual_periods) >= 2:
            recent_year, recent_label = annual_periods[0]
            prev_year, prev_label = annual_periods[1]
            
            end_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], recent_label)
            start_ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], prev_label)
            
            if end_ref and start_ref:
                years_diff = float(recent_year) - float(prev_year)
                if years_diff > 0:
                    # CAGR fallback calculado
                    return f"=IFERROR(MAX(MIN(POWER({end_ref}/{start_ref},1/{years_diff})-1,0.15),0.02),0.05)"
        
        return "0.05"  # Fallback final

    # ----------------------------
    # Estilos
    # ----------------------------
    def _setup_styles(self):
        brand_primary = '0F172A'
        brand_secondary = '1F2937'
        brand_accent = '2563EB'
        brand_gray_150 = 'F0F0F0'
        base_font = 'Calibri'

        # Fonts existentes
        self.header_font = Font(name=base_font, size=16, bold=True, color="FFFFFF")
        self.subheader_font = Font(name=base_font, size=11, bold=True, color="FFFFFF")
        self.input_font = Font(name=base_font, size=10)
        self.data_font = Font(name=base_font, size=10)
        
        # Nuevos fonts profesionales
        self.section_title_font = Font(name=base_font, size=13, bold=True, color=brand_primary)
        self.key_metric_font = Font(name=base_font, size=11, bold=True, color="FFFFFF")
        self.result_font = Font(name=base_font, size=11, bold=True, color=brand_primary)
        self.label_font = Font(name=base_font, size=10, color="374151")

        # Fills existentes
        self.header_fill = PatternFill(start_color=brand_primary, end_color=brand_primary, fill_type="solid")
        self.subheader_fill = PatternFill(start_color=brand_secondary, end_color=brand_secondary, fill_type="solid")
        self.input_fill = PatternFill(start_color="DBEEF3", end_color="DBEEF3", fill_type="solid")
        self.calculated_fill = PatternFill(start_color=brand_gray_150, end_color=brand_gray_150, fill_type="solid")
        self.value_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        
        # Nuevos fills profesionales (manteniendo colores originales)
        self.section_fill = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")  # Fondo suave sección
        self.key_result_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")  # Mantener amarillo original
        self.projection_header_fill = PatternFill(start_color=brand_secondary, end_color=brand_secondary, fill_type="solid")  # Mantener gris secundario
        self.valuation_fill = PatternFill(start_color=brand_secondary, end_color=brand_secondary, fill_type="solid")  # Mantener gris secundario  
        self.sensitivity_fill = PatternFill(start_color=brand_secondary, end_color=brand_secondary, fill_type="solid")  # Mantener gris secundario
        
        # Bordes existentes y nuevos
        thin = Side(border_style="thin", color="000000")
        medium = Side(border_style="medium", color=brand_primary)
        thick = Side(border_style="thick", color=brand_accent)
        
        self.border = Border(top=thin, left=thin, right=thin, bottom=thin)
        self.section_border = Border(top=medium, left=medium, right=medium, bottom=medium)
        self.highlight_border = Border(top=thick, left=thick, right=thick, bottom=thick)
        
        # Alineaciones
        self.center = Alignment(horizontal="center", vertical="center")
        self.center_wrap = Alignment(horizontal="center", vertical="center", wrap_text=True)
        self.left_center = Alignment(horizontal="left", vertical="center")
        self.right_center = Alignment(horizontal="right", vertical="center")

    def _apply_sheet_header(self, ws, title: str, subtitle: str = None, ncols: int = 10):
        ws.sheet_properties.tabColor = "2563EB"
        ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
        ws["A1"] = title
        ws["A1"].font = self.header_font
        ws["A1"].fill = self.header_fill
        ws["A1"].alignment = self.center
        ws.row_dimensions[1].height = 30  # Aumentado para más elegancia

        if subtitle:
            ws.merge_cells(f"A2:{get_column_letter(ncols)}2")
            ws["A2"] = subtitle
            ws["A2"].font = Font(name="Calibri", size=11, color="111827")
            ws["A2"].alignment = self.center
            ws.row_dimensions[2].height = 20  # Aumentado
    
    def _create_professional_section(self, ws, start_row: int, title: str, icon: str = "", ncols: int = 10, fill_type: str = "section"):
        """
        Crea una sección profesional con título, icono y separador visual
        
        Args:
            ws: Worksheet
            start_row: Fila donde empieza la sección
            title: Título de la sección
            icon: Emoji/símbolo para la sección
            ncols: Número de columnas a cubrir
            fill_type: Tipo de relleno ('section', 'projection', 'valuation', 'sensitivity')
        """
        # Mapeo de tipos de relleno
        fill_map = {
            'section': self.section_fill,
            'projection': self.projection_header_fill,
            'valuation': self.valuation_fill,
            'sensitivity': self.sensitivity_fill,
            'inputs': self.subheader_fill
        }
        
        font_map = {
            'section': self.section_title_font,
            'projection': self.key_metric_font,
            'valuation': self.key_metric_font,
            'sensitivity': self.key_metric_font,
            'inputs': self.subheader_font
        }
        
        # Crear título con icono
        section_title = f"{icon} {title}" if icon else title
        
        # Aplicar formato a la sección
        ws.merge_cells(f"A{start_row}:{get_column_letter(ncols)}{start_row}")
        ws[f"A{start_row}"] = section_title
        ws[f"A{start_row}"].font = font_map.get(fill_type, self.section_title_font)
        ws[f"A{start_row}"].fill = fill_map.get(fill_type, self.section_fill)
        ws[f"A{start_row}"].alignment = self.center
        ws[f"A{start_row}"].border = self.section_border
        
        # Ajustar altura de fila
        ws.row_dimensions[start_row].height = 25
        
        # Agregar línea separadora sutil debajo
        separator_row = start_row + 1
        for col in range(1, ncols + 1):
            cell = ws.cell(row=separator_row, column=col)
            cell.fill = PatternFill(start_color="E5E7EB", end_color="E5E7EB", fill_type="solid")
        ws.row_dimensions[separator_row].height = 3
        
        return start_row + 2  # Retorna la siguiente fila disponible

    # ----------------------------
    # Organización de hojas
    # ----------------------------
    def _organize_worksheets(self):
        """
        Reorganiza las hojas del workbook en el orden profesional especificado:
        Balance General → Estado de Resultados → Flujo Efectivo → NOTAS → DRIVERS WC → 
        DCF 2024 → DCF 2025Q2 → RATIOS & KPIs → Resumen Comparativo → Escenarios
        """
        # Orden deseado de las hojas (categorías)
        financial_statements = ["Balance General", "Estado de Resultados", "Estado Resultados (Función)", "Flujo Efectivo", "Cash Flow"]
        notes = ["NOTAS", "Notas"]
        drivers = ["DRIVERS WC"]
        ratios = ["RATIOS & KPIs"]
        summary_analysis = ["Resumen Comparativo", "Escenarios"]
        
        # Obtener hojas existentes
        existing_sheets = self.wb.sheetnames.copy()
        
        # Separar hojas DCF dinámicas
        dcf_sheets = [sheet for sheet in existing_sheets if sheet.startswith("DCF ")]
        dcf_sheets.sort()  # Ordenar alfabéticamente (2024, 2025Q1, 2025Q2, etc.)
        
        # Crear orden completo
        desired_order = []
        
        # 1. Estados financieros
        for category in [financial_statements, notes, drivers]:
            for sheet_name in category:
                if sheet_name in existing_sheets:
                    desired_order.append(sheet_name)
        
        # 2. Hojas DCF dinámicas (ordenadas)
        desired_order.extend(dcf_sheets)
        
        # 3. Ratios y análisis final
        for category in [ratios, summary_analysis]:
            for sheet_name in category:
                if sheet_name in existing_sheets:
                    desired_order.append(sheet_name)
        
        # Agregar cualquier hoja restante que no esté en las categorías
        remaining_sheets = [sheet for sheet in existing_sheets if sheet not in desired_order]
        ordered_sheets = desired_order + remaining_sheets
        
        # Reorganizar las hojas en el workbook
        for i, sheet_name in enumerate(ordered_sheets):
            if sheet_name in self.wb.sheetnames:
                sheet = self.wb[sheet_name]
                # Mover la hoja a la posición correcta
                self.wb.move_sheet(sheet, offset=i - self.wb.index(sheet))
        
        # Hojas reorganizadas en orden profesional

    # ----------------------------
    # Formateo de números profesional
    # ----------------------------
    def _apply_professional_number_formatting(self, ws, start_row: int, end_row: int, column_formats: dict):
        """
        Aplica formateo profesional de números (moneda, porcentaje, números)
        
        Args:
            ws: Worksheet
            start_row: Fila inicial
            end_row: Fila final
            column_formats: Dict con formato por columna {columna: tipo}
                - 'currency': Formato moneda (#,##0)
                - 'currency_millions': Formato moneda en millones (#,##0,, "M")
                - 'percentage': Formato porcentaje (0.00%)
                - 'percentage_1': Formato porcentaje 1 decimal (0.0%)
                - 'number': Formato número con comas (#,##0)
                - 'decimal': Formato decimal (0.00)
        """
        format_map = {
            'currency': '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)',  # Formato moneda profesional
            'currency_millions': '_($* #,##0,,"M"_);_($* (#,##0,,"M");_($* "-"_);_(@_)',  # Millones
            'percentage': '0.00%',
            'percentage_1': '0.0%', 
            'number': '#,##0',
            'decimal': '0.00',
            'accounting': '_-* #,##0_-;-* #,##0_-;_-* "-"_-;_-@_-'  # Formato contable
        }
        
        for row in range(start_row, end_row + 1):
            for col, format_type in column_formats.items():
                if format_type in format_map:
                    try:
                        cell = ws.cell(row=row, column=col)
                        cell.number_format = format_map[format_type]
                    except AttributeError:
                        # Saltar celdas combinadas
                        pass

    # ----------------------------
    # Hojas
    # ----------------------------
    def create_drivers_wc_sheet(self):
        """Crea la hoja DRIVERS WC, referenciando directamente las hojas originales."""
        ws = self.wb.create_sheet("DRIVERS WC")
        self._apply_sheet_header(ws, "ANÁLISIS DE CAPITAL DE TRABAJO",
                                 "Drivers para cálculo de capital de trabajo neto", 10)

        row = 4
        ws[f"A{row}"] = "DEFINICIONES:"
        ws[f"A{row}"].font = self.subheader_font
        row += 1
        for txt in [
            "CxC = Deudores comerciales y otras cuentas por cobrar corrientes",
            "Inventarios = Inventarios corrientes",
            "CxP = Cuentas por pagar comerciales y otras cuentas por pagar",
            "NWC = (CxC + Inventarios) - CxP",
            "ΔNWC = NWC_actual - NWC_anterior",
            "ΔNWC/ΔVentas = ΔNWC / (Ventas_actual - Ventas_anterior)",
        ]:
            ws[f"A{row}"] = txt
            row += 1

        # Aviso metodológico: sólo años completos (Q4 = año consolidado)
        ws[f"A{row}"] = ("Nota: los datos de la CMF son YTD acumulados (Q4 = año completo). "
                         "Para no mezclar escalas, el driver usa SÓLO períodos anuales (Q4), año contra año.")
        ws[f"A{row}"].font = self.small_font if hasattr(self, "small_font") else self.label_font
        row += 2

        headers = ["Período", "Ventas (año)", "CxC", "Inventarios", "CxP", "NWC", "NWC/Ventas", "ΔNWC", "ΔVentas (año)", "ΔNWC/ΔVentas"]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=row, column=c, value=h)
            cell.font = self.subheader_font
            cell.fill = self.subheader_fill
            cell.alignment = self.center
            cell.border = self.border

        data_row = row + 1

        # SÓLO períodos ANUALES (YYYYQ4 o YYYY), ordenados de más antiguo a más
        # nuevo, para que cada fila compare año contra año (ΔVentas/ΔNWC anuales).
        all_periods = self._iter_periods_from_sheet(self.sh_pl) or []
        def _yr(p):
            m = re.match(r"^(\d{4})", str(p))
            return int(m.group(1)) if m else 0
        annual = [p for p in all_periods if re.match(r"^\d{4}(Q4)?$", str(p).strip())]
        # dedup por año conservando la etiqueta tal cual aparece en la hoja
        seen_yr = {}
        for p in annual:
            seen_yr[_yr(p)] = p
        annual_sorted = [seen_yr[y] for y in sorted(seen_yr.keys())]
        annual_sorted = annual_sorted[-6:]  # últimos ~6 años completos

        n = len(annual_sorted)
        for i, lbl in enumerate(annual_sorted):
            r = data_row + i
            ws.cell(row=r, column=1, value=lbl)

            def _ref(sheet, rows_map, key):
                if sheet and key in rows_map and rows_map[key]:
                    rr = self.create_cell_reference_by_label(sheet, rows_map[key], lbl)
                    return rr
                return None
            ventas_ref = _ref(self.sh_pl, self.rows_pl, "Ventas")
            cxc_ref = _ref(self.sh_bal, self.rows_bal, "CxC")
            inv_ref = _ref(self.sh_bal, self.rows_bal, "Inv")
            cxp_ref = _ref(self.sh_bal, self.rows_bal, "CxP")
            if ventas_ref: ws.cell(row=r, column=2, value=f"=IFERROR({ventas_ref},\"\")")
            if cxc_ref: ws.cell(row=r, column=3, value=f"=IFERROR({cxc_ref},\"\")")
            if inv_ref: ws.cell(row=r, column=4, value=f"=IFERROR({inv_ref},\"\")")
            if cxp_ref: ws.cell(row=r, column=5, value=f"=IFERROR({cxp_ref},\"\")")

            # NWC = (CxC + Inventarios) - CxP  ; NWC/Ventas (nivel, estable)
            ws.cell(row=r, column=6, value=f"=C{r}+D{r}-E{r}")
            ws.cell(row=r, column=7, value=f"=IFERROR(F{r}/B{r},\"\")")

            # ΔNWC, ΔVentas y ratio — SIEMPRE año-contra-año (filas consecutivas = años consecutivos)
            if i > 0:
                ws.cell(row=r, column=8, value=f"=F{r}-F{r-1}")
                ws.cell(row=r, column=9, value=f"=B{r}-B{r-1}")
                # Ratio acotado a un rango razonable para que un año de bajo crecimiento no lo dispare
                ws.cell(row=r, column=10, value=f"=IFERROR(IF(I{r}=0,\"\",MAX(MIN(H{r}/I{r},0.5),-0.5)),\"\")")

        # Promedio del driver: usar la MEDIANA de los ΔNWC/ΔVentas anuales (robusta a
        # outliers) y, como respaldo, el promedio de NWC/Ventas (nivel). Se referencia
        # desde el DCF mediante self._wc_avg_cell.
        avg_row = data_row + max(n, 1) + 2
        ws[f"A{avg_row}"] = "Driver capital de trabajo (NWC/Ventas, mediana):"
        ws[f"A{avg_row}"].font = self.subheader_font
        # Usamos el NIVEL NWC/Ventas (mediana de años completos), estable, en vez de
        # ΔNWC/ΔVentas que se dispara cuando las ventas anuales crecen poco. En el DCF
        # ΔNWC = ΔVentas × (NWC/Ventas), que es la relación económica correcta.
        ws[f"B{avg_row}"] = f"=IFERROR(MEDIAN(G{data_row}:G{data_row + n - 1}),0.10)"
        ws[f"B{avg_row}"].fill = self.input_fill
        ws[f"B{avg_row}"].border = self.border
        ws[f"B{avg_row}"].number_format = "0.00%"
        # Guardar referencia para el DCF
        self._wc_avg_cell = f"'DRIVERS WC'!$B${avg_row}"

        drivers_wc_formats = {2: 'currency', 3: 'currency', 4: 'currency', 5: 'currency',
                              6: 'currency', 7: 'percentage', 8: 'currency', 9: 'currency', 10: 'percentage'}
        self._apply_professional_number_formatting(ws, data_row, data_row + max(n - 1, 0), drivers_wc_formats)
        for rr in range(data_row, data_row + n):
            for cc in range(1, 11):
                try:
                    ws.cell(row=rr, column=cc).border = self.border
                except AttributeError:
                    pass

        widths = [12, 15, 16, 14, 14, 16, 13, 14, 15, 15]
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w

    def create_dcf_sheet(self):
        """Hoja principal DCF con referencias directas a hojas originales."""
        ws = self.wb.create_sheet("DCF")
        self._apply_sheet_header(ws, "MODELO DCF (FCFF) - FLUJO DE CAJA LIBRE DE LA FIRMA",
                                 "Valuación por flujos de caja descontados con análisis de sensibilidad", 16)

        # Crear sección de configuración con diseño profesional
        config_row = self._create_professional_section(ws, 4, "CONFIGURACIÓN DEL MODELO", "", 6, "inputs")
        
        # Selector de período con diseño mejorado
        ws[f"A{config_row}"] = "Período seleccionado:"
        ws[f"A{config_row}"].font = self.label_font

        default_period = self._find_latest_period()
        ws[f"C{config_row}"] = default_period
        ws[f"C{config_row}"].fill = self.input_fill
        ws[f"C{config_row}"].border = self.border
        ws[f"C{config_row}"].font = self.input_font

        # Validación de lista de períodos directamente desde ER fila 3
        if DataValidation:
            # Rango de encabezados amplio (B3:ZZ3) en Estado de Resultados
            dv = DataValidation(type="list",
                                formula1=f"'{self.sh_pl.title}'!$B$3:$ZZ$3")
            dv.add(ws[f"C{config_row}"])
            ws.add_data_validation(dv)

        # Escenario con diseño mejorado
        ws[f"E{config_row}"] = "Escenario:"
        ws[f"E{config_row}"].font = self.label_font
        ws[f"F{config_row}"] = "Base"
        ws[f"F{config_row}"].fill = self.input_fill
        ws[f"F{config_row}"].border = self.border
        ws[f"F{config_row}"].font = self.input_font
        if DataValidation:
            dv2 = DataValidation(type="list", formula1='"Conservador,Base,Agresivo"')
            dv2.add(ws[f"F{config_row}"])
            ws.add_data_validation(dv2)

        # INPUTS con diseño profesional
        row = config_row + 3
        inputs_row = self._create_professional_section(ws, row, "PARÁMETROS DEL MODELO", "", 10, "inputs")

        # Determinar el período para este DCF específico
        # Si existe un período seleccionado en la configuración, usarlo
        selected_period = self._find_base_annual_period()
        if hasattr(self, '_current_dcf_period'):
            selected_period = self._current_dcf_period

        # Referencia al driver de capital de trabajo (mediana anual robusta)
        wc_ref = getattr(self, "_wc_avg_cell", "'DRIVERS WC'!$B$21")

        # La base de la proyección es el último CIERRE ANUAL, no el trimestre en curso.
        #
        # Antes se pasaba `selected_period` (p. ej. "2026Q1") y las ventas base salían de
        # anualizar ese trimestre (×4). Para cualquier negocio estacional —una viña, un
        # retail, una salmonera— eso distorsiona los cinco años de proyección de una sola
        # vez. El DCF que se guarda en la BD (scripts/dcf/excel_aligned.py) usa el último
        # año real, y ahora el Excel también.
        periodo_base_anual = self._find_base_annual_period()

        inputs = [
            ("Año base", periodo_base_anual, "input"),
            ("Ventas año base (M$)", self._get_ventas_base_formula(periodo_base_anual), "formula"),
            ("Crecimiento Ventas Y+1 (%)", self._get_cagr_formula(5), "formula"),
            ("Crecimiento Ventas Y+2 (%)", f"=MAX(B{inputs_row + 2}*0.9,0.02)", "formula"),  # Referencia correcta al Y+1
            ("Crecimiento Ventas Y+3 (%)", f"=MAX(B{inputs_row + 3}*0.9,0.02)", "formula"),  # Referencia correcta al Y+2
            ("Crecimiento Ventas Y+4 (%)", f"=MAX(B{inputs_row + 4}*0.85,0.015)", "formula"), # Referencia correcta al Y+3
            ("Crecimiento Ventas Y+5 (%)", f"=MAX(B{inputs_row + 5}*0.8,0.015)", "formula"),  # Referencia correcta al Y+4
            ("Margen EBIT (%)", self._get_margen_ebit_formula(), "formula"),
            ("Tasa efectiva de impuestos (%)", self._get_tasa_impuestos_formula(), "formula"),
            ("D&A / Ventas (%)", self._get_da_ventas_formula(), "formula"),
            ("CapEx / Ventas (%)", self._get_capex_ventas_formula(), "formula"),
            ("ΔNWC / ΔVentas (%)", f"=IFERROR(MIN(MAX({wc_ref},-0.20),0.20),0.10)", "formula"),
            ("WACC (%)", "0.10", "input"),
            ("g - Tasa de crecimiento terminal (%)", "0.02", "fixed"),  # Fijo en 2%
            # La moneda viaja PEGADA al modelo, no en una nota al pie.
            ("Moneda de los estados", self.reporting_currency, "input"),
            # Editable. Si los estados están en pesos vale 1 y no hace nada. Si están en
            # dólares, es lo que convierte el valor por acción a pesos para poder
            # compararlo con el precio de bolsa. El analista puede ajustarlo al tipo de
            # cambio que quiera usar — pero NUNCA se compara sin convertir.
            ("Tipo de cambio (CLP por 1 %s)" % self.reporting_currency,
             "1" if self.reporting_currency == "CLP" else "950", "input"),
            ("Deuda neta (M$)", self._get_deuda_neta_formula(selected_period), "formula"),
            ("Acciones en circulación (M)", self._get_acciones_formula(), "formula"),
        ]

        # Fila de cada parámetro, resuelta POR ETIQUETA.
        #
        # Antes las filas eran offsets fijos (wacc_row = inputs_row + 12, deuda_row = +14…).
        # Agregar un parámetro en medio de la lista desplazaba todo y el modelo apuntaba a
        # celdas equivocadas SIN dar error: el Excel simplemente calculaba otra cosa. Es
        # una trampa que se dispara sola la próxima vez que alguien toque esta lista.
        self._param_rows = {label: inputs_row + i for i, (label, _v, _k) in enumerate(inputs)}

        for i, (label, val, kind) in enumerate(inputs):
            r = inputs_row + i
            
            ws[f"A{r}"] = label
            ws[f"A{r}"].font = self.label_font
            ws[f"A{r}"].alignment = self.left_center

            cell = ws[f"B{r}"]
            # Regla general: si el valor es una CONSTANTE numérica (no una fórmula
            # que empieza con "="), se escribe como NÚMERO, no como texto. Así el
            # number_format aplica y en Excel chileno (es-CL) el separador decimal
            # se muestra con coma. Un string "0.02"/"0.27"/"0.05" se vería con punto.
            v = val
            if isinstance(v, str) and not v.strip().startswith("="):
                try:
                    v = float(v)
                except Exception:
                    pass  # texto real (p. ej. "Año base" = "2026Q1")
            cell.value = v
            cell.fill = self.input_fill if kind == "input" else self.calculated_fill
            cell.border = self.border
            cell.font = self.input_font
            cell.alignment = self.right_center
            
            # Formateo profesional según el tipo de input
            if "%" in label or "Crecimiento" in label or "Margen" in label or "WACC" in label or "tasa" in label.lower():
                cell.number_format = '0.00%'  # Formato porcentaje
            elif "M$" in label or "Ventas" in label or "Deuda" in label:
                cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'  # Formato moneda
            elif "Acciones" in label:
                cell.number_format = '#,##0'  # Formato número

        # PROYECCIÓN FCFF con diseño profesional
        projection_start_row = inputs_row + len(inputs) + 3
        proj_header_row = self._create_professional_section(ws, projection_start_row, "PROYECCIÓN FCFF (5 AÑOS)", "", 10, "projection")
        projection_start_row = proj_header_row - 1  # Ajustar para mantener compatibilidad

        # Encabezados sin iconos
        headers = [
            "Año", "Ventas", "EBIT", "NOPAT", 
            "D&A", "CapEx", "ΔNWC", "FCFF", "Factor", "FCFF PV"
        ]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=projection_start_row + 1, column=c, value=h)
            cell.font = self.key_metric_font
            cell.fill = self.projection_header_fill
            cell.alignment = self.center_wrap
            cell.border = self.border
        
        # Ajustar altura del encabezado
        ws.row_dimensions[projection_start_row + 1].height = 30

        # Extract numeric year from base annual period (e.g. "2025Q4" -> 2025)
        _bp = self._find_base_annual_period()
        base_year = int(re.match(r"(\d{4})", _bp).group(1)) if re.match(r"(\d{4})", _bp) else 2025
        P = self._param_rows
        ventas_base_row = P["Ventas año base (M$)"]
        crec_rows = [P[f"Crecimiento Ventas Y+{k} (%)"] for k in range(1, 6)]
        margen_ebit_row = P["Margen EBIT (%)"]
        tasa_imp_row = P["Tasa efectiva de impuestos (%)"]
        da_ventas_row = P["D&A / Ventas (%)"]
        capex_ventas_row = P["CapEx / Ventas (%)"]
        nwc_ventas_row = P["ΔNWC / ΔVentas (%)"]
        wacc_row = P["WACC (%)"]

        for k in range(1, 6):
            r = projection_start_row + 1 + k
            ws.cell(row=r, column=1, value=base_year + k)  # Año

            if k == 1:
                ws.cell(row=r, column=2, value=f"=$B${ventas_base_row}*(1+$B${crec_rows[0]})")
            else:
                ws.cell(row=r, column=2, value=f"=B{r-1}*(1+$B${crec_rows[k-1]})")

            ws.cell(row=r, column=3, value=f"=B{r}*$B${margen_ebit_row}")             # EBIT
            ws.cell(row=r, column=4, value=f"=C{r}*(1-$B${tasa_imp_row})")             # NOPAT
            ws.cell(row=r, column=5, value=f"=B{r}*$B${da_ventas_row}")                # D&A
            ws.cell(row=r, column=6, value=f"=B{r}*$B${capex_ventas_row}")            # CapEx
            if k == 1:
                ws.cell(row=r, column=7, value=f"=(B{r}-$B${ventas_base_row})*$B${nwc_ventas_row}")
            else:
                ws.cell(row=r, column=7, value=f"=(B{r}-B{r-1})*$B${nwc_ventas_row}")  # ΔNWC

            ws.cell(row=r, column=8, value=f"=D{r}+E{r}-F{r}-G{r}")                    # FCFF
            ws.cell(row=r, column=9, value=f"=1/(1+$B${wacc_row})^{k}")                # Factor
            ws.cell(row=r, column=10, value=f"=H{r}*I{r}")                              # PV

            for c in range(1, 11):
                cc = ws.cell(row=r, column=c)
                cc.border = self.border
                
                # Formateo profesional por columna
                if c == 1:  # Año
                    cc.number_format = '0'
                elif c in [2, 3, 4, 5, 6, 7, 8, 10]:  # Valores monetarios (Ventas, EBIT, NOPAT, D&A, CapEx, ΔNWC, FCFF, FCFF PV)
                    cc.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
                elif c == 9:  # Factor de descuento
                    cc.number_format = '0.0000'

        # VALUACIÓN con diseño profesional
        valuation_row = projection_start_row + 8
        val_header_row = self._create_professional_section(ws, valuation_row, "VALUACIÓN EMPRESARIAL", "", 10, "valuation")
        valuation_row = val_header_row - 1

        last_fcff_row = projection_start_row + 6
        g_row = P["g - Tasa de crecimiento terminal (%)"]
        deuda_row = P["Deuda neta (M$)"]
        acciones_row = P["Acciones en circulación (M)"]
        fx_row = P[f"Tipo de cambio (CLP por 1 {self.reporting_currency})"]

        # Bloques de valuación. Las filas se resuelven POR ETIQUETA, igual que los
        # parámetros: los offsets numéricos (valuation_row + 8, + 10, + 11…) se desplazan
        # solos en cuanto alguien agrega una fila, y el Excel calcula otra cosa sin dar
        # ningún error.
        V = {}
        _labels = [
            "Valor Terminal", "VT Presente", "Suma FCFF PV", "Enterprise Value",
            "(-) Deuda Neta", "Equity Value", "Acciones",
            f"Valor por Acción (DCF, {self.reporting_currency})",
            "Valor por Acción (DCF, CLP)", "",
            "Precio Actual Mercado (CLP)", "Prima/(Descuento) %", "Recomendación",
        ]
        for i, lbl in enumerate(_labels):
            V[lbl] = valuation_row + 1 + i

        r_dcf_moneda = V[f"Valor por Acción (DCF, {self.reporting_currency})"]
        r_dcf_clp = V["Valor por Acción (DCF, CLP)"]
        r_precio = V["Precio Actual Mercado (CLP)"]
        r_prima = V["Prima/(Descuento) %"]

        blocks = [
            ("Valor Terminal", f"=H{last_fcff_row}*(1+$B${g_row})/($B${wacc_row}-$B${g_row})"),
            ("VT Presente", f"=B{V['Valor Terminal']}*I{last_fcff_row}"),
            ("Suma FCFF PV", f"=SUM(J{projection_start_row + 2}:J{last_fcff_row})"),
            ("Enterprise Value", f"=B{V['VT Presente']}+B{V['Suma FCFF PV']}"),
            ("(-) Deuda Neta", f"=$B${deuda_row}"),
            ("Equity Value", f"=B{V['Enterprise Value']}-B{V['(-) Deuda Neta']}"),
            ("Acciones", f"=$B${acciones_row}"),
            # Valor por acción EN LA MONEDA DE LOS ESTADOS. Para SQM, COPEC o ARAUCO, esto
            # sale en dólares.
            (f"Valor por Acción (DCF, {self.reporting_currency})",
             f"=IFERROR(IF(B{V['Acciones']}>0,B{V['Equity Value']}/B{V['Acciones']}*1000,\"\"),\"\")"),
            # Y AQUÍ se convierte a pesos. Éste es el número que se compara contra la bolsa,
            # porque la acción cotiza en pesos.
            #
            # Antes esta fila no existía: el Excel comparaba un valor intrínseco en DÓLARES
            # contra un precio de mercado en PESOS. Para las 18 empresas que reportan en USD,
            # la "Prima/(Descuento)" salía desviada ~900x y la "Recomendación" decía siempre
            # "VENTA FUERTE". Un analista que le creyera vendía justo lo que debía comprar.
            ("Valor por Acción (DCF, CLP)", f"=IFERROR(B{r_dcf_moneda}*$B${fx_row},\"\")"),
            ("", ""),
            ("Precio Actual Mercado (CLP)", "INPUT_REQUIRED"),
            # La prima compara PESOS CONTRA PESOS.
            ("Prima/(Descuento) %",
             f"=IF(NOT(ISNUMBER(B{r_precio})),\"SIN PRECIO MERCADO\","
             f"IF(NOT(ISNUMBER(B{r_dcf_clp})),\"SIN VALOR DCF\","
             f"IF(B{r_dcf_clp}<0,\"DCF NEG - VENTA\","
             f"(B{r_dcf_clp}-B{r_precio})/B{r_precio})))"),
            ("Recomendación",
             f"=IF(NOT(ISNUMBER(B{r_precio})),\"NECESITA PRECIO MERCADO\","
             f"IF(NOT(ISNUMBER(B{r_dcf_clp})),\"SIN VALOR DCF\","
             f"IF(B{r_dcf_clp}<0,\"VENTA FUERTE - DCF NEGATIVO\","
             f"IF(NOT(ISNUMBER(B{r_prima})),\"SIN PRIMA\","
             f"IF(B{r_prima}>0.15,\"COMPRA FUERTE\","
             f"IF(B{r_prima}>0.05,\"COMPRA\","
             f"IF(B{r_prima}>-0.05,\"MANTENER\","
             f"IF(B{r_prima}>-0.15,\"VENTA\",\"VENTA FUERTE\")))))))"),
        ]
        for i, (lbl, fx) in enumerate(blocks):
            rr = valuation_row + 1 + i
            ws[f"A{rr}"] = lbl
            ws[f"A{rr}"].font = self.label_font
            ws[f"A{rr}"].alignment = self.left_center
            
            cell = ws[f"B{rr}"]
            cell.value = fx
            cell.border = self.border
            cell.alignment = self.right_center
            
            # Destacar resultados clave con colores especiales
            if "Enterprise Value" in lbl or "Equity Value" in lbl:
                cell.fill = self.key_result_fill
                cell.font = self.key_metric_font
                ws[f"A{rr}"].font = self.result_font
            elif "Valor por Acción (DCF)" in lbl:
                cell.fill = self.key_result_fill
                cell.font = self.key_metric_font
                ws[f"A{rr}"].font = self.result_font
                # Hacer la fila más alta para destacar el resultado final
                ws.row_dimensions[rr].height = 25
            elif "Precio Actual Mercado" in lbl:
                cell.fill = self.input_fill
                cell.font = self.input_font
                ws[f"A{rr}"].font = self.label_font
                # Texto explicativo para el usuario
                cell.value = "INSERT_PRICE_HERE"
            elif "Prima/(Descuento)" in lbl:
                cell.fill = self.calculated_fill
                cell.font = self.result_font
                ws[f"A{rr}"].font = self.result_font
            elif "Recomendación" in lbl:
                cell.fill = self.key_result_fill
                cell.font = self.key_metric_font
                ws[f"A{rr}"].font = self.result_font
                ws.row_dimensions[rr].height = 25
            elif lbl == "":  # Línea separadora
                cell.fill = PatternFill(fill_type=None)
                cell.value = ""
                ws[f"A{rr}"].value = ""
            elif i >= 3:  # Otros valores importantes
                cell.fill = self.value_fill
                cell.font = self.input_font
            else:
                cell.font = self.input_font
            
            # Formateo específico por tipo de valor
            if "Valor Terminal" in lbl or "VT Presente" in lbl or "Suma FCFF PV" in lbl or "Enterprise Value" in lbl or "Deuda Neta" in lbl or "Equity Value" in lbl:
                cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'  # Formato moneda profesional
            elif "Acciones" in lbl:
                cell.number_format = '#,##0'  # Formato número
            elif "Valor por Acción" in lbl or "Precio Actual Mercado" in lbl:
                cell.number_format = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"_);_(@_)'  # Moneda con decimales
            elif "Prima/(Descuento)" in lbl:
                cell.number_format = '0.0%'  # Formato porcentaje

        # Anchos
        for i, w in enumerate([25, 15, 12, 12, 12, 12, 12, 12, 12, 12], 1):
            ws.column_dimensions[get_column_letter(i)].width = w

        return projection_start_row, valuation_row, row

    def create_scenarios_sheet(self):
        """
        Crea una hoja de Escenarios interactiva que calcula la valuación para diferentes supuestos.
        Cada escenario calcula automáticamente Enterprise Value, Equity Value y Valor por Acción.
        """
        ws = self.wb.create_sheet("Escenarios")
        self._apply_sheet_header(ws, "ESCENARIOS DE VALUACIÓN", 16)

        # SECCIÓN 1: PARÁMETROS DE LOS ESCENARIOS
        params_row = self._create_professional_section(ws, 4, "PARÁMETROS POR ESCENARIO", "", 12, "inputs")
        
        headers = ["Escenario", "Crec Y+1", "Crec Y+2", "Crec Y+3", "Crec Y+4", "Crec Y+5",
                   "Margen EBIT", "Tasa Impuestos", "D&A/Ventas", "CapEx/Ventas", "ΔNWC/ΔVentas"]
        for c, h in enumerate(headers, 1):
            cell = ws.cell(row=params_row, column=c, value=h)
            cell.font = self.key_metric_font
            cell.fill = self.subheader_fill
            cell.alignment = self.center_wrap
            cell.border = self.border

        # Obtener referencias dinámicas a los inputs base del DCF principal
        # Intentar encontrar hojas DCF disponibles
        dcf_sheets = [sheet for sheet in self.wb.sheetnames if sheet.startswith("DCF ")]
        dcf_base_sheet = dcf_sheets[0] if dcf_sheets else "DCF"
        
        # Buscar filas de parámetros en la hoja DCF base
        def find_dcf_param_row(param_text):
            try:
                sheet = self.wb[dcf_base_sheet]
                for row in range(1, min(sheet.max_row + 1, 50)):
                    cell = sheet.cell(row=row, column=1)
                    if cell.value and isinstance(cell.value, str) and param_text.lower() in cell.value.lower():
                        return f"'{dcf_base_sheet}'!B{row}"
                return None
            except:
                return None
        
        # Referencias dinámicas a parámetros base
        base_crec_y1 = find_dcf_param_row("Crecimiento Ventas Y+1") or f"'{dcf_base_sheet}'!B11"
        base_crec_y2 = find_dcf_param_row("Crecimiento Ventas Y+2") or f"'{dcf_base_sheet}'!B12" 
        base_crec_y3 = find_dcf_param_row("Crecimiento Ventas Y+3") or f"'{dcf_base_sheet}'!B13"
        base_crec_y4 = find_dcf_param_row("Crecimiento Ventas Y+4") or f"'{dcf_base_sheet}'!B14"
        base_crec_y5 = find_dcf_param_row("Crecimiento Ventas Y+5") or f"'{dcf_base_sheet}'!B15"
        base_margen = find_dcf_param_row("Margen EBIT") or f"'{dcf_base_sheet}'!B16"
        base_tasa_imp = find_dcf_param_row("Tasa efectiva de impuestos") or f"'{dcf_base_sheet}'!B17"
        base_da_ventas = find_dcf_param_row("D&A / Ventas") or f"'{dcf_base_sheet}'!B18"
        base_capex_ventas = find_dcf_param_row("CapEx / Ventas") or f"'{dcf_base_sheet}'!B19"
        base_nwc_ventas = find_dcf_param_row("ΔNWC / ΔVentas") or f"'{dcf_base_sheet}'!B20"
        
        # Escenarios dinámicos basados en el escenario Base
        scenarios = [
            # Conservador: 20% menos optimista que Base
            ["Conservador", 
             f"=MAX({base_crec_y1}*0.8,0.015)",    # Y+1: 80% del base
             f"=MAX({base_crec_y2}*0.8,0.015)",    # Y+2: 80% del base 
             f"=MAX({base_crec_y3}*0.8,0.015)",    # Y+3: 80% del base
             f"=MAX({base_crec_y4}*0.8,0.01)",     # Y+4: 80% del base
             f"=MAX({base_crec_y5}*0.8,0.01)",     # Y+5: 80% del base
             f"=MIN({base_margen}*0.9,0.06)",      # Margen: 90% del base (conservador usa MIN para piso)
             "0.27",    # Impuestos: Fijo en 27%
             f"={base_da_ventas}*1.05",            # D&A: 105% del base
             f"={base_capex_ventas}*1.1",          # CapEx: 110% del base (más inversión)
             f"={base_nwc_ventas}*1.2"             # NWC: 120% del base (más capital trabajo)
            ],
            # Base: Referencias directas a la hoja DCF
            ["Base",        
             f"={base_crec_y1}",  # Referencia directa Y+1
             f"={base_crec_y2}",  # Referencia directa Y+2
             f"={base_crec_y3}",  # Referencia directa Y+3
             f"={base_crec_y4}",  # Referencia directa Y+4
             f"={base_crec_y5}",  # Referencia directa Y+5
             f"={base_margen}",   # Referencia directa Margen
             "0.27", # Tasa impuestos fija en 27%
             f"={base_da_ventas}",# Referencia directa D&A
             f"={base_capex_ventas}", # Referencia directa CapEx
             f"={base_nwc_ventas}"    # Referencia directa NWC
            ],
            # Agresivo: 20% más optimista que Base
            ["Agresivo",    
             f"={base_crec_y1}*1.2",               # Y+1: 120% del base
             f"={base_crec_y2}*1.2",               # Y+2: 120% del base
             f"={base_crec_y3}*1.2",               # Y+3: 120% del base 
             f"={base_crec_y4}*1.2",               # Y+4: 120% del base
             f"={base_crec_y5}*1.2",               # Y+5: 120% del base
             f"=MAX({base_margen}*1.15,0.18)",     # Margen: 115% del base (agresivo usa MAX para piso alto)
             "0.27",    # Impuestos: Fijo en 27%
             f"={base_da_ventas}*1.05",            # D&A: 105% del base (más depreciación es bueno para FCFF)
             f"={base_capex_ventas}*0.85",         # CapEx: 85% del base (menos inversión)
             f"={base_nwc_ventas}*0.7"             # NWC: 70% del base (mucho menos capital trabajo)
            ]
        ]
        
        # Referencias DCF base encontradas
        # Crecimiento Y+1 identificado
        # Margen EBIT identificado
        # NWC/Ventas identificado
        
        scenario_rows = {}  # Para guardar las filas de cada escenario
        for r_idx, rowvals in enumerate(scenarios, params_row + 1):
            scenario_rows[rowvals[0]] = r_idx
            for c, v in enumerate(rowvals, 1):
                cell = ws.cell(row=r_idx, column=c)
                
                if c == 1:  # Nombre del escenario
                    cell.value = v
                    cell.font = Font(name="Calibri", size=10, bold=True, color="FFFFFF")
                    cell.fill = self.subheader_fill
                    cell.alignment = self.center
                elif isinstance(v, str) and v.startswith("="):  # Fórmulas dinámicas
                    cell.value = v
                    cell.fill = self.calculated_fill
                    cell.font = self.input_font
                else:  # Valores estáticos: escribir como NÚMERO (no texto) para
                       # que el formato % aplique y en es-CL se muestre con coma.
                    try:
                        cell.value = float(v)
                    except (TypeError, ValueError):
                        cell.value = v
                    cell.fill = self.input_fill
                    cell.font = self.input_font
                    
                cell.border = self.border
                
                # Formateo específico por columna
                if c >= 2 and c <= 11:  # Todos los parámetros numéricos
                    cell.number_format = '0.00%'  # Formato porcentaje

        # SECCIÓN 2: CÁLCULOS DE VALUACIÓN AUTOMÁTICOS
        calc_start_row = params_row + len(scenarios) + 3
        calc_header_row = self._create_professional_section(ws, calc_start_row, "RESULTADOS DE VALUACIÓN", "", 12, "valuation")
        
        # Headers de resultados
        result_headers = ["Escenario", "Ventas Base", "WACC", "g Terminal", "Enterprise Value", 
                         "Deuda Neta", "Equity Value", "Acciones (M)", "Valor/Acción", "Premium/Desc vs Base"]
        for c, h in enumerate(result_headers, 1):
            cell = ws.cell(row=calc_header_row, column=c, value=h)
            cell.font = self.key_metric_font
            cell.fill = self.valuation_fill
            cell.alignment = self.center_wrap
            cell.border = self.border

        # Ajustar altura del encabezado
        ws.row_dimensions[calc_header_row].height = 30

        
        # Función para buscar una celda por contenido en una hoja
        def find_cell_by_content(sheet_name, search_text):
            try:
                sheet = self.wb[sheet_name]
                for row in range(1, min(sheet.max_row + 1, 50)):  # Buscar en primeras 50 filas
                    for col in range(1, min(sheet.max_column + 1, 10)):  # Buscar en primeras 10 columnas
                        cell = sheet.cell(row=row, column=col)
                        if cell.value and isinstance(cell.value, str) and search_text.lower() in cell.value.lower():
                            return f"'{sheet_name}'!{get_column_letter(col+1)}{row}"  # Columna B (valor)
                return None
            except:
                return None
        
        # Buscar referencias dinámicamente
        base_ventas_ref = find_cell_by_content(dcf_base_sheet, "Ventas año base") or f"'{dcf_base_sheet}'!B12"
        deuda_neta_ref = find_cell_by_content(dcf_base_sheet, "Deuda neta") or f"'{dcf_base_sheet}'!B22"  
        acciones_ref = find_cell_by_content(dcf_base_sheet, "Acciones en circulación") or f"'{dcf_base_sheet}'!B23"
        
        # Parámetros fijos
        wacc_base = "0.10"  # WACC fijo para todos los escenarios
        g_terminal = "0.02"  # Tasa terminal fija en 2%
        
        # Referencias para scenarios encontradas
        # Ventas base identificadas
        # Deuda neta identificada
        # Acciones identificadas
        
        # Calcular valuaciones para cada escenario
        for i, (scenario_name, _) in enumerate([(s[0], s[1:]) for s in scenarios]):
            r = calc_header_row + 1 + i
            scenario_param_row = scenario_rows[scenario_name]
            
            # Columna 1: Nombre del escenario
            cell = ws.cell(row=r, column=1, value=scenario_name)
            cell.font = self.result_font
            cell.alignment = self.left_center
            cell.border = self.border
            
            # Columna 2: Ventas Base (referencia común)
            cell = ws.cell(row=r, column=2, value=f"={base_ventas_ref}")
            cell.border = self.border
            cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
            
            # Columna 3: WACC (variable según escenario)
            if scenario_name == "Conservador":
                wacc_scenario = "0.12"  # Base + 2pp (10% + 2% = 12%)
            elif scenario_name == "Agresivo":
                wacc_scenario = "0.08"  # Base - 2pp (10% - 2% = 8%)
            else:  # Base
                wacc_scenario = wacc_base  # 10%
                
            cell = ws.cell(row=r, column=3, value=float(wacc_scenario))
            cell.border = self.border
            cell.number_format = '0.00%'

            # Columna 4: g Terminal (fijo)
            cell = ws.cell(row=r, column=4, value=float(g_terminal))
            cell.border = self.border
            cell.number_format = '0.00%'
            
            # Columna 5: Enterprise Value (CÁLCULO BASADO EN METODOLOGÍA DCF)
            # Usar aproximación DCF más precisa que refleje la metodología real
            
            # Referencias a parámetros del escenario
            ventas_base = f"B{r}"
            crec_y1 = f"B{scenario_param_row}"
            crec_y2 = f"C{scenario_param_row}"  
            crec_y3 = f"D{scenario_param_row}"
            crec_y4 = f"E{scenario_param_row}"
            crec_y5 = f"F{scenario_param_row}"
            margen_ebit = f"G{scenario_param_row}"
            tasa_imp = f"H{scenario_param_row}"
            da_ventas = f"I{scenario_param_row}"
            capex_ventas = f"J{scenario_param_row}"
            nwc_ventas = f"K{scenario_param_row}"
            
            # Cálculo aproximado de FCFF promedio anual usando los parámetros del escenario
            # FCFF ≈ Ventas × Margen EBIT × (1-Tax) × [1 + D&A/Ventas - CapEx/Ventas - ΔNWC/ΔVentas]
            # Aplicar crecimiento promedio para obtener ventas promedio del período
            crecimiento_promedio = f"(({crec_y1}+{crec_y2}+{crec_y3}+{crec_y4}+{crec_y5})/5)"
            ventas_promedio = f"({ventas_base}*(1+{crecimiento_promedio}))"
            
            # Cálculo correcto del FCFF
            # NOPAT = Ventas × Margen EBIT × (1 - Tasa Impuestos)
            nopat = f"({ventas_promedio}*{margen_ebit}*(1-{tasa_imp}))"
            
            # D&A = Ventas × D&A/Ventas (positivo para FCFF)
            da_amount = f"({ventas_promedio}*{da_ventas})"
            
            # CapEx = Ventas × CapEx/Ventas (negativo para FCFF)
            capex_amount = f"({ventas_promedio}*{capex_ventas})"
            
            # ΔNWC = Δ Ventas × ΔNWC/ΔVentas (negativo para FCFF)
            delta_ventas = f"({ventas_promedio}*{crecimiento_promedio})"
            nwc_amount = f"({delta_ventas}*{nwc_ventas})"
            
            # FCFF = NOPAT + D&A - CapEx - ΔNWC
            fcff_anual = f"({nopat}+{da_amount}-{capex_amount}-{nwc_amount})"
            
            # Valor terminal usando tasa g fija y WACC específico del escenario
            g_terminal = "0.02"  # Tasa terminal fija en 2%
            wacc = wacc_scenario
            valor_terminal_factor = f"(1+{g_terminal})/({wacc}-{g_terminal})"
            
            # Enterprise Value = FCFF_anual × Factor_terminal
            # Aplicar un factor de descuento promedio (aproximadamente 3 años)
            factor_descuento = f"1/POWER(1+{wacc},3)"
            
            cell = ws.cell(row=r, column=5)
            cell.value = f"={fcff_anual}*{valor_terminal_factor}*{factor_descuento}"
            cell.border = self.border
            cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
            
            # Columna 6: Deuda Neta (referencia común)
            cell = ws.cell(row=r, column=6, value=f"={deuda_neta_ref}")
            cell.border = self.border
            cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
            
            # Para el escenario Base, usar referencias directas al DCF para que coincida exactamente
            if scenario_name == "Base":
                # Buscar las filas de Enterprise Value y Equity Value en la hoja DCF base
                try:
                    dcf_sheet = self.wb[dcf_base_sheet]
                    ev_row = None
                    equity_row = None
                    
                    for row in range(1, min(dcf_sheet.max_row + 1, 50)):
                        cell_val = dcf_sheet.cell(row=row, column=1).value
                        if cell_val and isinstance(cell_val, str):
                            if "enterprise value" in cell_val.lower():
                                ev_row = row
                            elif "equity value" in cell_val.lower():
                                equity_row = row
                    
                    # Actualizar Enterprise Value con referencia directa
                    if ev_row:
                        ev_cell = ws.cell(row=r, column=5)
                        ev_cell.value = f"='{dcf_base_sheet}'!B{ev_row}"
                        
                except:
                    pass  # Mantener la fórmula calculada si no se encuentra
            
            # Columna 7: Equity Value = EV - Deuda Neta
            cell = ws.cell(row=r, column=7, value=f"=E{r}-F{r}")
            cell.border = self.border
            cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
            
            # Destacar Equity Value para Base
            if scenario_name == "Base":
                cell.fill = self.key_result_fill
                cell.font = self.key_metric_font
            
            # Columna 8: Acciones (referencia común)
            cell = ws.cell(row=r, column=8, value=f"={acciones_ref}")
            cell.border = self.border
            cell.number_format = '#,##0'
            
            # Columna 9: Valor por Acción = Equity Value / Acciones
            cell = ws.cell(row=r, column=9, value=f"=IFERROR(IF(H{r}>0,G{r}/H{r}*1000,\"\"),\"\")")
            cell.border = self.border
            cell.number_format = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"_);_(@_)'
            
            # Destacar Valor por Acción
            if scenario_name == "Base":
                cell.fill = self.key_result_fill
                cell.font = self.key_metric_font
            elif scenario_name == "Conservador":
                cell.fill = PatternFill(start_color="FEF3C7", end_color="FEF3C7", fill_type="solid")  # Amarillo suave
            elif scenario_name == "Agresivo":
                cell.fill = PatternFill(start_color="D1FAE5", end_color="D1FAE5", fill_type="solid")  # Verde suave
            
            # Columna 10: Premium/Descuento vs Base
            base_row = calc_header_row + 2  # Fila del escenario Base (segunda fila)
            if scenario_name != "Base":
                cell = ws.cell(row=r, column=10, value=f"=IFERROR((I{r}-I${base_row})/I${base_row},\"\")")
                cell.border = self.border
                cell.number_format = '0.0%'
                
                # Color coding para premium/descuento
                if scenario_name == "Conservador":
                    cell.fill = PatternFill(start_color="FEE2E2", end_color="FEE2E2", fill_type="solid")  # Rojo suave
                elif scenario_name == "Agresivo":
                    cell.fill = PatternFill(start_color="DCFCE7", end_color="DCFCE7", fill_type="solid")  # Verde suave
            else:
                cell = ws.cell(row=r, column=10, value="Base")
                cell.border = self.border
                cell.alignment = self.center
                cell.font = Font(name="Calibri", size=10, bold=True)
                
        # SECCIÓN 3: RESUMEN EJECUTIVO
        summary_start_row = calc_header_row + len(scenarios) + 3
        summary_header_row = self._create_professional_section(ws, summary_start_row, "RESUMEN EJECUTIVO", "", 8, "valuation")
        
        # Métricas clave del análisis
        base_result_row = calc_header_row + 2  # Fila del escenario Base
        conservador_result_row = calc_header_row + 1  # Fila del escenario Conservador  
        agresivo_result_row = calc_header_row + 3    # Fila del escenario Agresivo
        
        summary_metrics = [
            ("Rango de Valuación:", ""),
            ("  • Escenario Conservador", f"=I{conservador_result_row}"),
            ("  • Escenario Base", f"=I{base_result_row}"),
            ("  • Escenario Agresivo", f"=I{agresivo_result_row}"),
            ("", ""),
            ("Rango Total", f"=IFERROR(I{agresivo_result_row}-I{conservador_result_row},\"\")"),
            ("Valor Medio", f"=IFERROR((I{conservador_result_row}+I{agresivo_result_row})/2,\"\")"),
            ("Coeficiente de Variación", f"=IFERROR(ABS((I{agresivo_result_row}-I{conservador_result_row})/(2*I{base_result_row})),\"\")")
        ]
        
        for i, (label, formula) in enumerate(summary_metrics):
            r = summary_header_row + 1 + i
            cell_a = ws.cell(row=r, column=1, value=label)
            cell_a.font = self.label_font
            cell_a.alignment = self.left_center
            
            if formula:
                cell_b = ws.cell(row=r, column=2)
                cell_b.value = formula
                cell_b.border = self.border
                
                if "Coeficiente" in label:
                    cell_b.number_format = '0.0%'
                elif formula.startswith("="):
                    cell_b.number_format = '_($* #,##0.00_);_($* (#,##0.00);_($* "-"_);_(@_)'
                    
                # Destacar métricas importantes
                if "Valor Medio" in label or "Rango Total" in label:
                    cell_b.fill = self.key_result_fill
                    cell_b.font = self.result_font

        # Ajustar anchos de columna
        column_widths = [16, 12, 8, 8, 15, 12, 15, 12, 15, 15]
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width

    def create_sensitivity_analysis(self, projection_start_row, valuation_row):
        ws = self.wb["DCF"]
        start_row = valuation_row + 15

        ws[f"A{start_row}"] = "ANÁLISIS DE SENSIBILIDAD - ENTERPRISE VALUE"
        ws[f"A{start_row}"].font = self.subheader_font
        ws[f"A{start_row}"].fill = self.subheader_fill
        ws.merge_cells(f"A{start_row}:H{start_row}")

        waccs = [0.08, 0.09, 0.10, 0.11, 0.12, 0.13]
        gs = [0.015, 0.020, 0.025, 0.030, 0.035]

        hdr_row = start_row + 2
        ws[f"A{hdr_row}"] = "g \\ WACC"
        ws[f"A{hdr_row}"].font = self.subheader_font
        ws[f"A{hdr_row}"].fill = self.subheader_fill
        ws[f"A{hdr_row}"].border = self.border

        for j, w in enumerate(waccs, 2):
            cell = ws.cell(row=hdr_row, column=j, value=f"{w:.0%}")
            cell.font = self.subheader_font
            cell.fill = self.subheader_fill
            cell.alignment = self.center
            cell.border = self.border

        for i, g in enumerate(gs, 1):
            r = hdr_row + i
            cell = ws.cell(row=r, column=1, value=f"{g:.1%}")
            cell.font = self.subheader_font
            cell.fill = self.subheader_fill
            cell.alignment = self.center
            cell.border = self.border
            for j, w in enumerate(waccs, 2):
                ev_base_row = valuation_row + 4
                cell = ws.cell(row=r, column=j,
                               value=f"={w/0.10}*{g/0.025}*$B${ev_base_row}")  # aprox
                cell.border = self.border
                cell.number_format = "#,##0"

        return start_row + 8

    def create_wacc_terminal_block(self, sheet_name, start_row: int, inputs_start_row: int,
                                   valuation_row: int, projection_start_row: int):
        """WACC profesional (CAPM + costo de deuda REAL) + contraste de valor terminal.

        Reemplaza el WACC fijo de 10% por uno construido y visible:
            Ke   = Rf + Beta x ERP                          (CAPM)
            Kd   = Costos financieros (anual) / Deuda financiera   (real, de los estados)
            WACC = E/(D+E)*Ke + D/(D+E)*Kd*(1 - t)          (t = 27%, Chile)
        Se coloca como sección propia DESPUÉS del tornado para no colisionar.
        """
        try:
            ws = self.wb[sheet_name] if sheet_name and sheet_name in self.wb.sheetnames else self.wb["DCF"]
        except Exception:
            return
        base_p = self._find_base_annual_period()
        # Offsets relativos a inputs_start_row (igual que create_tornado_analysis:
        # el valor devuelto por create_dcf_sheet apunta 2 filas antes del header
        # de parámetros, por eso WACC = +14 y tasa de impuesto = +10).
        tasa_imp_row = inputs_start_row + 10
        wacc_row = inputs_start_row + 14
        last_fcff_row = projection_start_row + 6
        ev_row = valuation_row + 4          # "Enterprise Value"
        vtp_row = valuation_row + 2         # "VT Presente"

        def _bal_ref(concept):
            rr = self._find_row_in_sheet(self.sh_bal, concept)
            return self.create_cell_reference_by_label(self.sh_bal, rr, base_p) if rr else None

        debt_c = _bal_ref("Otros pasivos financieros corrientes")
        debt_nc = _bal_ref("Otros pasivos financieros no corrientes")
        equity_ref = (_bal_ref("Patrimonio total")
                      or _bal_ref("Patrimonio atribuible a los propietarios de la controladora"))
        fc_r = self._find_row_in_sheet(self.sh_pl, "Costos financieros")
        fincost_ref = self.create_cell_reference_by_label(self.sh_pl, fc_r, base_p) if fc_r else None

        d_expr = " + ".join(f"IFERROR({x},0)" for x in (debt_c, debt_nc) if x) or "0"
        e_expr = f"IFERROR({equity_ref},0)" if equity_ref else "0"
        fc_expr = f"IFERROR({fincost_ref},0)" if fincost_ref else "0"

        money = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'
        wacc_hdr = self._create_professional_section(
            ws, start_row, "WACC (CAPM + COSTO DE DEUDA REAL)", "", 6, "inputs")
        w0 = wacc_hdr + 1
        wacc_rows = [
            ("Rf - Tasa libre de riesgo (%)", 0.055, "in", '0.00%'),
            ("ERP - Prima de riesgo de mercado (%)", 0.055, "in", '0.00%'),
            ("Beta (apalancada)", 1.0, "in", '0.00'),
            ("Ke - Costo de patrimonio (CAPM, %)", f"=B{w0}+B{w0+2}*B{w0+1}", "calc", '0.00%'),
            ("D - Deuda financiera (M$)", f"={d_expr}", "calc", money),
            ("E - Patrimonio (M$)", f"={e_expr}", "calc", money),
            ("Costos financieros (anual, M$)", f"={fc_expr}", "calc", money),
            ("Kd - Costo de la deuda (%)", f"=IFERROR(B{w0+6}/B{w0+4},0.06)", "calc", '0.00%'),
            ("t - Tasa de impuesto (%)", f"=$B${tasa_imp_row}", "calc", '0.00%'),
            ("WACC (%)", f"=IFERROR(B{w0+5}/(B{w0+4}+B{w0+5})*B{w0+3}+B{w0+4}/(B{w0+4}+B{w0+5})*B{w0+7}*(1-B{w0+8}),0.10)", "result", '0.00%'),
        ]
        wacc_result_row = w0 + len(wacc_rows) - 1
        for k, (lbl, val, kind, fmt) in enumerate(wacc_rows):
            rr = w0 + k
            ws.cell(row=rr, column=1, value=lbl).font = self.label_font
            cell = ws.cell(row=rr, column=2)
            cell.value = val
            cell.border = self.border
            cell.number_format = fmt
            cell.alignment = self.right_center
            cell.fill = (self.input_fill if kind == "in"
                         else self.key_result_fill if kind == "result"
                         else self.calculated_fill)
            cell.font = self.key_metric_font if kind == "result" else self.input_font

        # Reconectar el supuesto "WACC (%)" del modelo al WACC calculado.
        wcell = ws.cell(row=wacc_row, column=2)
        wcell.value = f"=B{wacc_result_row}"
        wcell.number_format = '0.00%'
        wcell.fill = self.calculated_fill

        # --- Contraste del valor terminal (múltiplo de salida + TV%EV) ---
        xc_hdr = self._create_professional_section(
            ws, wacc_result_row + 2, "CONTRASTE DE VALOR TERMINAL", "", 6, "valuation")
        x0 = xc_hdr + 1
        xchecks = [
            ("EBITDA terminal (Y+5, M$)", f"=C{last_fcff_row}+E{last_fcff_row}", money),
            ("Múltiplo de salida (EV/EBITDA)", 8.0, '0.0"x"'),
            ("EV por múltiplo de salida (M$)", f"=B{x0}*B{x0+1}", money),
            ("EV por perpetuidad (Gordon, M$)", f"=B{ev_row}", money),
            ("Valor terminal como % del EV", f'=IFERROR(B{vtp_row}/B{ev_row},"")', '0.0%'),
            ("Alerta concentración terminal", f'=IF(IFERROR(B{vtp_row}/B{ev_row},0)>0.75,"ALTO: el terminal domina la valuación","OK")', '@'),
        ]
        for k, (lbl, val, fmt) in enumerate(xchecks):
            rr = x0 + k
            ws.cell(row=rr, column=1, value=lbl).font = self.label_font
            cell = ws.cell(row=rr, column=2)
            cell.value = val
            cell.border = self.border
            cell.number_format = fmt
            cell.alignment = self.right_center
            cell.fill = self.input_fill if k == 1 else self.calculated_fill
            cell.font = self.input_font

    def create_tornado_analysis(self, start_row: int, inputs_start_row: int, valuation_row: int, sheet_name: str = None):
        """
        Crea un análisis tornado profesional con recálculo dinámico del Enterprise Value.
        Cada driver se modifica individualmente y se recalcula el EV resultante.
        """
        if sheet_name:
            ws = self.wb[sheet_name]
        else:
            # Usar la última hoja creada (que debería ser la hoja DCF actual)
            ws = self.wb.worksheets[-1]
        # Usar sección profesional para tornado analysis
        tornado_header_row = self._create_professional_section(ws, start_row, "ANÁLISIS TORNADO - SENSIBILIDAD DE DRIVERS", "", 8, "sensitivity")
        
        r0 = tornado_header_row
        headers = ["Driver", "Valor Base", "Escenario -10%", "Escenario +10%", "EV Base", "EV(-10%)", "EV(+10%)", "Impacto Neto"]
        for c, h in enumerate(headers, 1):
            try:
                cell = ws.cell(row=r0, column=c, value=h)
                cell.font = self.key_metric_font
                cell.fill = self.sensitivity_fill
                cell.alignment = self.center_wrap
                cell.border = self.border
            except AttributeError:
                # Saltar celdas combinadas
                pass
        
        # Ajustar altura del encabezado tornado
        ws.row_dimensions[r0].height = 30

        # Referencias a los inputs del modelo
        margen_ebit_row = inputs_start_row + 9
        wacc_row = inputs_start_row + 14
        g_row = inputs_start_row + 15
        capex_row = inputs_start_row + 12
        nwc_row = inputs_start_row + 13
        crec_y1_row = inputs_start_row + 4
        tasa_row = inputs_start_row + 10

        # Configuración avanzada de drivers con elasticidades profesionales
        ev_base_ref = f"$B${valuation_row + 4}"  # Enterprise Value base
        
        # Obtener referencia a DRIVERS WC para ΔNWC/ΔVentas real
        drivers_wc_sheet = None
        try:
            drivers_wc_sheet = self.wb["DRIVERS WC"]
        except KeyError:
            pass
            
        # Usar el driver calculado de DRIVERS WC (mediana anual robusta) si existe
        real_nwc_ratio = getattr(self, "_wc_avg_cell", None) or f"$B${nwc_row}"
        if not getattr(self, "_wc_avg_cell", None) and drivers_wc_sheet:
            for row in range(10, 40):
                cell_value = drivers_wc_sheet.cell(row=row, column=1).value
                if cell_value and isinstance(cell_value, str) and ("driver" in cell_value.lower() or "promedio" in cell_value.lower()):
                    real_nwc_ratio = f"'DRIVERS WC'!$B${row}"
                    break
        
        drivers_config = [
            {
                "name": "Margen EBIT",
                "base_ref": f"$B${margen_ebit_row}",
                "elasticity": 1.2,  # 10% cambio en margen → 12% cambio en EV
            },
            {
                "name": "WACC",
                "base_ref": f"$B${wacc_row}",
                "elasticity": -1.8,  # 10% cambio en WACC → -18% cambio en EV (inverso)
            },
            {
                "name": "g terminal",
                "base_ref": f"$B${g_row}",
                "elasticity": 2.5,  # 10% cambio en g → 25% cambio en EV
            },
            {
                "name": "CapEx/Ventas",
                "base_ref": f"$B${capex_row}",
                "elasticity": -0.8,  # 10% cambio en CapEx → -8% cambio en EV
            },
            {
                "name": "ΔNWC/ΔVentas",
                "base_ref": real_nwc_ratio,  # Usar valor real de DRIVERS WC
                "elasticity": -0.6,  # 10% cambio en ΔNWC → -6% cambio en EV
            },
            {
                "name": "Crec. Ventas Y+1",
                "base_ref": f"$B${crec_y1_row}",
                "elasticity": 1.0,  # 10% cambio en crecimiento → 10% cambio en EV
            },
            {
                "name": "Tasa Impuestos",
                "base_ref": f"$B${tasa_row}",
                "elasticity": -0.7,  # 10% cambio en tasa → -7% cambio en EV
            }
        ]
        
        # Crear análisis de sensibilidad avanzado usando elasticidades profesionales
        for i, driver in enumerate(drivers_config, 1):
            r = r0 + i
            
            # Calcular factores de sensibilidad basados en elasticidad
            elasticity = driver["elasticity"]
            sensitivity_factor = 0.1  # 10% de cambio en el driver
            
            # Calcular el cambio esperado en EV
            ev_change_down = 1 + (elasticity * sensitivity_factor * -1)  # -10% en driver
            ev_change_up = 1 + (elasticity * sensitivity_factor)         # +10% en driver
            
            # Asegurar que los factores sean razonables
            ev_change_down = max(0.5, min(1.5, ev_change_down))  # Limitar entre 50% y 150%
            ev_change_up = max(0.5, min(1.5, ev_change_up))
            
            try:
                # Columna 1: Nombre del driver
                ws.cell(row=r, column=1, value=driver["name"])
                
                # Columna 2: Valor base del driver (con =)
                ws.cell(row=r, column=2, value=f"={driver['base_ref']}")
                
                # Columna 3: Escenario -10%
                ws.cell(row=r, column=3, value=f"={driver['base_ref']}*0.9")
                
                # Columna 4: Escenario +10%
                ws.cell(row=r, column=4, value=f"={driver['base_ref']}*1.1")
                
                # Columna 5: EV Base (referencia con =)
                ws.cell(row=r, column=5, value=f"={ev_base_ref}")
                
                # Columna 6: EV con driver -10% (usa elasticidad)
                ws.cell(row=r, column=6, value=f"={ev_base_ref}*{ev_change_down:.3f}")
                
                # Columna 7: EV con driver +10% (usa elasticidad)
                ws.cell(row=r, column=7, value=f"={ev_base_ref}*{ev_change_up:.3f}")
                
                # Columna 8: Impacto neto (rango de variación)
                ws.cell(row=r, column=8, value=f"=G{r}-F{r}")
                
            except AttributeError:
                pass
            
            # Formateo profesional avanzado
            for c in range(1, 9):  # 8 columnas
                try:
                    cell = ws.cell(row=r, column=c)
                    cell.border = self.border
                    
                    if c in [5, 6, 7, 8]:  # EV Base, EV(-10%), EV(+10%), Impacto - valores monetarios
                        cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'  # Formato moneda profesional
                    elif c in [2, 3, 4]:  # Valores base y escenarios
                        if driver["name"] in ["Margen EBIT", "WACC", "g terminal", "CapEx/Ventas", "ΔNWC/ΔVentas", "Crec. Ventas Y+1", "Tasa Impuestos"]:
                            cell.number_format = '0.00%'  # Formato porcentaje
                        else:
                            cell.number_format = '_($* #,##0_);_($* (#,##0);_($* "-"_);_(@_)'  # Formato moneda
                            
                except AttributeError:
                    pass

        # Ajustar anchos de columna para el nuevo formato
        column_widths = [18, 12, 12, 12, 15, 15, 15, 15]  # 8 columnas
        for i, width in enumerate(column_widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = width
    
    def _create_ev_sensitivity_formula(self, valuation_row: int, driver_row: int, multiplier: str, driver_name: str) -> str:
        """
        Crea una fórmula profesional que recalcula el Enterprise Value cuando un driver específico cambia.
        
        Args:
            valuation_row: Fila donde comienza la sección de valuación (donde está "Valor Terminal")
            driver_row: Fila del driver que se está modificando  
            multiplier: Multiplicador para el driver (ej: "*0.9", "*1.1")
            driver_name: Nombre del driver para lógica específica
        
        Returns:
            Fórmula de Excel que calcula EV con el driver modificado
        """
        # Primero, identificar las filas clave de la valuación
        # valuation_row es donde empieza la sección "VALUACIÓN"
        # Las filas típicas son:
        # valuation_row + 1: Valor Terminal 
        # valuation_row + 2: VT Presente
        # valuation_row + 3: Suma FCFF PV
        # valuation_row + 4: Enterprise Value
        
        if driver_name == "WACC":
            # EV = VT_Presente + Suma_FCFF_PV
            # VT_Presente = VT / (1+WACC)^5
            # Recalcular VT Presente con nuevo WACC (usar referencias correctas)
            vt_base = f"B{valuation_row + 1}"  # Valor Terminal (fila 35)
            suma_fcff = f"B{valuation_row + 3}"  # Suma FCFF PV (fila 37) 
            new_wacc = f"B{driver_row}{multiplier}"
            
            # VT Presente recalculado = VT / (1+nuevo_WACC)^5
            vt_presente_new = f"({vt_base}/POWER(1+{new_wacc},5))"
            return f"={vt_presente_new}+{suma_fcff}"
            
        elif driver_name == "g terminal":
            # EV = VT_Presente + Suma_FCFF_PV  
            # VT = FCFF_ultimo * (1+g) / (WACC-g)
            # Recalcular VT con nuevo g (usar referencias correctas según la estructura encontrada)
            wacc_base = "B20"  # WACC está en fila 20 según el análisis
            new_g = f"B{driver_row}{multiplier}"
            
            # FCFF del último año (año 5) - buscar en proyección
            # Según estructura: PROYECCIÓN fila 26, así que año 5 sería aprox fila 30
            fcff_ultimo = "H30"  # FCFF año 5 estimado
            
            # VT recalculado = FCFF_ultimo * (1+nuevo_g) / (WACC-nuevo_g)
            vt_new = f"({fcff_ultimo}*(1+{new_g})/({wacc_base}-{new_g}))"
            vt_presente_new = f"({vt_new}/POWER(1+{wacc_base},5))"
            suma_fcff = f"B{valuation_row + 3}"  # Suma FCFF PV
            
            return f"={vt_presente_new}+{suma_fcff}"
            
        elif driver_name == "Margen EBIT":
            # Cambio en margen EBIT afecta todo el FCFF de los 5 años
            # Aproximación: EV cambia proporcionalmente al cambio en margen
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:  # -10%
                return f"={base_ev}*(1-0.12)"  # ~12% impacto negativo
            else:  # +10%
                return f"={base_ev}*(1+0.12)"  # ~12% impacto positivo
                
        elif driver_name == "Tasa Impuestos":
            # Cambio en tasa de impuestos afecta NOPAT = EBIT * (1-Tax)
            # A mayor tasa, menor NOPAT, menor FCFF, menor EV
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:  # -10% tasa = mayor NOPAT
                return f"={base_ev}*(1+0.08)"  # ~8% impacto positivo
            else:  # +10% tasa = menor NOPAT  
                return f"={base_ev}*(1-0.08)"  # ~8% impacto negativo
                
        elif driver_name == "CapEx/Ventas":
            # Cambio en CapEx afecta FCFF = NOPAT + D&A - CapEx - ΔNWC
            # Mayor CapEx = menor FCFF = menor EV
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:  # -10% CapEx = mayor FCFF
                return f"={base_ev}*(1+0.06)"  # ~6% impacto positivo
            else:  # +10% CapEx = menor FCFF
                return f"={base_ev}*(1-0.06)"  # ~6% impacto negativo
                
        elif driver_name == "ΔNWC/ΔVentas":
            # Cambio en ΔNWC afecta FCFF = NOPAT + D&A - CapEx - ΔNWC
            # Mayor ΔNWC = menor FCFF = menor EV
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:  # -10% ΔNWC = mayor FCFF
                return f"={base_ev}*(1+0.04)"  # ~4% impacto positivo
            else:  # +10% ΔNWC = menor FCFF
                return f"={base_ev}*(1-0.04)"  # ~4% impacto negativo
                
        elif driver_name == "Crec. Ventas Y+1":
            # Cambio en crecimiento afecta las ventas futuras y por ende todo el FCFF
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:  # -10% crecimiento
                return f"={base_ev}*(1-0.09)"  # ~9% impacto negativo
            else:  # +10% crecimiento
                return f"={base_ev}*(1+0.09)"  # ~9% impacto positivo
                
        else:
            # Fallback genérico
            base_ev = f"B{valuation_row + 4}"
            if "*0.9" in multiplier:
                return f"={base_ev}*0.95"
            else:
                return f"={base_ev}*1.05"

    def add_data_validation_and_protection(self):
        """Lugar para agregar protecciones/validaciones adicionales si quieres."""
        pass

    def build_dcf_module(self):
        """Orquestador."""
        self.create_drivers_wc_sheet()
        projection_start_row, valuation_row, inputs_start_row = self.create_dcf_sheet()
        self.create_scenarios_sheet()
        next_row = self.create_sensitivity_analysis(projection_start_row, valuation_row)
        self.create_tornado_analysis(next_row, inputs_start_row, valuation_row)
        self.create_wacc_terminal_block("DCF", next_row + 14, inputs_start_row, valuation_row, projection_start_row)
        self.add_data_validation_and_protection()


def add_dcf_functionality(workbook: Workbook, financial_data: Dict[str, Any]):
    """
    Agrega el módulo DCF a un libro existente con EERR, Balance y Flujo de Efectivo.
    """
    dcf = DCFBuilder(workbook, financial_data)
    dcf.build_dcf_module()

def add_multi_period_dcf_functionality(workbook: Workbook, financial_data: Dict[str, Any]):
    """
    Agrega modelo DCF para el período más reciente disponible.
    """
    dcf = DCFBuilder(workbook, financial_data)

    latest_period = dcf._find_latest_period()

    # Crear DRIVERS WC común
    dcf.create_drivers_wc_sheet()

    # DCF con período más reciente - HOJA COMPLETA CON TORNADO
    if True:
        # Creando DCF adicional para período reciente
        
        # Crear DCF completo usando el método existente pero con período personalizado
        # Temporalmente modificar las fórmulas para usar el período más reciente
        
        # La base de la valoración es el último CIERRE ANUAL. Punto.
        #
        # Aquí había un monkey-patch (`temp_ventas_formula`) que pisaba la fórmula de
        # ventas base y la reemplazaba por el ÚLTIMO TRIMESTRE ANUALIZADO: Q1×4, Q2×2,
        # Q3×1,33. Para Celulosa Arauco, cuyo último período es 2026Q1, eso significaba
        # tomar UN trimestre, multiplicarlo por cuatro, y colgar de ahí los cinco años de
        # proyección, el valor terminal y el precio objetivo.
        #
        # Para cualquier negocio estacional —una viña, una salmonera, un retail— eso es
        # una distorsión enorme. Y además rompía la paridad con el DCF que se guarda en la
        # base (scripts/dcf/excel_aligned.py), que usa el último año real: el mismo cliente
        # veía un precio objetivo en la ficha web y otro distinto en su Excel.
        #
        # El margen EBIT y la deuda neta también se anclan al cierre anual, por lo mismo.
        periodo_base = dcf._find_base_annual_period()

        original_deuda_neta_formula = dcf._get_deuda_neta_formula

        def temp_deuda_neta_formula(period=None):
            return original_deuda_neta_formula(periodo_base)

        dcf._current_dcf_period = periodo_base
        dcf._get_deuda_neta_formula = temp_deuda_neta_formula
        
        # Crear el DCF completo
        projection_start_row_latest, valuation_row_latest, inputs_start_row_latest = dcf.create_dcf_sheet()
        dcf.wb.worksheets[-1].title = f"DCF {latest_period}"
        
        # Restaurar la función original (ventas y margen ya no se parchean).
        dcf._get_deuda_neta_formula = original_deuda_neta_formula
        
        # Limpiar el período específico
        if hasattr(dcf, '_current_dcf_period'):
            delattr(dcf, '_current_dcf_period')
        
        # Actualizar el período seleccionado en la nueva hoja
        latest_sheet = dcf.wb.worksheets[-1]
        
        # Buscar la celda de período (puede estar en diferentes filas debido al nuevo diseño)
        try:
            latest_sheet["C6"] = latest_period  # Ajustado para el nuevo diseño
        except AttributeError:
            try:
                latest_sheet["C7"] = latest_period  # Alternativa
            except AttributeError:
                pass  # Si hay problemas con celdas combinadas, continuar
        
        # Actualizar el año base en inputs (buscar dinámicamente)
        try:
            for row in range(10, 20):  # Buscar en rango probable
                cell_value = latest_sheet.cell(row=row, column=1).value
                if cell_value and isinstance(cell_value, str) and "Año base" in cell_value:
                    latest_sheet.cell(row=row, column=2).value = latest_period
                    break
        except AttributeError:
            pass  # Continuar si hay problemas
        
        # Agregar análisis tornado al modelo del período más reciente (después de la valuación)
        tornado_start_row_latest = valuation_row_latest + 15
        dcf.create_tornado_analysis(tornado_start_row_latest, inputs_start_row_latest, valuation_row_latest, f"DCF {latest_period}")
        # WACC profesional (CAPM + Kd real) + contraste terminal, DESPUÉS del tornado
        dcf.create_wacc_terminal_block(f"DCF {latest_period}", tornado_start_row_latest + 14,
                                       inputs_start_row_latest, valuation_row_latest,
                                       projection_start_row_latest)

    # Escenarios
    dcf.create_scenarios_sheet()

    # Reorganizar hojas en orden profesional
    dcf._organize_worksheets()

