# -*- coding: utf-8 -*-
"""
Tests unitarios para los ratios nuevos de RatioCalculator:
CRECIMIENTO, DUPONT, Deuda Financiera Neta / EBITDA y CALIDAD Y SCORES.

Usa datos sintéticos (sin archivos Excel reales).
"""

import numpy as np
import pandas as pd
import pytest

from analisis_excel.ratio_calculator import RatioCalculator


def make_series(values: dict) -> pd.Series:
    """Crea una serie indexada por columnas 'YYYY-12-31' como las del extractor."""
    return pd.Series({f"{year}-12-31": val for year, val in values.items()}, dtype=float)


def col(year: int) -> str:
    return f"{year}-12-31"


def build_data(balance=None, income=None, cash_flow=None, years=None):
    balance = balance or {}
    income = income or {}
    cash_flow = cash_flow or {}
    all_years = years
    if all_years is None:
        all_years = sorted({
            int(str(idx)[:4])
            for group in (balance, income, cash_flow)
            for series in group.values()
            for idx in series.index
        })
    return {
        "balance": balance,
        "income": income,
        "cash_flow": cash_flow,
        "years": all_years,
    }


# ---------------------------------------------------------------------------
# CRECIMIENTO
# ---------------------------------------------------------------------------

class TestCrecimiento:
    def test_variacion_yoy_ingresos(self):
        data = build_data(income={"Ventas": make_series({2023: 1000.0, 2024: 1100.0})})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        yoy = ratios["Variación Ingresos (YoY)"]
        assert yoy[col(2024)] == pytest.approx(0.10)
        # 2023 no tiene período anterior
        assert col(2023) not in yoy.index

    def test_variacion_yoy_divisor_cero(self):
        data = build_data(income={"Ventas": make_series({2023: 0.0, 2024: 500.0})})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        assert ratios["Variación Ingresos (YoY)"].dropna().empty

    def test_variacion_yoy_base_negativa(self):
        # Con base negativa se usa |base|: (-50 - (-100)) / 100 = 0.5
        data = build_data(income={"Neta": make_series({2023: -100.0, 2024: -50.0})})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        assert ratios["Variación Utilidad Neta (YoY)"][col(2024)] == pytest.approx(0.5)

    def test_variacion_yoy_ebitda_con_da(self):
        data = build_data(income={
            "EBIT": make_series({2023: 100.0, 2024: 130.0}),
            "DA": make_series({2023: 20.0, 2024: 20.0}),
        })
        ratios = RatioCalculator(data).calculate_growth_ratios()
        # EBITDA: 120 -> 150 => 25%
        assert ratios["Variación EBITDA (YoY)"][col(2024)] == pytest.approx(0.25)

    def test_cagr_3_anios(self):
        ventas = make_series({2021: 1000.0, 2022: 1050.0, 2023: 1200.0, 2024: 1331.0})
        data = build_data(income={"Ventas": ventas})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        # (1331/1000)^(1/3) - 1 = 0.10
        assert ratios["CAGR Ingresos 3 Años"][col(2024)] == pytest.approx(0.10)

    def test_cagr_5_anios(self):
        ventas = make_series({y: 1000.0 * 1.1 ** (y - 2019) for y in range(2019, 2025)})
        data = build_data(income={"Ventas": ventas})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        assert ratios["CAGR Ingresos 5 Años"][col(2024)] == pytest.approx(0.10)

    def test_cagr_sin_periodos_suficientes(self):
        data = build_data(income={"Ventas": make_series({2023: 1000.0, 2024: 1100.0})})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        assert ratios["CAGR Ingresos 3 Años"].dropna().empty
        assert ratios["CAGR Ingresos 5 Años"].dropna().empty

    def test_cagr_base_no_positiva(self):
        ventas = make_series({2021: -1000.0, 2022: 1.0, 2023: 1.0, 2024: 1331.0})
        data = build_data(income={"Ventas": ventas})
        ratios = RatioCalculator(data).calculate_growth_ratios()
        assert col(2024) not in ratios["CAGR Ingresos 3 Años"].dropna().index


# ---------------------------------------------------------------------------
# DUPONT
# ---------------------------------------------------------------------------

