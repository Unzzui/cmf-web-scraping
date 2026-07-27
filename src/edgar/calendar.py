"""Calendario de resultados de EEUU: del `submissions` de la SEC a eventos de calendario.

Parsers puros, sin red ni BD. Dos clases de evento salen de acá:

* **earnings** — el 8-K con item `2.02` ("Results of Operations"). Es el *press release*
  de resultados, y trae la HORA de aceptación: de ahí se deriva si el anuncio fue antes de
  la apertura (bmo) o tras el cierre (amc), que es lo que mira un analista. El 8-K no
  declara el período fiscal, así que va sin quarter.

* **financials** — el 10-Q / 10-K. La fecha oficial de los estados. El `reportDate` (fin
  del período) da el año y, para los 10-Q, el trimestre fiscal, que se reconstruye anclando
  cada 10-Q al 10-K (cierre de ejercicio) que le sigue.

Y una estimación:

* **estimated** — la PRÓXIMA fecha de resultados, proyectada desde la cadencia histórica de
  los earnings. La SEC no publica fechas futuras; la cadencia trimestral es tan regular que
  se predice con pocos días de error. Se marca como estimada, nunca como confirmada.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass(frozen=True)
class CalendarEvent:
    event_type: str            # 'earnings' | 'financials' | 'estimated'
    event_date: date
    event_time: str | None     # 'HH:MM' UTC, sólo earnings
    timing: str | None         # 'bmo' | 'amc' | 'during'
    period_year: int | None
    period_quarter: int | None
    form: str | None           # '8-K' | '10-Q' | '10-K'
    accession: str | None
    status: str                # 'confirmed' | 'estimated'


def _parse_date(s) -> date | None:
    if not s or not isinstance(s, str):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


# La apertura de la bolsa de EEUU son las 9:30 ET = 13:30/14:30 UTC según horario de
# verano; el cierre, 16:00 ET = 20:00/21:00 UTC. Con ventanas holgadas basta para
# clasificar: un earnings cae casi siempre bien antes de la apertura o bien tras el cierre.
def _timing_from_utc(t: datetime) -> str:
    minutes = t.hour * 60 + t.minute
    if minutes <= 13 * 60 + 30:      # <= 13:30 UTC: antes de que abra el mercado
        return "bmo"
    if minutes >= 20 * 60:           # >= 20:00 UTC: después del cierre
        return "amc"
    return "during"


def _rows(recent: dict) -> list[dict]:
    """Las columnas paralelas de `filings.recent` a una lista de dicts por filing."""
    keys = ("form", "filingDate", "reportDate", "acceptanceDateTime", "items",
            "accessionNumber")
    cols = [recent.get(k, []) for k in keys]
    return [dict(zip(keys, vals)) for vals in zip(*cols)]


def fiscal_year_end_month(submissions: dict) -> int | None:
    """El mes (1-12) en que cierra el año fiscal, o None.

    Es la moda del mes del `reportDate` de los 10-K: Apple cierra en septiembre, Nike en
    mayo, Nvidia en enero. Con este único número el front deriva el mes real de cualquier
    trimestre fiscal y deja de mostrar el ambiguo "2025Q4".
    """
    recent = (submissions.get("filings", {}) or {}).get("recent", {}) or {}
    months: list[int] = []
    for r in _rows(recent):
        if r.get("form") != "10-K":
            continue
        rd = _parse_date(r.get("reportDate"))
        if rd is not None:
            months.append(rd.month)
    if not months:
        return None
    return Counter(months).most_common(1)[0][0]


def _assign_periods(financials: list[dict]) -> dict[str, tuple[int | None, int | None]]:
    """{accession: (año_fiscal, quarter)}.

    El año es el FISCAL, no el calendario: el Q1 de Apple cierra en diciembre y pertenece
    al ejercicio que termina el septiembre siguiente (FY2026, no 2025). Por eso el año lo
    da el 10-K ancla y no el `reportDate.year` del 10-Q — así calza con `financial_data`,
    que también rotula por año fiscal. El 10-K es el cierre (Q4); cada 10-Q se ancla al
    10-K que le sigue y se numera 1-2-3 por orden de `reportDate` dentro del ejercicio.
    """
    ann = sorted(
        (r for r in financials if r["form"] == "10-K" and r["_report"]),
        key=lambda r: r["_report"],
    )
    fye = [r["_report"] for r in ann]
    out: dict[str, tuple[int | None, int | None]] = {}
    for r in ann:
        out[r["accessionNumber"]] = (r["_report"].year, 4)

    # Mes de cierre fiscal: la moda de los 10-K. Sirve para fechar los 10-Q del ejercicio
    # EN CURSO, cuyo 10-K todavía no existe y por eso no tienen ancla.
    fye_month = Counter(f.month for f in fye).most_common(1)
    fye_month = fye_month[0][0] if fye_month else None

    def fiscal_year(rd: date) -> int | None:
        if fye_month is None:
            return rd.year
        # Un período que cierra DESPUÉS del mes de cierre pertenece al ejercicio siguiente
        # (el Q1 de Apple cierra en diciembre y es del FY que termina el septiembre que viene).
        return rd.year + 1 if rd.month > fye_month else rd.year

    # Agrupar los 10-Q por el ejercicio al que pertenecen (el primer cierre >= su reportDate).
    by_fy: dict[date | None, list[dict]] = {}
    for r in financials:
        if r["form"] != "10-Q" or not r["_report"]:
            continue
        rd = r["_report"]
        anchor = next((f for f in fye if f >= rd and (f - rd).days <= 400), None)
        by_fy.setdefault(anchor, []).append(r)
    for anchor, group in by_fy.items():
        for i, r in enumerate(sorted(group, key=lambda r: r["_report"]), start=1):
            # Con ancla, el año es el del cierre; sin ella (ejercicio en curso), se deriva.
            fy = anchor.year if anchor else fiscal_year(r["_report"])
            out[r["accessionNumber"]] = (fy, i if i <= 3 else None)
    return out


def build_events(submissions: dict) -> list[CalendarEvent]:
    """`submissions` completo -> earnings + financials confirmados (sin la estimada)."""
    recent = (submissions.get("filings", {}) or {}).get("recent", {}) or {}
    rows = _rows(recent)
    for r in rows:
        r["_report"] = _parse_date(r.get("reportDate"))

    events: list[CalendarEvent] = []
    financials = [r for r in rows if r["form"] in ("10-Q", "10-K")]
    periods = _assign_periods(financials)

    for r in rows:
        form = r["form"]
        filed = _parse_date(r.get("filingDate"))
        if filed is None:
            continue
        accession = r.get("accessionNumber")

        if form == "8-K" and "2.02" in (r.get("items") or ""):
            ts = r.get("acceptanceDateTime")
            t = None
            timing = None
            if ts:
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    t = dt.strftime("%H:%M")
                    timing = _timing_from_utc(dt)
                except ValueError:
                    pass
            events.append(CalendarEvent(
                "earnings", filed, t, timing, None, None, "8-K", accession, "confirmed"))

        elif form in ("10-Q", "10-K"):
            fy, quarter = periods.get(accession, (None, None))
            events.append(CalendarEvent(
                "financials", filed, None, None, fy, quarter,
                form, accession, "confirmed"))

    return events


# Cuánto puede desviarse de la fecha que proyecta la cadencia un anuncio de resultados
# recién publicado para seguir contando como tal. Los emisores se corren unos días entre
# trimestres; el 8-K de entregas de Tesla se adelanta ~20, que es lo que hay que dejar
# afuera.
_DIAS_DE_FASE = 15


def _earnings_de_resultados(events: list[CalendarEvent]) -> list[CalendarEvent]:
    """Los 8-K item 2.02 que son el anuncio de resultados, no otra cosa.

    El item 2.02 cubre cualquier "results of operations": además del anuncio trimestral,
    ahí entran las entregas de Tesla —tres semanas antes de los resultados— y las ventas
    mensuales de varios emisores. Mezclados dan medianas de 20 días y la estimación se
    descarta por no parecer trimestral.

    El que manda es el 10-Q/10-K: el anuncio de resultados es el 2.02 MÁS CERCANO a cada
    estado financiero. Cercano en términos relativos, no dentro de una ventana fija: la
    separación entre press release y 10-Q es propia de cada emisor —Hilton los presenta el
    mismo día, Walmart hasta tres semanas antes— y cualquier umbral absoluto parte en dos
    a los que se demoran.

    Si el anclaje deja menos de 3 se devuelven todos: en emisores enormes `filings.recent`
    apenas cubre unos meses, y es preferible la cadencia ruidosa a no estimar nada.
    """
    earnings = sorted((e for e in events if e.event_type == "earnings"),
                      key=lambda e: e.event_date)
    estados = sorted(e.event_date for e in events if e.event_type == "financials")
    if not estados or len(earnings) < 3:
        return earnings
    anclados = {min(earnings, key=lambda e: abs((e.event_date - f).days)).accession
                for f in estados}
    elegidos = [e for e in earnings if e.accession in anclados]
    return elegidos if len(elegidos) >= 3 else earnings


def _anuncio_sin_estado_aun(events: list[CalendarEvent], ultimo: CalendarEvent,
                            median_gap: int) -> CalendarEvent | None:
    """El anuncio de resultados posterior al último 10-Q/10-K, si la cadencia lo esperaba.

    Entre el press release y el 10-Q pasan días o semanas, así que el anuncio más reciente
    de la temporada todavía no tiene estado financiero al cual anclarse y `_earnings_de_
    resultados` no lo ve. Ignorarlo hacía retroceder un trimestre entero la estimación de
    todo emisor que acabara de reportar. Se acepta el que caiga donde la cadencia lo
    predice: así entra el press release recién salido y no el 8-K de entregas de Tesla,
    que se adelanta demasiado.
    """
    esperado = ultimo.event_date + timedelta(days=median_gap)
    posteriores = [e for e in events
                   if e.event_type == "earnings" and e.event_date > ultimo.event_date
                   and abs((e.event_date - esperado).days) <= _DIAS_DE_FASE]
    return min(posteriores, key=lambda e: abs((e.event_date - esperado).days),
               default=None)


def _proyectar(earnings: list[CalendarEvent], events: list[CalendarEvent],
               today: date) -> CalendarEvent | None:
    """Proyecta la próxima fecha desde una serie de anuncios ya elegida."""
    if len(earnings) < 3:
        return None
    gaps = sorted((earnings[i + 1].event_date - earnings[i].event_date).days
                  for i in range(len(earnings) - 1))
    median_gap = gaps[len(gaps) // 2]
    if not 60 <= median_gap <= 120:   # una cadencia fuera de lo trimestral no es fiable
        return None

    ultimo = earnings[-1]
    reciente = _anuncio_sin_estado_aun(events, ultimo, median_gap)
    if reciente is not None:
        ultimo = reciente

    nxt = ultimo.event_date + timedelta(days=median_gap)
    while nxt <= today:
        nxt += timedelta(days=median_gap)

    timing = Counter(e.timing for e in earnings if e.timing).most_common(1)
    return CalendarEvent(
        "estimated", nxt, None, timing[0][0] if timing else None,
        None, None, None, None, "estimated")


def estimate_next(events: list[CalendarEvent], today: date) -> CalendarEvent | None:
    """La próxima fecha de resultados, proyectada desde los earnings confirmados.

    Necesita al menos 3 earnings para medir la cadencia. Toma la mediana del intervalo
    entre anuncios consecutivos (≈91 días) y avanza desde el último hasta pasar `today`.
    Hereda el horario (bmo/amc) más frecuente. Sin earnings suficientes, no inventa.

    Si la cadencia cruda no da nada, se reintenta con los anuncios anclados al 10-Q/10-K
    (ver `_earnings_de_resultados`). El orden importa y es deliberado: el anclaje se usa
    de rescate y no de camino principal porque, medido contra los anuncios que de verdad
    ocurrieron, rescata a los emisores que publican varios item 2.02 por trimestre —Tesla
    y sus entregas— pero corre unos días la fase de emisores que ya venían estimando bien.
    """
    earnings = sorted((e for e in events if e.event_type == "earnings"),
                      key=lambda e: e.event_date)
    estimada = _proyectar(earnings, events, today)
    if estimada is not None:
        return estimada

    de_resultados = _earnings_de_resultados(events)
    if len(de_resultados) == len(earnings):
        return None       # el anclaje no descartó nada: reintentar daría lo mismo
    return _proyectar(de_resultados, events, today)
