"""Parsers puros: JSON de companyfacts -> modelos. Sin red y sin BD.

Acá viven las tres reglas que deciden si los números salen bien o salen mal en silencio:

1. **El período se deriva de `start`/`end`, nunca de `fy`/`fp`** (spec §6.4). Verificado
   sobre Apple: el trimestre 2017-10-01..2017-12-30 aparece etiquetado `fy=2019 fp=Q1` en
   un 10-Q y `fy=2019 fp=FY` en un 10-K. `fy`/`fp` describen el filing, no el hecho.

2. **Los flujos se toman ACUMULADOS (YTD)** (spec §5): de un 10-Q se toma la duración que
   arranca en el inicio del año fiscal, no el trimestre suelto. En el dataset de Apple los
   hechos de 3 meses le ganan 62 a 16 a los acumulados, así que "tomar lo que venga" cae
   justo en el error. Ese error no lanza excepción: deja los estados de EEUU discretos
   mientras los chilenos son acumulados, y toda comparación entre mercados da mal callada.

3. **Deduplicar por `filed` más reciente** (spec §6.1): el mismo hecho se repite en el
   10-K original, en los 10-Q siguientes como comparativo y en las enmiendas. Gana el
   filing más nuevo, así una reexpresión pisa al original.
"""

import math
from collections import defaultdict
from datetime import date

from src.edgar.models import Fact, FiscalPeriod, LineValue
from src.edgar.taxonomy import CONCEPTS, resolve_tag

# Rangos en días para clasificar una duración como Q1/Q2/Q3/ejercicio completo. Son
# ventanas y no valores exactos porque el año fiscal de EEUU suele ser de 52/53 semanas y
# no de meses calendario: el FY2024 de Apple mide 363 días y sus trimestres 90/181/272.
_SPAN_TO_QUARTER = (
    (80, 100, 1),
    (170, 195, 2),
    (260, 290, 3),
    (350, 380, 4),
)

# Tolerancia al comparar el inicio de un hecho contra el inicio del año fiscal. Existe
# porque los emisores no son consistentes en el borde: el mismo ejercicio aparece a veces
# arrancando el día del cierre anterior y a veces el día siguiente. Sin holgura la serie
# YTD se parte en dos. 5 días es holgado para el borde y sigue siendo ínfimo frente a los
# ~90 que separan un trimestre suelto del inicio del año, que es lo que hay que excluir.
_START_TOLERANCE_DAYS = 5


def coerce_value(raw) -> float | None:
    """Convierte a float sólo lo que es un número de verdad; si no, None (hueco).

    El spec (§7) lo pide explícito por un incidente real: en JS `Number(null)` es `0`, y
    el cargador de precios metió 149 barras con precio cero. El equivalente en Python es
    `float(True) == 1.0` (bool es subclase de int), así que el bool se rechaza a mano.
    Un dato que no está tiene que quedar como hueco, jamás como cero.
    """
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return None if (math.isnan(value) or math.isinf(value)) else value
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _parse_date(raw) -> date | None:
    if not raw or not isinstance(raw, str):
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def parse_facts(payload: dict, tag: str, unit: str = "USD") -> list[Fact]:
    """Extrae los hechos de un tag us-gaap del payload de companyfacts."""
    entry = (payload.get("facts", {}).get("us-gaap", {}) or {}).get(tag)
    if not entry:
        return []
    items = (entry.get("units", {}) or {}).get(unit) or []
    facts: list[Fact] = []
    for item in items:
        end = _parse_date(item.get("end"))
        filed = _parse_date(item.get("filed"))
        value = coerce_value(item.get("val"))
        if end is None or filed is None or value is None:
            continue
        facts.append(
            Fact(
                tag=tag,
                start=_parse_date(item.get("start")),
                end=end,
                val=value,
                accn=item.get("accn", ""),
                form=item.get("form", ""),
                filed=filed,
            )
        )
    return facts


def dedupe_facts(facts: list[Fact]) -> list[Fact]:
    """Un hecho por (start, end): gana el `filed` más reciente (spec §6.1).

    Ante el mismo `filed` (una enmienda publicada el mismo día que el original) desempata
    el `accn` mayor, que es el correlativo de la SEC: sin eso el ganador depende del orden
    en que vino el JSON y dos corridas podrían cargar valores distintos.
    """
    best: dict[tuple[date | None, date], Fact] = {}
    for fact in facts:
        key = (fact.start, fact.end)
        current = best.get(key)
        if current is None or (fact.filed, fact.accn) > (current.filed, current.accn):
            best[key] = fact
    return list(best.values())