class TestDupont:
    def make_data(self):
        return build_data(
            balance={
                "AT": make_series({2023: 2000.0, 2024: 2400.0}),
                "Patr": make_series({2023: 900.0, 2024: 1100.0}),
            },
            income={
                "Ventas": make_series({2023: 1000.0, 2024: 1100.0}),
                "Neta": make_series({2023: 80.0, 2024: 110.0}),
            },
        )

    def test_componentes_2024(self):
        ratios = RatioCalculator(self.make_data()).calculate_dupont_ratios()
        # Margen Neto = 110/1100; Rotación = 1100/2200; Multiplicador = 2200/1000
        assert ratios["Margen Neto (DuPont)"][col(2024)] == pytest.approx(0.10)
        assert ratios["Rotación de Activos (DuPont)"][col(2024)] == pytest.approx(0.5)
        assert ratios["Multiplicador de Capital"][col(2024)] == pytest.approx(2.2)

    def test_roe_reconstituido_igual_a_roe(self):
        calc = RatioCalculator(self.make_data())
        dupont = calc.calculate_dupont_ratios()
        roe = calc.calculate_profitability_ratios()["ROE"]
        # ROE reconstituido = 0.10 × 0.5 × 2.2 = 0.11 = Neta / Patrimonio promedio
        assert dupont["ROE (DuPont)"][col(2024)] == pytest.approx(0.11)
        assert dupont["ROE (DuPont)"][col(2024)] == pytest.approx(roe[col(2024)])

    def test_ventas_cero(self):
        data = self.make_data()
        data["income"]["Ventas"] = make_series({2023: 1000.0, 2024: 0.0})
        ratios = RatioCalculator(data).calculate_dupont_ratios()
        assert col(2024) not in ratios["Margen Neto (DuPont)"].index
        assert col(2024) not in ratios["ROE (DuPont)"].index

    def test_patrimonio_no_positivo(self):
        data = self.make_data()
        data["balance"]["Patr"] = make_series({2023: -900.0, 2024: -1100.0})
        ratios = RatioCalculator(data).calculate_dupont_ratios()
        assert ratios["Multiplicador de Capital"].dropna().empty
        assert ratios["ROE (DuPont)"].dropna().empty


# ---------------------------------------------------------------------------
# SOLVENCIA: Deuda Financiera Neta / EBITDA
# ---------------------------------------------------------------------------

