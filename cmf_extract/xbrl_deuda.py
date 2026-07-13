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
from dataclasses import dataclass
from pathlib import Path

from . import xbrl_facts as xf

# Los ejes donde vive el detalle de la deuda. Son extensiones de la CMF: no existen en la
# taxonomía IFRS internacional, y por eso ninguna herramienta genérica las lee.
EJE_PRESTAMOS = "PrestamosEje"
EJE_EMISIONES = "EmisionesDeudaEje"

# Los montos tienen NOMBRES DISTINTOS según el instrumento, y no es un detalle: la deuda
# de Aguas Andinas es casi toda BONOS, así que leer sólo los conceptos de préstamos
# bancarios capturaba el 4% de su deuda y el Kd que salía no representaba nada.
#
#   préstamo bancario  ->  PrestamosBancarios{,Corrientes,NoCorrientes}
#   emisión de deuda   ->  ObligacionesConPublico{,Corrientes,NoCorrientes}
_CONTABLE_TOTAL = ("PrestamosBancarios", "ObligacionesConPublico")
_CONTABLE_CORRIENTE = ("PrestamosBancariosCorrientes", "ObligacionesConPublicoCorrientes")
_CONTABLE_NO_CORRIENTE = ("PrestamosBancariosNoCorrientes", "ObligacionesConPublicoNoCorrientes")
_NOMINAL = ("MontosNominalesPrestamos", "MontosNominalesObligacionesPublico")


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
    """Un préstamo o una emisión de deuda, tal como la empresa lo declara."""
    miembro: str                    # id del ítem en el XBRL (Item182)
    fecha: str                      # el cierre al que corresponde el saldo
    acreedor: str | None = None
    moneda: str | None = None       # 'EUR: Euro' → 'EUR'
    amortizacion: str | None = None
    vencimiento: str | None = None
    tasa_efectiva: float | None = None
    tasa_nominal: float | None = None
    monto_contable: float | None = None
    monto_nominal: float | None = None
    serie: str | None = None        # sólo en emisiones (bonos)

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

        creditos.append(Credito(
            miembro=miembro,
            fecha=fecha,
            acreedor=c.get("NombreEntidadAcreedora"),
            moneda=_limpiar_codigo(c.get("MonedaOUnidadReajuste")),
            amortizacion=c.get("TipoAmortizacion") or c.get("PeriodicidadAmortizacion"),
            vencimiento=c.get("FechaVencimiento"),
            tasa_efectiva=_tasa(c.get("TasaEfectiva")),
            tasa_nominal=_tasa(c.get("TasaNominal")),
            monto_contable=contable,
            monto_nominal=_primero(c, _NOMINAL),
            serie=c.get("Series"),
        ))
    return creditos


def creditos(xbrl_path: Path | str, fecha: str | None = None) -> list[Credito]:
    """Todos los créditos declarados (préstamos bancarios + emisiones de deuda).

    `fecha` acota al cierre del estado. Sin ella se devuelven también los del período
    comparativo, que son otro saldo y no deben mezclarse.
    """
    doc = xf.leer(xbrl_path)
    todos = _creditos_de_eje(doc, EJE_PRESTAMOS) + _creditos_de_eje(doc, EJE_EMISIONES)
    if fecha:
        todos = [c for c in todos if c.fecha == fecha]
    return todos


@dataclass
class CostoDeuda:
    kd: float                       # tasa efectiva ponderada por monto contable
    deuda_cubierta: float           # cuánta deuda respalda ese Kd
    n_creditos: int
    por_moneda: dict[str, float]    # moneda → monto. La exposición cambiaria de la deuda.


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
    for c in utiles:
        por_moneda[c.moneda or "?"] += c.monto_contable

    return CostoDeuda(
        kd=kd,
        deuda_cubierta=total,
        n_creditos=len(utiles),
        por_moneda=dict(por_moneda),
    )
