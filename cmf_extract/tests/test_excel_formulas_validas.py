"""Ninguna fórmula del Excel puede estar malformada.

POR QUÉ ESTE TEST EXISTE
------------------------
La fórmula de "Recomendación" anidaba OCHO `IF` y cerraba SIETE paréntesis. Excel no puede
evaluar eso: la descarta en silencio y al abrir el archivo pide repararlo --

    "Se detectaron errores en el archivo (...)
     Registros quitados: Fórmula de /xl/worksheets/sheet7.xml parte"

-- y la celda "Recomendación" queda vacía. En TODAS las empresas. Justo la celda que un
usuario mira primero.

El bug sobrevivió porque nada validaba las fórmulas: se escriben como texto y openpyxl no
las parsea. Sólo Excel se daba cuenta, en la máquina del cliente.

Marcado como `validation` porque necesita un Excel ya generado.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pytest

PRODUCT = Path(__file__).resolve().parent.parent / "Product_v1" / "Total"

_FORMULA = re.compile(r'<c r="([A-Z]+\d+)"[^>]*>\s*<f[^>]*>([^<]*)</f>')


def _excels() -> list[Path]:
    return sorted(PRODUCT.glob("*.xlsx")) if PRODUCT.is_dir() else []


def _formulas_desbalanceadas(xlsx: Path) -> list[tuple[str, str, str]]:
    """(hoja, celda, fórmula) de cada fórmula con paréntesis desbalanceados."""
    malas = []
    with zipfile.ZipFile(xlsx) as z:
        for nombre in z.namelist():
            if not nombre.startswith("xl/worksheets/sheet"):
                continue
            raw = z.read(nombre).decode("utf-8", errors="replace")
            for celda, formula in _FORMULA.findall(raw):
                # Las comillas de Excel pueden contener paréntesis literales; se sacan
                # antes de contar, o un texto como "Prima/(Descuento)" daría falso positivo.
                sin_texto = re.sub(r'"[^"]*"', "", formula)
                if sin_texto.count("(") != sin_texto.count(")"):
                    malas.append((nombre, celda, formula))
    return malas


@pytest.mark.validation
@pytest.mark.skipif(not _excels(), reason="no hay Excel generado en Product_v1/Total")
def test_ninguna_formula_tiene_parentesis_desbalanceados():
    """Una fórmula desbalanceada es un archivo corrupto para Excel. Cero tolerancia."""
    rotas: list[str] = []
    for xlsx in _excels():
        for hoja, celda, formula in _formulas_desbalanceadas(xlsx):
            rotas.append(f"{xlsx.name} · {hoja} · {celda}: {formula[:90]}")

    assert not rotas, (
        f"{len(rotas)} fórmula(s) con paréntesis desbalanceados. Excel las descarta y le "
        f"pide al usuario reparar el archivo:\n  " + "\n  ".join(rotas[:10])
    )
