#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMF Bank Data Scraper
Descarga información financiera de bancos chilenos desde la CMF
"""

import os
import time
import logging
import pandas as pd
import requests
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from urllib.parse import urlencode

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CMFBankScraper:
    """Scraper para datos bancarios de la CMF"""
    
    BASE_URL = "https://datosbanco.cmfchile.cl/sbifweb/servlet/BaseDato"
    
    BANK_CODES = {
        "001": "BANCO DE CHILE",
        "009": "BANCO INTERNACIONAL",
        "012": "BANCO DEL ESTADO DE CHILE",
        "014": "SCOTIABANK CHILE",
        "016": "BANCO DE CREDITO E INVERSIONES",
        "017": "BANCO DO BRASIL S.A.",
        "028": "BANCO BICE",
        "031": "HSBC BANK (CHILE)",
        "037": "BANCO SANTANDER-CHILE",
        "039": "ITAU CHILE",
        "041": "JP MORGAN CHASE BANK N.A.",
        "043": "BANCO DE LA NACION ARGENTINA",
        "045": "MUFG Bank, Ltd.",
        "049": "BANCO SECURITY",
        "051": "BANCO FALABELLA",
        "053": "BANCO RIPLEY",
        "055": "BANCO CONSORCIO",
        "059": "BANCO BTG PACTUAL CHILE",
        "060": "CHINA CONSTRUCTION BANK",
        "061": "BANK OF CHINA, AGENCIA EN CHILE",
        "504": "BBVA",
        "999": "SISTEMA FINANCIERO"
    }
    
    REPORT_TYPES = {
        "MB1": "ESTADO DE SITUACION",
        "MR1": "ESTADO DE RESULTADOS",
        "ADC": "ADECUACION DE CAPITAL",
        "ADC2": "ADEC. DE CAPITAL BASILEA III",
        "HEC": "HECHOS ESENCIALES",
        "FIC": "FICHA DE BANCO"
    }
    # RUTs de bancos chilenos por código
    BANKS_RUTS = {
        "001": "97004000-5",  # BANCO DE CHILE
        "009": "91011000-3",  # BANCO INTERNACIONAL
        "012": "97030000-7",  # BANCO DEL ESTADO DE CHILE
        "014": "97018000-1",  # SCOTIABANK CHILE
        "016": "97006000-6",  # BANCO DE CREDITO E INVERSIONES
        "017": "97003000-K",  # BANCO DO BRASIL S.A.
        "028": "97080000-K",  # BANCO BICE
        "031": "97080000-K",  # HSBC BANK (CHILE)
        "037": "97036000-K",  # BANCO SANTANDER-CHILE
        "039": "97039000-7",  # ITAU CHILE
        "041": "59135300-7",  # JP MORGAN CHASE BANK N.A.
        "043": "59135370-8",  # BANCO DE LA NACION ARGENTINA
        "045": "59135390-2",  # MUFG Bank, Ltd.
        "049": "96571240-2",  # BANCO SECURITY
        "051": "96509660-4",  # BANCO FALABELLA
        "053": "96947000-2",  # BANCO RIPLEY
        "055": "96571260-7",  # BANCO CONSORCIO
        "059": "96571300-K",  # BANCO BTG PACTUAL CHILE
        "060": "59135380-5",  # CHINA CONSTRUCTION BANK
        "061": "59135400-3",  # BANK OF CHINA, AGENCIA EN CHILE
        "504": "97032000-8",  # BBVA
        "999": "99999999-9"   # SISTEMA FINANCIERO
    }
    # Índices específicos para cada tipo de reporte
    REPORT_INDICES = {
        "MB1": "30.2.1",  # Estado de Situación
        "MR1": "30.3.1",  # Estado de Resultados
        "ADC": "30.4.1",  # Adecuación de Capital (estimado)
        "ADC2": "30.5.1", # Adecuación Capital Basilea III (estimado)
        "HEC": "30.6.1",  # Hechos Esenciales (estimado)
        "FIC": "30.7.1"   # Ficha de Banco (estimado)
    }
    
    def __init__(self, output_dir: str = "output/banks", last_available_period: str = None):
        """
        Inicializa el scraper de bancos
        
        Args:
            output_dir: Directorio donde se guardarán los archivos descargados
            last_available_period: Último período disponible en formato "MM/YYYY"
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        self.current_date = datetime.now()
        self.last_available_period = last_available_period
        
        # Parsear el último período disponible si se proporciona
        if last_available_period:
            try:
                if '/' in last_available_period:
                    parts = last_available_period.split('/')
                    if len(parts) != 2:
                        raise ValueError("Debe tener formato MM/YYYY")
                    month, year = parts
                else:
                    raise ValueError("Formato inválido - falta '/'")
                
                self.last_month = int(month)
                self.last_year = int(year)
                
                if not (1 <= self.last_month <= 12):
                    raise ValueError("Mes debe estar entre 01 y 12")
                if self.last_year < 2000 or self.last_year > 2030:
                    raise ValueError("Año fuera de rango válido")
                
                logger.info(f"Último período disponible configurado: {self.last_month:02d}/{self.last_year}")
                
            except (ValueError, IndexError) as e:
                logger.error(f"Formato de período inválido: '{last_available_period}'. Use MM/YYYY (ej: 07/2025)")
                logger.error(f"Error: {e}")
                raise ValueError(f"Período inválido: {last_available_period}")
        else:
            self.last_month = None
            self.last_year = None
    
    def get_bank_code_from_name(self, bank_name: str) -> Optional[str]:
        """
        Obtiene el código del banco a partir del nombre
        
        Args:
            bank_name: Nombre del banco
            
        Returns:
            Código del banco o None si no se encuentra
        """
        for code, name in self.BANK_CODES.items():
            if bank_name.upper() in name.upper():
                return code
        return None
    
    def build_view_url(self, bank_code: str, report_type: str, 
                      start_month: int, start_year: int,
                      end_month: int, end_year: int) -> str:
        """
        Construye la URL para ver los datos del banco
        
        Args:
            bank_code: Código del banco (ej: "001")
            report_type: Tipo de reporte (ej: "MB1")
            start_month: Mes inicial
            start_year: Año inicial
            end_month: Mes final
            end_year: Año final
            
        Returns:
            URL completa para acceder a los datos
        """
        params = {
            'listado': 'vigentes',
            'instituciones-financieras': bank_code.lstrip('0'),
            'codUnicoBank': '',
            'reporte': report_type,
            'TR': f'{start_month}/{start_year}',
            'TA': f'{start_month}/{start_year - 5}',
            'TA2': f'{start_month}/{start_year - 4}',
            'TF': f'{end_month}/{end_year}',
            'TB': f'{end_month}/{end_year}',
            'periodo_inicial_mes': str(start_month),
            'periodo_inicial_anio': str(start_year),
            'periodo_final_mes': str(end_month),
            'periodo_final_anio': str(end_year),
            'view-submit-bbdd': 'Ver',
            'indice': '30.1'
        }
        
        return f"{self.BASE_URL}?{urlencode(params)}"
    
    def build_download_csv_url(self, bank_code: str, report_type: str,
                              start_month: int, start_year: int,
                              end_month: int, end_year: int) -> str:
        """
        Construye la URL para descargar el CSV directamente
        
        Args:
            bank_code: Código del banco
            report_type: Tipo de reporte
            start_month: Mes inicial
            start_year: Año inicial
            end_month: Mes final
            end_year: Año final
            
        Returns:
            URL para descargar el CSV
        """
        bank_name = self.BANK_CODES.get(bank_code, "BANCO")
        report_name = self.REPORT_TYPES.get(report_type, "REPORTE")
        report_index = self.REPORT_INDICES.get(report_type, "30.2.1")  # Default a MB1 si no se encuentra
        
        params = {
            'indice': report_index,
            'instituciones-financieras': bank_code.lstrip('0'),
            'nombre_institucion': bank_name,
            'reporte': report_type,
            'nombre_reporte': report_name,
            'periodo_inicial_mes': f'{start_month:02d}',
            'periodo_inicial_anio': str(start_year),
            'periodo_final_mes': f'{end_month:02d}',
            'periodo_final_anio': str(end_year)
        }
        
        return f"{self.BASE_URL}?{urlencode(params)}"
    
    def is_period_available(self, month: int, year: int) -> bool:
        """
        Verifica si el período está disponible basado en el último período configurado
        
        Args:
            month: Mes a verificar
            year: Año a verificar
            
        Returns:
            True si el período está disponible, False si no
        """
        # Si no se configuró último período, usar validación por fecha actual
        if self.last_month is None or self.last_year is None:
            if year > self.current_date.year:
                return False
            elif year == self.current_date.year and month > self.current_date.month:
                return False
            return True
        
        # Usar el último período disponible configurado
        if year > self.last_year:
            return False
        elif year == self.last_year and month > self.last_month:
            return False
        return True
    
    def is_future_period(self, month: int, year: int) -> bool:
        """
        Alias para compatibilidad
        """
        return not self.is_period_available(month, year)
    
    def validate_csv_content(self, filepath: str) -> bool:
        """
        Valida básicamente que el archivo CSV no esté vacío
        
        Args:
            filepath: Ruta del archivo CSV
            
        Returns:
            True si el contenido parece válido, False si está vacío
        """
        try:
            file_size = os.path.getsize(filepath)
            # Solo verificar que el archivo no esté vacío
            if file_size < 100:
                logger.warning(f"Archivo muy pequeño o vacío: {filepath} ({file_size} bytes)")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validando archivo: {e}")
            return False
    
    def download_bank_data(self, bank_code: str, report_type: str,
                          start_month: int, start_year: int,
                          end_month: int = None, end_year: int = None,
                          save_as: str = None, organize_by_bank: bool = True) -> Optional[str]:
        """
        Descarga datos de un banco específico
        
        Args:
            bank_code: Código del banco
            report_type: Tipo de reporte
            start_month: Mes inicial
            start_year: Año inicial
            end_month: Mes final (por defecto igual al inicial)
            end_year: Año final (por defecto igual al inicial)
            save_as: Nombre del archivo a guardar
            organize_by_bank: Si True, crea subcarpeta para cada banco
            
        Returns:
            Path del archivo descargado o None si falla
        """
        if end_month is None:
            end_month = start_month
        if end_year is None:
            end_year = start_year
        
        # Validar si es un período futuro
        if self.is_future_period(start_month, start_year):
            logger.warning(f"Período futuro solicitado: {start_month:02d}/{start_year}")
            return None
            
        bank_name = self.BANK_CODES.get(bank_code, f"banco_{bank_code}")
        bank_name_clean = bank_name.replace(" ", "_").replace(",", "").replace(".", "")
        bank_rut = self.BANKS_RUTS.get(bank_code, f"RUT_{bank_code}")
        
        # Organizar en carpetas por banco (usando RUT) y reporte si está habilitado
        if organize_by_bank:
            bank_dir = self.output_dir / f"{bank_rut}_{bank_name_clean}"
            report_name = self.REPORT_TYPES.get(report_type, report_type)
            report_name_clean = report_name.replace(" ", "_").replace(",", "").replace(".", "")
            report_folder_name = f"{report_type}_{report_name_clean}"
            report_dir = bank_dir / report_folder_name
            report_dir.mkdir(parents=True, exist_ok=True)
            base_dir = report_dir
        else:
            base_dir = self.output_dir
        
        if save_as is None:
            # Nombre simplificado ya que el tipo está en la carpeta
            filename = f"{start_year}_{start_month:02d}.csv"
        else:
            filename = save_as if save_as.endswith('.csv') else f"{save_as}.csv"
        
        filepath = base_dir / filename
        
        try:
            url = self.build_download_csv_url(bank_code, report_type, 
                                             start_month, start_year,
                                             end_month, end_year)
            
            logger.info(f"Descargando {bank_name} - {start_month:02d}/{start_year}")
            
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            # Guardar directamente
            with open(filepath, 'wb') as f:
                f.write(response.content)
            
            # Validación básica del tamaño
            if self.validate_csv_content(filepath):
                logger.info(f"✓ Archivo guardado: {filepath}")
                return str(filepath)
            else:
                # Si el archivo está vacío, eliminarlo
                filepath.unlink()
                logger.warning(f"✗ Archivo vacío para {start_month:02d}/{start_year}")
                return None
            
        except requests.RequestException as e:
            logger.error(f"Error descargando datos: {e}")
            return None
        except Exception as e:
            logger.error(f"Error inesperado: {e}")
            return None
    
    def download_multiple_banks(self, bank_codes: List[str], report_type: str,
                               month: int, year: int) -> Dict[str, str]:
        """
        Descarga datos de múltiples bancos
        
        Args:
            bank_codes: Lista de códigos de bancos
            report_type: Tipo de reporte
            month: Mes a descargar
            year: Año a descargar
            
        Returns:
            Diccionario con código de banco y path del archivo descargado
        """
        results = {}
        
        for bank_code in bank_codes:
            if bank_code not in self.BANK_CODES:
                logger.warning(f"Código de banco no válido: {bank_code}")
                continue
            
            logger.info(f"Procesando {self.BANK_CODES[bank_code]}...")
            filepath = self.download_bank_data(bank_code, report_type, month, year)
            
            if filepath:
                results[bank_code] = filepath
            else:
                logger.error(f"No se pudo descargar datos para {bank_code}")
            
            time.sleep(2)
        
        return results
    
    def download_all_banks(self, report_type: str, month: int, year: int) -> Dict[str, str]:
        """
        Descarga datos de todos los bancos disponibles
        
        Args:
            report_type: Tipo de reporte
            month: Mes a descargar
            year: Año a descargar
            
        Returns:
            Diccionario con resultados de descarga
        """
        bank_codes = list(self.BANK_CODES.keys())
        bank_codes.remove("999")
        
        return self.download_multiple_banks(bank_codes, report_type, month, year)
    
    def process_csv_to_dataframe(self, filepath: str) -> Optional[pd.DataFrame]:
        """
        Procesa un archivo CSV descargado y lo convierte en DataFrame
        
        Args:
            filepath: Path del archivo CSV
            
        Returns:
            DataFrame con los datos o None si falla
        """
        try:
            df = pd.read_csv(filepath, encoding='latin-1', sep=';', thousands='.', decimal=',')
            
            if df.empty:
                logger.warning(f"DataFrame vacío para {filepath}")
                return None
            
            logger.info(f"DataFrame creado con {len(df)} filas y {len(df.columns)} columnas")
            return df
            
        except Exception as e:
            logger.error(f"Error procesando CSV: {e}")
            return None


def main():
    """Función principal para pruebas"""
    scraper = CMFBankScraper()
    
    logger.info("=== CMF Bank Scraper - Test ===")
    logger.info(f"Bancos disponibles: {len(scraper.BANK_CODES)}")
    
    test_bank = "001"
    test_report = "MB1"
    test_month = 7
    test_year = 2025
    
    logger.info(f"\nTest: Descargando {scraper.REPORT_TYPES[test_report]} para {scraper.BANK_CODES[test_bank]}")
    
    filepath = scraper.download_bank_data(test_bank, test_report, test_month, test_year)
    
    if filepath:
        logger.info(f"Descarga exitosa: {filepath}")
        
        df = scraper.process_csv_to_dataframe(filepath)
        if df is not None:
            logger.info(f"Primeras filas del DataFrame:")
            print(df.head())
    else:
        logger.error("Descarga falló")


if __name__ == "__main__":
    main()