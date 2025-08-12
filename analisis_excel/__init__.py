"""
Módulo de Análisis Financiero Excel
===================================

Este módulo proporciona herramientas para realizar análisis financiero 
automatizado sobre archivos Excel de estados financieros.

Componentes principales:
- data_extractor: Extracción de datos de estados financieros
- formula_builder: Construcción de fórmulas Excel para análisis
- ratio_calculator: Cálculo de ratios financieros
- excel_formatter: Formateo y estilizado de archivos Excel
- bulk_processor: Procesamiento masivo de archivos
"""

from .data_extractor import DataExtractor
from .formula_builder import FormulaBuilder
from .ratio_calculator import RatioCalculator
from .excel_formatter import ExcelFormatter
from .bulk_processor import BulkProcessor

__version__ = "1.0.0"
__author__ = "CMF Web Scraping Team"

__all__ = [
    'DataExtractor',
    'FormulaBuilder', 
    'RatioCalculator',
    'ExcelFormatter',
    'BulkProcessor'
]
