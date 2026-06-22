"""
Liquidity Mixin
===============

Provides methods for building liquidity ratio formulas.
"""

from typing import List, Tuple


class LiquidityMixin:
    """Mixin providing liquidity ratio formula builders."""

    def build_liquidity_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """
        Construye fórmulas para ratios de liquidez.

        Returns:
            Lista de tuplas (nombre, tipo, función_fórmula, descripción)
        """
        formulas = []

        # Liquidez Corriente = AC/PC
        def f_liq_corr():
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
                if ac and pc:
                    m[str(y)] = f"IFERROR({ac}/{pc},\"N/A\")"
            return m

        formulas.append(("Liquidez Corriente", "ratio", f_liq_corr,
                        "Activo Corriente / Pasivo Corriente"))

        # Prueba Ácida = (AC - Inventarios) / PC
        def f_prueba_acida():
            m = {}
            for y in self.years:
                ac = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AC"]
                )
                inv = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["Inv"]
                )
                pc = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PC"]
                )
                if ac and pc:
                    term_inv = inv if inv else "0"
                    m[str(y)] = f"IFERROR(({ac}-{term_inv})/{pc},\"N/A\")"
            return m

        formulas.append(("Prueba Ácida", "ratio", f_prueba_acida,
                        "(Activo Corriente - Inventarios) / Pasivo Corriente"))

        # Cash Ratio = Efectivo / PC
        def f_cash_ratio():
            m = {}
            for y in self.years:
                ef = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["Efec"]
                )
                pc = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PC"]
                )
                if ef and pc:
                    m[str(y)] = f"IFERROR({ef}/{pc},\"N/A\")"
            return m

        formulas.append(("Cash Ratio", "ratio", f_cash_ratio,
                        "Efectivo y Equivalentes / Pasivo Corriente"))

        # Capital de Trabajo = AC - PC
        def f_cap_trabajo():
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
                if ac and pc:
                    m[str(y)] = f"IFERROR({ac}-{pc},\"\")"
            return m

        formulas.append(("Capital de Trabajo", "number", f_cap_trabajo,
                        "Activo Corriente - Pasivo Corriente"))

        return formulas
