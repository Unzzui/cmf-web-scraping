# -*- coding: utf-8 -*-
"""
Configuraciones de pytest para el directorio de tests.
"""

def pytest_addoption(parser):
    """Agrega opciones de línea de comandos a pytest."""
    parser.addoption(
        "--excel-path", action="store", default=None, help="Ruta al archivo Excel a validar"
    )