def _quarter_from_span(start: date, end: date) -> int | None:
    days = (end - start).days
    for low, high, quarter in _SPAN_TO_QUARTER:
        if low <= days <= high:
            return quarter
    return None


def build_fiscal_calendar(facts: list[Fact]) -> dict[tuple[int, int], FiscalPeriod]:
    """Reconstruye el calendario fiscal de la empresa a partir de las fechas de los hechos.

    Estrategia: toda duración de ~12 meses es un ejercicio (venga del 10-K del año o de un
    comparativo dentro de otro filing — un comparativo sigue siendo un ejercicio real de
    esta empresa, y es de donde sale la historia). Con esas ventanas fijadas, los hechos
    que arrancan junto con el ejercicio dan los cierres de Q1/Q2/Q3.

    `period_year` es el **año fiscal**, tomado como el año calendario del cierre (spec
    §6.3). Ojo con lo que eso implica: el Q1 del FY2024 de Apple termina en diciembre de
    2023 y aun así va con `period_year=2024`, porque pertenece a ese ejercicio.
    """
    fy_windows: dict[int, tuple[date, date]] = {}
    for fact in facts:
        if fact.start is None:
            continue
        if _quarter_from_span(fact.start, fact.end) != 4:
            continue
        year = fact.end.year
        current = fy_windows.get(year)
        # Ante dos ventanas para el mismo año fiscal, gana la que cierra más tarde: es la
        # del ejercicio y no un recorte raro.
        if current is None or fact.end > current[1]:
            fy_windows[year] = (fact.start, fact.end)

    calendar: dict[tuple[int, int], FiscalPeriod] = {}
    for year, (fy_start, fy_end) in fy_windows.items():
        for fact in facts:
            if fact.start is None or fact.end > fy_end:
                continue
            if abs((fact.start - fy_start).days) > _START_TOLERANCE_DAYS:
                continue
            quarter = _quarter_from_span(fact.start, fact.end)
            if quarter is None:
                continue
            known = calendar.get((year, quarter))
            if known is None or fact.end > known.end:
                calendar[(year, quarter)] = FiscalPeriod(year, quarter, fy_start, fact.end)
    return calendar


def select_period_values(
    facts: list[Fact], calendar: dict[tuple[int, int], FiscalPeriod]
) -> dict[tuple[int, int], float]:
    """Mapea los hechos de un tag a {(year, quarter): valor}.

    Las duraciones sólo entran si arrancan con el año fiscal — ahí está aplicada la regla
    §5. El trimestre suelto de un 10-Q arranca ~90 días después del inicio del ejercicio,
    así que cae fuera de la tolerancia y queda descartado, que es exactamente lo que se
    busca.

    Los instants (balance) se ubican por fecha de cierre: un saldo no se acumula, es la
    foto al cierre del trimestre (§5.2).
    """
    ends_to_period = {p.end: p for p in calendar.values()}
    out: dict[tuple[int, int], float] = {}
    for fact in facts:
        if fact.is_instant:
            period = ends_to_period.get(fact.end)
            if period is None:
                continue
        else:
            period = ends_to_period.get(fact.end)
            if period is None:
                continue
            if abs((fact.start - period.start).days) > _START_TOLERANCE_DAYS:
                continue  # trimestre suelto: no es la serie acumulada
        out[(period.year, period.quarter)] = fact.val
    return out


def available_tags(payload: dict) -> frozenset[str]:
    return frozenset((payload.get("facts", {}) or {}).get("us-gaap", {}) or {})


