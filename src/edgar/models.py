"""Dataclasses de los hechos parseados desde companyfacts de la SEC."""

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Fact:
    """Un hecho XBRL suelto tal como lo devuelve `companyfacts`.

    `start is None` marca un **instant** (un saldo de balance a una fecha). Con `start`
    es una **duration** (un flujo entre dos fechas). Esa distinción es la que decide si
    el valor se acumula o no (spec §6.2), y es lo único confiable para reconstruir el
    período: `fy`/`fp` NO se guardan a propósito — identifican el filing donde apareció
    el hecho, no el período del hecho, y usarlos es el error clásico del §6.4.
    """

    tag: str
    start: date | None
    end: date
    val: float
    accn: str
    form: str
    filed: date

    @property
    def is_instant(self) -> bool:
        return self.start is None


@dataclass(frozen=True)
class FiscalPeriod:
    """Una ventana fiscal de la empresa, derivada de las fechas de los propios hechos."""

    year: int  # period_year: el año fiscal (año calendario del CIERRE del ejercicio)
    quarter: int  # period_quarter 1..4; el 4 es el ejercicio completo, no un Q4 suelto
    start: date  # inicio del AÑO fiscal (no del trimestre): los flujos van acumulados
    end: date


@dataclass(frozen=True)
class LineValue:
    """Una celda lista para cargar: qué línea, de qué período, con qué valor."""

    concept_key: str
    tag: str
    label_es: str
    label_en: str
    role_code: str
    category: str
    subcategory: str | None
    display_order: int
    year: int
    quarter: int
    value: float
    unit: str
