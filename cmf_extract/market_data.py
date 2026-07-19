"""Datos de mercado (beta de Yahoo) desde la BD de FinDataChile, por RUT.

El Excel es autocontenido del XBRL, pero el WACC necesita el beta de Yahoo para
CUADRAR con lo que muestra la web (que sale del mismo beta, en
``scripts/dcf/excel_aligned.calculate_wacc_excel``).

Este módulo hace un lookup por RUT a ``companies.yahoo_beta`` con DEGRADACIÓN
ELEGANTE: si la BD no está disponible, si falta el .env, o si la empresa no tiene
beta, devuelve ``None`` y el DCF cae a beta 1.0 — pero con un aviso VISIBLE en la
celda "Fuente del beta" del Excel (``DCFBuilder._beta_fuente``). Nunca un fallback
silencioso: el North Star pide que un supuesto se nombre, no que se esconda.

La conexión se abre una sola vez y los resultados se cachean por RUT: en un batch
de 218 empresas no se pega 218 veces a la BD por cada hoja.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, Optional

# El .env con las credenciales PG de FinDataChile (mismo que usan
# scripts/upload_to_supabase.py y scripts/refresh_ratios_dcf.py). Editable por env var.
_FDC_ENV = Path(os.environ.get("FDC_ENV", "/home/unzzui/Proyectos/FinDataChile/.env"))

# Cache por RUT para todo el proceso: dict {"beta": float|None, "shares": float|None}.
_cache: Dict[str, Dict[str, Optional[float]]] = {}
_deuda_cache: Dict[str, Optional[dict]] = {}
_avisado_sin_bd = False


def _load_pg_env(path: Path) -> Dict[str, str]:
    env: Dict[str, str] = {}
    try:
        for line in path.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                k = k.strip()
                if k.startswith("PG"):
                    env[k] = v.strip().strip('"').strip("'")
    except Exception:
        return {}
    return env


def _rut_from_filename(name: str) -> Optional[str]:
    """El RUT del nombre ``estados_<rut>_<rango>_<lang>.xlsx``."""
    m = re.match(r"^estados_(?P<rut>[^_]+)_", name, flags=re.I)
    return m.group("rut") if m else None


def _lookup(file_path) -> Dict[str, Optional[float]]:
    """Trae ``{"beta", "shares"}`` de la BD para la empresa del archivo, cacheado por RUT.

    Ambos valores pueden ser ``None`` (empresa que no cotiza → sin beta; BD caída;
    empresa sin acciones cargadas). ``None`` es una respuesta válida: el que llama cae
    a un fallback y lo DICE, no inventa un número.
    """
    global _avisado_sin_bd
    empty: Dict[str, Optional[float]] = {"beta": None, "shares": None, "currency": None}
    try:
        name = Path(file_path).name
    except Exception:
        return empty
    rut = _rut_from_filename(name)
    if not rut:
        return empty
    if rut in _cache:
        return _cache[rut]

    result = dict(empty)
    try:
        import psycopg2  # dependencia opcional: si no está, se degrada
        env = _load_pg_env(_FDC_ENV)
        if not env.get("PGHOST"):
            if not _avisado_sin_bd:
                print("[dcf] AVISO: sin credenciales PG de FinDataChile; el beta del "
                      "WACC cae a Hamada y las acciones a la hoja RATIOS. Definí "
                      "FDC_ENV si querés el beta de Yahoo y las acciones de la BD.")
                _avisado_sin_bd = True
            _cache[rut] = result
            return result
        conn = psycopg2.connect(
            host=env["PGHOST"], port=env.get("PGPORT", 5432),
            dbname=env["PGDATABASE"], user=env["PGUSER"],
            password=env["PGPASSWORD"], sslmode="require", connect_timeout=5)
        rut_num = rut.split("-")[0]
        # El "rut" del nombre de archivo es un RUT chileno O, para EEUU, el CIK sin ceros
        # (las empresas US tienen rut NULL y cik). Se prueban ambos: rut exacto/por número
        # y cik (crudo o con ceros a 10 dígitos).
        cik_padded = rut_num.zfill(10)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, yahoo_beta, shares_outstanding, financial_statements_currency
                FROM companies
                WHERE rut = %s OR rut LIKE %s OR cik = %s OR cik = %s
                ORDER BY (yahoo_beta IS NULL)
                LIMIT 1
                """,
                [rut, f"{rut_num}-%", rut_num, cik_padded],
            )
            row = cur.fetchone()
            if row:
                company_id = int(row[0])
                result["beta"] = float(row[1]) if row[1] is not None else None
                result["shares"] = float(row[2]) if row[2] is not None else None
                result["currency"] = str(row[3]).upper() if row[3] else None
                # EEUU: companies.shares_outstanding viene NULL (la ingesta EDGAR no lo
                # puebla ahí). Las acciones están en financial_data como "Total número de
                # acciones emitidas" (CommonStockSharesOutstanding), en UNIDADES. Se toma el
                # período más reciente. Para Chile no se ejecuta: shares_outstanding ya vino.
                if result["shares"] is None:
                    cur.execute(
                        """
                        SELECT fd.value
                        FROM financial_data fd
                        JOIN financial_line_items fli ON fd.line_item_id = fli.id
                        WHERE fli.company_id = %s
                          AND (LOWER(TRIM(fli.label)) = 'total número de acciones emitidas'
                               OR fli.source_tag IN ('CommonStockSharesOutstanding',
                                                     'CommonStockSharesIssued'))
                          AND fd.value IS NOT NULL AND fd.value > 0
                        ORDER BY fd.period_year DESC, fd.period_quarter DESC
                        LIMIT 1
                        """,
                        [company_id],
                    )
                    srow = cur.fetchone()
                    if srow and srow[0] is not None:
                        result["shares"] = float(srow[0])
        conn.close()
    except Exception as exc:  # noqa: BLE001
        if not _avisado_sin_bd:
            print(f"[dcf] AVISO: no se pudo leer beta/acciones de la BD ({exc}); "
                  f"el WACC cae a Hamada y las acciones a la hoja RATIOS.")
            _avisado_sin_bd = True

    _cache[rut] = result
    return result