def resolve_concept_periods(
    payload: dict, concept, calendar: dict[tuple[int, int], FiscalPeriod]
) -> dict[tuple[int, int], tuple[float, str]]:
    """{(year, quarter): (valor, tag)} eligiendo **un solo tag por año fiscal**.

    Las dos tentaciones son resolver la cadena una vez por empresa o resolverla trimestre a
    trimestre, y las dos están mal:

    * **Una vez por empresa** (quedarse con el primer tag que el emisor haya usado alguna
      vez) rompe cuando el emisor migra de tag a mitad de la historia. XOM publicó ingresos
      como `RevenueFromContractWithCustomerExcludingAssessedTax` hasta 2023 y desde ahí usa
      `Revenues`: ganaba el primero —que existe, pero está muerto— y XOM se quedaba sin
      ingresos de 2023 en adelante, sin error ni aviso.

    * **Trimestre a trimestre** rompe cuando dos tags conviven midiendo cosas distintas.
      Mastercard tagea `RevenueFromContractWithCustomerExcludingAssessedTax` = ingresos
      BRUTOS y `Revenues` = ingresos NETOS (su cifra de titular), y conviven en 29 períodos
      con valores siempre distintos. Como MA no publica el bruto del ejercicio, la serie
      2022 salía con Q1-Q3 en bruto y Q4 en neto: 8.025 / 16.729 / 25.896 / 22.237. El Q4
      "bajaba" respecto del Q3 — mezcla de dos magnitudes, no un dato malo.

    El año fiscal es la unidad correcta: es lo bastante chico para tolerar una migración
    (que ocurre en el borde de un año) y lo bastante grande para que una serie trimestral
    no mezcle dos magnitudes.

    El tag del año se elige por: (1) que tenga el dato ANUAL —el Q4 es la cifra de titular
    y quedarse sin ella es lo más caro—, (2) que cubra más trimestres, (3) el orden de la
    cadena. Con eso MA toma `Revenues` en todos los trimestres (5.167 / 10.664 / 16.420 /
    22.237, que es lo que reporta), y XOM y JPM no se mueven.
    """
    tags = available_tags(payload)
    candidates = [t for t in concept.tags if t in tags]
    by_tag = {
        tag: select_period_values(
            dedupe_facts(parse_facts(payload, tag, unit=concept.unit)), calendar
        )
        for tag in candidates
    }

    resolved: dict[tuple[int, int], tuple[float, str]] = {}
    years = {year for periods in by_tag.values() for (year, _) in periods}
    for year in years:
        best_key, best_tag = None, None
        for priority, tag in enumerate(candidates):
            quarters = {q for (y, q) in by_tag[tag] if y == year}
            if not quarters:
                continue
            key = (4 in quarters, len(quarters), -priority)
            if best_key is None or key > best_key:
                best_key, best_tag = key, tag
        if best_tag is None:
            continue
        for (y, q), value in by_tag[best_tag].items():
            if y == year:
                resolved[(y, q)] = (value, best_tag)
    return resolved


def build_line_values(payload: dict, min_year: int | None = None) -> list[LineValue]:
    """companyfacts completo -> celdas listas para cargar.

    Un concepto que la empresa no publica no genera filas: queda hueco. Es deliberado —
    JPM no tiene `AssetsCurrent` (un banco no presenta balance clasificado) y WMT no
    publica `Liabilities`; inventarles un valor sería peor que no tenerlos.
    """
    # El calendario se arma con TODAS las duraciones del catálogo y no tag por tag: si una
    # empresa no publicó ingresos en un trimestre pero sí el balance, igual necesitamos
    # saber qué día cierra ese trimestre para poder ubicar el saldo.
    tags = available_tags(payload)
    all_facts: list[Fact] = []
    for concept in CONCEPTS:
        if concept.unit != "USD":
            continue
        for tag in concept.tags:
            if tag in tags:
                all_facts.extend(dedupe_facts(parse_facts(payload, tag)))

    calendar = build_fiscal_calendar(all_facts)
    if min_year is not None:
        calendar = {k: v for k, v in calendar.items() if v.year >= min_year}

    values: list[LineValue] = []
    for concept in CONCEPTS:
        for (year, quarter), (value, tag) in resolve_concept_periods(
            payload, concept, calendar
        ).items():
            values.append(
                LineValue(
                    concept_key=concept.key,
                    tag=tag,
                    label_es=concept.label_es,
                    label_en=concept.label_en,
                    role_code=concept.role_code,
                    category=concept.category,
                    subcategory=concept.subcategory,
                    display_order=concept.display_order,
                    year=year,
                    quarter=quarter,
                    value=value,
                    unit=concept.unit,
                )
            )
    return values


def primary_tag_by_concept(values: list[LineValue]) -> dict[str, str]:
    """Tag representativo de cada concepto: el del período más reciente.

    Hace falta porque `source_tag` vive en `financial_line_items`, que es **por empresa**,
    mientras que el tag puede cambiar a lo largo de la serie (ver `resolve_concept_periods`).
    Se guarda el vigente, que es el que describe cómo reporta hoy el emisor.
    """
    latest: dict[str, tuple[tuple[int, int], str]] = {}
    for v in values:
        key = (v.year, v.quarter)
        current = latest.get(v.concept_key)
        if current is None or key > current[0]:
            latest[v.concept_key] = (key, v.tag)
    return {k: tag for k, (_, tag) in latest.items()}


def group_by_period(values: list[LineValue]) -> dict[tuple[int, int], dict[str, float]]:
    """{(year, quarter): {concept_key: valor}} — para validar cuadratura y acumulación."""
    out: dict[tuple[int, int], dict[str, float]] = defaultdict(dict)
    for v in values:
        out[(v.year, v.quarter)][v.concept_key] = v.value
    return dict(out)
