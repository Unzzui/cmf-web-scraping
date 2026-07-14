#!/usr/bin/env python3
"""Fotografía del estado de la base después de una corrida del pipeline.

Responde las preguntas que uno se hace al día siguiente y que, si no se responden con
una consulta, se responden con una suposición:

  - ¿Cuántas empresas tienen datos, y hasta qué período?
  - ¿La moneda está bien? (24 en USD; una empresa mal etiquetada mueve sus múltiplos ~900x)
  - ¿Corrieron los ratios y el DCF, o quedaron de la corrida anterior?
  - ¿Hay empresas cuyos datos se actualizaron pero cuyos ratios NO?  ← lo importante

Esa última es la que importa: el upsert nunca purga, así que un ratio viejo sobrevive
callado al lado de un dato nuevo, y nadie lo nota hasta que un número no cuadra.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import psycopg2  # noqa: E402

from src.gui.pipeline.supabase_uploader import load_env_file, resolve_pg_conn  # noqa: E402


def main() -> int:
    env = load_env_file(Path.home() / "Proyectos" / "FinDataChile" / ".env")
    cfg = resolve_pg_conn(env)
    conn = psycopg2.connect(
        host=cfg["host"], port=int(cfg["port"]), dbname=cfg["dbname"],
        user=cfg["user"], password=cfg["password"], sslmode="require",
    )
    cur = conn.cursor()

    print("=" * 72)
    print("ESTADO DE LA BASE")
    print("=" * 72)

    cur.execute("SELECT count(DISTINCT company_id), count(*) FROM financial_data")
    empresas, filas = cur.fetchone()
    print(f"\nfinancial_data : {empresas} empresas, {filas:,} filas")

    cur.execute("""SELECT count(*) FROM financial_data
                   WHERE updated_at > now() - interval '12 hours'""")
    print(f"                 {cur.fetchone()[0]:,} filas tocadas en las últimas 12 h")

    print("\n--- moneda ---")
    cur.execute("""SELECT currency, count(DISTINCT company_id), count(*)
                   FROM financial_data GROUP BY 1 ORDER BY 2 DESC""")
    for moneda, emp, n in cur.fetchall():
        print(f"  {str(moneda):5}  {emp:>4} empresas  {n:>9,} filas")

    print("\n--- ratios y DCF ---")
    for tabla in ("financial_ratios", "dcf_analysis"):
        cur.execute(f"SELECT count(DISTINCT company_id), count(*) FROM {tabla}")
        emp, n = cur.fetchone()
        cur.execute(f"""SELECT count(*) FROM {tabla}
                        WHERE updated_at > now() - interval '12 hours'""")
        recientes = cur.fetchone()[0]
        print(f"  {tabla:18} {emp:>4} empresas  {n:>9,} filas  "
              f"({recientes:,} recalculadas en 12 h)")

    # La pregunta que de verdad importa: datos nuevos con ratios viejos.
    print("\n--- datos nuevos con ratios VIEJOS (el upsert nunca purga) ---")
    cur.execute("""
        SELECT c.razon_social,
               max(fd.updated_at)::date AS datos,
               max(fr.updated_at)::date AS ratios
        FROM companies c
        JOIN financial_data fd   ON fd.company_id = c.id
        LEFT JOIN financial_ratios fr ON fr.company_id = c.id
        GROUP BY c.id, c.razon_social
        HAVING max(fd.updated_at) > coalesce(max(fr.updated_at), '-infinity'::timestamptz)
                                    + interval '1 hour'
        ORDER BY 1
    """)
    desfasadas = cur.fetchall()
    if not desfasadas:
        print("  ninguna — los ratios están al día con los datos")
    else:
        print(f"  {len(desfasadas)} empresas con ratios más viejos que sus datos:")
        for nombre, datos, ratios in desfasadas[:15]:
            print(f"    {nombre[:44]:46} datos={datos}  ratios={ratios}")
        if len(desfasadas) > 15:
            print(f"    … y {len(desfasadas) - 15} más")

    print("\n--- empresas sin ratios o sin DCF ---")
    cur.execute("""
        SELECT count(*) FROM companies c
        WHERE EXISTS (SELECT 1 FROM financial_data fd WHERE fd.company_id = c.id)
          AND NOT EXISTS (SELECT 1 FROM financial_ratios fr WHERE fr.company_id = c.id)
    """)
    print(f"  con datos pero SIN ratios: {cur.fetchone()[0]}")
    cur.execute("""
        SELECT count(*) FROM companies c
        WHERE EXISTS (SELECT 1 FROM financial_data fd WHERE fd.company_id = c.id)
          AND NOT EXISTS (SELECT 1 FROM dcf_analysis d WHERE d.company_id = c.id)
    """)
    print(f"  con datos pero SIN DCF   : {cur.fetchone()[0]}")

    conn.close()
    print("\n" + "=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