def get_yahoo_beta(file_path) -> Optional[float]:
    """Beta de Yahoo para la empresa del archivo, o ``None`` si no se puede obtener."""
    return _lookup(file_path).get("beta")


def get_shares_outstanding(file_path) -> Optional[float]:
    """Acciones en circulación (UNIDADES, companies.shares_outstanding), o ``None``.

    Es la fuente de verdad del XBRL, cubre las 218 empresas. Se usa como fallback del
    valor por acción del DCF cuando la hoja RATIOS no trae el número (para AGUAS, por
    ejemplo, la fila "Total número de acciones emitidas" viene vacía).
    """
    return _lookup(file_path).get("shares")


def get_currency(file_path) -> Optional[str]:
    """Moneda de reporte (companies.financial_statements_currency), o ``None``.

    Necesaria para las empresas de EEUU: sus estados vienen de la BD (EDGAR), no del XBRL
    de la CMF, así que el detector de moneda por facts no tiene de dónde leer y el DCF
    asumiría CLP. Con esto el DCF sabe que Apple reporta en USD y agrega la fila de tipo
    de cambio para comparar el valor por acción contra el precio de bolsa.
    """
    cur = _lookup(file_path).get("currency")
    return str(cur) if cur else None


def get_deuda_detalle(file_path) -> Optional[dict]:
    """Detalle de deuda declarada de EEUU para la hoja DEUDA FINANCIERA del Excel.

    Devuelve el mismo dict que el ``deuda.json`` chileno (kd, n_creditos, por_moneda,
    por_instrumento, creditos[...]) para que ``DCFBuilder`` construya la hoja crédito por
    crédito y use el Kd declarado — igual que Chile. SÓLO para EEUU: la deuda chilena la
    resuelve ``formula_processor._deuda_declarada`` (deuda.json local).

    Fuente: la tabla ``us_costo_deuda`` (columna ``detalle``, poblada por
    ``scripts/refresh_us_kd.py``). Si no hay fila y está la env ``EDGAR_UA``, se parsea el
    10-K en vivo (para una empresa suelta antes de poblar la BD). ``None`` si la empresa no
    taggea tasas o no se puede resolver → el DCF cae a la estimación y lo dice.
    """
    try:
        name = Path(file_path).name
    except Exception:
        return None
    rut = _rut_from_filename(name)
    if not rut:
        return None
    if rut in _deuda_cache:
        return _deuda_cache[rut]

    detalle: Optional[dict] = None
    company_id = None
    cik = None
    try:
        import psycopg2
        env = _load_pg_env(_FDC_ENV)
        if env.get("PGHOST"):
            conn = psycopg2.connect(
                host=env["PGHOST"], port=env.get("PGPORT", 5432),
                dbname=env["PGDATABASE"], user=env["PGUSER"],
                password=env["PGPASSWORD"], sslmode="require", connect_timeout=5)
            rut_num = rut.split("-")[0]
            cik_padded = rut_num.zfill(10)
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, cik FROM companies "
                    "WHERE market = 'US' AND (cik = %s OR cik = %s) LIMIT 1",
                    [rut_num, cik_padded])
                row = cur.fetchone()
                if row:
                    company_id, cik = int(row[0]), str(row[1])
                    # La tabla puede no existir todavía (migración 059 sin correr).
                    try:
                        cur.execute(
                            "SELECT detalle FROM us_costo_deuda WHERE company_id = %s "
                            "ORDER BY period_year DESC, period_quarter DESC LIMIT 1",
                            [company_id])
                        drow = cur.fetchone()
                        if drow and drow[0]:
                            detalle = drow[0] if isinstance(drow[0], dict) else None
                    except Exception:
                        conn.rollback()
            conn.close()
    except Exception:
        detalle = None

    # Fallback: parseo en vivo del 10-K (empresa US con cik y EDGAR_UA definido).
    if detalle is None and cik and os.environ.get("EDGAR_UA"):
        try:
            _ROOT = Path(__file__).resolve().parent.parent
            if str(_ROOT) not in sys.path:
                sys.path.insert(0, str(_ROOT))
            from src.edgar.api_client import EdgarClient
            from src.edgar import deuda as _edgar_deuda
            client = EdgarClient(user_agent=os.environ["EDGAR_UA"])
            r = _edgar_deuda.costo_de_deuda(client, cik)
            if r is not None:
                cd, _filing = r
                detalle = _edgar_deuda.a_dict_excel(cd)
        except Exception:
            detalle = None

    _deuda_cache[rut] = detalle
    return detalle
