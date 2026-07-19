#!/usr/bin/env python3
"""Puebla shares_outstanding, market_cap y beta de las empresas US.

El plan Basic de Marketstack no entrega fundamentales y el poblador de Yahoo está atado a
Chile (fuerza sufijo .SN) y es inestable. Así que estos tres campos se DERIVAN de datos que
ya tenemos, sin depender de Yahoo:

- **shares**: el último "Total número de acciones emitidas" (CommonStockSharesOutstanding,
  de EDGAR) en financial_data. En UNIDADES.
- **market_cap**: precio (stock_quotes) × shares. En la moneda del precio (USD).
- **beta**: regresión de los retornos diarios de la acción contra el ^GSPC (S&P 500), la
  ventana de ~3 años más reciente. beta = Cov(r_accion, r_mercado) / Var(r_mercado).

Escribe en companies.shares_outstanding / yahoo_market_cap / yahoo_beta (lo que lee el motor
DCF) y también en stock_quotes (market_cap/shares_outstanding/beta, que lee la web). DRY-RUN
por defecto; --apply escribe. Con --only <ids/tickers> se limita a algunas empresas.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import psycopg2

FDC = Path(os.environ.get("FDC_DIR", "/home/unzzui/Proyectos/FinDataChile"))
_VENTANA = 1300  # ~5 años de días hábiles (se resamplea a mensual)
_MIN_MESES = 24  # mínimo de retornos MENSUALES solapados para una beta creíble


def load_env(path: Path) -> dict[str, str]:
    env = {}
    for line in path.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _cierres(cur, company_id: int) -> dict:
    cur.execute(
        "SELECT trade_date, close FROM stock_price_history "
        "WHERE company_id = %s AND close > 0 ORDER BY trade_date DESC LIMIT %s",
        [company_id, _VENTANA])
    return {d: float(c) for d, c in cur.fetchall()}


def _cierres_benchmark(cur) -> dict:
    cur.execute(
        "SELECT trade_date, close FROM stock_price_history "
        "WHERE symbol = '^GSPC' AND close > 0 ORDER BY trade_date DESC LIMIT %s",
        [_VENTANA])
    return {d: float(c) for d, c in cur.fetchall()}


def _mensual(cierres: dict) -> dict:
    """Resamplea cierres diarios a MENSUAL: el último cierre de cada (año, mes).

    La beta mensual es la práctica estándar (Yahoo/Bloomberg): los retornos diarios traen
    ruido de microestructura y sesgan la beta hacia abajo en las acciones defensivas (KO
    daba 0,04 con diarios). El cierre mensual promedia ese ruido.
    """
    ult: dict[tuple[int, int], tuple] = {}
    for d, c in cierres.items():
        k = (d.year, d.month)
        if k not in ult or d > ult[k][0]:
            ult[k] = (d, c)
    return {k: v[1] for k, v in ult.items()}


def beta(cur, company_id: int, bench_m: dict) -> float | None:
    stock_m = _mensual(_cierres(cur, company_id))
    meses = sorted(set(stock_m) & set(bench_m))  # (año,mes) con ambos
    if len(meses) < _MIN_MESES + 1:
        return None
    rs, rm = [], []
    for i in range(1, len(meses)):
        s0, s1 = stock_m[meses[i - 1]], stock_m[meses[i]]
        m0, m1 = bench_m[meses[i - 1]], bench_m[meses[i]]
        if s0 > 0 and m0 > 0:
            rs.append(s1 / s0 - 1)
            rm.append(m1 / m0 - 1)
    if len(rs) < _MIN_MESES:
        return None
    n = len(rs)
    ma = sum(rs) / n
    mb = sum(rm) / n
    cov = sum((a - ma) * (b - mb) for a, b in zip(rs, rm)) / n
    var = sum((b - mb) ** 2 for b in rm) / n
    if var <= 0:
        return None
    return cov / var


def shares(cur, company_id: int) -> float | None:
    cur.execute(
        """
        SELECT fd.value FROM financial_data fd
        JOIN financial_line_items fli ON fd.line_item_id = fli.id
        WHERE fli.company_id = %s
          AND (LOWER(TRIM(fli.label)) = 'total número de acciones emitidas'
               OR fli.source_tag IN ('CommonStockSharesOutstanding','CommonStockSharesIssued'))
          AND fd.value IS NOT NULL AND fd.value > 0
        ORDER BY fd.period_year DESC, fd.period_quarter DESC
        LIMIT 1
        """,
        [company_id])
    r = cur.fetchone()
    return float(r[0]) if r else None


def precio(cur, company_id: int) -> float | None:
    cur.execute("SELECT price FROM stock_quotes WHERE company_id = %s AND price > 0", [company_id])
    r = cur.fetchone()
    if r:
        return float(r[0])
    # Fallback: el último cierre de la historia. Las recién backfilleadas tienen historia
    # pero todavía no stock_quotes.price (eso lo pone el cron us-eod en su próxima corrida).
    cur.execute("SELECT close FROM stock_price_history WHERE company_id = %s AND close > 0 "
                "ORDER BY trade_date DESC LIMIT 1", [company_id])
    r = cur.fetchone()
    return float(r[0]) if r else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Escribir (default: dry-run)")
    ap.add_argument("--only", default="", help="IDs o tickers separados por coma")
    args = ap.parse_args()

    env = load_env(FDC / ".env")
    conn = psycopg2.connect(host=env["PGHOST"], port=env.get("PGPORT", 5432),
                            dbname=env["PGDATABASE"], user=env["PGUSER"],
                            password=env["PGPASSWORD"], sslmode="require")
    cur = conn.cursor()

    q = "SELECT id, ticker FROM companies WHERE market='US' AND cik IS NOT NULL"
    params: list = []
    if args.only:
        toks = [t.strip() for t in args.only.split(",") if t.strip()]
        ids = [int(t) for t in toks if t.isdigit()]
        tks = [t.upper() for t in toks if not t.isdigit()]
        q += " AND (id = ANY(%s) OR UPPER(ticker) = ANY(%s))"
        params = [ids, tks]
    q += " ORDER BY id"
    cur.execute(q, params)
    empresas = cur.fetchall()

    bench_m = _mensual(_cierres_benchmark(cur))
    print(f"US: {len(empresas)} | ^GSPC meses: {len(bench_m)} | modo: {'APPLY' if args.apply else 'DRY-RUN'}")

    n_sh = n_mc = n_b = 0
    for cid, ticker in empresas:
        sh = shares(cur, cid)
        px = precio(cur, cid)
        mc = (px * sh) if (px and sh) else None
        b = beta(cur, cid, bench_m)
        if sh:
            n_sh += 1
        if mc:
            n_mc += 1
        if b is not None:
            n_b += 1
        print(f"  {str(ticker):6} shares={sh/1e9 if sh else 0:6.2f}B  precio={px or 0:8.2f}  "
              f"mcap={mc/1e9 if mc else 0:8.1f}B  beta={b if b is not None else '—'}")
        if args.apply and (sh or mc or b is not None):
            cur.execute(
                """
                UPDATE companies SET
                  shares_outstanding = COALESCE(%s, shares_outstanding),
                  yahoo_market_cap   = COALESCE(%s, yahoo_market_cap),
                  yahoo_beta         = COALESCE(%s, yahoo_beta)
                WHERE id = %s
                """,
                [sh, mc, b, cid])
            cur.execute(
                """
                UPDATE stock_quotes SET
                  shares_outstanding = COALESCE(%s, shares_outstanding),
                  market_cap = COALESCE(%s, market_cap),
                  beta = COALESCE(%s, beta)
                WHERE company_id = %s
                """,
                [sh, mc, b, cid])
    if args.apply:
        conn.commit()

    conn.close()
    print(f"\nshares: {n_sh}/{len(empresas)}  ·  market_cap: {n_mc}  ·  beta: {n_b}")
    if not args.apply:
        print("DRY-RUN: nada escrito. Repetí con --apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
