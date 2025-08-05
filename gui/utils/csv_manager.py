#!/usr/bin/env python3
"""
Utilidades para manejo de archivos CSV en el CMF Scraper
"""

import os
import pandas as pd
from typing import Optional, Tuple


class CSVManager:
    """Manejador de archivos CSV para el scraper"""
    
    def __init__(self, default_path: str = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"):
        self.default_path = default_path
        self.current_path = None
        self.companies_df = None
    
    def load_default(self) -> Tuple[bool, str]:
        """Cargar archivo CSV por defecto"""
        return self.load_csv(self.default_path)
    
    def load_csv(self, file_path: str) -> Tuple[bool, str]:
        """
        Cargar archivo CSV
        
        Returns:
            Tuple[bool, str]: (éxito, mensaje)
        """
        try:
            if not os.path.exists(file_path):
                return False, f"Archivo no encontrado: {file_path}"
            
            # Leer CSV
            self.companies_df = pd.read_csv(file_path)
            
            # Verificar columnas requeridas
            required_columns = ['Razón Social', 'RUT', 'RUT_Sin_Guión']
            missing_columns = [col for col in required_columns if col not in self.companies_df.columns]
            
            if missing_columns:
                return False, f"Columnas faltantes en el CSV: {missing_columns}"
            
            # Limpiar datos
            self.companies_df = self._clean_data(self.companies_df)
            
            self.current_path = file_path
            num_companies = len(self.companies_df)
            
            return True, f"Archivo cargado correctamente: {num_companies} empresas encontradas"
            
        except Exception as e:
            return False, f"Error cargando CSV: {str(e)}"
    
    def _clean_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Limpiar y validar datos del DataFrame"""
        # Eliminar filas con datos faltantes en columnas críticas
        df = df.dropna(subset=['Razón Social', 'RUT', 'RUT_Sin_Guión'])
        
        # Limpiar espacios en blanco
        string_columns = ['Razón Social', 'RUT', 'RUT_Sin_Guión']
        for col in string_columns:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip()
        
        # Validar formato de RUT sin guión (solo números)
        if 'RUT_Sin_Guión' in df.columns:
            df = df[df['RUT_Sin_Guión'].str.isdigit()]
        
        return df
    
    def get_companies_data(self) -> Optional[pd.DataFrame]:
        """Obtener DataFrame de empresas"""
        return self.companies_df
    
    def get_current_path(self) -> Optional[str]:
        """Obtener ruta del archivo actual"""
        return self.current_path
    
    def reload_current(self) -> Tuple[bool, str]:
        """Recargar archivo actual"""
        if self.current_path:
            return self.load_csv(self.current_path)
        else:
            return False, "No hay archivo cargado para recargar"
    
    def validate_company_data(self, company_data: dict) -> bool:
        """Validar datos de una empresa"""
        required_fields = ['razon_social', 'rut', 'rut_sin_guion']
        
        for field in required_fields:
            if field not in company_data or not company_data[field]:
                return False
        
        # Validar que RUT sin guión sea numérico
        if not str(company_data['rut_sin_guion']).isdigit():
            return False
        
        return True
    
    def get_company_count(self) -> int:
        """Obtener número de empresas cargadas"""
        if self.companies_df is not None:
            return len(self.companies_df)
        return 0
