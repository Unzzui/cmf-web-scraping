#!/usr/bin/env python3
"""Mina el XBRL y lo carga a la base. Identidad, segmentos y deuda.

    python scripts/xbrl_a_base.py                 # dry-run: dice qué haría
    python scripts/xbrl_a_base.py --apply
    python scripts/xbrl_a_base.py --apply --empresas 93458000,61808000

POR QUÉ
-------
Le pedimos a Yahoo datos que la empresa ya declaró ante la CMF. Y para las 176 empresas
sin ticker, Yahoo NO TIENE NADA — el XBRL las cubre a las 218.

Lo que NO se puede rescatar de aquí, y hay que decirlo: el PRECIO de la acción y el BETA.
Son hechos de mercado. Ningún estado financiero dice a qué precio se transó la acción
ayer. Esos dos van a seguir necesitando una fuente externa.

LA ESCALA
---------
El XBRL trae los montos en UNIDADES de la moneda. `financial_data` los guarda en MILES.
Este cargador divide por 1000, para que las dos tablas se puedan comparar sin que nadie
tenga que acordarse de una excepción. Es la misma convención del resto del pipeline.
"""

from __future__ import annotations

import argparse
import collections
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras

from cmf_extract import xbrl_facts as xf
from cmf_extract import xbrl_deuda as xd

RAIZ_XBRL = Path(__file__).resolve().parent.parent / "data" / "XBRL" / "Total"

# El XBRL viene en unidades; la base, en miles.
ESCALA = 1000.0

_ULTIMO_DIA = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}

# ─────────────────────────────────────────────────────── Identidad
# Los conceptos que reemplazan a Yahoo. Entre paréntesis, en cuántas de las 74 empresas
# medidas está cada uno.
IDENTIDAD = {
    "xbrl_domicilio": "DomicileOfEntity",                                              # 78%
    "xbrl_direccion": "AddressOfRegisteredOfficeOfEntity",                             # 87%
    "xbrl_pais": "CountryOfIncorporation",                                             # 93%
    "xbrl_forma_legal": "LegalFormOfEntity",                                           # 84%
    "xbrl_giro": "DescriptionOfNatureOfEntitysOperationsAndPrincipalActivities",       # 81%
    "xbrl_matriz": "NameOfParentEntity",                                               # 81%
    "xbrl_matriz_ultima": "NameOfUltimateParentOfGroup",                               # 58%
}

# Los conceptos con desglose por segmento que valen la pena. Todos existen a nivel
# consolidado en `financial_data`, así que el segmento es la pieza que faltaba.
CONCEPTOS_SEGMENTO = (
    "Revenue",
    "ProfitLoss",
    "ProfitLossBeforeTax",
    "Assets",
    "Liabilities",
    "CostOfSales",
    "GrossProfit",
    "DepreciationAndAmortisationExpense",
)

# La deuda financiera del balance, para medir cuánto de ella cubre la nota de créditos.
DEUDA_BALANCE = ("OtherCurrentFinancialLiabilities", "OtherNoncurrentFinancialLiabilities",
                 "CurrentLeaseLiabilities", "NoncurrentLeaseLiabilities")

# Metadatos que hoy adivinamos o no tenemos. Ver migración 028.
#
# NO se lee `LevelOfRoundingUsedInFinancialStatements`, aunque prometía declarar la
# ESCALA de las cifras — justo el bug que más caro nos salió. Se verificó contra los 74
# archivos: es TEXTO LIBRE con 38 valores distintos ('"Llos presentes esta…', 'Toda la
# información…') y no predice nada. Falabella declara "Pesos", Aguas Andinas "Miles de
# Pesos", y las dos traen los hechos en UNIDADES. El /1000 del pipeline es correcto.
# Un dato que no se puede creer es peor que ninguno.
#
# Tampoco `NumeroAccionistas`: mezcla el número de accionistas con el de acciones
# ('64' junto a '1705831078'). Nadie lo llena en serio.
METADATOS = {
    "xbrl_actividad_cmf": "CodigoActividadPrincipal",       # 92% — el sector OFICIAL
    "xbrl_cotiza_santiago": "BolsaComercioSantiago",        # 78%
    "xbrl_cotiza_electronica": "BolsaElectronicaChile",
    "xbrl_acciones_inscritas": "AccionesInscritas",
}
_BOOLEANOS = {"xbrl_cotiza_santiago", "xbrl_cotiza_electronica", "xbrl_acciones_inscritas"}


