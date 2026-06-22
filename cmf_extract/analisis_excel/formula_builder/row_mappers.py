"""
Row Mapper Mixin
================

Provides methods for mapping financial concepts to Excel row numbers,
plus COGS reference builders and D&A (Depreciation & Amortization) helpers.
"""

import re
from typing import Dict, List, Optional, Tuple, Any


class RowMapperMixin:
    """Mixin providing row mapping and related helper methods."""

    def _map_balance_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del balance a números de fila."""
        concepts = {
            # Activos básicos
            "AC": "Activos corrientes totales",
            "AT": "Total de activos",
            "ANC": "Total de activos no corrientes",
            "PPE": "Propiedades, planta y equipo",
            "Efec": "Efectivo y equivalentes al efectivo",
            "Inv": "Inventarios corrientes",
            "InvNC": "Inventarios, no corrientes",
            "CxC": "Deudores comerciales y otras cuentas por cobrar corrientes",
            "CxCNC": "Cuentas por cobrar no corrientes",
            "Intang": "Activos intangibles distintos de la plusvalía",
            "Plusvalia": "Plusvalía",
            "ActivDifImp": "Activos por impuestos diferidos",
            "PropInv": "Propiedad de inversión",
            "ActivDerUso": "Activos por derecho de uso",
            "InvAsoc": "Inversiones contabilizadas utilizando el método de la participación",

            # Pasivos básicos
            "PC": "Pasivos corrientes totales",
            "PT": "Total de pasivos",
            "PNC": "Total de pasivos no corrientes",
            "CxP": "Cuentas por pagar comerciales y otras cuentas por pagar",
            "CxPNC": "Cuentas por pagar no corrientes",
            "DeudaFinCorr": "Otros pasivos financieros corrientes",
            "DeudaFinNC": "Otros pasivos financieros no corrientes",
            "ArrCorr": "Pasivos por arrendamientos corrientes",
            "ArrNC": "Pasivos por arrendamientos no corrientes",
            "PasivDifImp": "Pasivo por impuestos diferidos",
            "ProvCorr": "Otras provisiones a corto plazo",
            "ProvNC": "Otras provisiones a largo plazo",
            "BenefEmpl": "Provisiones corrientes por beneficios a los empleados",
            "BenefEmplNC": "Provisiones no corrientes por beneficios a los empleados",

            # Patrimonio
            "Patr": "Patrimonio atribuible a los propietarios de la controladora",
            "PatrTotal": "Patrimonio total",
            "CapitalEmit": "Capital emitido y pagado",
            "GanAcum": "Ganancias (pérdidas) acumuladas",
            "PrimaEmis": "Prima de emisión",
            "AccPropias": "Acciones propias en cartera",
            "OtraPartPatr": "Otras participaciones en el patrimonio",
            "OtraReserv": "Otras reservas",
            "PartNoControl": "Participaciones no controladoras"
        }

        # Necesitamos el DataFrame del balance
        df_bal = self.financial_data.get("_df_bal")
        if df_bal is None:
            # Si no está disponible, crear un mapeo vacío
            return {key: None for key in concepts.keys()}

        return {key: self._find_row_in_sheet(self.sh_bal, df_bal, concept)
                for key, concept in concepts.items()}

    def _map_income_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del estado de resultados a números de fila."""
        concepts = {
            "Ventas": "Ingresos de actividades ordinarias",
            "COGS": "Costo de ventas",
            "Bruta": "Ganancia bruta",
            "EBIT": "Ganancias (pérdidas) de actividades operacionales",
            "Neta": "Ganancia (pérdida)",
            "NetaControl": "Ganancia (pérdida), atribuible a los propietarios de la controladora",
            "Interes": "Costos financieros",
            "IngFinanc": "Ingresos financieros",
            "Dep": "Depreciación",
            "Amort": "Amortización",
            # Fila combinada (cuando EN usa "Depreciation and amorti(s)ation expense")
            "DepAmort": "Depreciación y amortización",
            "OtrosIng": "Otros ingresos",
            "CostDistrib": "Costos de distribución",
            "GastAdmin": "Gastos de administración",
            "OtrosGast": "Otros gastos, por función",
            "OtraGanPerd": "Otras ganancias (pérdidas)",
            "AntesImp": "Ganancia (pérdida), antes de impuestos",
            "ImpGanan": "Gasto por impuestos a las ganancias",
            "OperCont": "Ganancia (pérdida) procedente de operaciones continuadas",
            "OperDisc": "Ganancia (pérdida) procedente de operaciones discontinuadas",
            "DeterioBanco": "Deterioro de valor de ganancias y reversión de pérdidas por deterioro de valor (pérdidas por deterioro de valor) determinado de acuerdo con la NIIF 9",
            "PartAsoc": "Participación en las ganancias (pérdidas) de asociadas y negocios conjuntos que se contabilicen utilizando el método de la participación",
            "GanCambio": "Ganancias (pérdidas) de cambio en moneda extranjera",
            "ResUniReaj": "Resultados por unidades de reajuste",
            "GanBasAcc": "Ganancia (pérdida) por acción básica",
            "GanDilAcc": "Ganancias (pérdida) diluida por acción"
        }

        # Soporte por naturaleza ([320000]): materias primas, cambio inventarios, trabajos capitalizados
        # Estos pueden usarse para construir un COGS proxy cuando no existe "Costo de ventas".
        concepts.update({
            "RawMat": "Materias primas y consumibles utilizados",
            "InvChange": "Disminución (aumento) en inventarios de productos terminados y en proceso",
            "WorkCap": "Otros trabajos realizados por la entidad y capitalizados",
        })

        df_pl = self.financial_data.get("_df_pl")
        if df_pl is None:
            return {key: None for key in concepts.keys()}

        return {key: self._find_row_in_sheet(self.sh_pl, df_pl, concept)
                for key, concept in concepts.items()}

    def _find_row_by_regex_in_pl(self, pattern: str, exclude_abstract: bool = True) -> Optional[int]:
        df_pl = self.financial_data.get("_df_pl")
        if df_pl is None or "Concepto" not in df_pl.columns:
            return None
        ser = df_pl["Concepto"].astype(str)
        ser_lc = ser.str.strip().str.lower()
        mask = ser_lc.str.contains(pattern, regex=True, na=False)
        if exclude_abstract:
            mask = mask & ~ser_lc.str.contains("abstract|resumen", regex=True, na=False)
        if mask.any():
            idx = df_pl.index[mask][0]
            return int(idx) + self.HDR_PL + 1
        return None

    def _cogs_ref_by_label(self, label: str) -> Optional[str]:
        """Construye una expresión Excel de COGS cuando no existe una fila explícita de Costo de Ventas.

        COGS ≈ Raw materials and consumables used
                + Decrease (increase) in inventories of finished goods and WIP
                − Other work performed by entity and capitalised
        """
        # Si existe COGS explícito, usarlo
        if self.rows_pl.get("COGS"):
            ref = self.create_cell_reference_by_label(self.sh_pl, self.rows_pl["COGS"], label)
            if ref:
                return ref

        # Priorizar método por naturaleza si hay conceptos disponibles (independiente de detección automática)
        row_rm = self.rows_pl.get("RawMat")
        row_ch = self.rows_pl.get("InvChange")
        row_wc = self.rows_pl.get("WorkCap")

        # Si tenemos al menos materias primas, intentar construir COGS por naturaleza
        if row_rm or row_ch:
            nature_based_cogs = self._build_nature_based_cogs_force(label)
            if nature_based_cogs:
                return nature_based_cogs

        # Si estamos usando vista por naturaleza ([320000]), usar la función específica
        nature_based_cogs = self._build_nature_based_cogs(label)
        if nature_based_cogs:
            return nature_based_cogs
        rm = self.create_cell_reference_by_label(self.sh_pl, row_rm, label) if row_rm else None
        ch = self.create_cell_reference_by_label(self.sh_pl, row_ch, label) if row_ch else None
        wc = self.create_cell_reference_by_label(self.sh_pl, row_wc, label) if row_wc else None
        parts: list[str] = []
        if rm:
            parts.append(f"IFERROR({rm},0)")
        if ch:
            parts.append(f"IFERROR({ch},0)")
        expr = None
        if parts:
            expr = "+".join(parts)
        if wc:
            expr = f"({expr if expr else '0'})-IFERROR({wc},0)"
        return f"({expr})" if expr else None

    def _cogs_ref_by_year(self, year: int) -> Optional[str]:
        """Versión anual de _cogs_ref_by_label (usa columnas por año)."""
        # Si existe COGS explícito, usarlo
        if self.rows_pl.get("COGS"):
            col = self.find_year_column(self.sh_pl, year)
            return self.create_cell_reference(self.sh_pl.title, col, self.rows_pl["COGS"]) if col else None

        # Priorizar método por naturaleza si hay conceptos disponibles
        row_rm = self.rows_pl.get("RawMat")
        row_ch = self.rows_pl.get("InvChange")
        row_wc = self.rows_pl.get("WorkCap")

        # Si tenemos al menos materias primas, intentar construir COGS por naturaleza
        if row_rm or row_ch:
            nature_based_cogs = self._build_nature_based_cogs_annual_force(year)
            if nature_based_cogs:
                return nature_based_cogs

        # Si estamos usando vista por naturaleza ([320000]), usar la función específica
        nature_based_cogs = self._build_nature_based_cogs_annual(year)
        if nature_based_cogs:
            return nature_based_cogs
        col = self.find_year_column(self.sh_pl, year)
        if not col:
            return None
        rm = self.create_cell_reference(self.sh_pl.title, col, row_rm) if row_rm else None
        ch = self.create_cell_reference(self.sh_pl.title, col, row_ch) if row_ch else None
        wc = self.create_cell_reference(self.sh_pl.title, col, row_wc) if row_wc else None
        parts: list[str] = []
        if rm:
            parts.append(f"IFERROR({rm},0)")
        if ch:
            parts.append(f"IFERROR({ch},0)")
        expr = None
        if parts:
            expr = "+".join(parts)
        if wc:
            expr = f"({expr if expr else '0'})-IFERROR({wc},0)"
        return f"({expr})" if expr else None

    def _build_da_ttm(self, label: str) -> Optional[str]:
        """Construye referencia TTM para Depreciación+Amortización evitando doble conteo.
        Estrategia: Dep&Amort combinadas → Dep + Amort separadas → (Total D&A+impairment) − (Impairment).
        """
        # 1) Fila combinada estándar (ES o EN). Acepta '... and amortization' con y sin 'expense'.
        row_depam = self.rows_pl.get("DepAmort")
        if not row_depam:
            row_depam = self._find_row_by_regex_in_pl(r"\bdepreciation and amorti[sz]ation(?:\s+expense)?\b")
        if row_depam:
            cur = self.create_cell_reference_by_label(self.sh_pl, row_depam, label)
            # Q4 is already annual — no TTM subtraction
            if label.endswith("Q4"):
                return cur
            prev4_label = self._previous_year_same_quarter_label(label)
            prev = self.create_cell_reference_by_label(self.sh_pl, row_depam, prev4_label) if prev4_label else None
            if cur and prev:
                return f"IFERROR({cur}-{prev},{cur})"
            return cur

        # 2) Suma de líneas separadas
        row_dep = self.rows_pl.get("Dep") or self._find_row_by_regex_in_pl(r"\bdepreciation(?:\s+expense)?\b")
        row_amort = self.rows_pl.get("Amort") or self._find_row_by_regex_in_pl(r"\bamorti[sz]ation(?:\s+expense)?\b")
        dep_ref = self.create_cell_reference_by_label(self.sh_pl, row_dep, label) if row_dep else None
        amort_ref = self.create_cell_reference_by_label(self.sh_pl, row_amort, label) if row_amort else None
        # Q4 is already annual — skip TTM subtraction
        if label.endswith("Q4"):
            dep_ttm = dep_ref
            amort_ttm = amort_ref
        else:
            dep_prev = None
            amort_prev = None
            prev4_label = self._previous_year_same_quarter_label(label)
            if prev4_label:
                if row_dep:
                    dep_prev = self.create_cell_reference_by_label(self.sh_pl, row_dep, prev4_label)
                if row_amort:
                    amort_prev = self.create_cell_reference_by_label(self.sh_pl, row_amort, prev4_label)
            # Construir TTM
            dep_ttm = f"IFERROR({dep_ref}-{dep_prev},{dep_ref})" if dep_ref and dep_prev else dep_ref
            amort_ttm = f"IFERROR({amort_ref}-{amort_prev},{amort_ref})" if amort_ref and amort_prev else amort_ref
        if dep_ttm and amort_ttm:
            if dep_ttm == amort_ttm:
                return dep_ttm
            return f"IFERROR({dep_ttm},0)+IFERROR({amort_ttm},0)"
        if dep_ttm or amort_ttm:
            return dep_ttm or amort_ttm

        # 3) Fallback: usar Total (Dep+Amort+Impairment) - Impairment (más amplio para [320000] u otras vistas)
        row_total_dai = self._find_row_by_regex_in_pl(r"total\s+depreciation,\s+amorti[sz]ation\s+and\s+impairment.*profit\s+or\s+loss|total\s+depreciation\s+and\s+amorti[sz]ation", exclude_abstract=False)
        row_impair = self._find_row_by_regex_in_pl(r"impairment\s+loss.*profit\s+or\s+loss", exclude_abstract=False)
        if row_total_dai:
            total_cur = self.create_cell_reference_by_label(self.sh_pl, row_total_dai, label)
            total_prev = self.create_cell_reference_by_label(self.sh_pl, row_total_dai, prev4_label) if prev4_label else None
            total_ttm = f"IFERROR({total_cur}-{total_prev},{total_cur})" if (total_cur and total_prev) else total_cur
            if row_impair:
                imp_cur = self.create_cell_reference_by_label(self.sh_pl, row_impair, label)
                imp_prev = self.create_cell_reference_by_label(self.sh_pl, row_impair, prev4_label) if prev4_label else None
                imp_ttm = f"IFERROR({imp_cur}-{imp_prev},{imp_cur})" if (imp_cur and imp_prev) else imp_cur
                if total_ttm and imp_ttm:
                    return f"IFERROR({total_ttm}-({imp_ttm}),{total_ttm})"
            return total_ttm
        return None

    def _build_da_annual(self, year: int) -> Optional[str]:
        """Construye referencia anual para Depreciación+Amortización evitando doble conteo (con fallback EN)."""
        col = self.find_year_column(self.sh_pl, year)
        # 1) Combinada
        row_depam = self.rows_pl.get("DepAmort") or self._find_row_by_regex_in_pl(r"\bdepreciation and amorti[sz]ation(?:\s+expense)?\b")
        if row_depam:
            ref = self.create_cell_reference(self.sh_pl.title, col, row_depam)
            if ref:
                return ref
        # 2) Separadas
        row_dep = self.rows_pl.get("Dep") or self._find_row_by_regex_in_pl(r"\bdepreciation(?:\s+expense)?\b")
        row_amort = self.rows_pl.get("Amort") or self._find_row_by_regex_in_pl(r"\bamorti[sz]ation(?:\s+expense)?\b")
        dep = self.create_cell_reference(self.sh_pl.title, col, row_dep) if row_dep else None
        amort = self.create_cell_reference(self.sh_pl.title, col, row_amort) if row_amort else None
        if dep and amort:
            if dep == amort:
                return dep
            return f"IFERROR({dep},0)+IFERROR({amort},0)"
        if dep or amort:
            return dep or amort
        # 3) Fallback: Total D&A+impairment - impairment
        row_total_dai = self._find_row_by_regex_in_pl(r"^total depreciation, amorti[sz]ation and impairment .*profit or loss$")
        row_impair = self._find_row_by_regex_in_pl(r"^impairment loss \(reversal of impairment loss\) recognised in profit or loss$")
        total = self.create_cell_reference(self.sh_pl.title, col, row_total_dai) if row_total_dai else None
        if total and row_impair:
            imp = self.create_cell_reference(self.sh_pl.title, col, row_impair)
            if imp:
                return f"IFERROR({total}-({imp}),{total})"
        return total

    def _map_cash_flow_rows(self) -> Dict[str, Optional[int]]:
        """Mapea conceptos del flujo de efectivo a números de fila."""
        concepts = {
            "CFO": "Flujos de efectivo netos procedentes de (utilizados en) actividades de operación",
            "CFI": "Flujos de efectivo netos procedentes de (utilizados en) actividades de inversión",
            "CFF": "Flujos de efectivo netos procedentes de (utilizados en) actividades de financiación",
            "CapexBuy": "Compras de propiedades, planta y equipo",
            "CapexSale": "Importes procedentes de la venta de propiedades, planta y equipo",
            "IntangBuy": "Compras de activos intangibles",
            "IntangSale": "Importes procedentes de ventas de activos intangibles",
            "DivPag": "Dividendos pagados",
            "DivRec": "Dividendos recibidos",
            "IntPag": "Intereses pagados",
            "IntRec": "Intereses recibidos",
            "ImpPag": "Impuestos a las ganancias pagados (reembolsados)",
            "EmisPrest": "Importes procedentes de préstamos",
            "ReembPrest": "Reembolsos de préstamos",
            "EmisAcc": "Importes procedentes de la emisión de acciones",
            "CompAcc": "Pagos por adquirir o rescatar las acciones de la entidad",
            "PagArrend": "Pagos de pasivos por arrendamientos",
            "CobrosVenta": "Cobros procedentes de las ventas de bienes y prestación de servicios",
            "PagosProveed": "Pagos a proveedores por el suministro de bienes y servicios",
            "PagosEmpl": "Pagos a y por cuenta de los empleados",
            "EfecInic": "Efectivo y equivalentes al efectivo al principio del periodo",
            "EfecFinal": "Efectivo y equivalentes al efectivo al final del periodo",
            "VarEfec": "Incremento (disminución) neto de efectivo y equivalentes al efectivo"
        }

        df_cfs = self.financial_data.get("_df_cfs")
        if df_cfs is None:
            return {key: None for key in concepts.keys()}

        return {key: self._find_row_in_sheet(self.sh_cfs, df_cfs, concept)
                for key, concept in concepts.items()}
