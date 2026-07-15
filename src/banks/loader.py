"""Carga de data de bancos a Postgres (tablas bank_*)."""

from pathlib import Path


class BankLoader:
    def __init__(self, conn):
        self.conn = conn

    def apply_schema(self, sql_path: str = "sql/bank_schema.sql") -> None:
        sql = Path(sql_path).read_text()
        with self.conn.cursor() as cur:
            cur.execute(sql)
