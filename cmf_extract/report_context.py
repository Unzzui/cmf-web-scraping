"""Contexto de reporte de un Excel: mercado, moneda de comparación, fuente y estándar.

El pipeline de análisis (portada, NOTAS, Ficha Técnica, RATIOS, DCF) nació para Chile y por
eso asumía CMF / IFRS / CLP en todas partes. Cuando se le da un estado de EEUU esos textos
son FALSOS: la empresa reporta a la SEC en US GAAP y en dólares, no a la CMF en pesos. Mostrar
"Miles CLP" o "Fuente: CMF Chile" en el Excel de NVIDIA no es un detalle de formato — rompe la
trazabilidad (fuente, unidad, estándar) que es la razón de ser de FinData.

Este módulo centraliza esa distinción. El mercado se decide, en orden:
  1. env `CMF_REPORT_MARKET` (lo setea `run_products_analysis`/el orquestador para el pipeline US),
  2. una pista de ruta (`Product_v1_US`, `..._US`) por si se corre a mano.
Chile es el default. NUNCA se inventa la moneda: si es US es USD (SEC/EDGAR, US GAAP); si es CL,
la moneda real la sigue leyendo el pipeline del XBRL como hasta ahora.
"""
from __future__ import annotations

import os


def es_us(hint: str = "") -> bool:
    """True si el reporte es de EEUU. Mira el env primero, luego una pista de ruta."""
    if os.environ.get("CMF_REPORT_MARKET", "").strip().upper() == "US":
        return True
    h = str(hint or "")
    return "product_v1_us" in h.lower() or "_us/" in h.lower() or h.endswith("_US")


def contexto(hint: str = "", moneda: str = "") -> dict:
    """Devuelve los rótulos del reporte (mercado, moneda, fuente, estándar, disclaimers).

    `moneda` (opcional) es la moneda real leída de los datos; si no viene, se usa el default
    del mercado (USD para EEUU, y se deja vacío para Chile porque allá se lee del XBRL).
    """
    if es_us(hint):
        m = (moneda or "USD").upper()
        return {
            "market": "US",
            "moneda": m,                     # moneda de los estados (USD)
            "moneda_precio": m,              # moneda contra la que se compara el precio de bolsa
            "pais": "Estados Unidos",
            "fuente": "SEC/EDGAR",
            "fuente_ficha": "SEC/EDGAR - XBRL US GAAP",
            "estandar": "US GAAP",
            "regulador_largo": "la SEC (U.S. Securities and Exchange Commission) vía EDGAR",
            "disclaimer_footer": ("Datos oficiales US GAAP de SEC/EDGAR. Solo fines "
                                  "educativos/profesionales. No constituye asesoría de inversión."),
            "resumen_fuente": ("bajo estándar US GAAP reportados por la empresa a la SEC "
                               "(U.S. Securities and Exchange Commission) vía EDGAR"),
            "notas_fuente": ("Datos extraídos de reportes XBRL (10-K/10-Q) publicados por la SEC "
                             "(U.S. Securities and Exchange Commission) vía EDGAR."),
        }
    m = (moneda or "").upper()
    return {
        "market": "CL",
        "moneda": m,
        "moneda_precio": "CLP",             # en Chile el precio de bolsa está en pesos
        "pais": "Chile",
        "fuente": "CMF Chile",
        "fuente_ficha": "CMF Chile - XBRL IFRS",
        "estandar": "IFRS",
        "regulador_largo": "la CMF (Comisión para el Mercado Financiero de Chile)",
        "disclaimer_footer": ("Datos oficiales IFRS de CMF Chile. Solo fines "
                              "educativos/profesionales. No constituye asesoría de inversión."),
        "resumen_fuente": ("bajo estándar IFRS reportados por la empresa a la CMF "
                           "(Comisión para el Mercado Financiero de Chile)"),
        "notas_fuente": ("Datos extraídos de reportes XBRL publicados por la Comisión para el "
                         "Mercado Financiero (CMF) de Chile."),
    }
