"""
Data Extractor Module
====================

Módulo para extraer datos de estados financieros desde archivos Excel.
Maneja la identificación y extracción de conceptos contables específicos.
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple


class DataExtractor:
    """
    Extractor de datos de estados financieros desde archivos Excel.
    """
    
    def __init__(self, file_path: str):
        """
        Inicializa el extractor con un archivo Excel.
        
        Args:
            file_path: Ruta al archivo Excel de estados financieros
        """
        self.file_path = file_path
        self.df_bal = None
        self.df_pl = None
        self.df_cfs = None
        self.years = []
        
    def load_data(self) -> bool:
        """
        Carga los datos de las hojas de estados financieros.
        
        Returns:
            True si la carga fue exitosa, False en caso contrario
        """
        try:
            # Cargar las hojas principales
            self.df_bal = pd.read_excel(self.file_path, sheet_name="Balance General")
            self.df_pl = pd.read_excel(self.file_path, sheet_name="Estado Resultados (Función)")
            self.df_cfs = pd.read_excel(self.file_path, sheet_name="Flujo Efectivo")
            
            # Renombrar primera columna como 'Concepto'
            self.df_bal.rename(columns={self.df_bal.columns[0]: "Concepto"}, inplace=True)
            self.df_pl.rename(columns={self.df_pl.columns[0]: "Concepto"}, inplace=True)
            self.df_cfs.rename(columns={self.df_cfs.columns[0]: "Concepto"}, inplace=True)
            
            # Extraer años disponibles
            self._extract_years()
            
            return True
        except Exception as e:
            print(f"Error cargando datos: {e}")
            return False
    
    def _extract_years(self):
        """Extrae los años disponibles de las columnas de los dataframes."""
        years_set = set()
        
        for df in [self.df_bal, self.df_pl, self.df_cfs]:
            for col in df.columns[1:]:  # Excluir columna 'Concepto'
                match = re.match(r"^(\d{4})-", str(col))
                if match:
                    years_set.add(int(match.group(1)))
        
        self.years = sorted(years_set)
    
    def find_row_series(self, df: pd.DataFrame, concept_name: str) -> pd.Series:
        """
        Busca una serie de datos por concepto exacto o contiene.
        
        Args:
            df: DataFrame donde buscar
            concept_name: Nombre del concepto a buscar
            
        Returns:
            Serie con los valores numéricos del concepto
        """
        # Búsqueda exacta primero
        mask = df["Concepto"].astype(str).str.strip().str.lower() == concept_name.strip().lower()
        if mask.any():
            series = df[mask].iloc[0].drop(labels=["Concepto"])
            series.index = series.index.astype(str)
            return pd.to_numeric(series, errors="coerce")
        
        # Búsqueda por contiene
        mask = df["Concepto"].astype(str).str.contains(re.escape(concept_name), case=False, na=False)
        if mask.any():
            series = df[mask].iloc[0].drop(labels=["Concepto"])
            series.index = series.index.astype(str)
            return pd.to_numeric(series, errors="coerce")
        
        return pd.Series(dtype=float)
    
    def extract_balance_sheet_items(self) -> Dict[str, pd.Series]:
        """
        Extrae los conceptos principales del Balance General.
        
        Returns:
            Diccionario con los conceptos del balance general
        """
        concepts = {
            "AC": "Activos corrientes totales",
            "PC": "Pasivos corrientes totales", 
            "Efec": "Efectivo y equivalentes al efectivo",
            "Inv": "Inventarios corrientes",
            "AT": "Total de activos",
            "PT": "Total de pasivos",
            "Patr": "Patrimonio atribuible a los propietarios de la controladora",
            "CxC": "Deudores comerciales y otras cuentas por cobrar corrientes",
            "CxP": "Cuentas por pagar comerciales y otras cuentas por pagar"
        }
        
        return {key: self.find_row_series(self.df_bal, concept) 
                for key, concept in concepts.items()}
    
    def extract_income_statement_items(self) -> Dict[str, pd.Series]:
        """
        Extrae los conceptos principales del Estado de Resultados.
        
        Returns:
            Diccionario con los conceptos del estado de resultados
        """
        concepts = {
            "Ventas": "Ingresos de actividades ordinarias",
            "COGS": "Costo de ventas",
            "Bruta": "Ganancia bruta",
            "EBIT": "Ganancias (pérdidas) de actividades operacionales",
            "Neta": "Ganancia (pérdida)",
            "Interes": "Costos financieros",
            "Dep": "Depreciación",
            "Amort": "Amortización"
        }
        
        items = {}
        for key, concept in concepts.items():
            items[key] = self.find_row_series(self.df_pl, concept)
        
        # Calcular D&A combinado
        dep = items.get("Dep", pd.Series(dtype=float))
        amort = items.get("Amort", pd.Series(dtype=float))
        items["DA"] = dep.add(amort, fill_value=0)
        
        return items
    
    def extract_cash_flow_items(self) -> Dict[str, pd.Series]:
        """
        Extrae los conceptos principales del Flujo de Efectivo.
        
        Returns:
            Diccionario con los conceptos del flujo de efectivo
        """
        concepts = {
            "CFO": "Flujos de efectivo netos procedentes de (utilizados en) operaciones",
            "CapexBuy": "Compras de propiedades, planta y equipo"
        }
        
        items = {}
        for key, concept in concepts.items():
            items[key] = self.find_row_series(self.df_cfs, concept)
        
        # Calcular CAPEX y FCF
        capex_buy = items.get("CapexBuy", pd.Series(dtype=float))
        items["CAPEX"] = capex_buy.abs()
        
        cfo = items.get("CFO", pd.Series(dtype=float))
        items["FCF"] = cfo.subtract(items["CAPEX"], fill_value=0)
        
        return items
    
    def get_column_for_year(self, series: pd.Series, year: int) -> Optional[str]:
        """
        Encuentra la columna correspondiente a un año específico.
        
        Args:
            series: Serie de datos
            year: Año a buscar
            
        Returns:
            Nombre de la columna o None si no se encuentra
        """
        for col in series.index:
            if str(col).startswith(f"{year}-"):
                return col
        return None
    
    def get_all_financial_data(self) -> Dict[str, Dict[str, pd.Series]]:
        """
        Extrae todos los datos financieros de las tres hojas.
        
        Returns:
            Diccionario con todos los datos organizados por hoja
        """
        return {
            "balance": self.extract_balance_sheet_items(),
            "income": self.extract_income_statement_items(),
            "cash_flow": self.extract_cash_flow_items(),
            "years": self.years
        }
