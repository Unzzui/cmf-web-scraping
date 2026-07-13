"""
Nature-Based Mixin
==================

Provides methods for building formulas specific to nature-based income
statements ([320000]), plus detection and helper methods.
"""

import re
from typing import List, Optional, Tuple


class NatureBasedMixin:
    """Mixin providing nature-based income statement formula builders."""

    def build_nature_based_formulas(self) -> List[Tuple[str, str, callable, str]]:
        """
        Construye fórmulas específicas para estados de resultados por naturaleza ([320000]).

        Returns:
            Lista de tuplas (nombre, tipo, función_fórmula, descripción)
        """
        formulas = []

        # Solo agregar estas fórmulas si estamos usando vista por naturaleza
        if not self._is_using_nature_based_income_statement():
            return formulas

        # DPO (Days Payable Outstanding) para vista por naturaleza
        def f_dpo_nature():
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

                    # DPO = 365 × (Cuentas por pagar promedio) / Compras
                    # Compras basadas en naturaleza
                    purchases = self._build_nature_based_purchases(lb)
                    cxp_now = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb)
                    lb_prev4 = self._previous_year_same_quarter_label(lb)
                    cxp_prev4 = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal["CxP"], lb_prev4) if lb_prev4 else None

                    if purchases and cxp_now:
                        cxp_avg = f"AVERAGE({cxp_now},{cxp_prev4})" if cxp_prev4 else cxp_now
                        # Usar días correspondientes al período
                        period_days = self._get_period_days(lb)
                        m[lb] = f"IFERROR(({period_days}*{cxp_avg})/{purchases},\"N/A\")"

                # Completar claves anuales
                for y in self.years:
                    if str(y) in m:
                        continue
                    purchases_y = self._build_nature_based_purchases_annual(y)
                    cxp_avg_y = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)
                    if purchases_y and cxp_avg_y:
                        m[str(y)] = f"IFERROR((365*{cxp_avg_y})/{purchases_y},\"N/A\")"
            else:
                for y in self.years:
                    purchases = self._build_nature_based_purchases_annual(y)
                    cxp_avg = self.create_average_reference(self.sh_bal, self.rows_bal["CxP"], y)
                    if purchases and cxp_avg:
                        m[str(y)] = f"IFERROR((365*{cxp_avg})/{purchases},\"N/A\")"

            return m

        formulas.append(("DPO (Vista por Naturaleza)", "days", f_dpo_nature,
                        "Días Promedio de Pago - Calculado usando compras basadas en naturaleza"))



        return formulas

    def _is_using_nature_based_income_statement(self) -> bool:
        """
        Detecta si el estado de resultados está usando la vista por naturaleza ([320000]).

        Returns:
            True si se detecta que se está usando la vista por naturaleza
        """
        # Verificar si existen los conceptos específicos de la vista por naturaleza
        has_raw_materials = self.rows_pl.get("RawMat") is not None
        has_inventory_change = self.rows_pl.get("InvChange") is not None
        has_work_capitalized = self.rows_pl.get("WorkCap") is not None

        # Si tenemos al menos 2 de estos conceptos, probablemente es vista por naturaleza
        nature_indicators = sum([has_raw_materials, has_inventory_change, has_work_capitalized])

        # Verificar si existe COGS explícito
        has_explicit_cogs = self.rows_pl.get("COGS") is not None

        # Verificar si existe ganancia bruta explícita (común en vista por función)
        has_explicit_gross_profit = self.rows_pl.get("Bruta") is not None

        # Detección mejorada: es vista por naturaleza si:
        # 1. Tiene al menos 2 indicadores de naturaleza Y
        # 2. (NO tiene COGS explícito O NO tiene ganancia bruta explícita)
        # Esto captura casos híbridos donde hay COGS pero se calculan ratios por naturaleza
        return nature_indicators >= 2 and (not has_explicit_cogs or not has_explicit_gross_profit)

    def _build_nature_based_cogs_force(self, label: str) -> Optional[str]:
        """
        Construye COGS basado en conceptos de naturaleza SIN verificar detección automática.
        Útil para casos híbridos donde existen ambos formatos.

        Args:
            label: Etiqueta del período

        Returns:
            Fórmula Excel para COGS basado en naturaleza
        """
        # COGS = Materias primas + Cambio inventarios - Trabajos capitalizados
        row_rm = self.rows_pl.get("RawMat")
        row_ch = self.rows_pl.get("InvChange")
        row_wc = self.rows_pl.get("WorkCap")

        rm = self.create_cell_reference_by_label(self.sh_pl, row_rm, label) if row_rm else None
        ch = self.create_cell_reference_by_label(self.sh_pl, row_ch, label) if row_ch else None
        wc = self.create_cell_reference_by_label(self.sh_pl, row_wc, label) if row_wc else None

        parts = []
        if rm:
            parts.append(f"IFERROR({rm},0)")
        if ch:
            parts.append(f"IFERROR({ch},0)")
        if wc:
            # Trabajos capitalizados se restan (reducen el costo)
            parts.append(f"-IFERROR({wc},0)")

        if len(parts) >= 2:  # Al menos materias primas + algún otro
            return "(" + "+".join(parts) + ")"
        elif rm:  # Solo materias primas
            return f"IFERROR({rm},0)"

        return None

    def _build_nature_based_cogs_annual_force(self, year: int) -> Optional[str]:
        """
        Construye COGS basado en conceptos de naturaleza SIN verificar detección automática (versión anual).

        Args:
            year: Año para el cual construir COGS

        Returns:
            Fórmula Excel para COGS basado en naturaleza
        """
        col = self.find_year_column(self.sh_pl, year)
        if not col:
            return None

        # COGS = Materias primas + Cambio inventarios - Trabajos capitalizados
        row_rm = self.rows_pl.get("RawMat")
        row_ch = self.rows_pl.get("InvChange")
        row_wc = self.rows_pl.get("WorkCap")

        rm = self.create_cell_reference(self.sh_pl.title, col, row_rm) if row_rm else None
        ch = self.create_cell_reference(self.sh_pl.title, col, row_ch) if row_ch else None
        wc = self.create_cell_reference(self.sh_pl.title, col, row_wc) if row_wc else None

        parts = []
        if rm:
            parts.append(f"IFERROR({rm},0)")
        if ch:
            parts.append(f"IFERROR({ch},0)")
        if wc:
            # Trabajos capitalizados se restan (reducen el costo)
            parts.append(f"-IFERROR({wc},0)")

        if len(parts) >= 2:  # Al menos materias primas + algún otro
            return "(" + "+".join(parts) + ")"
        elif rm:  # Solo materias primas
            return f"IFERROR({rm},0)"

        return None

    def _build_nature_based_cogs(self, label: str) -> Optional[str]:
        """
        Construye COGS basado en la vista por naturaleza ([320000]).

        Args:
            label: Etiqueta del período

        Returns:
            Fórmula Excel para COGS basado en naturaleza
        """
        if not self._is_using_nature_based_income_statement():
            return None

        # COGS = Materias primas + Cambio inventarios - Trabajos capitalizados
        raw_mat = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("RawMat"), label)
        inv_change = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("InvChange"), label)
        work_cap = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("WorkCap"), label)

        parts = []
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")
        if inv_change:
            parts.append(f"IFERROR({inv_change},0)")

        if not parts:
            return None

        cogs_expr = "+".join(parts)

        if work_cap:
            cogs_expr = f"({cogs_expr})-IFERROR({work_cap},0)"

        return f"({cogs_expr})"

    def _build_nature_based_cogs_annual(self, year: int) -> Optional[str]:
        """
        Versión anual de _build_nature_based_cogs.

        Args:
            year: Año para el cual construir la referencia

        Returns:
            Fórmula Excel para COGS basado en naturaleza
        """
        if not self._is_using_nature_based_income_statement():
            return None

        col = self.find_year_column(self.sh_pl, year)
        if not col:
            return None

        # COGS = Materias primas + Cambio inventarios - Trabajos capitalizados
        raw_mat = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat")) if self.rows_pl.get("RawMat") else None
        inv_change = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("InvChange")) if self.rows_pl.get("InvChange") else None
        work_cap = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap")) if self.rows_pl.get("WorkCap") else None

        parts = []
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")
        if inv_change:
            parts.append(f"IFERROR({inv_change},0)")

        if not parts:
            return None

        cogs_expr = "+".join(parts)

        if work_cap:
            cogs_expr = f"({cogs_expr})-IFERROR({work_cap},0)"

        return f"({cogs_expr})"

    def _build_nature_based_operating_costs(self, label: str) -> Optional[str]:
        """
        Construye costos operativos basados en la vista por naturaleza ([320000]).

        Args:
            label: Etiqueta del período

        Returns:
            Fórmula Excel para costos operativos
        """
        if not self._is_using_nature_based_income_statement():
            return None

        # Costos operativos incluyen:
        # - Materias primas y consumibles utilizados
        # - Gastos por beneficios a los empleados (operativos)
        # - Gasto por depreciación y amortización (operativa)
        # - Otros gastos, por naturaleza (operativos)
        # - Disminución (aumento) en inventarios de productos terminados y en proceso
        # - Otros trabajos realizados por la entidad y capitalizados

        raw_mat = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("RawMat"), label)
        inv_change = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("InvChange"), label)
        work_cap = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("WorkCap"), label)

        # Buscar conceptos adicionales por naturaleza
        employee_benefits = self._find_row_by_regex_in_pl(r"gastos.*beneficios.*empleados|beneficios.*empleados", exclude_abstract=True)
        dep_amort = self._build_da_ttm(label) if label else None
        other_expenses = self._find_row_by_regex_in_pl(r"otros gastos.*naturaleza", exclude_abstract=True)

        parts = []

        # Materias primas
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")

        # Beneficios empleados (operativos)
        if employee_benefits:
            emp_ben_ref = self.create_cell_reference_by_label(self.sh_pl, employee_benefits, label)
            if emp_ben_ref:
                parts.append(f"IFERROR({emp_ben_ref},0)")

        # Depreciación y amortización (operativa)
        if dep_amort:
            parts.append(f"IFERROR({dep_amort},0)")

        # Otros gastos por naturaleza
        if other_expenses:
            other_ref = self.create_cell_reference_by_label(self.sh_pl, other_expenses, label)
            if other_ref:
                parts.append(f"IFERROR({other_ref},0)")

        # Cambio en inventarios (ya viene con signo IFRS)
        if inv_change:
            parts.append(f"IFERROR({inv_change},0)")

        # Trabajos capitalizados (se resta)
        if work_cap:
            parts.append(f"-IFERROR({work_cap},0)")

        if not parts:
            return None

        return f"({' + '.join(parts)})"

    def _build_nature_based_operating_costs_annual(self, year: int) -> Optional[str]:
        """
        Versión anual de _build_nature_based_operating_costs.

        Args:
            year: Año para el cual construir la referencia

        Returns:
            Fórmula Excel para costos operativos
        """
        if not self._is_using_nature_based_income_statement():
            return None

        col = self.find_year_column(self.sh_pl, year)
        if not col:
            return None

        # Costos operativos incluyen:
        # - Materias primas y consumibles utilizados
        # - Gastos por beneficios a los empleados (operativos)
        # - Gasto por depreciación y amortización (operativa)
        # - Otros gastos, por naturaleza (operativos)
        # - Disminución (aumento) en inventarios de productos terminados y en proceso
        # - Otros trabajos realizados por la entidad y capitalizados

        raw_mat = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat")) if self.rows_pl.get("RawMat") else None
        inv_change = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("InvChange")) if self.rows_pl.get("InvChange") else None
        work_cap = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap")) if self.rows_pl.get("WorkCap") else None

        # Buscar conceptos adicionales por naturaleza
        employee_benefits = self._find_row_by_regex_in_pl(r"gastos.*beneficios.*empleados|beneficios.*empleados", exclude_abstract=True)
        dep_amort = self._build_da_annual(year) if year else None
        other_expenses = self._find_row_by_regex_in_pl(r"otros gastos.*naturaleza", exclude_abstract=True)

        parts = []

        # Materias primas
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")

        # Beneficios empleados (operativos)
        if employee_benefits:
            emp_ben_ref = self.create_cell_reference(self.sh_pl.title, col, employee_benefits)
            if emp_ben_ref:
                parts.append(f"IFERROR({emp_ben_ref},0)")

        # Depreciación y amortización (operativa)
        if dep_amort:
            parts.append(f"IFERROR({dep_amort},0)")

        # Otros gastos por naturaleza
        if other_expenses:
            other_ref = self.create_cell_reference(self.sh_pl.title, col, other_expenses)
            if other_ref:
                parts.append(f"IFERROR({other_ref},0)")

        # Cambio en inventarios (ya viene con signo IFRS)
        if inv_change:
            parts.append(f"IFERROR({inv_change},0)")

        # Trabajos capitalizados (se resta)
        if work_cap:
            parts.append(f"-IFERROR({work_cap},0)")

        if not parts:
            return None

        return f"({' + '.join(parts)})"

    def _build_nature_based_purchases(self, label: str) -> Optional[str]:
        """
        Construye compras basadas en la vista por naturaleza ([320000]).

        Args:
            label: Etiqueta del período

        Returns:
            Fórmula Excel para compras
        """
        if not self._is_using_nature_based_income_statement():
            return None

        # Compras = Materias primas - Trabajos capitalizados + Variación inventarios MP
        raw_mat = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("RawMat"), label)
        work_cap = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl.get("WorkCap"), label)

        # Buscar inventario de materias primas (si existe)
        raw_mat_inv = self._find_row_by_regex_in_pl(r"inventario.*materias primas|materias primas.*inventario", exclude_abstract=True)

        parts = []

        # Materias primas
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")

        # Trabajos capitalizados (se resta)
        if work_cap:
            parts.append(f"-IFERROR({work_cap},0)")

        # Variación de inventarios de materias primas
        if raw_mat_inv:
            # Buscar inventario actual y anterior
            current_inv = self.create_cell_reference_by_label(self.sh_bal, self.rows_bal.get("Inv"), label)
            # Para variación, necesitaríamos inventario anterior (mismo período año anterior)
            # Por ahora, usamos solo el inventario actual como aproximación
            if current_inv:
                parts.append(f"IFERROR({current_inv},0)")

        if not parts:
            return None

        return f"({' + '.join(parts)})"

    def _build_nature_based_purchases_ttm(self, label: str) -> Optional[str]:
        """
        Construye compras TTM (Trailing Twelve Months) basadas en naturaleza para trimestres.

        Args:
            label: Etiqueta del trimestre (ej: "2024Q1")

        Returns:
            Fórmula Excel para compras TTM
        """
        if not self._is_using_nature_based_income_statement():
            return None

        if not re.match(r"^\d{4}Q[1-4]$", label):
            # Para datos anuales, usar la función estándar
            year = int(label) if label.isdigit() else None
            return self._build_nature_based_purchases_annual(year) if year else None

        # TTM = YTD actual - YTD hace 4 trimestres
        raw_mat_ttm = self.ttm_ref_pl("RawMat", label)
        work_cap_ttm = self.ttm_ref_pl("WorkCap", label)
        inv_change_ttm = self.ttm_ref_pl("InvChange", label)

        parts = []
        if raw_mat_ttm:
            parts.append(f"IFERROR({raw_mat_ttm},0)")
        if work_cap_ttm:
            parts.append(f"-IFERROR({work_cap_ttm},0)")
        if inv_change_ttm:
            parts.append(f"IFERROR({inv_change_ttm},0)")

        return f"({' + '.join(parts)})" if parts else None

    def _get_period_days(self, label: str) -> int:
        """
        Retorna los días que cubre el período de un label.

        Las columnas trimestrales del Estado de Resultados vienen ACUMULADAS desde
        el 1 de enero (así las publica la CMF): Q2 son 6 meses, Q3 nueve y Q4 el año
        completo. Por eso los días también son acumulados (Q1=90, Q2=181, Q3=273,
        Q4=365) y no los días sueltos del trimestre. Usar los sueltos hace que los
        ratios de días (inventario, cobro, pago) se dividan por una rotación anual
        con un numerador trimestral, subestimándolos hasta 4x en Q4.

        Args:
            label: Etiqueta del período (ej: "2024Q1", "2024")

        Returns:
            Días acumulados hasta el cierre del período
        """
        m = re.match(r"^(\d{4})Q([1-4])$", label)
        if not m:
            # Período anual: el ejercicio completo.
            return self._get_year_days(label)

        quarter = int(m.group(2))
        # Días acumulados a fin de marzo / junio / septiembre / diciembre.
        cumulative = {1: 90, 2: 181, 3: 273, 4: 365}[quarter]
        return cumulative + (1 if self._is_leap(label) else 0)

    @staticmethod
    def _is_leap(label: str) -> bool:
        m = re.match(r"^(\d{4})", label)
        if not m:
            return False
        year = int(m.group(1))
        return year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)

    def _get_year_days(self, label: str) -> int:
        """Días del ejercicio completo al que pertenece el label (365 o 366)."""
        return 366 if self._is_leap(label) else 365

    def _get_annualization_expr(self, label: str) -> Optional[str]:
        """Factor para llevar una cifra acumulada YTD a base anual, como expresión Excel.

        Es exactamente el recíproco de los días del período, de modo que
        `DíasAño / Rotación` devuelva el ratio de días correspondiente. Se emite como
        división literal ("(365/90)") en vez de un decimal redondeado para que la
        fórmula sea autoexplicativa y no arrastre error: los factores fijos que había
        antes (Q3 = 1.333 en vez de 365/273 = 1.3370) descuadraban con los días.

        Devuelve None cuando el período ya cubre el año y no hay que anualizar.
        """
        period_days = self._get_period_days(label)
        year_days = self._get_year_days(label)
        if period_days >= year_days:
            return None
        return f"({year_days}/{period_days})"

    def _annualized(self, expr: str, label: str) -> str:
        """Envuelve una cifra acumulada YTD para llevarla a base anual, si hace falta."""
        factor = self._get_annualization_expr(label)
        return f"({expr}*{factor})" if factor else expr

    def _build_nature_based_operating_costs_ttm(self, label: str) -> Optional[str]:
        """
        Construye costos operativos TTM (Trailing Twelve Months) basados en naturaleza para trimestres.

        Args:
            label: Etiqueta del trimestre (ej: "2024Q1")

        Returns:
            Fórmula Excel para costos operativos TTM
        """
        if not self._is_using_nature_based_income_statement():
            return None

        if not re.match(r"^\d{4}Q[1-4]$", label):
            # Para datos anuales, usar la función estándar
            return self._build_nature_based_operating_costs(label)

        # TTM = YTD actual - YTD hace 4 trimestres
        raw_mat_ttm = self.ttm_ref_pl("RawMat", label)
        inv_change_ttm = self.ttm_ref_pl("InvChange", label)
        work_cap_ttm = self.ttm_ref_pl("WorkCap", label)

        parts = []

        # Materias primas y consumibles utilizados
        if raw_mat_ttm:
            parts.append(f"IFERROR({raw_mat_ttm},0)")

        # Disminución (aumento) en inventarios de productos terminados y en proceso
        if inv_change_ttm:
            parts.append(f"IFERROR({inv_change_ttm},0)")

        # Otros trabajos realizados por la entidad y capitalizados (se resta)
        if work_cap_ttm:
            parts.append(f"-IFERROR({work_cap_ttm},0)")

        # Buscar conceptos adicionales por naturaleza usando TTM
        employee_benefits_row = self._find_row_by_regex_in_pl(r"gastos.*beneficios.*empleados|beneficios.*empleados", exclude_abstract=True)
        if employee_benefits_row and isinstance(employee_benefits_row, int):
            emp_ben_ref = self.create_cell_reference_by_label(self.sh_pl, employee_benefits_row, label)
            if emp_ben_ref:
                # Q4 is the full-year value: no TTM subtraction needed
                if label.endswith("Q4"):
                    parts.append(f"IFERROR({emp_ben_ref},0)")
                else:
                    # Usar TTM para esta referencia
                    prev4_label = self._previous_year_same_quarter_label(label)
                    if prev4_label:
                        emp_ben_prev = self.create_cell_reference_by_label(self.sh_pl, employee_benefits_row, prev4_label)
                        if emp_ben_prev:
                            emp_ben_ttm = f"IFERROR({emp_ben_ref}-{emp_ben_prev},0)"
                            parts.append(emp_ben_ttm)
                        else:
                            parts.append(f"IFERROR({emp_ben_ref},0)")
                    else:
                        parts.append(f"IFERROR({emp_ben_ref},0)")

        # Depreciación y amortización TTM
        dep_amort_ttm = self._build_da_ttm(label)
        if dep_amort_ttm:
            parts.append(f"IFERROR({dep_amort_ttm},0)")

        # Otros gastos por naturaleza
        other_expenses_row = self._find_row_by_regex_in_pl(r"otros gastos.*naturaleza", exclude_abstract=True)
        if other_expenses_row and isinstance(other_expenses_row, int):
            other_exp_ref = self.create_cell_reference_by_label(self.sh_pl, other_expenses_row, label)
            if other_exp_ref:
                # Q4 is the full-year value: no TTM subtraction needed
                if label.endswith("Q4"):
                    parts.append(f"IFERROR({other_exp_ref},0)")
                else:
                    # Usar TTM para esta referencia
                    prev4_label = self._previous_year_same_quarter_label(label)
                    if prev4_label:
                        other_exp_prev = self.create_cell_reference_by_label(self.sh_pl, other_expenses_row, prev4_label)
                        if other_exp_prev:
                            other_exp_ttm = f"IFERROR({other_exp_ref}-{other_exp_prev},0)"
                            parts.append(other_exp_ttm)
                        else:
                            parts.append(f"IFERROR({other_exp_ref},0)")
                    else:
                        parts.append(f"IFERROR({other_exp_ref},0)")

        return f"({' + '.join(parts)})" if parts else None

    def _build_nature_based_purchases_annual(self, year: int) -> Optional[str]:
        """
        Versión anual de _build_nature_based_purchases.

        Args:
            year: Año para el cual construir la referencia

        Returns:
            Fórmula Excel para compras
        """
        if not self._is_using_nature_based_income_statement():
            return None

        col = self.find_year_column(self.sh_pl, year)
        if not col:
            return None

        # Compras = Materias primas - Trabajos capitalizados + Variación inventarios MP
        raw_mat = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("RawMat")) if self.rows_pl.get("RawMat") else None
        work_cap = self.create_cell_reference(self.sh_pl.title, col, self.rows_pl.get("WorkCap")) if self.rows_pl.get("WorkCap") else None

        # Buscar inventario de materias primas (si existe)
        raw_mat_inv = self._find_row_by_regex_in_pl(r"inventario.*materias primas|materias primas.*inventario", exclude_abstract=True)

        parts = []

        # Materias primas
        if raw_mat:
            parts.append(f"IFERROR({raw_mat},0)")

        # Trabajos capitalizados (se resta)
        if work_cap:
            parts.append(f"-IFERROR({work_cap},0)")

        # Variación de inventarios de materias primas
        if raw_mat_inv:
            # Buscar inventario actual y anterior
            current_inv = self.create_cell_reference(self.sh_bal.title, col, self.rows_bal.get("Inv"))
            prev_inv = self.create_cell_reference(self.sh_bal.title, self.find_year_column(self.sh_bal, year-1), self.rows_bal.get("Inv"))

            if current_inv and prev_inv:
                parts.append(f"IFERROR({current_inv}-{prev_inv},0)")
            elif current_inv:
                parts.append(f"IFERROR({current_inv},0)")

        if not parts:
            return None

        return f"({' + '.join(parts)})"