class TestDeudaFinancieraNeta:
    def test_deuda_financiera_neta_sobre_ebitda(self):
        data = build_data(
            balance={
                "OPFC": make_series({2024: 100.0}),
                "OPFNC": make_series({2024: 400.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_solvency_ratios()
        # (100 + 400 - 50) / 150 = 3.0
        assert ratios["Deuda Financiera Neta / EBITDA"][col(2024)] == pytest.approx(3.0)

    def test_deuda_financiera_neta_con_da(self):
        data = build_data(
            balance={
                "OPFC": make_series({2024: 100.0}),
                "OPFNC": make_series({2024: 400.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={
                "EBIT": make_series({2024: 150.0}),
                "DA": make_series({2024: 75.0}),
            },
        )
        ratios = RatioCalculator(data).calculate_solvency_ratios()
        # 450 / (150 + 75) = 2.0
        assert ratios["Deuda Financiera Neta / EBITDA"][col(2024)] == pytest.approx(2.0)

    def test_sin_cuentas_de_deuda_financiera(self):
        # Sin OPFC/OPFNC no se aproxima con pasivos totales: queda vacío (N/A)
        data = build_data(
            balance={
                "PT": make_series({2024: 1300.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_solvency_ratios()
        assert ratios["Deuda Financiera Neta / EBITDA"].dropna().empty

    def test_ebitda_cero(self):
        data = build_data(
            balance={
                "OPFC": make_series({2024: 100.0}),
                "OPFNC": make_series({2024: 400.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={"EBIT": make_series({2024: 0.0})},
        )
        ratios = RatioCalculator(data).calculate_solvency_ratios()
        assert ratios["Deuda Financiera Neta / EBITDA"].dropna().empty


# ---------------------------------------------------------------------------
# CALIDAD Y SCORES
# ---------------------------------------------------------------------------

class TestCalidadYScores:
    def test_accruals(self):
        data = build_data(
            balance={"AT": make_series({2024: 2400.0})},
            income={"Neta": make_series({2024: 110.0})},
            cash_flow={"CFO": make_series({2024: 100.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Accruals (UN - CFO) / Activos"][col(2024)] == pytest.approx(10.0 / 2400.0)

    def test_accruals_activos_cero(self):
        data = build_data(
            balance={"AT": make_series({2024: 0.0})},
            income={"Neta": make_series({2024: 110.0})},
            cash_flow={"CFO": make_series({2024: 100.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Accruals (UN - CFO) / Activos"].dropna().empty

    def test_roic(self):
        data = build_data(
            balance={
                "Patr": make_series({2023: 900.0, 2024: 1100.0}),
                "OPFC": make_series({2023: 100.0, 2024: 100.0}),
                "OPFNC": make_series({2023: 400.0, 2024: 400.0}),
                "Efec": make_series({2023: 50.0, 2024: 50.0}),
            },
            income={
                "EBIT": make_series({2024: 150.0}),
                "Impuesto": make_series({2024: -30.0}),
                "PreTax": make_series({2024: 120.0}),
            },
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        # Tasa efectiva = |−30/120| = 0.25; NOPAT = 150 × 0.75 = 112.5
        # Capital invertido = Patr prom (1000) + DFN prom (450) = 1450
        assert ratios["ROIC"][col(2024)] == pytest.approx(112.5 / 1450.0)

    def test_roic_sin_impuestos(self):
        data = build_data(
            balance={
                "Patr": make_series({2024: 1100.0}),
                "OPFC": make_series({2024: 100.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["ROIC"].dropna().empty

    def test_roic_pretax_cero(self):
        data = build_data(
            balance={
                "Patr": make_series({2024: 1100.0}),
                "OPFC": make_series({2024: 100.0}),
                "Efec": make_series({2024: 50.0}),
            },
            income={
                "EBIT": make_series({2024: 150.0}),
                "Impuesto": make_series({2024: -30.0}),
                "PreTax": make_series({2024: 0.0}),
            },
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["ROIC"].dropna().empty

    def test_roic_sin_deuda_financiera(self):
        # Sin cuentas de deuda financiera no hay capital invertido confiable
        data = build_data(
            balance={"Patr": make_series({2024: 1100.0})},
            income={
                "EBIT": make_series({2024: 150.0}),
                "Impuesto": make_series({2024: -30.0}),
                "PreTax": make_series({2024: 120.0}),
            },
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["ROIC"].dropna().empty

    def test_altman_z(self):
        data = build_data(
            balance={
                "AC": make_series({2024: 800.0}),
                "PC": make_series({2024: 400.0}),
                "AT": make_series({2024: 2400.0}),
                "PT": make_series({2024: 1300.0}),
                "Patr": make_series({2024: 1100.0}),
                "UtilRet": make_series({2024: 600.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        x1 = 400.0 / 2400.0
        x2 = 600.0 / 2400.0
        x3 = 150.0 / 2400.0
        x4 = 1100.0 / 1300.0
        expected = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
        assert ratios["Altman Z''-Score (EM)"][col(2024)] == pytest.approx(expected)

    def test_altman_sin_utilidades_retenidas(self):
        data = build_data(
            balance={
                "AC": make_series({2024: 800.0}),
                "PC": make_series({2024: 400.0}),
                "AT": make_series({2024: 2400.0}),
                "PT": make_series({2024: 1300.0}),
                "Patr": make_series({2024: 1100.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Altman Z''-Score (EM)"].dropna().empty

    def test_altman_pasivos_cero(self):
        data = build_data(
            balance={
                "AC": make_series({2024: 800.0}),
                "PC": make_series({2024: 400.0}),
                "AT": make_series({2024: 2400.0}),
                "PT": make_series({2024: 0.0}),
                "Patr": make_series({2024: 1100.0}),
                "UtilRet": make_series({2024: 600.0}),
            },
            income={"EBIT": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Altman Z''-Score (EM)"].dropna().empty

    def piotroski_data(self):
        return build_data(
            balance={
                "AC": make_series({2023: 700.0, 2024: 800.0}),
                "PC": make_series({2023: 400.0, 2024: 400.0}),
                "AT": make_series({2023: 2000.0, 2024: 2400.0}),
                "PT": make_series({2023: 1100.0, 2024: 1300.0}),
                "OPFNC": make_series({2023: 400.0, 2024: 400.0}),
            },
            income={
                "Ventas": make_series({2023: 1000.0, 2024: 1100.0}),
                "Bruta": make_series({2023: 300.0, 2024: 400.0}),
                "Neta": make_series({2023: 80.0, 2024: 110.0}),
            },
            cash_flow={"CFO": make_series({2023: 120.0, 2024: 150.0})},
        )

    def test_piotroski_sin_dato_de_acciones(self):
        # Señales: ROA>0 (1), CFO>0 (1), ΔROA 0.0458>0.04 (1), CFO 150>Neta 110 (1),
        # apalancamiento 400/2400 < 400/2000 (1), liquidez 2.0>1.75 (1),
        # dilución sin dato (0), margen bruto 0.364>0.30 (1),
        # rotación 1100/2400 < 1000/2000 (0) => 7
        ratios = RatioCalculator(self.piotroski_data()).calculate_quality_scores()
        assert ratios["Piotroski F-Score"][col(2024)] == 7
        # Primer año sin período anterior => sin score
        assert col(2023) not in ratios["Piotroski F-Score"].index

    def test_piotroski_con_acciones_sin_dilucion(self):
        data = self.piotroski_data()
        data["balance"]["Acciones"] = make_series({2023: 100.0, 2024: 100.0})
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Piotroski F-Score"][col(2024)] == 8

    def test_piotroski_con_dilucion(self):
        data = self.piotroski_data()
        data["balance"]["Acciones"] = make_series({2023: 100.0, 2024: 120.0})
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Piotroski F-Score"][col(2024)] == 7

    def test_piotroski_sin_periodo_anterior(self):
        data = build_data(
            balance={"AT": make_series({2024: 2400.0})},
            income={"Neta": make_series({2024: 110.0})},
            cash_flow={"CFO": make_series({2024: 150.0})},
        )
        ratios = RatioCalculator(data).calculate_quality_scores()
        assert ratios["Piotroski F-Score"].dropna().empty


# ---------------------------------------------------------------------------
# Etiquetas trimestrales (YYYYQn), como en archivos consolidados Total
# ---------------------------------------------------------------------------

class TestEtiquetasTrimestrales:
    def make_q_series(self, values: dict) -> pd.Series:
        return pd.Series(values, dtype=float)

    def test_get_column_for_year_prefiere_q4(self):
        calc = RatioCalculator({"years": [2024, 2025]})
        ser = self.make_q_series({"2025Q2": 1.0, "2025Q4": 2.0, "2024Q4": 3.0})
        assert calc.get_column_for_year(ser, 2025) == "2025Q4"
        assert calc.get_column_for_year(ser, 2024) == "2024Q4"
        assert calc.get_column_for_year(ser, 2023) is None

    def test_yoy_y_dupont_con_labels_trimestrales(self):
        data = {
            "balance": {
                "AT": self.make_q_series({"2024Q4": 2000.0, "2025Q4": 2400.0}),
                "Patr": self.make_q_series({"2024Q4": 900.0, "2025Q4": 1100.0}),
            },
            "income": {
                "Ventas": self.make_q_series({"2024Q4": 1000.0, "2025Q4": 1100.0}),
                "Neta": self.make_q_series({"2024Q4": 80.0, "2025Q4": 110.0}),
            },
            "cash_flow": {},
            "years": [2024, 2025],
        }
        calc = RatioCalculator(data)
        growth = calc.calculate_growth_ratios()
        assert growth["Variación Ingresos (YoY)"]["2025Q4"] == pytest.approx(0.10)
        dupont = calc.calculate_dupont_ratios()
        assert dupont["ROE (DuPont)"]["2025Q4"] == pytest.approx(0.11)


# ---------------------------------------------------------------------------
# Integración en calculate_all_ratios
# ---------------------------------------------------------------------------

class TestIntegracion:
    def test_grupos_nuevos_presentes(self):
        data = build_data(income={"Ventas": make_series({2024: 1000.0})})
        all_ratios = RatioCalculator(data).calculate_all_ratios()
        for group in ("CRECIMIENTO", "DUPONT", "CALIDAD Y SCORES"):
            assert group in all_ratios
        assert "Deuda Financiera Neta / EBITDA" in all_ratios["SOLVENCIA Y ESTRUCTURA"]

    def test_datos_vacios_no_fallan(self):
        all_ratios = RatioCalculator({"years": []}).calculate_all_ratios()
        assert set(all_ratios) >= {"CRECIMIENTO", "DUPONT", "CALIDAD Y SCORES"}
        for group in all_ratios.values():
            for series in group.values():
                assert series.dropna().empty
