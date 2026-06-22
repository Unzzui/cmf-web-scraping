"""
Cash Flow Mixin
===============

Provides methods for building cash flow ratio formulas.
"""

import re
from typing import List, Optional, Tuple


class CashFlowMixin:
    """Mixin providing cash flow ratio formula builders."""

    def build_cash_flow_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """Construye fórmulas para ratios de flujos y adicionales."""
        formulas = []

        # Conversión de caja (CFO_TTM/Utilidad Neta_TTM en trimestral)
        def f_conv_caja():
            m = {}
            labels_cfs = []
            hdr = self.HDR_CFS
            for c in range(2, self.sh_cfs.max_column + 1):
                v = self.sh_cfs.cell(row=hdr, column=c).value
                if isinstance(v, str):
                    labels_cfs.append(v.strip().split("\n", 1)[0])
            is_quarter = any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_cfs)
            if is_quarter:
                for lb in labels_cfs:
                    if not re.match(r"^\d{4}Q[1-4]$", lb):
                        continue
                    cfo = self.ttm_ref_cfs("CFO", lb)
                    net = self.ttm_ref_pl("Neta", lb)
                    if cfo and net:
                        m[lb] = f"IFERROR({cfo}/{net},\"N/A\")"
                # duplicar claves anuales (YYYY)
                for y in self.years:
                    if str(y) in m:
                        continue
                    cfo_y = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CFO"]
                    ) if self.rows_cfs.get("CFO") else None
                    net_y = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Neta"]
                    ) if self.rows_pl.get("Neta") else None
                    if cfo_y and net_y:
                        m[str(y)] = f"IFERROR({cfo_y}/{net_y},\"N/A\")"
            else:
                for y in self.years:
                    cfo = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CFO"]
                    )
                    net = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Neta"]
                    )
                    if cfo and net:
                        m[str(y)] = f"IFERROR({cfo}/{net},\"N/A\")"
            return m

        formulas.append(("Conversión de caja (CFO/Utilidad Neta)", "ratio", f_conv_caja,
                        "Flujo Operativo / Utilidad Neta"))

        # Free Cash Flow (TTM en trimestral)
        def f_fcf():
            m = {}
            labels_cfs = []
            hdr = self.HDR_CFS
            for c in range(2, self.sh_cfs.max_column + 1):
                v = self.sh_cfs.cell(row=hdr, column=c).value
                if isinstance(v, str):
                    labels_cfs.append(v.strip().split("\n", 1)[0])
            is_quarter = any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_cfs)
            if is_quarter:
                for lb in labels_cfs:
                    if not re.match(r"^\d{4}Q[1-4]$", lb):
                        continue
                    cfo = self.ttm_ref_cfs("CFO", lb)
                    capex = self.ttm_ref_cfs("CapexBuy", lb) if self.rows_cfs.get("CapexBuy") else None
                    if cfo:
                        if capex:
                            m[lb] = f"IFERROR({cfo}-ABS({capex}),\"N/A\")"
                        else:
                            m[lb] = f"IFERROR({cfo},\"\")"
                # duplicar claves anuales (YYYY)
                for y in self.years:
                    if str(y) in m:
                        continue
                    cfo_y = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CFO"]
                    ) if self.rows_cfs.get("CFO") else None
                    capex_y = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CapexBuy"]
                    ) if self.rows_cfs.get("CapexBuy") else None
                    if cfo_y:
                        if capex_y:
                            m[str(y)] = f"IFERROR({cfo_y}-ABS({capex_y}),\"N/A\")"
                        else:
                            m[str(y)] = f"IFERROR({cfo_y},\"\")"
            else:
                for y in self.years:
                    cfo = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CFO"]
                    )
                    capex = self.create_cell_reference(
                        self.sh_cfs.title,
                        self.find_year_column(self.sh_cfs, y),
                        self.rows_cfs["CapexBuy"]
                    ) if self.rows_cfs["CapexBuy"] else None
                    if cfo:
                        if capex:
                            m[str(y)] = f"IFERROR({cfo}-ABS({capex}),\"N/A\")"
                        else:
                            m[str(y)] = f"IFERROR({cfo},\"\")"
            return m

        formulas.append(("Free Cash Flow (CFO - CAPEX)", "number", f_fcf,
                        "CFO - CAPEX (Compras PPE)"))

        # AC / AT
        def f_ac_at():
            m = {}
            for y in self.years:
                ac = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AC"]
                )
                at = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["AT"]
                )
                if ac and at:
                    m[str(y)] = f"IFERROR({ac}/{at},\"N/A\")"
            return m

        formulas.append(("AC / AT", "pct", f_ac_at,
                        "Activo Corriente / Activo Total"))

        # PC / PT
        def f_pc_pt():
            m = {}
            for y in self.years:
                pc = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PC"]
                )
                pt = self.create_cell_reference(
                    self.sh_bal.title,
                    self.find_year_column(self.sh_bal, y),
                    self.rows_bal["PT"]
                )
                if pc and pt:
                    m[str(y)] = f"IFERROR({pc}/{pt},\"N/A\")"
            return m

        formulas.append(("PC / PT", "pct", f_pc_pt,
                        "Pasivo Corriente / Pasivo Total"))

        return formulas
