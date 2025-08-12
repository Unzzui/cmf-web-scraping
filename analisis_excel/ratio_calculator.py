"""
Ratio Calculator Module
======================

Módulo para calcular ratios financieros a partir de datos extraídos.
Incluye ratios de liquidez, solvencia, rentabilidad, eficiencia y flujos.
"""

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
        """Encuentra la columna correspondiente a un año específico."""
        for col in series.index:
            if str(col).startswith(f"{year}-"):
                return col
        return None
    
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
        ebitda = ebit.add(da, fill_value=0)
        ratios["Deuda / EBITDA"] = pt.divide(ebitda, fill_value=np.nan)
        
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
            if neta_col and not pd.isna(patr_avg) and patr_avg != 0:
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
            "FLUJOS Y ADICIONALES": self.calculate_cash_flow_ratios()
        }
