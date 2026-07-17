"""Carga de data de bancos a Postgres (tablas bank_*)."""

import json
from pathlib import Path

from src.banks.models import (
    AccountRow, CapitalAdequacy, Executive, Institution, Profile, Shareholder,
)


class BankLoader:
    def __init__(self, conn):
        self.conn = conn

    def apply_schema(self, sql_path: str = "sql/bank_schema.sql") -> None:
        sql = Path(sql_path).read_text()
        with self.conn.cursor() as cur:
            cur.execute(sql)

    def upsert_institution(
        self, inst: Institution, rut: str | None = None, is_aggregate: bool = False
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_institutions
                    (codigo_institucion, nombre_institucion, rut, is_aggregate)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (codigo_institucion) DO UPDATE SET
                    nombre_institucion = EXCLUDED.nombre_institucion,
                    rut = COALESCE(EXCLUDED.rut, bank_institutions.rut),
                    is_aggregate = EXCLUDED.is_aggregate,
                    updated_at = now()
                """,
                (inst.codigo_institucion, inst.nombre_institucion, rut, is_aggregate),
            )

    def upsert_account(
        self, statement: str, codigo_cuenta: str, descripcion: str, epoch: str
    ) -> int:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_accounts
                    (statement, codigo_cuenta, descripcion_cuenta, taxonomy_epoch)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (statement, codigo_cuenta, taxonomy_epoch) DO UPDATE SET
                    descripcion_cuenta = EXCLUDED.descripcion_cuenta,
                    updated_at = now()
                RETURNING id
                """,
                (statement, codigo_cuenta, descripcion, epoch),
            )
            return cur.fetchone()[0]

    def upsert_financial_row(
        self, cod: str, account_id: int, year: int, month: int,
        row: AccountRow, epoch: str, unit: str,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_financial_data
                    (codigo_institucion, account_id, period_year, period_month,
                     moneda_no_reajustable, moneda_reajustable_ipc, moneda_reajustable_tc,
                     moneda_extranjera, moneda_total, taxonomy_epoch, unit)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_institucion, account_id, period_year, period_month)
                DO UPDATE SET
                    moneda_no_reajustable = EXCLUDED.moneda_no_reajustable,
                    moneda_reajustable_ipc = EXCLUDED.moneda_reajustable_ipc,
                    moneda_reajustable_tc = EXCLUDED.moneda_reajustable_tc,
                    moneda_extranjera = EXCLUDED.moneda_extranjera,
                    moneda_total = EXCLUDED.moneda_total,
                    taxonomy_epoch = EXCLUDED.taxonomy_epoch,
                    unit = EXCLUDED.unit,
                    updated_at = now()
                """,
                (cod, account_id, year, month,
                 row.moneda_no_reajustable, row.moneda_reajustable_ipc,
                 row.moneda_reajustable_tc, row.moneda_extranjera, row.moneda_total,
                 epoch, unit),
            )

    def upsert_accounts_bulk(
        self, statement: str, rows: list[AccountRow], epoch: str
    ) -> dict[str, int]:
        """Upsert de todas las cuentas de un statement en un solo round-trip.

        Devuelve {codigo_cuenta: account_id}. Deduplica por codigo_cuenta: Postgres
        aborta un ON CONFLICT DO UPDATE que toque la misma fila dos veces en el mismo
        statement, y el API a veces repite un codigo dentro del mismo payload.
        """
        if not rows:
            return {}
        from psycopg2.extras import execute_values

        dedup: dict[str, AccountRow] = {}
        for row in rows:
            dedup[row.codigo_cuenta] = row
        # Ordenado por la clave de conflicto a propósito: el catálogo de cuentas es
        # compartido por todos los bancos, así que con --workers varios procesos hacen
        # ON CONFLICT sobre las mismas filas. Si cada uno las tomara en el orden en que
        # vienen del payload, dos podrían lockearlas en orden distinto y deadlockear.
        values = sorted(
            (statement, r.codigo_cuenta, r.descripcion_cuenta, epoch)
            for r in dedup.values()
        )
        with self.conn.cursor() as cur:
            result = execute_values(
                cur,
                """
                INSERT INTO bank_accounts
                    (statement, codigo_cuenta, descripcion_cuenta, taxonomy_epoch)
                VALUES %s
                ON CONFLICT (statement, codigo_cuenta, taxonomy_epoch) DO UPDATE SET
                    descripcion_cuenta = EXCLUDED.descripcion_cuenta,
                    updated_at = now()
                RETURNING codigo_cuenta, id
                """,
                values,
                fetch=True,
            )
            return {codigo: account_id for codigo, account_id in result}

    def upsert_financial_rows_bulk(
        self, cod: str, year: int, month: int,
        rows: list[tuple[int, AccountRow]], epoch: str, unit: str,
    ) -> int:
        """Upsert de las filas financieras de un banco/período en un round-trip.

        ``rows`` son pares (account_id, AccountRow). Deduplica por account_id por la
        misma razón que upsert_accounts_bulk.
        """
        if not rows:
            return 0
        from psycopg2.extras import execute_values

        dedup: dict[int, AccountRow] = {}
        for account_id, row in rows:
            dedup[account_id] = row
        values = [
            (cod, account_id, year, month, r.moneda_no_reajustable,
             r.moneda_reajustable_ipc, r.moneda_reajustable_tc, r.moneda_extranjera,
             r.moneda_total, epoch, unit)
            for account_id, r in dedup.items()
        ]
        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO bank_financial_data
                    (codigo_institucion, account_id, period_year, period_month,
                     moneda_no_reajustable, moneda_reajustable_ipc,
                     moneda_reajustable_tc, moneda_extranjera, moneda_total,
                     taxonomy_epoch, unit)
                VALUES %s
                ON CONFLICT (codigo_institucion, account_id, period_year, period_month)
                DO UPDATE SET
                    moneda_no_reajustable = EXCLUDED.moneda_no_reajustable,
                    moneda_reajustable_ipc = EXCLUDED.moneda_reajustable_ipc,
                    moneda_reajustable_tc = EXCLUDED.moneda_reajustable_tc,
                    moneda_extranjera = EXCLUDED.moneda_extranjera,
                    moneda_total = EXCLUDED.moneda_total,
                    taxonomy_epoch = EXCLUDED.taxonomy_epoch,
                    unit = EXCLUDED.unit,
                    updated_at = now()
                """,
                values,
            )
        return len(values)

    def upsert_capital_adequacy(
        self, cod: str, year: int, month: int, ca: CapitalAdequacy
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_capital_adequacy
                    (codigo_institucion, period_year, period_month,
                     activos_ponderados_riesgo, activos_totales, capital_basico,
                     patrimonio_efectivo, provisiones_voluntarias, bonos_subordinados,
                     interes_minoritario, indice_irs, indice_ire, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (codigo_institucion, period_year, period_month) DO UPDATE SET
                    activos_ponderados_riesgo = EXCLUDED.activos_ponderados_riesgo,
                    activos_totales = EXCLUDED.activos_totales,
                    capital_basico = EXCLUDED.capital_basico,
                    patrimonio_efectivo = EXCLUDED.patrimonio_efectivo,
                    provisiones_voluntarias = EXCLUDED.provisiones_voluntarias,
                    bonos_subordinados = EXCLUDED.bonos_subordinados,
                    interes_minoritario = EXCLUDED.interes_minoritario,
                    indice_irs = EXCLUDED.indice_irs,
                    indice_ire = EXCLUDED.indice_ire,
                    raw = EXCLUDED.raw,
                    updated_at = now()
                """,
                (cod, year, month, ca.activos_ponderados_riesgo, ca.activos_totales,
                 ca.capital_basico, ca.patrimonio_efectivo, ca.provisiones_voluntarias,
                 ca.bonos_subordinados, ca.interes_minoritario, ca.indice_irs,
                 ca.indice_ire, json.dumps(ca.raw)),
            )

    def upsert_profile(self, cod: str, year: int, month: int, p: Profile) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_profiles
                    (codigo_institucion, period_year, period_month, codigo_swift, rut,
                     direccion, telefono, sitio_web, sucursales, oficinas, cajeros,
                     empleados, emp_hombres_perm, emp_mujeres_perm, emp_hombres_ext,
                     emp_mujeres_ext, fecha_publicacion, raw)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s)
                ON CONFLICT (codigo_institucion, period_year, period_month) DO UPDATE SET
                    codigo_swift = EXCLUDED.codigo_swift, rut = EXCLUDED.rut,
                    direccion = EXCLUDED.direccion, telefono = EXCLUDED.telefono,
                    sitio_web = EXCLUDED.sitio_web, sucursales = EXCLUDED.sucursales,
                    oficinas = EXCLUDED.oficinas, cajeros = EXCLUDED.cajeros,
                    empleados = EXCLUDED.empleados,
                    emp_hombres_perm = EXCLUDED.emp_hombres_perm,
                    emp_mujeres_perm = EXCLUDED.emp_mujeres_perm,
                    emp_hombres_ext = EXCLUDED.emp_hombres_ext,
                    emp_mujeres_ext = EXCLUDED.emp_mujeres_ext,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    raw = EXCLUDED.raw, updated_at = now()
                """,
                (cod, year, month, p.codigo_swift, p.rut, p.direccion, p.telefono,
                 p.sitio_web, p.sucursales, p.oficinas, p.cajeros, p.empleados,
                 p.emp_hombres_perm, p.emp_mujeres_perm, p.emp_hombres_ext,
                 p.emp_mujeres_ext, p.fecha_publicacion or None, json.dumps(p.raw)),
            )

    def replace_shareholders(
        self, cod: str, year: int, month: int, rows: list[Shareholder]
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bank_shareholders WHERE codigo_institucion=%s "
                "AND period_year=%s AND period_month=%s", (cod, year, month),
            )
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO bank_shareholders
                        (codigo_institucion, period_year, period_month, serie, rut,
                         nombre, participacion, numero_acciones)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codigo_institucion, period_year, period_month, rut, serie)
                    DO NOTHING
                    """,
                    (cod, year, month, r.serie, r.rut, r.nombre, r.participacion,
                     r.numero_acciones),
                )

    def replace_executives(
        self, cod: str, year: int, month: int, rows: list[Executive]
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bank_executives WHERE codigo_institucion=%s "
                "AND period_year=%s AND period_month=%s", (cod, year, month),
            )
            for r in rows:
                cur.execute(
                    """
                    INSERT INTO bank_executives
                        (codigo_institucion, period_year, period_month, nombre, cargo,
                         fecha_asuncion, tipo)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (codigo_institucion, period_year, period_month, nombre, cargo)
                    DO NOTHING
                    """,
                    (cod, year, month, r.nombre, r.cargo, r.fecha_asuncion or None, r.tipo),
                )

    def log_import(
        self, cod: str | None, report: str, year: int | None, month: int | None,
        status: str, rows_total: int = 0, rows_ok: int = 0, rows_failed: int = 0,
        message: str | None = None,
    ) -> None:
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bank_data_imports
                    (codigo_institucion, report, period_year, period_month, status,
                     rows_total, rows_ok, rows_failed, message, finished_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (cod, report, year, month, status, rows_total, rows_ok, rows_failed,
                 message),
            )
