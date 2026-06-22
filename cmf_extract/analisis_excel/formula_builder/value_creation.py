"""
Value Creation Mixin
====================

Provides methods for building value creation indicator formulas.
"""

from typing import List, Optional, Tuple


class ValueCreationMixin:
    """Mixin providing value creation formula builders."""

    def build_value_creation_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """Construye fórmulas para indicadores de creación de valor."""
        formulas = []

        # ROA (ya existe en rentabilidad, pero lo incluimos aquí también)
        def f_roa_value():
            m = {}
            for y in self.years:
                net = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["Neta"]
                )
                at_avg = self.create_average_reference(self.sh_bal, self.rows_bal["AT"], y)
                if net and at_avg:
                    m[str(y)] = f"IFERROR({net}/{at_avg},\"N/A\")"
            return m

        formulas.append(("ROA", "pct", f_roa_value,
                        "Utilidad Neta / Activos Totales Promedio"))

        # ROIC = NOPAT / Capital Invertido
        # NOPAT ≈ EBIT * (1 - Tax Rate)
        # Capital Invertido ≈ AT - Pasivos Sin Costo (efectivo, cuentas por pagar operativas)
        def f_roic():
            m = {}
            for y in self.years:
                ebit = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["EBIT"]
                )
                antes_imp = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["AntesImp"]
                )
                imp_ganan = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["ImpGanan"]
                )
                at_avg = self.create_average_reference(self.sh_bal, self.rows_bal["AT"], y)
                efec_avg = self.create_average_reference(self.sh_bal, self.rows_bal["Efec"], y)
                cxp_avg = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)

                if ebit and antes_imp and imp_ganan and at_avg:
                    # Tax rate = Impuestos / EBT
                    tax_rate = f"IFERROR(ABS({imp_ganan})/{antes_imp},0.25)"
                    nopat = f"({ebit}*(1-{tax_rate}))"

                    # Capital Invertido (simplificado)
                    cap_inv = f"({at_avg}"
                    if efec_avg:
                        cap_inv += f"-{efec_avg}"
                    if cxp_avg:
                        cap_inv += f"-{cxp_avg}"
                    cap_inv += ")"

                    m[str(y)] = f"IFERROR({nopat}/{cap_inv},\"N/A\")"
            return m

        formulas.append(("ROIC", "pct", f_roic,
                        "NOPAT / Capital Invertido"))

        # EVA = NOPAT - (Capital Invertido * WACC)
        # Asumimos WACC del 10% como proxy
        def f_eva():
            m = {}
            for y in self.years:
                ebit = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["EBIT"]
                )
                antes_imp = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["AntesImp"]
                )
                imp_ganan = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["ImpGanan"]
                )
                at_avg = self.create_average_reference(self.sh_bal, self.rows_bal["AT"], y)
                efec_avg = self.create_average_reference(self.sh_bal, self.rows_bal["Efec"], y)
                cxp_avg = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)

                if ebit and antes_imp and imp_ganan and at_avg:
                    # Tax rate
                    tax_rate = f"IFERROR(ABS({imp_ganan})/{antes_imp},0.25)"
                    nopat = f"({ebit}*(1-{tax_rate}))"

                    # Capital Invertido
                    cap_inv = f"({at_avg}"
                    if efec_avg:
                        cap_inv += f"-{efec_avg}"
                    if cxp_avg:
                        cap_inv += f"-{cxp_avg}"
                    cap_inv += ")"

                    # EVA = NOPAT - (Cap_Inv * 10%)
                    m[str(y)] = f"IFERROR({nopat}-({cap_inv}*0.10),\"\")"
            return m

        formulas.append(("EVA (WACC=10%)", "number", f_eva,
                        "NOPAT - (Capital Invertido × WACC estimado)"))

        # Spread = ROIC - WACC (asumiendo WACC 10%)
        def f_spread():
            m = {}
            roic_map = f_roic()
            for y in self.years:
                roic_formula = roic_map.get(str(y))
                if roic_formula:
                    inner = self._unwrap_iferror(roic_formula)
                    m[str(y)] = f"IFERROR(({inner})-0.10,\"\")"
            return m

        formulas.append(("Spread (ROIC - WACC)", "pct", f_spread,
                        "ROIC - WACC estimado (10%)"))

        return formulas
