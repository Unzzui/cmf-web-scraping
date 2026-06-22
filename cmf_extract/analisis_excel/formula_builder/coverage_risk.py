"""
Coverage & Risk Mixin
=====================

Provides methods for building coverage and risk indicator formulas.
"""

import re
from typing import List, Optional, Tuple


class CoverageRiskMixin:
    """Mixin providing coverage and risk formula builders."""

    def build_coverage_risk_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """Construye fórmulas para indicadores de cobertura y riesgo."""
        formulas = []

        # Cobertura de Servicio de Deuda (DSCR) = CFO_TTM / (Intereses_TTM + Amortización Principal_TTM)
        def f_debt_service():
            m = {}
            labels = []
            hdr_pl = self.HDR_PL
            for c in range(2, self.sh_pl.max_column + 1):
                v = self.sh_pl.cell(row=hdr_pl, column=c).value
                if isinstance(v, str):
                    labels.append(v.strip().split("\n", 1)[0])
            is_quarter = any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels)
            if is_quarter:
                for lb in labels:
                    if not re.match(r"^\d{4}Q[1-4]$", lb):
                        continue
                    cfo = self.ttm_ref_cfs("CFO", lb)
                    interes = self.ttm_ref_pl("Interes", lb)
                    principal = self.ttm_ref_cfs("ReembPrest", lb) if self.rows_cfs.get("ReembPrest") else None
                    if cfo and interes:
                        service = f"(ABS({interes})" + (f"+IFERROR(ABS({principal}),0)" if principal else "") + ")"
                        m[lb] = f"IFERROR({cfo}/{service},\"N/A\")"
                # duplicar claves anuales (YYYY)
                for y in self.years:
                    if str(y) in m:
                        continue
                    cfo_y = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs.get("CFO")
                    ) if self.rows_cfs.get("CFO") else None
                    interes_y = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl.get("Interes")
                    ) if self.rows_pl.get("Interes") else None
                    principal_y = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs.get("ReembPrest")
                    ) if self.rows_cfs.get("ReembPrest") else None
                    if cfo_y and interes_y:
                        service_y = f"(ABS({interes_y})" + (f"+IFERROR(ABS({principal_y}),0)" if principal_y else "") + ")"
                        m[str(y)] = f"IFERROR({cfo_y}/{service_y},\"N/A\")"
            else:
                for y in self.years:
                    cfo = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs.get("CFO")
                    ) if self.rows_cfs.get("CFO") else None
                    interes = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl.get("Interes")
                    ) if self.rows_pl.get("Interes") else None
                    principal = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs.get("ReembPrest")
                    ) if self.rows_cfs.get("ReembPrest") else None
                    if cfo and interes:
                        service = f"(ABS({interes})" + (f"+IFERROR(ABS({principal}),0)" if principal else "") + ")"
                        m[str(y)] = f"IFERROR({cfo}/{service},\"N/A\")"
            return m

        formulas.append(("Cobertura Servicio Deuda", "ratio", f_debt_service,
                        "CFO / (Intereses + Amortización Principal)"))

        # Cobertura de Gastos Fijos = (EBIT + Gastos Fijos) / Gastos Fijos
        # Gastos Fijos ≈ Gastos Admin + Costos Distribución + Gastos Financieros
        def f_fixed_coverage():
            m = {}
            for y in self.years:
                ebit = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["EBIT"]
                )
                gast_admin = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["GastAdmin"]
                ) if self.rows_pl["GastAdmin"] else None
                cost_distr = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["CostDistrib"]
                ) if self.rows_pl["CostDistrib"] else None
                interes = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["Interes"]
                )

                if ebit:
                    # Gastos fijos estimados
                    gastos_fijos = "("
                    componentes = []
                    if gast_admin:
                        componentes.append(f"IFERROR(ABS({gast_admin}),0)")
                    if cost_distr:
                        componentes.append(f"IFERROR(ABS({cost_distr}),0)")
                    if interes:
                        componentes.append(f"IFERROR(ABS({interes}),0)")

                    if componentes:
                        gastos_fijos += "+".join(componentes) + ")"

                        m[str(y)] = f"IFERROR(({ebit}+{gastos_fijos})/{gastos_fijos},\"N/A\")"
            return m

        formulas.append(("Cobertura Gastos Fijos", "ratio", f_fixed_coverage,
                        "(EBIT + Gastos Fijos) / Gastos Fijos"))

        # Altman Z-Score = 1.2*A + 1.4*B + 3.3*C + 0.6*D + 1.0*E
        # A = Capital Trabajo / AT
        # B = Utilidades Retenidas / AT
        # C = EBIT / AT
        # D = Valor Mercado Patrimonio / PT (usaremos valor contable)
        # E = Ventas / AT
        def f_altman_zscore():
            m = {}
            for y in self.years:
                ac = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AC"]
                )
                pc = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PC"]
                )
                gan_acum = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["GanAcum"]
                ) if self.rows_bal["GanAcum"] else None
                ebit = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["EBIT"]
                )
                patr = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["Patr"]
                )
                pt = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PT"]
                )
                ventas = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["Ventas"]
                )
                at = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AT"]
                )

                if ac and pc and ebit and patr and pt and ventas and at:
                    # A = (AC - PC) / AT
                    comp_a = f"1.2*(({ac}-{pc})/{at})"

                    # B = Utilidades Retenidas / AT
                    comp_b = f"1.4*({gan_acum}/{at})" if gan_acum else "0"

                    # C = EBIT / AT
                    comp_c = f"3.3*({ebit}/{at})"

                    # D = Patrimonio / Pasivos (valor contable)
                    comp_d = f"0.6*({patr}/{pt})"

                    # E = Ventas / AT
                    comp_e = f"1.0*({ventas}/{at})"

                    z_score = f"IFERROR({comp_a}+{comp_b}+{comp_c}+{comp_d}+{comp_e},\"N/A\")"
                    m[str(y)] = z_score
            return m

        formulas.append(("Altman Z-Score", "ratio", f_altman_zscore,
                        "1.2×(CT/AT) + 1.4×(RE/AT) + 3.3×(EBIT/AT) + 0.6×(E/D) + 1.0×(S/AT)"))

        return formulas
