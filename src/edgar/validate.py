"""Los criterios de aceptación del spec (§8), como código que corre en cada ingesta.

Son chequeos sobre los datos ya normalizados, antes de que toquen la BD: un mapeo de tags
mal hecho tiene que notarse acá y no seis meses después en un ratio raro.
"""

from src.edgar.ingest import group_by_period, parse_facts
from src.edgar.models import LineValue

# Tolerancia relativa del cuadre. No es cero porque los emisores redondean a millones y un
# descuadre de unos dólares sobre cientos de miles de millones es ruido, no un mapeo malo.
_IDENTITY_TOLERANCE = 1e-6

# Un descuadre por debajo de esto entre dos vintages es una reexpresión normal y no se
# reporta. Se calibró contra las 49: los desfases reales por reexpresión llegan a 1,7% (GE
# 2016) y los errores de mapeo, cuando los hubo, estaban en otro orden de magnitud (30%+).
_DRIFT_TOLERANCE = 0.05


def check_accounting_identity(payload: dict, min_year: int | None = None) -> list[str]:
    """§8.1: Activos = Pasivos + Patrimonio, comparado DENTRO DE CADA FILING.

    La comparación va por `accn` (el filing) y no sobre la serie ya deduplicada, y esa es
    toda la diferencia. El §8.1 existe para responder "¿elegimos bien los tags?", y sobre
    la serie deduplicada esa pregunta no se puede responder: el dedupe por `filed` más
    reciente (§6.1) toma cada hecho por separado, así que si el emisor reexpresa `Assets`
    en un 10-K posterior pero deja de tagear `LiabilitiesAndStockholdersEquity`, la serie
    termina con un `Assets` nuevo contra un total viejo y no cuadra — sin que haya nada mal
    en el mapeo.

    Pasa de verdad y no es marginal: JPM reexpresó los activos de 2013 en su 10-K de 2016
    (2.414.879 contra 2.415.689) y no volvió a tagear el total. Contrastando dentro del
    mismo filing, ambos valen 2.415.689 y cuadran exacto.

    Se usa `LiabilitiesAndStockholdersEquity` como contraparte y no `Liabilities +
    StockholdersEquity` porque lo publican todos —hasta JPM y WMT, que no tagean
    `Liabilities`— y al ser un total declarado por el emisor no depende de que hayamos
    elegido bien los componentes.

    `min_year` acota el chequeo a lo que efectivamente se carga. Importa: el único
    descuadre real de las 49 es JPM al 2009-12-31 (4%, en el filing 0000950123-10-074254),
    y 2009 es el primer año del mandato XBRL —tagueo notoriamente flojo— y está fuera de la
    ventana que ingestamos. Auditar años que no se cargan sólo produce ruido.
    """
    assets = {(f.accn, f.end): f.val for f in parse_facts(payload, "Assets")}
    totals = {
        (f.accn, f.end): f.val
        for f in parse_facts(payload, "LiabilitiesAndStockholdersEquity")
    }
    problems: list[str] = []
    shared = {k for k in set(assets) & set(totals) if min_year is None or k[1].year >= min_year}
    for key in sorted(shared, key=lambda k: (k[1], k[0])):
        left, right = assets[key], totals[key]
        if abs(left - right) > max(abs(left), 1.0) * _IDENTITY_TOLERANCE:
            accn, end = key
            problems.append(
                f"{end} (filing {accn}): Activos {left:,.0f} != Patrimonio+Pasivos "
                f"{right:,.0f} (dif {left - right:,.0f})"
            )
    return problems


def check_restatement_drift(values: list[LineValue]) -> list[str]:
    """Períodos donde el balance YA CARGADO no cuadra por mezcla de vintages.

    No es lo mismo que `check_accounting_identity`: acá el mapeo está bien y aun así la
    fila guardada no cierra, porque un tag se reexpresó y el otro se quedó con el valor
    viejo. Es una consecuencia inevitable de la regla del §6.1 (cada hecho toma su `filed`
    más reciente por separado) y el spec pide documentarla porque "cambia los números".

    Se deja como aviso y no como error: la alternativa —reconstruir cada período desde un
    único filing— tiraría a la basura toda línea que ese filing no haya tageado, que es
    bastante peor. Sobre las 49 el desfase máximo es 1,7% y casi todo vive bajo 0,2%,
    siempre en períodos viejos.
    """
    problems: list[str] = []
    for (year, quarter), data in sorted(group_by_period(values).items()):
        assets, total = data.get("AT"), data.get("PatPas")
        if assets is None or total is None or assets == 0:
            continue
        drift = abs(assets - total) / abs(assets)
        if drift > _DRIFT_TOLERANCE:
            problems.append(
                f"{year}Q{quarter}: descuadre {drift * 100:.2f}% "
                f"({assets:,.0f} vs {total:,.0f}) — demasiado para una reexpresión"
            )
    return problems


def check_accumulation(values: list[LineValue], concept: str = "Ventas") -> list[str]:
    """§8.2: en un flujo, valor(Q1) <= valor(Q2) <= valor(Q3) <= valor(Q4).

    Es LA prueba de que se tomó la duración acumulada y no el trimestre suelto. Si Q2 ≈ Q1
    en vez de ser ~el doble, se tomaron los 3 meses: está mal (spec §5).

    Se compara con <= y no con <: un trimestre de ingresos en cero es raro pero posible, y
    no es lo que este chequeo busca cazar. Y sólo se evalúa la serie completa de 4
    trimestres, porque un hueco no dice nada del orden.

    Ojo: sólo vale para flujos que no pueden ser negativos, por eso el default es Ventas.
    Un flujo de caja puede perfectamente decrecer acumulando.
    """
    problems: list[str] = []
    by_period = group_by_period(values)
    for year in sorted({year for year, _ in by_period}):
        series = [by_period.get((year, q), {}).get(concept) for q in (1, 2, 3, 4)]
        if any(v is None for v in series):
            continue
        for q in range(3):
            if series[q] > series[q + 1]:
                problems.append(
                    f"{year}: {concept} Q{q + 1}={series[q]:,.0f} > Q{q + 2}="
                    f"{series[q + 1]:,.0f} — ¿se tomó la duración de 3 meses?"
                )
    return problems


def summarize(payload: dict, values: list[LineValue]) -> dict:
    by_period = group_by_period(values)
    years = sorted({year for year, _ in by_period})
    return {
        "celdas": len(values),
        "conceptos": len({v.concept_key for v in values}),
        "periodos": len(by_period),
        "años": (years[0], years[-1]) if years else None,
        "identidad": check_accounting_identity(payload),
        "drift": check_restatement_drift(values),
        "acumulacion": check_accumulation(values),
    }
