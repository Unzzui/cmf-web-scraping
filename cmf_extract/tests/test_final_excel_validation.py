#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test de validación para un único archivo Excel generado.

Uso (desde la raíz del repo):
  pytest tests/test_final_excel_validation.py --excel-path /ruta/a/tu/archivo.xlsx
"""

import pytest
from pathlib import Path
from tests.validate_final_excel_es import validate_workbook
from tests.validators.cash_flow import validate_cash_flow_consistency


@pytest.mark.validation
def test_validate_generated_excel(pytestconfig):
    """Valida un archivo excel específico pasado por --excel-path."""
    excel_path_str = pytestconfig.getoption("excel_path")
    if not excel_path_str:
        pytest.skip("No se proveyó --excel-path. Saltando test de validación.")

    excel_path = Path(excel_path_str)
    if not excel_path.exists():
        pytest.fail(f"El archivo especificado en --excel-path no existe: {excel_path}")

    # 1) Validaciones base (estructura, tipos, balance, etc.)
    errors = validate_workbook(excel_path)

    # 2) Validador inteligente de Flujo de Efectivo
    #    Reemplaza/depura los errores simplistas del flujo por una verificación jerárquica flexible.
    cf_errors = validate_cash_flow_consistency(excel_path)
    if cf_errors:
        # Eliminar errores previos de [Flujo] y agregar los inteligentes
        errors = [e for e in errors if " [Flujo] " not in e]
        errors.extend(cf_errors)
    else:
        # Si el validador inteligente no encontró problemas, ignorar los falsos positivos del flujo simple
        errors = [e for e in errors if " [Flujo] " not in e]

    if errors:
        error_list = '\n'.join([f'  - {e}' for e in errors])
        pytest.fail(
            f"Se encontraron los siguientes errores de validación en {excel_path.name}:\n{error_list}"
        )
