"""
Solvency Mixin
==============

Provides methods for building solvency and capital structure ratio formulas.
"""

import re
from typing import List, Optional, Tuple


class SolvencyMixin:
    """Mixin providing solvency ratio formula builders."""

    def build_solvency_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """Construye fórmulas para ratios de solvencia."""
        formulas = []

        # Endeudamiento (D/E)
        def f_de():
            m = {}
            for y in self.years:
                pt = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PT"]
                )
                patr = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["Patr"]
                )
                if pt and patr:
                    m[str(y)] = f"IF({patr}=0,\"N/A\",IFERROR({pt}/{patr},\"N/A\"))"
            return m

        formulas.append(("Endeudamiento (D/E)", "ratio", f_de,
                        "Deuda Total / Patrimonio"))

        # Apalancamiento (D/A)
        def f_da():
            m = {}
            for y in self.years:
                pt = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PT"]
                )
                at = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AT"]
                )
                if pt and at:
                    m[str(y)] = f"IFERROR({pt}/{at},\"N/A\")"
            return m

        formulas.append(("Apalancamiento (D/A)", "ratio", f_da,
                        "Deuda Total / Activos Totales"))

        # Cobertura de Intereses (TTM si hay quarters)
        def f_cover():
            m = {}
            labels_pl = []
            hdr = self.HDR_PL
            for c in range(2, self.sh_pl.max_column + 1):
                v = self.sh_pl.cell(row=hdr, column=c).value
                if isinstance(v, str):
                    labels_pl.append(v.strip().split("\n", 1)[0])
            is_quarter = any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_pl)
            if is_quarter:
                for lb in labels_pl:
                    if not re.match(r"^\d{4}Q[1-4]$", lb):
                        continue
                    ebit = self.ttm_ref_pl("EBIT", lb)
                    interes = self.ttm_ref_pl("Interes", lb)
                    if ebit and interes:
                        m[lb] = f"IFERROR({ebit}/ABS({interes}),\"N/A\")"
                # Duplicar claves anuales (YYYY) usando referencias anuales
                for y in self.years:
                    if str(y) in m:
                        continue
                    ebit_a = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["EBIT"]
                    )
                    interes_a = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Interes"]
                    )
                    if ebit_a and interes_a:
                        m[str(y)] = f"IFERROR({ebit_a}/ABS({interes_a}),\"N/A\")"
            else:
                for y in self.years:
                    ebit = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["EBIT"]
                    )
                    interes = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Interes"]
                    )
                    if ebit and interes:
                        m[str(y)] = f"IFERROR({ebit}/ABS({interes}),\"N/A\")"
            return m

        formulas.append(("Cobertura de Intereses", "ratio", f_cover,
                        "EBIT / |Gastos por Intereses|"))

        # Deuda / EBITDA (EBITDA TTM si hay quarters)
        def f_deuda_ebitda():
            m = {}
            labels_pl = []
            hdr = self.HDR_PL
            for c in range(2, self.sh_pl.max_column + 1):
                v = self.sh_pl.cell(row=hdr, column=c).value
                if isinstance(v, str):
                    labels_pl.append(v.strip().split("\n", 1)[0])
            is_quarter = any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_pl)
            if is_quarter:
                for lb in labels_pl:
                    if not re.match(r"^\d{4}Q[1-4]$", lb):
                        continue
                    # Net Debt = (DeudaFinCorr + DeudaFinNC + ArrCorr + ArrNC) - Efectivo
                    dfc = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("DeudaFinCorr"), lb) if self.rows_bal.get("DeudaFinCorr") else None
                    dfnc = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("DeudaFinNC"), lb) if self.rows_bal.get("DeudaFinNC") else None
                    arrc = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("ArrCorr"), lb) if self.rows_bal.get("ArrCorr") else None
                    arrn = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("ArrNC"), lb) if self.rows_bal.get("ArrNC") else None
                    cash = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("Efec"), lb) if self.rows_bal.get("Efec") else None
                    net_debt_parts = [p for p in [dfc, dfnc, arrc, arrn] if p]
                    if net_debt_parts:
                        net_debt = "+".join(net_debt_parts)
                        if cash:
                            net_debt = f"({net_debt})-IFERROR({cash},0)"
                    else:
                        net_debt = None
                    ebit = self.ttm_ref_pl("EBIT", lb)
                    da_ttm = self._build_da_ttm(lb)
                    if net_debt and ebit:
                        if da_ttm:
                            ebitda = f"({ebit}+({da_ttm}))"
                        else:
                            ebitda = f"({ebit})"
                        # Parentizar el numerador completo para evitar (Caja/EBITDA)
                        m[lb] = f"IFERROR(({net_debt})/{ebitda},\"N/A\")"
            else:
                for y in self.years:
                    dfc = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal.get("DeudaFinCorr")
                    ) if self.rows_bal.get("DeudaFinCorr") else None
                    dfnc = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal.get("DeudaFinNC")
                    ) if self.rows_bal.get("DeudaFinNC") else None
                    arrc = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal.get("ArrCorr")
                    ) if self.rows_bal.get("ArrCorr") else None
                    arrn = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal.get("ArrNC")
                    ) if self.rows_bal.get("ArrNC") else None
                    cash = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal.get("Efec")
                    ) if self.rows_bal.get("Efec") else None
                    net_debt_parts = [p for p in [dfc, dfnc, arrc, arrn] if p]
                    net_debt = "+".join(net_debt_parts) if net_debt_parts else None
                    if net_debt and cash:
                        net_debt = f"({net_debt})-IFERROR({cash},0)"
                    ebit = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["EBIT"]
                    )
                    da = self._build_da_annual(y)
                    if net_debt and ebit:
                        if da:
                            ebitda = f"({ebit}+({da}))"
                        else:
                            ebitda = f"({ebit})"
                        # Parentizar el numerador completo para evitar (Caja/EBITDA)
                        m[str(y)] = f"IFERROR(({net_debt})/{ebitda},\"N/A\")"
            return m

        formulas.append(("Deuda / EBITDA", "ratio", f_deuda_ebitda,
                        "Deuda Total / (EBIT + Depreciación + Amortización)"))

        # Autonomía Financiera
        def f_autonomia():
            m = {}
            for y in self.years:
                patr = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PatrTotal"]
                )
                at = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AT"]
                )
                if patr and at:
                    m[str(y)] = f"IFERROR({patr}/{at},\"N/A\")"
            return m

        formulas.append(("Autonomía Financiera", "pct", f_autonomia,
                        "Patrimonio Total / Activo Total"))

        return formulas
