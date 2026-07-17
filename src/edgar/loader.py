"""Carga de estados financieros de EEUU a Postgres (financial_line_items / financial_data).

Las mismas dos tablas que usan las chilenas: son un EAV genérico, no tienen nada de CMF
ni de IFRS en las columnas. No se crea ni se altera ninguna tabla acá.

Reglas que no se negocian:

* **Nunca purga.** No hay DELETE. Sólo INSERT ... ON CONFLICT DO UPDATE. Una línea que
  desaparece del origen sobrevive en la BD con su `updated_at` viejo, y así es como tiene
  que ser: ese `updated_at` es lo primero que hay que mirar cuando un número no cuadra.
* **`currency` explícito en 'USD'.** El default de la columna es 'CLP' por herencia; sin
  pasarlo, los estados de Apple quedarían etiquetados en pesos chilenos (spec §4).
* **Idempotente.** Correr dos veces no duplica ni cambia valores.
"""

from src.edgar.models import LineValue

# Todas las filas de EEUU van en dólares, incluidas las que no son plata (número de
# acciones) y las que son por acción. Es lo mismo que hacen las chilenas, que llevan CLP
# hasta en "Total número de acciones emitidas", y además `financial_data` tiene un CHECK
# que sólo admite CLP o USD: no hay dónde poner 'shares'. La unidad fina del concepto vive
# en el catálogo (`Concept.unit`), no en esta columna.
CURRENCY_US = "USD"


class EdgarLoader:
    def __init__(self, conn, dry_run: bool = True):
        self.conn = conn
        self.dry_run = dry_run

    def company_by_cik(self, cik: str) -> tuple[int, str] | None:
        """(company_id, ticker) de una empresa de EEUU por CIK, o None.

        Filtra por `market = 'US'` a propósito: una query sin ese filtro mezcla emisores
        chilenos y gringos (spec §3). Este repo NO inventa filas en `companies` — si el
        CIK no está, se siembra desde la web con `seed-us-companies.mjs`, porque el ticker
        tiene un UNIQUE global y una fila creada a ciegas puede chocar.
        """
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, ticker FROM companies WHERE market = 'US' AND cik = %s",
                (cik,),
            )
            row = cur.fetchone()
            return (int(row[0]), row[1]) if row else None

    def upsert_line_items(
        self, company_id: int, values: list[LineValue], tags_by_concept: dict[str, str]
    ) -> dict[int, int]:
        """Crea/actualiza las líneas de la empresa. Devuelve {display_order: line_item_id}.

        Las line items son POR EMPRESA (cada emisor usa su subconjunto de us-gaap), y su
        identidad es `(company_id, display_order)`, no el label: el label puede cambiar y
        si fuera la identidad, un rename partiría la cuenta en dos filas — que es
        exactamente el bug que ya pasó con la CMF.
        """
        by_order: dict[int, LineValue] = {}
        for value in values:
            by_order.setdefault(value.display_order, value)

        mapping: dict[int, int] = {}
        if self.dry_run:
            return {order: -order for order in by_order}

        sql = """
            INSERT INTO financial_line_items
                (company_id, label, role_code, category, subcategory, display_order,
                 source_tag, source_label)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (company_id, display_order) DO UPDATE SET
                label = EXCLUDED.label,
                role_code = EXCLUDED.role_code,
                category = EXCLUDED.category,
                subcategory = EXCLUDED.subcategory,
                source_tag = EXCLUDED.source_tag,
                source_label = EXCLUDED.source_label,
                updated_at = now()
            RETURNING id, display_order
        """
        with self.conn.cursor() as cur:
            for order, value in sorted(by_order.items()):
                cur.execute(
                    sql,
                    (
                        company_id,
                        value.label_es,
                        value.role_code,
                        value.category,
                        value.subcategory,
                        order,
                        tags_by_concept.get(value.concept_key, value.tag),
                        value.label_en,
                    ),
                )
                row = cur.fetchone()
                mapping[int(row[1])] = int(row[0])
        return mapping

    def upsert_financial_data(
        self, company_id: int, values: list[LineValue], ids_by_order: dict[int, int]
    ) -> int:
        """Upsert de las celdas. Idempotente por (company_id, line_item_id, year, quarter)."""
        records = [
            (
                company_id,
                ids_by_order[v.display_order],
                v.year,
                v.quarter,
                v.value,
                CURRENCY_US,
            )
            for v in values
            if v.display_order in ids_by_order
        ]
        if self.dry_run or not records:
            return len(records)

        from psycopg2.extras import execute_values

        with self.conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO financial_data
                    (company_id, line_item_id, period_year, period_quarter, value, currency)
                VALUES %s
                ON CONFLICT (company_id, line_item_id, period_year, period_quarter)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    currency = EXCLUDED.currency,
                    updated_at = now()
                """,
                records,
                page_size=1000,
            )
        return len(records)

    def log_import(
        self, company_id: int, source: str, total: int, ok: int, status: str,
        error: str | None = None,
    ) -> None:
        if self.dry_run:
            return
        with self.conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO financial_data_imports
                    (company_id, file_name, total_records, successful_records,
                     failed_records, import_status, error_log, imported_by, completed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, now())
                """,
                (company_id, source, total, ok, total - ok, status, error, "ingest_edgar"),
            )

    def has_source_columns(self) -> bool:
        """¿Está aplicada la migración que agrega source_tag/source_label?"""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) FROM information_schema.columns
                WHERE table_name = 'financial_line_items'
                  AND column_name IN ('source_tag', 'source_label')
                """
            )
            return cur.fetchone()[0] == 2

    def count_rows(self, market: str) -> tuple[int, int]:
        """(line_items, financial_data) de un mercado. Para el conteo antes/después que
        pide el §8.6: las chilenas tienen que quedar intactas."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                  (SELECT count(*) FROM financial_line_items li
                     JOIN companies c ON c.id = li.company_id WHERE c.market = %s),
                  (SELECT count(*) FROM financial_data fd
                     JOIN companies c ON c.id = fd.company_id WHERE c.market = %s)
                """,
                (market, market),
            )
            row = cur.fetchone()
            return int(row[0]), int(row[1])
