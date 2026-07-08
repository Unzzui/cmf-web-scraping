"""
Ratio Calculator Module
======================

Módulo para calcular ratios financieros a partir de datos extraídos.
Incluye ratios de liquidez, solvencia, rentabilidad, eficiencia y flujos.
"""

import re
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any


class RatioCalculator:
    """
    Calculadora de ratios financieros.
    """
    
    def __init__(self, financial_data: Dict[str, Any]):
        """
        Inicializa la calculadora con datos financieros.
        
        Args:
            financial_data: Diccionario con datos financieros extraídos
        """
        self.balance = financial_data.get("balance", {})
        self.income = financial_data.get("income", {})
        self.cash_flow = financial_data.get("cash_flow", {})
        self.years = financial_data.get("years", [])
    
    def get_column_for_year(self, series: pd.Series, year: int) -> Optional[str]:
        """Encuentra la columna correspondiente a un año específico.

        Soporta etiquetas 'YYYY-MM(-DD)', 'YYYY' y 'YYYYQn'; para trimestres
        se prefiere el más reciente del año (Q4 > Q3 > Q2 > Q1, i.e. YTD completo).
        """
        for col in series.index:
            if str(col).startswith(f"{year}-"):
                return col
        best = None
        best_q = 0
        for col in series.index:
            s = str(col).strip().split("\n", 1)[0]
            if s == str(year):
                return col
            m = re.match(rf"^{year}Q([1-4])$", s)
            if m and int(m.group(1)) > best_q:
                best_q = int(m.group(1))
                best = col
        return best
    
    def get_average_balance_item(self, series: pd.Series, year: int) -> float:
        """
        Calcula el promedio de un item del balance entre el año actual y anterior.
        
        Args:
            series: Serie de datos del balance
            year: Año actual
            
        Returns:
            Promedio entre año actual y anterior
        """
        current_col = self.get_column_for_year(series, year)
        previous_col = self.get_column_for_year(series, year - 1)
        
        current_val = series.get(current_col, np.nan) if current_col else np.nan
        previous_val = series.get(previous_col, np.nan) if previous_col else np.nan
        
        if pd.isna(previous_val):
            return current_val
        if pd.isna(current_val):
            return previous_val
        return (current_val + previous_val) / 2

    def get_value_for_year(self, series: pd.Series, year: int) -> float:
        """Obtiene el valor de una serie para un año específico (NaN si no existe)."""
        col = self.get_column_for_year(series, year)
        return series.get(col, np.nan) if col else np.nan

    def get_financial_debt(self) -> pd.Series:
        """
        Deuda financiera total = Otros pasivos financieros corrientes + no corrientes (IFRS/CMF).

        Returns:
            Serie con la deuda financiera, o serie vacía si las cuentas no están disponibles
        """
        opfc = self.balance.get("OPFC", pd.Series(dtype=float))
        opfnc = self.balance.get("OPFNC", pd.Series(dtype=float))
        if opfc.dropna().empty and opfnc.dropna().empty:
            return pd.Series(dtype=float)
        return opfc.add(opfnc, fill_value=0)

    def get_net_financial_debt(self) -> pd.Series:
        """
        Deuda Financiera Neta = Deuda financiera total - Efectivo y equivalentes.

        Returns:
            Serie con la deuda financiera neta, o serie vacía si no hay deuda financiera identificable
        """
        deuda_fin = self.get_financial_debt()
        if deuda_fin.empty:
            return pd.Series(dtype=float)
        efec = self.balance.get("Efec", pd.Series(dtype=float))
        return deuda_fin.subtract(efec, fill_value=0)

    def calculate_liquidity_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios de liquidez.
        
        Returns:
            Diccionario con ratios de liquidez por año
        """
        ratios = {}
        
        # Liquidez Corriente = AC / PC
        ac = self.balance.get("AC", pd.Series(dtype=float))
        pc = self.balance.get("PC", pd.Series(dtype=float))
        ratios["Liquidez Corriente"] = ac.divide(pc, fill_value=np.nan)
        
        # Prueba Ácida = (AC - Inventarios) / PC
        inv = self.balance.get("Inv", pd.Series(dtype=float))
        ratios["Prueba Ácida"] = (ac - inv).divide(pc, fill_value=np.nan)
        
        # Cash Ratio = Efectivo / PC
        efec = self.balance.get("Efec", pd.Series(dtype=float))
        ratios["Cash Ratio"] = efec.divide(pc, fill_value=np.nan)
        
        # Capital de Trabajo = AC - PC
        ratios["Capital de Trabajo"] = ac.subtract(pc, fill_value=np.nan)
        
        return ratios
    
    def calculate_solvency_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios de solvencia y estructura.
        
        Returns:
            Diccionario con ratios de solvencia por año
        """
        ratios = {}
        
        pt = self.balance.get("PT", pd.Series(dtype=float))
        patr = self.balance.get("Patr", pd.Series(dtype=float))
        at = self.balance.get("AT", pd.Series(dtype=float))
        ebit = self.income.get("EBIT", pd.Series(dtype=float))
        interes = self.income.get("Interes", pd.Series(dtype=float))
        da = self.income.get("DA", pd.Series(dtype=float))
        
        # Endeudamiento (D/E) = Deuda Total / Patrimonio
        ratios["Endeudamiento (D/E)"] = pt.divide(patr, fill_value=np.nan)
        
        # Apalancamiento (D/A) = Deuda Total / Activos Totales
        ratios["Apalancamiento (D/A)"] = pt.divide(at, fill_value=np.nan)
        
        # Cobertura de Intereses = EBIT / |Gastos por Intereses|
        ratios["Cobertura de Intereses"] = ebit.divide(interes.abs(), fill_value=np.nan)
        
        # Deuda / EBITDA
        # Only add D&A if it contains actual data; otherwise EBITDA = EBIT
        if da.dropna().empty or (da.dropna() == 0).all():
            ebitda = ebit.copy()
        else:
            ebitda = ebit.add(da, fill_value=0)
        ratios["Deuda / EBITDA"] = pt.divide(ebitda, fill_value=np.nan)

        # Deuda Financiera Neta / EBITDA = (Deuda financiera - Efectivo) / EBITDA
        # Si las cuentas de deuda financiera no están disponibles se deja N/A
        # (no se aproxima con pasivos totales)
        deuda_fin_neta = self.get_net_financial_debt()
        if deuda_fin_neta.empty:
            ratios["Deuda Financiera Neta / EBITDA"] = pd.Series(dtype=float)
        else:
            ratios["Deuda Financiera Neta / EBITDA"] = (
                deuda_fin_neta.divide(ebitda, fill_value=np.nan)
                .replace([np.inf, -np.inf], np.nan)
            )

        # Autonomía Financiera = Patrimonio / Activo Total
        ratios["Autonomía Financiera"] = patr.divide(at, fill_value=np.nan)
        
        return ratios
    
    def calculate_profitability_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios de rentabilidad.
        
        Returns:
            Diccionario con ratios de rentabilidad por año
        """
        ratios = {}
        
        ventas = self.income.get("Ventas", pd.Series(dtype=float))
        bruta = self.income.get("Bruta", pd.Series(dtype=float))
        ebit = self.income.get("EBIT", pd.Series(dtype=float))
        neta = self.income.get("Neta", pd.Series(dtype=float))
        da = self.income.get("DA", pd.Series(dtype=float))
        
        # Margen Bruto = Utilidad Bruta / Ventas
        ratios["Margen Bruto"] = bruta.divide(ventas, fill_value=np.nan)
        
        # Margen Operativo = EBIT / Ventas
        ratios["Margen Operativo (EBIT)"] = ebit.divide(ventas, fill_value=np.nan)
        
        # Margen EBITDA = EBITDA / Ventas
        # Only add D&A if it contains actual data; otherwise EBITDA = EBIT
        if da.dropna().empty or (da.dropna() == 0).all():
            ebitda = ebit.copy()
        else:
            ebitda = ebit.add(da, fill_value=0)
        ratios["Margen EBITDA"] = ebitda.divide(ventas, fill_value=np.nan)
        
        # Margen Neto = Utilidad Neta / Ventas
        ratios["Margen Neto"] = neta.divide(ventas, fill_value=np.nan)
        
        # ROE y ROA necesitan promedios del balance
        roe_values = {}
        roa_values = {}
        
        for year in self.years:
            # ROE = Utilidad Neta / Patrimonio Promedio
            patr_avg = self.get_average_balance_item(self.balance.get("Patr", pd.Series(dtype=float)), year)
            neta_col = self.get_column_for_year(neta, year)
            if neta_col and not pd.isna(patr_avg) and patr_avg > 0:
                roe_values[neta_col] = neta[neta_col] / patr_avg
            
            # ROA = Utilidad Neta / Activos Totales Promedio
            at_avg = self.get_average_balance_item(self.balance.get("AT", pd.Series(dtype=float)), year)
            if neta_col and not pd.isna(at_avg) and at_avg != 0:
                roa_values[neta_col] = neta[neta_col] / at_avg
        
        ratios["ROE"] = pd.Series(roe_values)
        ratios["ROA"] = pd.Series(roa_values)
        
        return ratios
    
    def calculate_efficiency_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios de eficiencia operativa.
        
        Returns:
            Diccionario con ratios de eficiencia por año
        """
        ratios = {}
        
        ventas = self.income.get("Ventas", pd.Series(dtype=float))
        cogs = self.income.get("COGS", pd.Series(dtype=float))
        # Fallback COGS para estados por naturaleza (320000):
        # COGS ≈ Materias primas y consumibles utilizados + Δ Inventarios de PT/WIP - Trabajos capitalizados
        if cogs.empty or cogs.sum(skipna=True) == 0:
            rawmat = self.income.get("RawMat", pd.Series(dtype=float))
            invchg = self.income.get("InvChange", pd.Series(dtype=float))
            workcap = self.income.get("WorkCap", pd.Series(dtype=float))
            if not (rawmat.empty and invchg.empty and workcap.empty):
                cogs = rawmat.add(invchg, fill_value=0).subtract(workcap, fill_value=0)
        
        # Rotación de Activos = Ventas / Activos Promedio
        rot_activos = {}
        rot_inventarios = {}
        dias_inventario = {}
        rot_cxc = {}
        dias_cobro = {}
        rot_cxp = {}
        dias_pago = {}
        cce = {}
        
        for year in self.years:
            ventas_col = self.get_column_for_year(ventas, year)
            cogs_col = self.get_column_for_year(cogs, year)
            
            # Rotación de Activos
            at_avg = self.get_average_balance_item(self.balance.get("AT", pd.Series(dtype=float)), year)
            if ventas_col and not pd.isna(at_avg) and at_avg != 0:
                rot_activos[ventas_col] = ventas[ventas_col] / at_avg
            
            # Rotación de Inventarios
            inv_avg = self.get_average_balance_item(self.balance.get("Inv", pd.Series(dtype=float)), year)
            if cogs_col and not pd.isna(inv_avg) and inv_avg != 0:
                rot_inv = cogs[cogs_col] / inv_avg
                rot_inventarios[cogs_col] = rot_inv
                dias_inventario[cogs_col] = 365 / rot_inv if rot_inv != 0 else np.nan
            
            # Rotación de Cuentas por Cobrar
            cxc_avg = self.get_average_balance_item(self.balance.get("CxC", pd.Series(dtype=float)), year)
            if ventas_col and not pd.isna(cxc_avg) and cxc_avg != 0:
                rot_cxc_val = ventas[ventas_col] / cxc_avg
                rot_cxc[ventas_col] = rot_cxc_val
                dias_cobro[ventas_col] = 365 / rot_cxc_val if rot_cxc_val != 0 else np.nan
            
            # Rotación de Cuentas por Pagar
            cxp_avg = self.get_average_balance_item(self.balance.get("CxP", pd.Series(dtype=float)), year)
            # Aproximación de compras = COGS + Δ Inventario
            inv_current = self.balance.get("Inv", pd.Series(dtype=float)).get(self.get_column_for_year(self.balance.get("Inv", pd.Series(dtype=float)), year), 0)
            inv_previous = self.balance.get("Inv", pd.Series(dtype=float)).get(self.get_column_for_year(self.balance.get("Inv", pd.Series(dtype=float)), year-1), 0)
            compras = cogs.get(cogs_col, 0) + (inv_current - inv_previous)
            
            if cogs_col and not pd.isna(cxp_avg) and cxp_avg != 0:
                rot_cxp_val = compras / cxp_avg
                rot_cxp[cogs_col] = rot_cxp_val
                dias_pago[cogs_col] = 365 / rot_cxp_val if rot_cxp_val != 0 else np.nan
            
            # Ciclo de Conversión de Efectivo
            if (cogs_col in dias_inventario and 
                ventas_col in dias_cobro and 
                cogs_col in dias_pago):
                cce[ventas_col] = (dias_inventario[cogs_col] + 
                                 dias_cobro[ventas_col] - 
                                 dias_pago[cogs_col])
        
        ratios["Rotación de Activos"] = pd.Series(rot_activos)
        ratios["Rotación de Inventarios"] = pd.Series(rot_inventarios)
        ratios["Días de Inventario"] = pd.Series(dias_inventario)
        ratios["Rotación de Cuentas por Cobrar"] = pd.Series(rot_cxc)
        ratios["Período Promedio de Cobro"] = pd.Series(dias_cobro)
        ratios["Rotación de Cuentas por Pagar"] = pd.Series(rot_cxp)
        ratios["Período Promedio de Pago"] = pd.Series(dias_pago)
        ratios["Ciclo de Conversión de Efectivo"] = pd.Series(cce)
        
        return ratios
    
    def calculate_cash_flow_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios relacionados con flujos de efectivo.
        
        Returns:
            Diccionario con ratios de flujo de efectivo por año
        """
        ratios = {}
        
        cfo = self.cash_flow.get("CFO", pd.Series(dtype=float))
        fcf = self.cash_flow.get("FCF", pd.Series(dtype=float))
        neta = self.income.get("Neta", pd.Series(dtype=float))
        
        ac = self.balance.get("AC", pd.Series(dtype=float))
        at = self.balance.get("AT", pd.Series(dtype=float))
        pc = self.balance.get("PC", pd.Series(dtype=float))
        pt = self.balance.get("PT", pd.Series(dtype=float))
        
        # Conversión de caja = CFO / Utilidad Neta
        ratios["Conversión de caja (CFO/Utilidad Neta)"] = cfo.divide(neta, fill_value=np.nan)
        
        # Free Cash Flow (ya calculado en data_extractor)
        ratios["Free Cash Flow (CFO - CAPEX)"] = fcf
        
        # AC / AT
        ratios["AC / AT"] = ac.divide(at, fill_value=np.nan)
        
        # PC / PT
        ratios["PC / PT"] = pc.divide(pt, fill_value=np.nan)

        return ratios

    def calculate_growth_ratios(self) -> Dict[str, pd.Series]:
        """
        Calcula ratios de crecimiento: variaciones YoY y CAGR.

        Returns:
            Diccionario con ratios de crecimiento por año
        """
        ratios = {}

        ventas = self.income.get("Ventas", pd.Series(dtype=float))
        ebit = self.income.get("EBIT", pd.Series(dtype=float))
        neta = self.income.get("Neta", pd.Series(dtype=float))
        da = self.income.get("DA", pd.Series(dtype=float))

        # Only add D&A if it contains actual data; otherwise EBITDA = EBIT
        if da.dropna().empty or (da.dropna() == 0).all():
            ebitda = ebit.copy()
        else:
            ebitda = ebit.add(da, fill_value=0)

        def _yoy(series: pd.Series) -> Dict[str, float]:
            # Variación YoY = (Valor_t - Valor_t-1) / |Valor_t-1|
            values = {}
            for year in self.years:
                cur_col = self.get_column_for_year(series, year)
                cur_val = self.get_value_for_year(series, year)
                prev_val = self.get_value_for_year(series, year - 1)
                if not cur_col or pd.isna(cur_val) or pd.isna(prev_val) or prev_val == 0:
                    continue
                values[cur_col] = (cur_val - prev_val) / abs(prev_val)
            return values

        def _cagr(series: pd.Series, n: int) -> Dict[str, float]:
            # CAGR n años = (Valor_t / Valor_t-n)^(1/n) - 1 (requiere valores positivos)
            values = {}
            for year in self.years:
                cur_col = self.get_column_for_year(series, year)
                cur_val = self.get_value_for_year(series, year)
                base_val = self.get_value_for_year(series, year - n)
                if not cur_col or pd.isna(cur_val) or pd.isna(base_val) or base_val <= 0 or cur_val <= 0:
                    continue
                values[cur_col] = (cur_val / base_val) ** (1 / n) - 1
            return values

        ratios["Variación Ingresos (YoY)"] = pd.Series(_yoy(ventas))
        ratios["Variación EBITDA (YoY)"] = pd.Series(_yoy(ebitda))
        ratios["Variación Utilidad Neta (YoY)"] = pd.Series(_yoy(neta))
        ratios["CAGR Ingresos 3 Años"] = pd.Series(_cagr(ventas, 3))
        ratios["CAGR Ingresos 5 Años"] = pd.Series(_cagr(ventas, 5))

        return ratios

    def calculate_dupont_ratios(self) -> Dict[str, pd.Series]:
        """
        Descomposición DuPont del ROE:
        ROE = Margen Neto × Rotación de Activos × Multiplicador de Capital.
        Usa promedios de balance (activos y patrimonio), igual que ROE/ROA.

        Returns:
            Diccionario con los componentes DuPont y el ROE reconstituido por año
        """
        ratios = {}

        ventas = self.income.get("Ventas", pd.Series(dtype=float))
        neta = self.income.get("Neta", pd.Series(dtype=float))

        margen = {}
        rotacion = {}
        multiplicador = {}
        roe_dupont = {}

        for year in self.years:
            ventas_col = self.get_column_for_year(ventas, year)
            neta_col = self.get_column_for_year(neta, year)
            at_avg = self.get_average_balance_item(self.balance.get("AT", pd.Series(dtype=float)), year)
            patr_avg = self.get_average_balance_item(self.balance.get("Patr", pd.Series(dtype=float)), year)

            # Margen Neto = Utilidad Neta / Ventas
            if neta_col and ventas_col and not pd.isna(ventas[ventas_col]) and ventas[ventas_col] != 0:
                margen[neta_col] = neta[neta_col] / ventas[ventas_col]

            # Rotación de Activos = Ventas / Activos Promedio
            if ventas_col and not pd.isna(at_avg) and at_avg != 0:
                rotacion[ventas_col] = ventas[ventas_col] / at_avg

            # Multiplicador de Capital = Activos Promedio / Patrimonio Promedio
            if neta_col and not pd.isna(at_avg) and not pd.isna(patr_avg) and patr_avg > 0:
                multiplicador[neta_col] = at_avg / patr_avg

            # ROE reconstituido = producto de los tres componentes
            if neta_col in margen and neta_col in multiplicador and ventas_col in rotacion:
                roe_dupont[neta_col] = margen[neta_col] * rotacion[ventas_col] * multiplicador[neta_col]

        ratios["Margen Neto (DuPont)"] = pd.Series(margen)
        ratios["Rotación de Activos (DuPont)"] = pd.Series(rotacion)
        ratios["Multiplicador de Capital"] = pd.Series(multiplicador)
        ratios["ROE (DuPont)"] = pd.Series(roe_dupont)

        return ratios

    def calculate_quality_scores(self) -> Dict[str, pd.Series]:
        """
        Calcula indicadores de calidad de resultados y scores compuestos (valores).

        - Accruals = (Utilidad Neta - CFO) / Activos Totales
        - ROIC = NOPAT / Capital Invertido, con NOPAT = EBIT × (1 - tasa efectiva),
          tasa efectiva = |Impuesto / Utilidad antes de impuestos| y
          Capital Invertido = Patrimonio promedio + Deuda Financiera Neta promedio
        - Altman Z''-Score (mercados emergentes) = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4,
          con X1 = Capital de trabajo/Activos, X2 = Utilidades retenidas/Activos,
          X3 = EBIT/Activos, X4 = Patrimonio/Pasivos totales
        - Piotroski F-Score (0-9, entero): 9 señales clásicas con dos períodos consecutivos;
          None si falta el período anterior. La señal de dilución (no emisión de acciones)
          otorga el punto sólo si existe el dato de acciones emitidas ("Acciones") y no
          aumentó; sin dato la señal vale 0 (el score se mantiene sobre 9, sin reescalar).
          La señal de apalancamiento usa Otros pasivos financieros no corrientes y, si no
          están disponibles, pasivos no corrientes (PT - PC).

        Returns:
            Diccionario con indicadores de calidad y scores por año
        """
        ratios = {}

        ac = self.balance.get("AC", pd.Series(dtype=float))
        pc = self.balance.get("PC", pd.Series(dtype=float))
        at = self.balance.get("AT", pd.Series(dtype=float))
        pt = self.balance.get("PT", pd.Series(dtype=float))
        patr = self.balance.get("Patr", pd.Series(dtype=float))
        utilret = self.balance.get("UtilRet", pd.Series(dtype=float))
        acciones = self.balance.get("Acciones", pd.Series(dtype=float))
        ventas = self.income.get("Ventas", pd.Series(dtype=float))
        bruta = self.income.get("Bruta", pd.Series(dtype=float))
        ebit = self.income.get("EBIT", pd.Series(dtype=float))
        neta = self.income.get("Neta", pd.Series(dtype=float))
        impuesto = self.income.get("Impuesto", pd.Series(dtype=float))
        pretax = self.income.get("PreTax", pd.Series(dtype=float))
        cfo = self.cash_flow.get("CFO", pd.Series(dtype=float))

        # Accruals = (Utilidad Neta - CFO) / Activos Totales
        ratios["Accruals (UN - CFO) / Activos"] = (
            neta.subtract(cfo, fill_value=np.nan)
            .divide(at, fill_value=np.nan)
            .replace([np.inf, -np.inf], np.nan)
        )

        # ROIC = NOPAT / (Patrimonio promedio + Deuda Financiera Neta promedio)
        deuda_fin_neta = self.get_net_financial_debt()
        roic = {}
        for year in self.years:
            ebit_col = self.get_column_for_year(ebit, year)
            ebit_val = self.get_value_for_year(ebit, year)
            tax_val = self.get_value_for_year(impuesto, year)
            pretax_val = self.get_value_for_year(pretax, year)
            if not ebit_col or pd.isna(ebit_val) or pd.isna(tax_val) or pd.isna(pretax_val) or pretax_val == 0:
                continue
            # Tasa impositiva efectiva implícita = |Impuesto / Utilidad antes de impuestos|
            tax_rate = abs(tax_val / pretax_val)
            nopat = ebit_val * (1 - tax_rate)
            patr_avg = self.get_average_balance_item(patr, year)
            dfn_avg = self.get_average_balance_item(deuda_fin_neta, year) if not deuda_fin_neta.empty else np.nan
            if pd.isna(patr_avg) or pd.isna(dfn_avg):
                continue
            invertido = patr_avg + dfn_avg
            if invertido <= 0:
                continue
            roic[ebit_col] = nopat / invertido
        ratios["ROIC"] = pd.Series(roic)

        # Altman Z'' (mercados emergentes) = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4
        altman = {}
        for year in self.years:
            at_col = self.get_column_for_year(at, year)
            at_val = self.get_value_for_year(at, year)
            pt_val = self.get_value_for_year(pt, year)
            if not at_col or pd.isna(at_val) or at_val == 0 or pd.isna(pt_val) or pt_val == 0:
                continue
            x1 = (self.get_value_for_year(ac, year) - self.get_value_for_year(pc, year)) / at_val
            x2 = self.get_value_for_year(utilret, year) / at_val
            x3 = self.get_value_for_year(ebit, year) / at_val
            x4 = self.get_value_for_year(patr, year) / pt_val
            if any(pd.isna(x) for x in (x1, x2, x3, x4)):
                continue
            altman[at_col] = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        ratios["Altman Z''-Score (EM)"] = pd.Series(altman)

        # Piotroski F-Score (0-9): ver docstring
        opfnc = self.balance.get("OPFNC", pd.Series(dtype=float))
        if opfnc.dropna().empty:
            lt_debt = pt.subtract(pc, fill_value=np.nan)
        else:
            lt_debt = opfnc

        piotroski = {}
        for year in self.years:
            neta_col = self.get_column_for_year(neta, year)
            at_t = self.get_value_for_year(at, year)
            at_p = self.get_value_for_year(at, year - 1)
            neta_t = self.get_value_for_year(neta, year)
            neta_p = self.get_value_for_year(neta, year - 1)
            # Sin período anterior no hay score
            if (not neta_col or pd.isna(at_t) or pd.isna(at_p) or at_t == 0 or at_p == 0
                    or pd.isna(neta_t) or pd.isna(neta_p)):
                continue

            score = 0
            roa_t = neta_t / at_t
            roa_p = neta_p / at_p
            cfo_t = self.get_value_for_year(cfo, year)

            # 1. ROA > 0
            if roa_t > 0:
                score += 1
            # 2. CFO > 0
            if not pd.isna(cfo_t) and cfo_t > 0:
                score += 1
            # 3. ΔROA > 0
            if roa_t > roa_p:
                score += 1
            # 4. Accruals: CFO > Utilidad Neta
            if not pd.isna(cfo_t) and cfo_t > neta_t:
                score += 1
            # 5. ΔApalancamiento: deuda de largo plazo / activos disminuye
            lt_t = self.get_value_for_year(lt_debt, year)
            lt_p = self.get_value_for_year(lt_debt, year - 1)
            if not pd.isna(lt_t) and not pd.isna(lt_p) and (lt_t / at_t) < (lt_p / at_p):
                score += 1
            # 6. ΔLiquidez: liquidez corriente aumenta
            ac_t = self.get_value_for_year(ac, year)
            ac_p = self.get_value_for_year(ac, year - 1)
            pc_t = self.get_value_for_year(pc, year)
            pc_p = self.get_value_for_year(pc, year - 1)
            if (not pd.isna(ac_t) and not pd.isna(ac_p) and not pd.isna(pc_t) and not pd.isna(pc_p)
                    and pc_t != 0 and pc_p != 0 and (ac_t / pc_t) > (ac_p / pc_p)):
                score += 1
            # 7. Dilución: sin aumento de acciones emitidas (sin dato = 0 puntos)
            acc_t = self.get_value_for_year(acciones, year)
            acc_p = self.get_value_for_year(acciones, year - 1)
            if not pd.isna(acc_t) and not pd.isna(acc_p) and acc_t <= acc_p:
                score += 1
            # 8. ΔMargen Bruto > 0
            bruta_t = self.get_value_for_year(bruta, year)
            bruta_p = self.get_value_for_year(bruta, year - 1)
            ventas_t = self.get_value_for_year(ventas, year)
            ventas_p = self.get_value_for_year(ventas, year - 1)
            if (not pd.isna(bruta_t) and not pd.isna(bruta_p) and not pd.isna(ventas_t) and not pd.isna(ventas_p)
                    and ventas_t != 0 and ventas_p != 0 and (bruta_t / ventas_t) > (bruta_p / ventas_p)):
                score += 1
            # 9. ΔRotación de Activos > 0
            if (not pd.isna(ventas_t) and not pd.isna(ventas_p)
                    and (ventas_t / at_t) > (ventas_p / at_p)):
                score += 1

            piotroski[neta_col] = score
        ratios["Piotroski F-Score"] = pd.Series(piotroski)

        return ratios

    def calculate_all_ratios(self) -> Dict[str, Dict[str, pd.Series]]:
        """
        Calcula todos los ratios financieros organizados por categoría.

        Returns:
            Diccionario con todos los ratios organizados por categoría
        """
        return {
            "LIQUIDEZ": self.calculate_liquidity_ratios(),
            "SOLVENCIA Y ESTRUCTURA": self.calculate_solvency_ratios(),
            "RENTABILIDAD": self.calculate_profitability_ratios(),
            "EFICIENCIA OPERATIVA": self.calculate_efficiency_ratios(),
            "FLUJOS Y ADICIONALES": self.calculate_cash_flow_ratios(),
            "CRECIMIENTO": self.calculate_growth_ratios(),
            "DUPONT": self.calculate_dupont_ratios(),
            "CALIDAD Y SCORES": self.calculate_quality_scores()
        }
