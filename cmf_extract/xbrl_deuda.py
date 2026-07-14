"""Estructura de la deuda, préstamo por préstamo, leída del XBRL.

POR QUÉ IMPORTA
---------------
El DCF necesita el costo de la deuda (Kd). Hoy se estima:

    Kd = costos financieros del período / deuda financiera

Es una aproximación cruda: mezcla intereses de deuda vieja con deuda nueva, se
distorsiona cuando la deuda cambió a mitad de año, y no dice nada de en qué moneda está
la deuda ni cuándo vence.

Pero la empresa YA DECLARA la tasa. En la nota de préstamos del XBRL, cada crédito viene
con su acreedor, su moneda, su tipo de amortización, su vencimiento y su TASA EFECTIVA.
Arauco declara 76 préstamos, uno por uno. Ninguna API entrega esto.

    Kd = promedio de las tasas efectivas, ponderado por el monto de cada crédito

Eso no es una estimación: es lo que la empresa firma ante la CMF.

LAS TRAMPAS DE ESTA NOTA (verificadas contra Arauco)
----------------------------------------------------
1) CADA PRÉSTAMO APARECE DOS VECES: una por el cierre actual y otra por el comparativo
   del año anterior. La clave de un crédito no es su miembro, es (miembro, fecha).
   Agrupar sólo por miembro mezcla el saldo de 2026 con el de 2025.

2) LOS TRAMOS DE VENCIMIENTO ESTÁN ANIDADOS:

       MasDe1AñoHasta3Años   141.255.000
         MasDe1AñoHasta2Años  69.066.000
         MasDe2AñosHasta3Años 72.189.000     (69.066 + 72.189 = 141.255)

   Sumar todos los tramos duplica la deuda. Se usan sólo los tramos hoja.

3) HAY DOS MONTOS Y NO SON LO MISMO: `MontosNominalesPrestamos` es el nominal (lo que se
   debe devolver) y `PrestamosBancarios` es el valor contable (lo que está en el balance).
   Para ponderar la tasa se usa el CONTABLE, que es el que está en el estado.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
from pathlib import Path

# El pipeline corre con cwd=cmf_extract y este módulo entra como `import xbrl_deuda`, sin
# paquete padre: el import relativo revienta con "attempted relative import with no known
# parent package" y la deuda se pierde en silencio (el llamador sólo ve un AVISO).
try:
    from . import xbrl_facts as xf
except ImportError:
    import xbrl_facts as xf

# Los ejes donde vive el detalle de la deuda. Son extensiones de la CMF: no existen en la
# taxonomía IFRS internacional, y por eso ninguna herramienta genérica las lee.
EJE_PRESTAMOS = "PrestamosEje"
EJE_EMISIONES = "EmisionesDeudaEje"
# BAJO IFRS 16 UN ARRIENDO ES DEUDA, y el XBRL lo trata así: `LeasingEje` declara cada
# contrato con acreedor, moneda y TASA EFECTIVA — la misma estructura que un préstamo.
# Dejarlo fuera del Kd no es una omisión menor: en SMU los arriendos son el 58,6% de su
# deuda total, en Tricot el 54,2%, en Falabella el 28,9%. Un costo de deuda que ignora la
# mitad de la deuda no es el costo de deuda de esa empresa.
EJE_ARRIENDOS = "LeasingEje"

# Los montos tienen NOMBRES DISTINTOS según el instrumento, y no es un detalle: la deuda
# de Aguas Andinas es casi toda BONOS, así que leer sólo los conceptos de préstamos
# bancarios capturaba el 4% de su deuda y el Kd que salía no representaba nada.
#
#   préstamo bancario  ->  PrestamosBancarios{,Corrientes,NoCorrientes}
#   emisión de deuda   ->  ObligacionesConPublico{,Corrientes,NoCorrientes}
_CONTABLE_TOTAL = ("PrestamosBancarios", "ObligacionesConPublico", "LeaseLiabilities")
_CONTABLE_CORRIENTE = ("PrestamosBancariosCorrientes", "ObligacionesConPublicoCorrientes",
                       "CurrentLeaseLiabilities")
_CONTABLE_NO_CORRIENTE = ("PrestamosBancariosNoCorrientes", "ObligacionesConPublicoNoCorrientes",
                          "NoncurrentLeaseLiabilities")
_NOMINAL = ("MontosNominalesPrestamos", "MontosNominalesObligacionesPublico",
            "MontosNominalesLeasing")

# EL PERFIL DE VENCIMIENTOS: cuánto vence en cada tramo.
#
# Es lo que dice si la empresa tiene un muro de deuda el año que viene o si lo tiene
# repartido a diez años. Dos empresas con la misma deuda total y el mismo Kd pueden ser
# riesgos completamente distintos, y eso no se ve en ningún ratio del balance.
#
# LA TRAMPA: LOS TRAMOS ESTÁN ANIDADOS.
#
#     MasDe1AñoHasta3Años   141.255      <- agregado
#       MasDe1AñoHasta2Años  69.066      <- hoja
#       MasDe2AñosHasta3Años 72.189      <- hoja      (69.066 + 72.189 = 141.255)
#
# Sumar todos los tramos duplica la deuda. Sólo se usan las HOJAS.
#
# Y la taxonomía escribe "Masde90Dias..." (d minúscula) en el concepto Contable y
# "MasDe90Dias..." (D mayúscula) en el Nominal. Es una errata de la CMF, no del lector:
# hay que aceptar las dos o se pierde el tramo de 90 días a 1 año entero.
_TRAMOS = (
    ("Hasta 90 días",        ("Hasta90Dias{}Contable",)),
    ("90 días a 1 año",      ("Masde90DiasHasta1Año{}Contable",
                              "MasDe90DiasHasta1Año{}Contable")),
    ("1 a 2 años",           ("MasDe1AñoHasta2Años{}Contable",)),
    ("2 a 3 años",           ("MasDe2AñosHasta3Años{}Contable",)),
    ("3 a 4 años",           ("MasDe3AñosHasta4Años{}Contable",)),
    ("4 a 5 años",           ("MasDe4AñosHasta5Años{}Contable",)),
    ("Más de 5 años",        ("MasDe5Años{}Contable",)),
)

# El sufijo del concepto según el instrumento: el mismo tramo se llama distinto en un
# préstamo, un bono y un arriendo.
_SUFIJO = {
    "prestamo": "Prestamos",
    "bono": "ObligacionesPublico",
    "arriendo": "Leasing",
}


def _primero(campos: dict[str, str], claves: tuple[str, ...]) -> float | None:
    for k in claves:
        v = _numero(campos.get(k))
        if v is not None:
            return v
    return None


# LA TASA VIENE EN DOS CONVENCIONES, Y HAY 17 EMPRESAS QUE MEZCLAN LAS DOS EN EL MISMO
# ARCHIVO. De 12.700 tasas leídas, 10.289 son decimales (0,0526) y 1.413 son porcentajes
# (5,26). Así que no hay una regla por empresa: la decisión es por HECHO.
#
# La frontera está en 0,30 y no es arbitraria:
#
#   · un 0,0111 leído como porcentaje sería 0,011% anual — no existe;
#     leído como decimal es 1,11%, que es lo que paga Arauco en euros. → decimal
#   · un 11,8 leído como decimal sería 1.180% — no existe;
#     leído como porcentaje es 11,8%, que es lo que paga ILC. → porcentaje
#   · un 0,52 es el caso incómodo: como decimal sería 52% (deuda corporativa al 52%:
#     no existe) y como porcentaje 0,52% (un crédito en dólares o euros: común).
#     → porcentaje
#
# Sin esta regla, Inversiones La Construcción salía con un costo de deuda del 52%.
_FRONTERA_DECIMAL = 0.30


def _tasa(valor: str | None) -> float | None:
    v = _numero(valor)
    if v is None or v <= 0:
        return None
    return v / 100 if v > _FRONTERA_DECIMAL else v


@dataclass
class Credito:
    """Un préstamo, una emisión de deuda o un arriendo, tal como la empresa lo declara."""
    miembro: str                    # id del ítem en el XBRL (Item182)
    fecha: str                      # el cierre al que corresponde el saldo
    instrumento: str = "prestamo"   # 'prestamo' | 'bono' | 'arriendo'
    acreedor: str | None = None
    moneda: str | None = None       # 'EUR: Euro' → 'EUR'
    amortizacion: str | None = None
    vencimiento: str | None = None
    tasa_efectiva: float | None = None
    tasa_nominal: float | None = None
    monto_contable: float | None = None
    monto_nominal: float | None = None
    serie: str | None = None        # sólo en emisiones (bonos)

    # QUIÉN se endeudó. En un grupo como Arauco o Enel no es la matriz la que toma cada
    # crédito, sino una filial, y a veces en otro país. Esa es la diferencia entre una
    # deuda con recurso a la matriz y una que no.
    deudor: str | None = None
    pais_deudor: str | None = None

    # CORRIENTE vs NO CORRIENTE. Antes esto se leía sólo para sumarlo y se perdía el
    # desglose. Pero es exactamente lo que dice cuánta deuda hay que refinanciar dentro de
    # los próximos doce meses: la diferencia entre una empresa cómoda y una apretada.
    monto_corriente: float | None = None
    monto_no_corriente: float | None = None

    # EL PERFIL DE VENCIMIENTOS: {tramo -> monto}. Sólo los tramos HOJA, nunca los
    # agregados (ver `_TRAMOS`), o la deuda se contaría dos veces.
    vencimientos: dict[str, float] = field(default_factory=dict)

    @property
    def utilizable(self) -> bool:
        """Sirve para ponderar el Kd sólo si trae tasa Y monto, y ambos son plausibles.

        El techo es 35%, no 100%: la tasa ya viene normalizada, y ninguna empresa se
        financia por sobre eso. Si aparece algo mayor, la lectura está mal y preferimos
        perder ese crédito a envenenar el promedio.
        """
        return (
            self.tasa_efectiva is not None
            and 0 < self.tasa_efectiva < 0.35
            and self.monto_contable is not None
            and self.monto_contable > 0
        )


def _limpiar_codigo(valor: str | None) -> str | None:
    """'EUR: Euro' → 'EUR'   ·   'CHL: Chile' → 'CHL'."""
    if not valor:
        return None
    return valor.split(":")[0].strip() if ":" in valor else valor.strip()


def _numero(valor: str | None) -> float | None:
    if valor is None:
        return None
    try:
        return float(valor.replace(",", "").strip())
    except ValueError:
        return None


_INSTRUMENTO = {
    EJE_PRESTAMOS: "prestamo",
    EJE_EMISIONES: "bono",
    EJE_ARRIENDOS: "arriendo",
}


def _creditos_de_eje(doc: xf.Documento, eje: str) -> list[Credito]:
    """Reconstruye cada crédito juntando sus hechos.

    La clave es (miembro, fecha) — ver trampa (1). Los hechos de un mismo crédito están
    repartidos en varios contextos que sólo comparten esas dos cosas.
    """
    campos: dict[tuple[str, str], dict[str, str]] = collections.defaultdict(dict)
    for h in doc.hechos:
        ejes = dict(h.contexto.ejes)
        miembro = ejes.get(eje)
        if not miembro or not h.contexto.fin:
            continue
        campos[(miembro, h.contexto.fin)][h.concepto] = h.valor

    creditos: list[Credito] = []
    for (miembro, fecha), c in campos.items():
        contable = _primero(c, _CONTABLE_TOTAL)
        if contable is None:
            corr = _primero(c, _CONTABLE_CORRIENTE) or 0.0
            nocorr = _primero(c, _CONTABLE_NO_CORRIENTE) or 0.0
            contable = (corr + nocorr) or None

        instrumento = _INSTRUMENTO.get(eje, "prestamo")

        # El perfil de vencimientos: sólo los tramos HOJA. Los agregados
        # (MasDe1AñoHasta3Años, MasDe3AñosHasta5Años) contienen a los otros y sumarlos
        # duplicaría la deuda.
        sufijo = _SUFIJO.get(instrumento, "Prestamos")
        venc: dict[str, float] = {}
        for etiqueta, plantillas in _TRAMOS:
            monto = _primero(c, tuple(p.format(sufijo) for p in plantillas))
            if monto:
                venc[etiqueta] = monto

        creditos.append(Credito(
            instrumento=instrumento,
            miembro=miembro,
            fecha=fecha,
            acreedor=c.get("NombreEntidadAcreedora"),
            deudor=c.get("NombreEntidadDeudora"),
            pais_deudor=_limpiar_codigo(c.get("PaisEmpresaDeudora")),
            moneda=_limpiar_codigo(c.get("MonedaOUnidadReajuste")),
            amortizacion=c.get("TipoAmortizacion") or c.get("PeriodicidadAmortizacion"),
            vencimiento=c.get("FechaVencimiento"),
            tasa_efectiva=_tasa(c.get("TasaEfectiva")),
            tasa_nominal=_tasa(c.get("TasaNominal")),
            monto_contable=contable,
            monto_corriente=_primero(c, _CONTABLE_CORRIENTE),
            monto_no_corriente=_primero(c, _CONTABLE_NO_CORRIENTE),
            monto_nominal=_primero(c, _NOMINAL),
            vencimientos=venc,
            serie=c.get("Series"),
        ))
    return creditos


def creditos(xbrl_path: Path | str, fecha: str | None = None) -> list[Credito]:
    """Todos los créditos declarados (préstamos bancarios + emisiones de deuda).

    `fecha` acota al cierre del estado. Sin ella se devuelven también los del período
    comparativo, que son otro saldo y no deben mezclarse.
    """
    doc = xf.leer(xbrl_path)
    todos = (_creditos_de_eje(doc, EJE_PRESTAMOS)
             + _creditos_de_eje(doc, EJE_EMISIONES)
             + _creditos_de_eje(doc, EJE_ARRIENDOS))
    if fecha:
        todos = [c for c in todos if c.fecha == fecha]
    return todos


@dataclass
class CostoDeuda:
    kd: float                       # tasa efectiva ponderada por monto contable
    deuda_cubierta: float           # cuánta deuda respalda ese Kd
    n_creditos: int
    por_moneda: dict[str, float]    # moneda → monto. La exposición cambiaria de la deuda.

    # Cuánto hay que refinanciar dentro de los próximos doce meses. Es la diferencia entre
    # una empresa cómoda y una apretada, y no se ve en el Kd.
    corriente: float = 0.0
    no_corriente: float = 0.0

    # El perfil de vencimientos consolidado: {tramo -> monto}. Dice si la empresa tiene un
    # muro de deuda el año que viene o si lo tiene repartido a diez años. Dos empresas con
    # la misma deuda y el mismo Kd pueden ser riesgos completamente distintos.
    vencimientos: dict[str, float] = field(default_factory=dict)

    # Por instrumento: cuánto es préstamo bancario, cuánto bono y cuánto arriendo. Bajo
    # IFRS 16 un arriendo es deuda, y en SMU son el 58,6% del total.
    por_instrumento: dict[str, float] = field(default_factory=dict)


def costo_de_deuda(xbrl_path: Path | str, fecha: str | None = None) -> CostoDeuda | None:
    """Kd: el promedio de las tasas efectivas declaradas, ponderado por monto.

    Devuelve None si la empresa no declara tasas: preferimos un hueco a un Kd inventado.
    Quien llame decide si cae a la estimación (costos financieros / deuda).
    """
    utiles = [c for c in creditos(xbrl_path, fecha) if c.utilizable]
    if not utiles:
        return None

    total = sum(c.monto_contable for c in utiles)
    if total <= 0:
        return None

    kd = sum(c.tasa_efectiva * c.monto_contable for c in utiles) / total

    por_moneda: dict[str, float] = collections.defaultdict(float)
    por_instrumento: dict[str, float] = collections.defaultdict(float)
    vencimientos: dict[str, float] = collections.defaultdict(float)
    corriente = no_corriente = 0.0

    for c in utiles:
        por_moneda[c.moneda or "?"] += c.monto_contable
        por_instrumento[c.instrumento] += c.monto_contable
        corriente += c.monto_corriente or 0.0
        no_corriente += c.monto_no_corriente or 0.0
        for tramo, monto in c.vencimientos.items():
            vencimientos[tramo] += monto

    # Los tramos salen en ORDEN CRONOLÓGICO, no alfabético: "Hasta 90 días" antes que
    # "1 a 2 años". Un perfil de vencimientos ordenado al azar no es un perfil.
    orden = [etiqueta for etiqueta, _ in _TRAMOS]
    vencimientos_ordenados = {t: vencimientos[t] for t in orden if vencimientos.get(t)}

    return CostoDeuda(
        kd=kd,
        deuda_cubierta=total,
        n_creditos=len(utiles),
        por_moneda=dict(por_moneda),
        corriente=corriente,
        no_corriente=no_corriente,
        vencimientos=vencimientos_ordenados,
        por_instrumento=dict(por_instrumento),
    )
