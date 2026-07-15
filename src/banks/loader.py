"""Carga de data de bancos a Postgres (tablas bank_*)."""

from pathlib import Path

from src.banks.models import AccountRow, Institution


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
