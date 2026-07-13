"""
Efficiency Mixin
================

Provides methods for building operational efficiency ratio formulas.
"""

import re
from typing import List, Optional, Tuple


class EfficiencyMixin:
    """Mixin providing efficiency ratio formula builders."""

    def build_efficiency_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """Construye fórmulas para ratios de eficiencia operativa."""
        formulas = []

        # Rotación de Activos (Ventas TTM / Activos promedio trimestral)
        def f_rot_act():
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
                    ven = self.ttm_ref_pl("Ventas", lb)
                    at_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["AT"], lb)
                    lb_prev4 = self._previous_year_same_quarter_label(lb)
                    at_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["AT"], lb_prev4) if lb_prev4 else None
                    at_avg = f"AVERAGE({at_now},{at_prev4})" if at_now and at_prev4 else (at_now or at_prev4)
                    if ven and at_avg:
                        m[lb] = f"IFERROR({ven}/{at_avg},\"N/A\")"
                for y in self.years:
                    if str(y) in m:
                        continue
                    ven_a = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Ventas"]
                    )
                    at_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["AT"], y)
                    if ven_a and at_avg_a:
                        m[str(y)] = f"IFERROR({ven_a}/{at_avg_a},\"N/A\")"
            else:
                for y in self.years:
                    ven = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Ventas"]
                    )
                    at_avg = self.create_average_reference(self.sh_bal, self.rows_bal["AT"], y)
                    if ven and at_avg:
                        m[str(y)] = f"IFERROR({ven}/{at_avg},\"N/A\")"
            return m

        formulas.append(("Rotación de Activos", "ratio", f_rot_act,
                        "Ventas / Activos Promedio"))

        # Rotación de Activos Fijos
        def f_rot_act_fijos():
            m = {}
            for y in self.years:
                ven = self.create_cell_reference(
                    self.sh_pl.title,
                    self.find_year_column(self.sh_pl, y),
                    self.rows_pl["Ventas"]
                )
                ppe_avg = self.create_average_reference(self.sh_bal, self.rows_bal["PPE"], y)
                if ven and ppe_avg:
                    m[str(y)] = f"IFERROR({ven}/{ppe_avg},\"N/A\")"
            return m

        formulas.append(("Rotación de Activos Fijos", "ratio", f_rot_act_fijos,
                        "Ventas / PPE Promedio"))

        # Rotación de Inventarios (COGS TTM / Inventario promedio) y Días de Inventario
        def f_rot_inv_y_dias():
            m_rot = {}
            m_dias = {}
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
                    cogs = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["COGS"], lb) if self.rows_pl.get("COGS") else None
                    if not cogs:
                        cogs = self._cogs_ref_by_label(lb)
                    inv_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], lb)
                    lb_prev4 = self._previous_year_same_quarter_label(lb)
                    inv_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], lb_prev4) if lb_prev4 else None
                    inv_avg = f"AVERAGE({inv_now},{inv_prev4})" if inv_now and inv_prev4 else (inv_now or inv_prev4)
                    if cogs and inv_avg:
                        # La rotación va en base anual (numerador YTD anualizado) para que sea
                        # comparable entre trimestres. Los días se escriben sobre el YTD sin anualizar
                        # y los días acumulados del período: es la forma legible del mismo cociente y
                        # cumple exactamente Días = DíasAño / Rotación.
                        m_rot[lb] = f"IFERROR({self._annualized(cogs, lb)}/{inv_avg},\"N/A\")"
                        m_dias[lb] = f"IFERROR({self._get_period_days(lb)}/(IFERROR({cogs}/{inv_avg},\"N/A\")),\"N/A\")"
                # duplicar claves anuales (YYYY) usando referencias anuales
                for y in self.years:
                    if str(y) in m_rot:
                        continue
                    cogs_y = None
                    if self.rows_pl.get("COGS"):
                        cogs_y = self.create_cell_reference(
                            self.sh_pl.title,
                            self.find_year_column(self.sh_pl, y),
                            self.rows_pl["COGS"]
                        )
                    if not cogs_y:
                        cogs_y = self._cogs_ref_by_year(y)
                    inv_avg_y = self.create_average_reference(self.sh_bal, self.rows_bal["Inv"], y)
                    if cogs_y and inv_avg_y:
                        rot_expr_y = f"IFERROR({cogs_y}/{inv_avg_y},\"N/A\")"
                        m_rot[str(y)] = rot_expr_y
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr_y}),\"N/A\")"
            else:
                for y in self.years:
                    cogs = None
                    if self.rows_pl.get("COGS"):
                        cogs = self.create_cell_reference(
                            self.sh_pl.title,
                            self.find_year_column(self.sh_pl, y),
                            self.rows_pl["COGS"]
                        )
                    if not cogs:
                        cogs = self._cogs_ref_by_year(y)
                    inv_now = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y),
                        self.rows_bal["Inv"]
                    )
                    inv_prev = self.create_cell_reference(
                        self.sh_bal.title,
                        self.find_year_column(self.sh_bal, y-1),
                        self.rows_bal["Inv"]
                    )
                    inv_avg = None
                    if inv_now and inv_prev:
                        inv_avg = f"AVERAGE({inv_now},{inv_prev})"
                    elif inv_now:
                        inv_avg = inv_now
                    elif inv_prev:
                        inv_avg = inv_prev
                    if cogs and inv_avg:
                        rot_expr = f"IFERROR({cogs}/{inv_avg},\"N/A\")"
                        m_rot[str(y)] = rot_expr
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr}),\"N/A\")"
            return m_rot, m_dias

        rot_inv, dias_inv = f_rot_inv_y_dias()

        formulas.append(("Rotación de Inventarios", "ratio", lambda: rot_inv,
                        "Costo de Ventas / Inventario Promedio"))
        formulas.append(("Días de Inventario", "days", lambda: dias_inv,
                        "Días del período / Rotación de Inventarios"))

        # Rotación de Cuentas por Cobrar y Período Promedio de Cobro
        def f_rot_cxc_y_dias():
            m_rot = {}
            m_dias = {}
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
                    ven = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], lb)
                    cxc_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxC"], lb)
                    lb_prev4 = self._previous_year_same_quarter_label(lb)
                    cxc_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxC"], lb_prev4) if lb_prev4 else None
                    cxc_avg = f"AVERAGE({cxc_now},{cxc_prev4})" if cxc_now and cxc_prev4 else (cxc_now or cxc_prev4)
                    if ven and cxc_avg:
                        m_rot[lb] = f"IFERROR({self._annualized(ven, lb)}/{cxc_avg},\"N/A\")"
                        m_dias[lb] = f"IFERROR({self._get_period_days(lb)}/(IFERROR({ven}/{cxc_avg},\"N/A\")),\"N/A\")"
                # duplicar claves anuales (YYYY)
                for y in self.years:
                    if str(y) in m_rot:
                        continue
                    ven_y = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Ventas"]
                    )
                    cxc_avg_y = self.create_average_reference(self.sh_bal, self.rows_bal["CxC"], y)
                    if ven_y and cxc_avg_y:
                        rot_expr_y = f"IFERROR({ven_y}/{cxc_avg_y},\"N/A\")"
                        m_rot[str(y)] = rot_expr_y
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr_y}),\"N/A\")"
            else:
                for y in self.years:
                    ven = self.create_cell_reference(
                        self.sh_pl.title,
                        self.find_year_column(self.sh_pl, y),
                        self.rows_pl["Ventas"]
                    )
                    cxc_avg = self.create_average_reference(self.sh_bal, self.rows_bal["CxC"], y)
                    if ven and cxc_avg:
                        rot_expr = f"IFERROR({ven}/{cxc_avg},\"N/A\")"
                        m_rot[str(y)] = rot_expr
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr}),\"N/A\")"
            return m_rot, m_dias

        rot_cxc, dias_cobro = f_rot_cxc_y_dias()

        formulas.append(("Rotación de Cuentas por Cobrar", "ratio", lambda: rot_cxc,
                        "Ventas / Cuentas por Cobrar Promedio"))
        formulas.append(("Período Promedio de Cobro", "days", lambda: dias_cobro,
                        "Días del período / Rotación de CxC"))

        # Rotación de Cuentas por Pagar y Período Promedio de Pago
        def f_rot_cxp_y_dias():
            m_rot = {}
            m_dias = {}
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
                    cogs = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["COGS"], lb) if self.rows_pl.get("COGS") else None
                    if not cogs:
                        cogs = self._cogs_ref_by_label(lb)

                    # Si estamos usando vista por naturaleza ([320000]), usar compras basadas en naturaleza
                    if self._is_using_nature_based_income_statement():
                        # Para Período Promedio de Pago, usar referencia directa al trimestre, no TTM
                        # Fórmula: (RawMat - WorkCap) del trimestre específico
                        raw_mat = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("RawMat"), lb)
                        work_cap = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("WorkCap"), lb)

                        comp_parts = []
                        if raw_mat:
                            comp_parts.append(f"IFERROR({raw_mat},0)")
                        if work_cap:
                            comp_parts.append(f"-IFERROR({work_cap},0)")

                        comp = f"({'+'.join(comp_parts)})" if comp_parts else None

                        # Para natura-based, necesitamos CxP promedio para calcular rotación
                        cxp_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb)
                        lb_prev4 = self._previous_year_same_quarter_label(lb)
                        cxp_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb_prev4) if lb_prev4 else None
                        cxp_avg = f"AVERAGE({cxp_now},{cxp_prev4})" if cxp_now and cxp_prev4 else (cxp_now or cxp_prev4)
                    else:
                        # Método estándar: COGS + cambio en inventarios
                        inv_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], lb)
                        begin_label = self._year_start_quarter_label(lb)
                        inv_begin = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], begin_label) if begin_label else None
                        comp = f"({cogs}+({inv_now}-{inv_begin}))" if (cogs and inv_now and inv_begin) else (cogs if cogs else None)
                        cxp_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb)
                        lb_prev4 = self._previous_year_same_quarter_label(lb)
                        cxp_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb_prev4) if lb_prev4 else None
                        cxp_avg = f"AVERAGE({cxp_now},{cxp_prev4})" if cxp_now and cxp_prev4 else (cxp_now or cxp_prev4)
                    if comp and cxp_avg:
                        m_rot[lb] = f"IFERROR({self._annualized(comp, lb)}/{cxp_avg},\"N/A\")"
                        m_dias[lb] = f"IFERROR({self._get_period_days(lb)}/(IFERROR({comp}/{cxp_avg},\"N/A\")),\"N/A\")"
                # duplicar claves anuales (YYYY)
                for y in self.years:
                    if str(y) in m_rot:
                        continue
                    cogs_y = None
                    if self.rows_pl.get("COGS"):
                        cogs_y = self.create_cell_reference(
                            self.sh_pl.title,
                            self.find_year_column(self.sh_pl, y),
                            self.rows_pl["COGS"]
                        )
                    if not cogs_y:
                        cogs_y = self._cogs_ref_by_year(y)

                    # Si estamos usando vista por naturaleza ([320000]), usar compras basadas en naturaleza
                    if self._is_using_nature_based_income_statement():
                        # Para Período Promedio de Pago anual, usar referencia directa, no anualizada
                        # Fórmula: (RawMat - WorkCap) del año específico
                        col = self.find_year_column(self.sh_pl, y)
                        raw_mat_y = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat"))
                        work_cap_y = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap"))

                        comp_parts_y = []
                        if raw_mat_y:
                            comp_parts_y.append(f"IFERROR({raw_mat_y},0)")
                        if work_cap_y:
                            comp_parts_y.append(f"-IFERROR({work_cap_y},0)")

                        comp_y = f"({'+'.join(comp_parts_y)})" if comp_parts_y else None
                        inv_now_y = None  # No se usa en vista por naturaleza
                        inv_prev_y = None  # No se usa en vista por naturaleza
                    else:
                        # Método estándar: COGS + cambio en inventarios
                        inv_now_y = self.create_cell_reference(
                            self.sh_bal.title,
                            self.find_year_column(self.sh_bal, y),
                            self.rows_bal["Inv"]
                        )
                        inv_prev_y = self.create_cell_reference(
                            self.sh_bal.title,
                            self.find_year_column(self.sh_bal, y-1),
                            self.rows_bal["Inv"]
                        )
                        comp_y = None
                    if cogs_y and inv_now_y and inv_prev_y:
                        comp_y = f"({cogs_y}+({inv_now_y}-{inv_prev_y}))"
                    cxp_avg_y = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)
                    if comp_y and cxp_avg_y:
                        rot_expr_y = f"IFERROR({comp_y}/{cxp_avg_y},\"N/A\")"
                        m_rot[str(y)] = rot_expr_y
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr_y}),\"N/A\")"
            else:
                for y in self.years:
                    cogs = None
                    if self.rows_pl.get("COGS"):
                        cogs = self.create_cell_reference(
                            self.sh_pl.title,
                            self.find_year_column(self.sh_pl, y),
                            self.rows_pl["COGS"]
                        )
                    if not cogs:
                        cogs = self._cogs_ref_by_year(y)

                    # Si estamos usando vista por naturaleza ([320000]), usar compras basadas en naturaleza
                    if self._is_using_nature_based_income_statement():
                        # Para Período Promedio de Pago, usar referencia directa al año
                        # Fórmula: (RawMat - WorkCap) del año específico
                        col = self.find_year_column(self.sh_pl, y)
                        raw_mat = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat"))
                        work_cap = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap"))

                        comp_parts = []
                        if raw_mat:
                            comp_parts.append(f"IFERROR({raw_mat},0)")
                        if work_cap:
                            comp_parts.append(f"-IFERROR({work_cap},0)")

                        comp = f"({'+'.join(comp_parts)})" if comp_parts else None
                    else:
                        # Método estándar: COGS + cambio en inventarios
                        inv_now = self.create_cell_reference(
                            self.sh_bal.title,
                            self.find_year_column(self.sh_bal, y),
                            self.rows_bal["Inv"]
                        )
                        inv_prev = self.create_cell_reference(
                            self.sh_bal.title,
                            self.find_year_column(self.sh_bal, y-1),
                            self.rows_bal["Inv"]
                        )
                        comp = None
                        if cogs and inv_now and inv_prev:
                            comp = f"({cogs}+({inv_now}-{inv_prev}))"
                    cxp_avg = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)
                    if comp and cxp_avg:
                        rot_expr = f"IFERROR({comp}/{cxp_avg},\"N/A\")"
                        m_rot[str(y)] = rot_expr
                        m_dias[str(y)] = f"IFERROR({self._get_year_days(str(y))}/({rot_expr}),\"N/A\")"
            return m_rot, m_dias

        rot_cxp, dias_pago = f_rot_cxp_y_dias()

        formulas.append(("Rotación de Cuentas por Pagar", "ratio", lambda: rot_cxp,
                        "Compras (≈ COGS + ΔInventario) / Cuentas por Pagar Promedio"))
        formulas.append(("Período Promedio de Pago", "days", lambda: dias_pago,
                        "Días del período / Rotación de CxP"))

        # Ciclo de Conversión de Efectivo
        def f_cce():
            m = {}
            # soportar trimestral (labels) y anual (years)
            labels_all = []
            hdr = self.HDR_PL
            for c in range(2, self.sh_pl.max_column + 1):
                v = self.sh_pl.cell(row=hdr, column=c).value
                if isinstance(v, str):
                    labels_all.append(v.strip().split("\n", 1)[0])

            # Si usa vista por naturaleza, calcular directamente con fórmula específica del usuario
            if self._is_using_nature_based_income_statement():
                if any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_all):
                    for lb in labels_all:
                        if not re.match(r"^\d{4}Q[1-4]$", lb):
                            continue

                        # Obtener días del período para trimestres
                        period_days = self._get_period_days(lb)

                        # Fórmula específica del usuario adaptada para trimestres:
                        # Días Inventario (naturaleza): period_days / ((RawMat+InvChange-WorkCap) / Inv_Avg)
                        # Días Cobro: period_days / (Ventas / CxC_Avg)
                        # Días Pago (naturaleza): period_days / ((RawMat-WorkCap) / CxP_Avg)

                        # Referencias a celdas por label
                        ventas = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["Ventas"], lb)
                        raw_mat = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("RawMat"), lb)
                        inv_change = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("InvChange"), lb)
                        work_cap = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("WorkCap"), lb)

                        # Promedios de balance (actual vs anterior mismo trimestre)
                        inv_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], lb)
                        cxc_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxC"], lb)
                        cxp_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb)

                        lb_prev4 = self._previous_year_same_quarter_label(lb)
                        inv_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["Inv"], lb_prev4) if lb_prev4 else None
                        cxc_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxC"], lb_prev4) if lb_prev4 else None
                        cxp_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb_prev4) if lb_prev4 else None

                        inv_avg = f"AVERAGE({inv_now},{inv_prev4})" if inv_now and inv_prev4 else (inv_now or inv_prev4)
                        cxc_avg = f"AVERAGE({cxc_now},{cxc_prev4})" if cxc_now and cxc_prev4 else (cxc_now or cxc_prev4)
                        cxp_avg = f"AVERAGE({cxp_now},{cxp_prev4})" if cxp_now and cxp_prev4 else (cxp_now or cxp_prev4)

                        if ventas and raw_mat and inv_avg and cxc_avg and cxp_avg:
                            # Construir componentes de la fórmula específica
                            # Días Inventario (C11+C9-C10 = RawMat+InvChange-WorkCap)
                            inv_numerator_parts = [f"IFERROR({raw_mat},0)"]
                            if inv_change:
                                inv_numerator_parts.append(f"IFERROR({inv_change},0)")
                            if work_cap:
                                inv_numerator_parts.append(f"-IFERROR({work_cap},0)")
                            inv_numerator = "+".join(inv_numerator_parts)
                            dias_inv_formula = f"IFERROR({period_days}/(IFERROR(({inv_numerator})/{inv_avg},\"N/A\")),\"N/A\")"

                            # Días Cobro (C7 = Ventas)
                            dias_cobro_formula = f"IFERROR({period_days}/(IFERROR({ventas}/{cxc_avg},\"N/A\")),\"N/A\")"

                            # Días Pago (C11-C10 = RawMat-WorkCap)
                            pago_numerator_parts = [f"IFERROR({raw_mat},0)"]
                            if work_cap:
                                pago_numerator_parts.append(f"-IFERROR({work_cap},0)")
                            pago_numerator = "+".join(pago_numerator_parts)
                            dias_pago_formula = f"IFERROR({period_days}/(IFERROR(({pago_numerator})/{cxp_avg},\"N/A\")),\"N/A\")"

                            # CCE = Días Inventario + Días Cobro - Días Pago
                            m[lb] = f"IFERROR({dias_inv_formula}+{dias_cobro_formula}-{dias_pago_formula},\"N/A\")"

                    # Completar claves anuales para vista por naturaleza
                    for y in self.years:
                        if str(y) in m:
                            continue

                        col = self.find_year_column(self.sh_pl, y)
                        if not col:
                            continue

                        # Referencias anuales
                        ventas_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl["Ventas"])
                        raw_mat_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat"))
                        inv_change_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("InvChange"))
                        work_cap_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap"))

                        inv_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["Inv"], y)
                        cxc_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["CxC"], y)
                        cxp_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)

                        if ventas_a and raw_mat_a and inv_avg_a and cxc_avg_a and cxp_avg_a:
                            # Usar 365 días para años
                            # Días Inventario
                            inv_numerator_parts_a = [f"IFERROR({raw_mat_a},0)"]
                            if inv_change_a:
                                inv_numerator_parts_a.append(f"IFERROR({inv_change_a},0)")
                            if work_cap_a:
                                inv_numerator_parts_a.append(f"-IFERROR({work_cap_a},0)")
                            inv_numerator_a = "+".join(inv_numerator_parts_a)
                            dias_inv_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR(({inv_numerator_a})/{inv_avg_a},\"N/A\")),\"N/A\")"

                            # Días Cobro
                            dias_cobro_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR({ventas_a}/{cxc_avg_a},\"N/A\")),\"N/A\")"

                            # Días Pago
                            pago_numerator_parts_a = [f"IFERROR({raw_mat_a},0)"]
                            if work_cap_a:
                                pago_numerator_parts_a.append(f"-IFERROR({work_cap_a},0)")
                            pago_numerator_a = "+".join(pago_numerator_parts_a)
                            dias_pago_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR(({pago_numerator_a})/{cxp_avg_a},\"N/A\")),\"N/A\")"

                            # CCE = Días Inventario + Días Cobro - Días Pago
                            m[str(y)] = f"IFERROR({dias_inv_formula_a}+{dias_cobro_formula_a}-{dias_pago_formula_a},\"N/A\")"
                else:
                    # Solo años para vista por naturaleza
                    for y in self.years:
                        col = self.find_year_column(self.sh_pl, y)
                        if not col:
                            continue

                        # Referencias anuales
                        ventas_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl["Ventas"])
                        raw_mat_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat"))
                        inv_change_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("InvChange"))
                        work_cap_a = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap"))

                        inv_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["Inv"], y)
                        cxc_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["CxC"], y)
                        cxp_avg_a = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)

                        if ventas_a and raw_mat_a and inv_avg_a and cxc_avg_a and cxp_avg_a:
                            # Días Inventario
                            inv_numerator_parts_a = [f"IFERROR({raw_mat_a},0)"]
                            if inv_change_a:
                                inv_numerator_parts_a.append(f"IFERROR({inv_change_a},0)")
                            if work_cap_a:
                                inv_numerator_parts_a.append(f"-IFERROR({work_cap_a},0)")
                            inv_numerator_a = "+".join(inv_numerator_parts_a)
                            dias_inv_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR(({inv_numerator_a})/{inv_avg_a},\"N/A\")),\"N/A\")"

                            # Días Cobro
                            dias_cobro_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR({ventas_a}/{cxc_avg_a},\"N/A\")),\"N/A\")"

                            # Días Pago
                            pago_numerator_parts_a = [f"IFERROR({raw_mat_a},0)"]
                            if work_cap_a:
                                pago_numerator_parts_a.append(f"-IFERROR({work_cap_a},0)")
                            pago_numerator_a = "+".join(pago_numerator_parts_a)
                            dias_pago_formula_a = f"IFERROR({self._get_year_days(str(y))}/(IFERROR(({pago_numerator_a})/{cxp_avg_a},\"N/A\")),\"N/A\")"

                            # CCE = Días Inventario + Días Cobro - Días Pago
                            m[str(y)] = f"IFERROR({dias_inv_formula_a}+{dias_cobro_formula_a}-{dias_pago_formula_a},\"N/A\")"
            else:
                # Método estándar para empresas no-naturaleza usando componentes ya calculados
                if any(re.match(r"^\d{4}Q[1-4]$", lb) for lb in labels_all):
                    for lb in labels_all:
                        if not re.match(r"^\d{4}Q[1-4]$", lb):
                            continue
                        di = dias_inv.get(lb)
                        dc = dias_cobro.get(lb)
                        dp = dias_pago.get(lb)
                        if di and dc and dp:
                            m[lb] = f"IFERROR({di}+{dc}-{dp},\"N/A\")"
                    # duplicar claves anuales (YYYY) si existen mapas anuales
                    for y in self.years:
                        di_y = dias_inv.get(str(y))
                        dc_y = dias_cobro.get(str(y))
                        dp_y = dias_pago.get(str(y))
                        if di_y and dc_y and dp_y:
                            m[str(y)] = f"IFERROR({di_y}+{dc_y}-{dp_y},\"N/A\")"
                else:
                    for y in self.years:
                        di = dias_inv.get(str(y))
                        dc = dias_cobro.get(str(y))
                        dp = dias_pago.get(str(y))
                        if di and dc and dp:
                            m[str(y)] = f"IFERROR({di}+{dc}-{dp},\"N/A\")"
            return m

        formulas.append(("Ciclo de Conversión de Efectivo", "days", f_cce,
                        "Días Inventario + Días CxC - Días CxP"))

        return formulas
