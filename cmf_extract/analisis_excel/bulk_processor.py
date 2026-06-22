"""
Bulk Processor Module
====================

Módulo para procesamiento masivo de archivos Excel de estados financieros.
Permite analizar múltiples empresas y generar reportes consolidados.

.. deprecated::
    This module is a backward-compatibility shim.  The real implementation
    now lives in ``analisis_excel.processor``.
"""

from .processor import BulkProcessor

__all__ = ["BulkProcessor"]
