"""Lectura de las tablas bank_* para armar la data de un banco.

Cobertura compendio 2022 (mensual). Devuelve estructuras en memoria que el generador
del workbook consume. No depende de openpyxl.
"""

from dataclasses import dataclass, field


@dataclass
class Account:
    codigo: str
    descripcion: str


@dataclass
class BankData:
    codigo_institucion: str
    nombre: str
    rut: str | None
    swift: str | None
    periods: list[tuple[int, int]]                      # (year, month) ascendente
    balance_accounts: list[Account]                     # orden por codigo
    resultado_accounts: list[Account]
    balance_values: dict[tuple[str, tuple[int, int]], float | None]
    resultado_values: dict[tuple[str, tuple[int, int]], float | None]
    capital: dict[tuple[int, int], dict]                # (y,m) -> {irs, ire, capital_basico, ...}
    profile: dict                                       # ultima ficha
    market: dict = field(default_factory=dict)          # de companies: beta, market_cap, shares
    row_of: dict = field(default_factory=dict)          # (statement, codigo) -> fila Excel (lo llena workbook)
    col_of: dict = field(default_factory=dict)          # (y,m) -> letra de columna (lo llena workbook)


def _accounts_and_values(cur, cod, statement, epoch):
    cur.execute(
        """
        SELECT a.codigo_cuenta, a.descripcion_cuenta, fd.period_year, fd.period_month,
               fd.moneda_total
        FROM bank_financial_data fd
        JOIN bank_accounts a ON a.id = fd.account_id
        WHERE fd.codigo_institucion = %s AND a.statement = %s
          AND a.taxonomy_epoch = %s
        ORDER BY a.codigo_cuenta
        """,
        (cod, statement, epoch),
    )
    accounts: dict[str, str] = {}
    values: dict[tuple[str, tuple[int, int]], float | None] = {}
    periods: set[tuple[int, int]] = set()
    for codigo, descripcion, y, m, total in cur.fetchall():
        accounts.setdefault(codigo, descripcion)
        values[(codigo, (y, m))] = float(total) if total is not None else None
        periods.add((y, m))
    ordered = [Account(c, accounts[c]) for c in sorted(accounts)]
    return ordered, values, periods


def read_bank(conn, cod: str, epoch: str = "compendio_2022") -> BankData:
    cur = conn.cursor()

    cur.execute(
        "SELECT nombre_institucion, rut, codigo_swift FROM bank_institutions "
        "WHERE codigo_institucion = %s",
        (cod,),
    )
    row = cur.fetchone()
    nombre, rut, swift = row if row else (cod, None, None)

    bal_acc, bal_val, bal_periods = _accounts_and_values(cur, cod, "balance", epoch)
    res_acc, res_val, res_periods = _accounts_and_values(cur, cod, "resultado", epoch)
    periods = sorted(bal_periods | res_periods)

    cur.execute(
        """
        SELECT period_year, period_month, indice_irs, indice_ire, capital_basico,
               patrimonio_efectivo, activos_ponderados_riesgo
        FROM bank_capital_adequacy WHERE codigo_institucion = %s
        """,
        (cod,),
    )
    capital: dict[tuple[int, int], dict] = {}
    for y, m, irs, ire, capbas, pat_ef, apr in cur.fetchall():
        capital[(y, m)] = {
            "irs": float(irs) if irs is not None else None,
            "ire": float(ire) if ire is not None else None,
            "capital_basico": float(capbas) if capbas is not None else None,
            "patrimonio_efectivo": float(pat_ef) if pat_ef is not None else None,
            "apr": float(apr) if apr is not None else None,
        }

    cur.execute(
        """
        SELECT codigo_swift, rut, direccion, telefono, sitio_web, sucursales, oficinas,
               cajeros, empleados, fecha_publicacion
        FROM bank_profiles WHERE codigo_institucion = %s
        ORDER BY period_year DESC, period_month DESC LIMIT 1
        """,
        (cod,),
    )
    p = cur.fetchone()
    profile: dict = {}
    if p:
        keys = ["swift", "rut", "direccion", "telefono", "sitio_web", "sucursales",
                "oficinas", "cajeros", "empleados", "fecha_publicacion"]
        profile = dict(zip(keys, p))

    # bank_institutions.rut suele venir vacio (el sync no lo setea); el perfil trae el RUT.
    if not rut and profile.get("rut"):
        rut = profile["rut"]
    # companies.rut va sin puntos ("97004000-5"); el del perfil viene con puntos.
    rut = rut.replace(".", "") if rut else None

    market: dict = {}
    if rut:
        cur.execute(
            "SELECT yahoo_beta, yahoo_market_cap, shares_outstanding, yahoo_current_price "
            "FROM companies WHERE rut = %s",
            (rut,),
        )
        c = cur.fetchone()
        if c:
            market = {
                "beta": float(c[0]) if c[0] is not None else None,
                "market_cap": float(c[1]) if c[1] is not None else None,
                "shares": float(c[2]) if c[2] is not None else None,
                "price": float(c[3]) if c[3] is not None else None,
            }

    cur.close()
    return BankData(
        codigo_institucion=cod, nombre=nombre, rut=rut, swift=swift, periods=periods,
        balance_accounts=bal_acc, resultado_accounts=res_acc,
        balance_values=bal_val, resultado_values=res_val, capital=capital,
        profile=profile, market=market,
    )