# El piso NO es cosmético. Hay créditos que declaran una tasa de 0,0000004 — algunas
# empresas rellenan el campo con basura en vez de dejarlo vacío. En NUMERIC(8,6) eso
# redondea a 0,000000, que el CHECK rechaza (y con razón: no es una tasa).
#
# Y aunque cupiera: un crédito al 0,00004% no existe. Meterlo al promedio ponderado lo
# arrastraría hacia abajo con un dato que nadie escribió en serio.
_TASA_MINIMA = 0.0001    # 0,01%
_TASA_MAXIMA = 0.35      # 35%


def _tasa_guardable(tasa: float | None) -> float | None:
    """La tasa, o None si no es una tasa. Un hueco se nota; un cero falso, no."""
    if tasa is None or not (_TASA_MINIMA <= tasa < _TASA_MAXIMA):
        return None
    return tasa


def _limpiar_codigo(valor: str | None) -> str | None:
    """'CHL: Chile' → 'CHL'. La CMF codifica así los países y las monedas."""
    if not valor:
        return None
    return valor.split(":")[0].strip() if ":" in valor else valor.strip()


def _conexion():
    faltan = [k for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not os.environ.get(k)]
    if faltan:
        # El .env del repo, igual que hace supabase_uploader.
        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.is_file():
            for linea in env_file.read_text(encoding="utf-8").splitlines():
                if "=" in linea and not linea.strip().startswith("#"):
                    k, v = linea.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        faltan = [k for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD") if not os.environ.get(k)]
    if faltan:
        sys.exit(f"Faltan credenciales: {' '.join(faltan)}")

    return psycopg2.connect(
        host=os.environ["PGHOST"],
        port=int(os.environ.get("PGPORT", 5432)),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        sslmode="require",
    )


def _empresas_de_la_base(cur) -> dict[str, str]:
    """RUT (sin guión) → company_id."""
    cur.execute("SELECT id, UPPER(rut) AS rut FROM companies WHERE rut IS NOT NULL")
    return {fila["rut"].split("-")[0]: fila["id"] for fila in cur.fetchall()}


def _identidad(doc: xf.Documento) -> dict[str, str | None]:
    """Los hechos de identidad, del período más reciente y sin desglose."""
    fuera: dict[str, str | None] = {}
    for columna, concepto in IDENTIDAD.items():
        hechos = doc.consolidados(concepto)
        valor = hechos[0].valor.strip() if hechos else None
        if columna == "xbrl_pais":
            valor = _limpiar_codigo(valor)
        fuera[columna] = valor or None

    # Empleados: es un conteo, y viene con unidad 'pure'. Se toma el consolidado.
    empleados = [h.numero for h in doc.consolidados("NumberOfEmployees") if h.numero]
    fuera["xbrl_empleados"] = max(empleados) if empleados else None

    for columna, concepto in METADATOS.items():
        hechos = doc.consolidados(concepto)
        valor = hechos[0].valor.strip() if hechos else None
        if columna in _BOOLEANOS:
            fuera[columna] = (valor.lower() == "si") if valor else None
        else:
            fuera[columna] = valor or None
    return fuera


def _segmentos(ruta: Path, doc: xf.Documento, fecha_fin: str) -> list[dict]:
    """Los ingresos/resultado/activos por segmento. SÓLO las hojas bajo OperatingSegments.

    Ver migración 027: sumar el eje entero sin distinguir el árbol daba 4.448 millones de
    ingresos donde Arauco tiene 1.482.
    """
    hijos = xf.arbol(ruta)
    etiquetas = xf.etiquetas(ruta)
    moneda = doc.moneda()
    if not moneda:
        return []

    filas: list[dict] = []
    for eje, ancestro in (
        ("OperatingSegmentsAxis", "OperatingSegmentsMember"),
        ("GeographicalAreasAxis", "GeographicalAreasMember"),
    ):
        hojas = xf.hojas_bajo(hijos, ancestro)
        if not hojas:
            continue
        for concepto in CONCEPTOS_SEGMENTO:
            for h in xf.hojas_de_eje(doc, eje, hojas, concepto):
                if not h.es_numerico or h.contexto.fin != fecha_fin:
                    continue
                miembro = h.contexto.ejes[0][1]
                filas.append({
                    "eje": eje,
                    "miembro": miembro,
                    "nombre": etiquetas.get(miembro),
                    "concepto": concepto,
                    "valor": h.numero / ESCALA,
                    "moneda": moneda,
                })
    return filas


def _por_miembro(doc: xf.Documento, eje: str, fecha_fin: str) -> dict[str, dict[str, str]]:
    """Junta los hechos de cada miembro de un eje, en UNA fecha.

    Es el mismo patrón que la deuda: los hechos de una filial (o de una parte relacionada,
    o de un proyecto) están repartidos en varios contextos que sólo comparten el miembro y
    la fecha. Agrupar sólo por miembro mezclaría el saldo del período con el comparativo
    del año anterior.
    """
    grupos: dict[str, dict[str, str]] = collections.defaultdict(dict)
    for h in doc.hechos:
        m = dict(h.contexto.ejes).get(eje)
        if m and h.contexto.fin == fecha_fin:
            grupos[m][h.concepto] = h.valor
    return grupos


def _num(campos: dict, clave: str, escalar: bool = True) -> float | None:
    v = campos.get(clave)
    if v is None:
        return None
    try:
        n = float(str(v).replace(",", "").strip())
    except ValueError:
        return None
    return n / ESCALA if escalar else n


def _filiales(doc: xf.Documento, fecha_fin: str) -> list[dict]:
    """Las sociedades que la empresa controla, con su RUT y su porcentaje.

    Arauco declara 110. Con esto y `xbrl_matriz_ultima` se puede reconstruir el mapa de
    propiedad de las sociedades chilenas — que hoy no existe en ninguna parte, y menos
    para las 176 empresas que no cotizan.
    """
    filas = []
    for miembro, c in _por_miembro(doc, "SignificantInvestmentsInSubsidiariesAxis", fecha_fin).items():
        part = _num(c, "ProportionOfOwnershipInterestInSubsidiary", escalar=False)
        # Una participación fuera de [0,1] no es una participación: es una lectura mala.
        if part is not None and not (0 <= part <= 1):
            part = None
        filas.append({
            "miembro": miembro,
            "rut": c.get("RutSubsidiaria") or c.get("RUTSubsidiaria"),
            "nombre": c.get("NameOfSubsidiary"),
            "pais": _limpiar_codigo(c.get("CountryOfIncorporationOrResidenceOfSubsidiary")),
            "moneda_funcional": _limpiar_codigo(c.get("MonedaFuncionalSubsidiaria")),
            "participacion": part,
            "domicilio": c.get("PrincipalPlaceOfBusinessOfSubsidiary"),
        })
    return filas


def _partes_relacionadas(doc: xf.Documento, fecha_fin: str) -> list[dict]:
    """Con quién opera la empresa dentro de su propio grupo, y cuánto se deben.

    Es una señal de gobierno corporativo: una empresa cuyas cuentas por cobrar son
    mayormente con relacionadas carga un riesgo que el balance consolidado no muestra.
    """
    filas = []
    for miembro, c in _por_miembro(doc, "CategoriesOfRelatedPartiesAxis", fecha_fin).items():
        filas.append({
            "miembro": miembro,
            "rut": c.get("RUTParteRelacionada"),
            "nombre": c.get("NombreParteRelacionada"),
            "pais": _limpiar_codigo(c.get("PaisOrigen")),
            "relacion": c.get("DescriptionOfNatureOfRelatedPartyRelationship"),
            "transaccion": c.get("DescriptionOfTransactionsWithRelatedParty"),
            "moneda": _limpiar_codigo(c.get("TipoMonedaOUnidadReajuste")),
            "por_cobrar": _num(c, "CuentasCobrarEntidadesRelacionadas"),
            "por_pagar": _num(c, "CuentasPagarEntidadesRelacionadas"),
        })
    return filas


def _exposicion_moneda(doc: xf.Documento, fecha_fin: str) -> list[dict]:
    """Activos y pasivos POR MONEDA.

    Una empresa que reporta en pesos con la mitad de su deuda en dólares carga un riesgo
    cambiario que su estado consolidado NO muestra. Sólo aparece si alguien lee esta nota.
    """
    filas = []
    for miembro, c in _por_miembro(doc, "MonedaExtranjeraEje", fecha_fin).items():
        moneda = _limpiar_codigo(c.get("MonedaExtranjera"))
        if not moneda:
            continue
        filas.append({
            "moneda": moneda,
            "activos": _num(c, "ActivosME"),
            "pasivos": _num(c, "PasivosME"),
        })
    return filas


def _ambientales(doc: xf.Documento, fecha_fin: str) -> list[dict]:
    """Proyectos de protección medioambiental: nombre, estado, monto, fecha.

    La CMF los obliga a declararlos. Es el único dato ESG verificable y estructurado que
    existe para el mercado chileno, y hoy no lo publica nadie.
    """
    filas = []
    for miembro, c in _por_miembro(doc, "ProyectosProteccionMedioAmbienteEje", fecha_fin).items():
        filas.append({
            "miembro": miembro,
            "nombre": c.get("NombreProyecto"),
            "estado": c.get("EstadoDelProyecto"),
            "concepto": c.get("Concepto"),
            "monto": _num(c, "MontoDesembolsosAlPeriodoActual"),
            "activo_o_gasto": c.get("ActivoGasto"),
            # Texto libre: las empresas escriben "2027", "2do sem 2026", "En ejecución"…
            # No se fuerza a DATE, porque forzarlo significa inventar un día.
            "fecha_estimada": c.get("FechaEstimadaDesembolso"),
        })
    return filas


def _deuda(ruta: Path, doc: xf.Documento, fecha_fin: str) -> tuple[list[dict], dict | None]:
    """Los créditos y el Kd ponderado, con su cobertura sobre la deuda del balance."""
    creditos = xd.creditos(ruta, fecha_fin)
    if not creditos:
        return [], None

    filas = []
    for c in creditos:
        filas.append({
            "instrumento": c.instrumento,
            "miembro": c.miembro,
            "acreedor": c.acreedor,
            "serie": c.serie,
            "moneda": c.moneda,
            "amortizacion": c.amortizacion,
            "vencimiento": c.vencimiento,
            # La tasa ya viene normalizada a decimal por xbrl_deuda. Si queda fuera de
            # rango, NO se escribe: preferimos el hueco.
            "tasa_efectiva": _tasa_guardable(c.tasa_efectiva),
            "tasa_nominal": _tasa_guardable(c.tasa_nominal),
            "monto_contable": c.monto_contable / ESCALA if c.monto_contable else None,
            "monto_nominal": c.monto_nominal / ESCALA if c.monto_nominal else None,
        })

    cd = xd.costo_de_deuda(ruta, fecha_fin)
    if cd is None:
        return filas, None

    # Cobertura: ¿cuánta de la deuda del balance respalda este Kd? Si es baja, el Kd no
    # representa a la empresa. Leer sólo los conceptos de préstamos bancarios capturaba
    # el 4% de la deuda de Aguas Andinas, que es casi toda bonos.
    balance = 0.0
    for concepto in DEUDA_BALANCE:
        hs = [h.numero for h in doc.consolidados(concepto)
              if h.es_numerico and h.contexto.fin == fecha_fin]
        if hs:
            balance += abs(hs[0])

    resumen = {
        "kd": cd.kd,
        "deuda_cubierta": cd.deuda_cubierta / ESCALA,
        "n_creditos": cd.n_creditos,
        "cobertura": (cd.deuda_cubierta / balance) if balance > 0 else None,
    }
    return filas, resumen


def main() -> None:
    ap = argparse.ArgumentParser(description="Mina el XBRL a la base")
    ap.add_argument("--apply", action="store_true", help="escribir (por defecto: dry-run)")
    ap.add_argument("--empresas", default="", help="RUTs sin DV, separados por coma")
    ap.add_argument("--periodos", type=int, default=8,
                    help="cuántos períodos recientes por empresa (default: 8)")
    args = ap.parse_args()

    if not RAIZ_XBRL.is_dir():
        sys.exit(f"No encuentro los XBRL en {RAIZ_XBRL}")

    filtro = {r.strip() for r in args.empresas.split(",") if r.strip()}

    conn = _conexion()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    por_rut = _empresas_de_la_base(cur)

    n_id = n_seg = n_deuda = n_kd = 0
    n_extra: dict[str, int] = collections.Counter()
    sin_empresa = []

    for carpeta in sorted(RAIZ_XBRL.iterdir()):
        if not carpeta.is_dir():
            continue
        rut = carpeta.name.split("-")[0]
        if filtro and rut not in filtro:
            continue
        company_id = por_rut.get(rut)
        if not company_id:
            sin_empresa.append(carpeta.name[:30])
            continue

        periodos = list(xf.periodos_de(carpeta))
        if not periodos:
            continue

        # La identidad se toma del período MÁS RECIENTE: es el dato vigente.
        anio, trimestre, ruta = periodos[-1]
        doc = xf.leer(ruta)
        ident = _identidad(doc)
        fecha_ult = f"{anio}-{_ULTIMO_DIA[trimestre]}"

        if args.apply and any(v for v in ident.values()):
            cur.execute(
                """UPDATE companies SET
                     xbrl_domicilio = COALESCE(%(xbrl_domicilio)s, xbrl_domicilio),
                     xbrl_direccion = COALESCE(%(xbrl_direccion)s, xbrl_direccion),
                     xbrl_pais = COALESCE(%(xbrl_pais)s, xbrl_pais),
                     xbrl_forma_legal = COALESCE(%(xbrl_forma_legal)s, xbrl_forma_legal),
                     xbrl_giro = COALESCE(%(xbrl_giro)s, xbrl_giro),
                     xbrl_matriz = COALESCE(%(xbrl_matriz)s, xbrl_matriz),
                     xbrl_matriz_ultima = COALESCE(%(xbrl_matriz_ultima)s, xbrl_matriz_ultima),
                     xbrl_empleados = COALESCE(%(xbrl_empleados)s, xbrl_empleados),
                     xbrl_actividad_cmf = COALESCE(%(xbrl_actividad_cmf)s, xbrl_actividad_cmf),
                     xbrl_cotiza_santiago = COALESCE(%(xbrl_cotiza_santiago)s, xbrl_cotiza_santiago),
                     xbrl_cotiza_electronica = COALESCE(%(xbrl_cotiza_electronica)s, xbrl_cotiza_electronica),
                     xbrl_acciones_inscritas = COALESCE(%(xbrl_acciones_inscritas)s, xbrl_acciones_inscritas),
                     xbrl_perfil_as_of = %(as_of)s
                   WHERE id = %(id)s""",
                {**ident, "as_of": fecha_ult, "id": company_id},
            )
        if any(v for v in ident.values()):
            n_id += 1

        # Segmentos y deuda: por período, hasta `--periodos` hacia atrás.
        for anio, trimestre, ruta in periodos[-args.periodos:]:
            fecha = f"{anio}-{_ULTIMO_DIA[trimestre]}"
            doc = xf.leer(ruta)

            segs = _segmentos(ruta, doc, fecha)
            n_seg += len(segs)
            if args.apply and segs:
                psycopg2.extras.execute_batch(cur,
                    """INSERT INTO xbrl_segmentos
                         (company_id, period_year, period_quarter, eje, miembro, nombre,
                          concepto, valor, moneda)
                       VALUES (%(cid)s, %(y)s, %(q)s, %(eje)s, %(miembro)s, %(nombre)s,
                               %(concepto)s, %(valor)s, %(moneda)s)
                       ON CONFLICT (company_id, period_year, period_quarter, eje, miembro, concepto)
                       DO UPDATE SET valor = EXCLUDED.valor, nombre = EXCLUDED.nombre,
                                     moneda = EXCLUDED.moneda""",
                    [{**s, "cid": company_id, "y": anio, "q": trimestre} for s in segs],
                    page_size=200)

            aprob = doc.consolidados("FechaSesionDirectorioAprobaronEstadosFinancieros")
            tipo = doc.consolidados("TipoEEFF")
            if args.apply:
                cur.execute(
                    """INSERT INTO xbrl_periodos
                         (company_id, period_year, period_quarter, fecha_aprobacion,
                          tipo_eeff, moneda)
                       VALUES (%s, %s, %s, %s, %s, %s)
                       ON CONFLICT (company_id, period_year, period_quarter)
                       DO UPDATE SET fecha_aprobacion = EXCLUDED.fecha_aprobacion,
                                     tipo_eeff = EXCLUDED.tipo_eeff,
                                     moneda = EXCLUDED.moneda""",
                    (company_id, anio, trimestre,
                     aprob[0].valor.strip() if aprob else None,
                     tipo[0].valor.strip() if tipo else None,
                     doc.moneda()))

            # ── las cuatro tablas nuevas (migración 029) ──────────────────────
            for tabla, filas, cols in (
                ("xbrl_filiales", _filiales(doc, fecha),
                 ("miembro", "rut", "nombre", "pais", "moneda_funcional", "participacion", "domicilio")),
                ("xbrl_partes_relacionadas", _partes_relacionadas(doc, fecha),
                 ("miembro", "rut", "nombre", "pais", "relacion", "transaccion", "moneda",
                  "por_cobrar", "por_pagar")),
                ("xbrl_proyectos_ambientales", _ambientales(doc, fecha),
                 ("miembro", "nombre", "estado", "concepto", "monto", "activo_o_gasto",
                  "fecha_estimada")),
            ):
                n_extra[tabla] += len(filas)
                if args.apply and filas:
                    campos = ("company_id", "period_year", "period_quarter") + cols
                    marcas = ", ".join(f"%({c})s" for c in campos)
                    actualiza = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "miembro")
                    psycopg2.extras.execute_batch(cur,
                        f"""INSERT INTO {tabla} ({', '.join(campos)}) VALUES ({marcas})
                            ON CONFLICT (company_id, period_year, period_quarter, miembro)
                            DO UPDATE SET {actualiza}""",
                        [{**f, "company_id": company_id, "period_year": anio,
                          "period_quarter": trimestre} for f in filas],
                        page_size=200)

            fx = _exposicion_moneda(doc, fecha)
            n_extra["xbrl_exposicion_moneda"] += len(fx)
            if args.apply and fx:
                psycopg2.extras.execute_batch(cur,
                    """INSERT INTO xbrl_exposicion_moneda
                         (company_id, period_year, period_quarter, moneda, activos, pasivos)
                       VALUES (%(company_id)s, %(period_year)s, %(period_quarter)s,
                               %(moneda)s, %(activos)s, %(pasivos)s)
                       ON CONFLICT (company_id, period_year, period_quarter, moneda)
                       DO UPDATE SET activos = EXCLUDED.activos, pasivos = EXCLUDED.pasivos""",
                    [{**f, "company_id": company_id, "period_year": anio,
                      "period_quarter": trimestre} for f in fx],
                    page_size=100)

            creditos, resumen = _deuda(ruta, doc, fecha)
            n_deuda += len(creditos)
            if args.apply and creditos:
                psycopg2.extras.execute_batch(cur,
                    """INSERT INTO xbrl_deuda
                         (company_id, period_year, period_quarter, instrumento, miembro,
                          acreedor, serie, moneda, amortizacion, vencimiento,
                          tasa_efectiva, tasa_nominal, monto_contable, monto_nominal)
                       VALUES (%(cid)s, %(y)s, %(q)s, %(instrumento)s, %(miembro)s,
                               %(acreedor)s, %(serie)s, %(moneda)s, %(amortizacion)s,
                               %(vencimiento)s, %(tasa_efectiva)s, %(tasa_nominal)s,
                               %(monto_contable)s, %(monto_nominal)s)
                       ON CONFLICT (company_id, period_year, period_quarter, instrumento, miembro)
                       DO UPDATE SET
                         acreedor = EXCLUDED.acreedor, serie = EXCLUDED.serie,
                         moneda = EXCLUDED.moneda, amortizacion = EXCLUDED.amortizacion,
                         vencimiento = EXCLUDED.vencimiento,
                         tasa_efectiva = EXCLUDED.tasa_efectiva,
                         tasa_nominal = EXCLUDED.tasa_nominal,
                         monto_contable = EXCLUDED.monto_contable,
                         monto_nominal = EXCLUDED.monto_nominal""",
                    [{**c, "cid": company_id, "y": anio, "q": trimestre} for c in creditos],
                    page_size=200)

            if resumen:
                n_kd += 1
                if args.apply:
                    cur.execute(
                        """INSERT INTO xbrl_costo_deuda
                             (company_id, period_year, period_quarter, kd, deuda_cubierta,
                              n_creditos, cobertura)
                           VALUES (%(cid)s, %(y)s, %(q)s, %(kd)s, %(deuda_cubierta)s,
                                   %(n_creditos)s, %(cobertura)s)
                           ON CONFLICT (company_id, period_year, period_quarter)
                           DO UPDATE SET kd = EXCLUDED.kd,
                                         deuda_cubierta = EXCLUDED.deuda_cubierta,
                                         n_creditos = EXCLUDED.n_creditos,
                                         cobertura = EXCLUDED.cobertura""",
                        {**resumen, "cid": company_id, "y": anio, "q": trimestre})

        if args.apply:
            conn.commit()
        print(".", end="", flush=True)

    print()
    print(f"identidad:  {n_id} empresas")
    print(f"segmentos:  {n_seg} filas")
    print(f"deuda:      {n_deuda} créditos (préstamos + bonos + ARRIENDOS)  ·  {n_kd} períodos con Kd")
    for tabla, n in sorted(n_extra.items()):
        print(f"{tabla.replace('xbrl_', ''):26} {n} filas")
    if sin_empresa:
        print(f"\n⚠️  {len(sin_empresa)} carpetas de XBRL sin empresa en la base: {', '.join(sin_empresa[:4])}…")
    if not args.apply:
        print("\n(dry-run — corre con --apply para escribir.)")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
