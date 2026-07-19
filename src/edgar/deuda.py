"""Kd declarado de EEUU: la tasa efectiva ponderada de la deuda, reconstruida desde los
facts DIMENSIONALES del 10-K.

Es el equivalente para EDGAR de ``cmf_extract/xbrl_deuda.py`` (Chile). La idea es la misma:

    Kd = Σ(tasa × monto) / Σ(monto)   sobre cada instrumento de deuda declarado

En Chile las tasas salen de la nota de préstamos que la CMF OBLIGA a estructurar. En EEUU
la SEC NO obliga: sólo ~15-20% de las empresas taggea las tasas en XBRL
(``us-gaap:DebtInstrumentInterestRateStatedPercentage`` / ``...EffectivePercentage``),
dimensionadas por miembro del ``us-gaap:DebtInstrumentAxis`` (un valor por bono/crédito).
Para el resto este módulo devuelve ``None`` y el DCF cae a la estimación
``InterestExpense / deuda``. Preferimos un hueco a un Kd inventado.

Los facts NO vienen en el ``companyfacts`` plano de la SEC (que aplana las dimensiones):
hay que parsear la instancia iXBRL del propio filing, resolviendo cada ``contextRef`` a su
miembro del eje y a su fecha, y cruzando tasa + monto por miembro.
"""
from __future__ import annotations

import html as _html
import re
from dataclasses import dataclass, field
from typing import Optional

try:
    from src.edgar.endpoints import pad_cik, submissions_url
except ImportError:  # ejecutado desde dentro de src/edgar/
    from endpoints import pad_cik, submissions_url  # type: ignore


# Conceptos us-gaap, en orden de PREFERENCIA. La tasa efectiva refleja el costo real
# (incluye descuentos/primas de emisión); la nominal es el cupón. El monto contable
# (carrying) es lo que figura en el balance; el nominal (face) es el principal emitido.
_TAGS_TASA = ("DebtInstrumentInterestRateEffectivePercentage",
              "DebtInstrumentInterestRateStatedPercentage")
_TAGS_MONTO = ("DebtInstrumentCarryingAmount", "DebtInstrumentFaceAmount")

_EJE_DEUDA = "DebtInstrumentAxis"

# Clasificación gruesa del instrumento a partir del nombre del miembro. No es un dato de la
# SEC: es una heurística sobre la etiqueta que el emisor eligió (crm:A2028SeniorNotesMember).
_PATRONES_INSTRUMENTO = (
    ("bono", re.compile(r"note|bond|debenture|senior", re.I)),
    ("prestamo", re.compile(r"credit|loan|facility|revolv|term", re.I)),
)


def _clasificar(miembro: str) -> str:
    nombre = miembro.split(":")[-1]
    for etiqueta, patron in _PATRONES_INSTRUMENTO:
        if patron.search(nombre):
            return etiqueta
    return "otro"


@dataclass
class Credito:
    """Un instrumento de deuda declarado: su tasa y su monto, atados al mismo miembro."""
    miembro: str
    instrumento: str            # 'bono' | 'prestamo' | 'otro'
    tasa_efectiva: Optional[float] = None
    monto_contable: Optional[float] = None
    fecha: Optional[str] = None

    @property
    def utilizable(self) -> bool:
        """Sólo pondera el Kd si trae tasa Y monto, ambos plausibles.

        Rango de tasa **[0.3%, 35%)**. El techo 35% es el mismo CHECK que la tabla
        chilena ``xbrl_deuda`` (rechaza un cupón mal escalado, 3,70 en vez de 0,0370).
        El PISO 0,3% es específico de EEUU: varias empresas (Apple, p. ej.) taggean
        un miembro AGREGADO de toda su deuda con una "tasa efectiva" de 3 puntos base
        (0,03%) —en realidad un ajuste de cobertura/basis, no el costo del crédito—.
        Ponderarlo hunde el Kd (Apple daría 0,23% sobre $91B). Ninguna deuda corporativa
        cuesta 0,3%: por debajo de eso es un mis-tag, no un instrumento. Un bono genuino a
        0% aporta ~0 al Kd ponderado igual, así que excluirlo no cambia el resultado.
        """
        return (
            self.tasa_efectiva is not None
            and 0.003 <= self.tasa_efectiva < 0.35
            and self.monto_contable is not None
            and self.monto_contable > 0
        )


@dataclass
class CostoDeuda:
    kd: float                       # tasa efectiva ponderada por monto contable
    deuda_cubierta: float           # cuánta deuda respalda ese Kd (para la cobertura)
    n_creditos: int
    por_instrumento: dict[str, float] = field(default_factory=dict)
    # El detalle usado, de mayor a menor monto: es lo que alimenta la hoja DEUDA FINANCIERA
    # del Excel (mismo rol que la lista `creditos` del deuda.json chileno).
    creditos: list[Credito] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Parsing de la instancia iXBRL
# ---------------------------------------------------------------------------

_RE_CONTEXT = re.compile(
    r'<(?:\w+:)?context[^>]*\bid="([^"]+)"[^>]*>(.*?)</(?:\w+:)?context>', re.S)
_RE_MIEMBRO = re.compile(
    r'dimension="[^"]*' + _EJE_DEUDA + r'"[^>]*>\s*([^<\s]+)', re.S)
_RE_FECHA = re.compile(
    r'<(?:\w+:)?(?:instant|enddate)>\s*([\d-]+)', re.I)


def _contextos_por_eje(html: str) -> dict[str, tuple[str, Optional[str]]]:
    """``{context_id: (miembro_del_DebtInstrumentAxis, fecha)}``.

    Sólo los contextos que dimensionan por ``DebtInstrumentAxis`` (los que atan un fact a un
    bono/crédito puntual). La fecha desempata el saldo del período actual del comparativo.
    """
    out: dict[str, tuple[str, Optional[str]]] = {}
    for cid, body in _RE_CONTEXT.findall(html):
        m = _RE_MIEMBRO.search(body)
        if not m:
            continue
        f = _RE_FECHA.search(body)
        out[cid] = (m.group(1), f.group(1) if f else None)
    return out


def _facts(html: str, concepto: str) -> list[tuple[str, float]]:
    """``[(context_id, valor)]`` de un concepto us-gaap en la instancia iXBRL.

    Aplica ``scale`` y ``sign`` como manda inline XBRL: el texto visible ("3.70", "1,500")
    se transforma con ``scale`` (×10^scale) al valor real (0.0370, 1.5e9).
    """
    out: list[tuple[str, float]] = []
    patron = re.compile(
        r'<ix:nonfraction([^>]*name="us-gaap:' + re.escape(concepto) + r'"[^>]*)>(.*?)</ix:nonfraction>',
        re.I | re.S)
    for match in patron.finditer(html):
        attrs, inner = match.group(1), match.group(2)
        cref = re.search(r'contextref="([^"]+)"', attrs, re.I)
        if not cref:
            continue
        texto = _html.unescape(re.sub(r"<[^>]+>", "", inner)).strip().replace(",", "")
        try:
            val = float(texto)
        except ValueError:
            continue
        scale = re.search(r'scale="(-?\d+)"', attrs, re.I)
        if scale:
            val *= 10 ** int(scale.group(1))
        sign = re.search(r'sign="([^"]+)"', attrs, re.I)
        if sign and sign.group(1).strip() == "-":
            val = -val
        out.append((cref.group(1), val))
    return out


def _mejor_por_miembro(html: str, tags: tuple[str, ...],
                       ctx: dict[str, tuple[str, Optional[str]]]
                       ) -> dict[str, tuple[float, Optional[str]]]:
    """Para cada miembro, el valor del PRIMER tag disponible (por preferencia) en su fecha
    más reciente. Devuelve ``{miembro: (valor, fecha)}``.

    - La preferencia entre tags (efectiva antes que nominal; carrying antes que face) se
      respeta: si un miembro ya tiene valor de un tag más preferente, no lo pisa uno menos.
    - Entre fechas de un mismo tag gana la más nueva (el saldo actual, no el comparativo).
    """
    elegido: dict[str, tuple[float, Optional[str], int]] = {}  # miembro -> (val, fecha, prioridad)
    for prioridad, tag in enumerate(tags):
        for cid, val in _facts(html, tag):
            if cid not in ctx:
                continue
            miembro, fecha = ctx[cid]
            prev = elegido.get(miembro)
            if prev is None:
                elegido[miembro] = (val, fecha, prioridad)
            else:
                _, prev_fecha, prev_prio = prev
                if prioridad < prev_prio:
                    elegido[miembro] = (val, fecha, prioridad)
                elif prioridad == prev_prio and (fecha or "") > (prev_fecha or ""):
                    elegido[miembro] = (val, fecha, prioridad)
    return {m: (v, f) for m, (v, f, _p) in elegido.items()}


def parsear_instancia(html: str) -> list[Credito]:
    """Los créditos declarados en la instancia iXBRL de un 10-K.

    Cruza tasa (``DebtInstrument*Percentage``) y monto (``DebtInstrument*Amount``) por
    miembro del ``DebtInstrumentAxis``. Devuelve lista vacía si la empresa no taggea tasas.
    """
    ctx = _contextos_por_eje(html)
    if not ctx:
        return []
    tasas = _mejor_por_miembro(html, _TAGS_TASA, ctx)
    montos = _mejor_por_miembro(html, _TAGS_MONTO, ctx)
    creditos: list[Credito] = []
    for miembro, (tasa, fecha_t) in tasas.items():
        if miembro not in montos:
            continue
        monto, fecha_m = montos[miembro]
        creditos.append(Credito(
            miembro=miembro,
            instrumento=_clasificar(miembro),
            tasa_efectiva=tasa,
            monto_contable=monto,
            fecha=fecha_m or fecha_t,
        ))
    return creditos


def a_dict_excel(cd: CostoDeuda) -> dict:
    """El dict que consume la hoja DEUDA FINANCIERA del Excel (mismo formato que el
    ``deuda.json`` chileno). Los montos van en la moneda de reporte (USD); el 10-K
    presenta el carrying amount en USD sea cual sea la moneda original del bono.
    """
    return {
        "kd": cd.kd,
        "n_creditos": cd.n_creditos,
        "por_moneda": {"USD": cd.deuda_cubierta},
        "por_instrumento": cd.por_instrumento,
        "vencimientos": {},  # el parser US no reconstruye el perfil de vencimientos
        "fuente": "Nota de deuda del 10-K (SEC/EDGAR)",
        "creditos": [
            {
                "miembro": c.miembro.split(":")[-1],
                "instrumento": c.instrumento,
                "moneda": "USD",
                "monto_contable": c.monto_contable,
                "tasa_efectiva": c.tasa_efectiva,
            }
            for c in cd.creditos
        ],
    }


def costo_de_deuda_desde_instancia(html: str) -> Optional[CostoDeuda]:
    """El Kd ponderado de una instancia iXBRL, o ``None`` si no hay tasas declaradas."""
    utiles = [c for c in parsear_instancia(html) if c.utilizable]
    if not utiles:
        return None
    total = sum(c.monto_contable for c in utiles)  # type: ignore[misc]
    if total <= 0:
        return None
    kd = sum(c.tasa_efectiva * c.monto_contable for c in utiles) / total  # type: ignore[misc]
    por_instrumento: dict[str, float] = {}
    for c in utiles:
        por_instrumento[c.instrumento] = por_instrumento.get(c.instrumento, 0.0) + c.monto_contable  # type: ignore[misc]
    ordenados = sorted(utiles, key=lambda c: c.monto_contable or 0, reverse=True)
    return CostoDeuda(kd=kd, deuda_cubierta=total, n_creditos=len(utiles),
                      por_instrumento=por_instrumento, creditos=ordenados)


# ---------------------------------------------------------------------------
# Localización del último 10-K y su instancia
# ---------------------------------------------------------------------------

@dataclass
class Filing10K:
    instancia_url: str
    period_year: int
    period_quarter: int  # 4 (el 10-K es anual)
    filing_date: str


def ultimo_10k(client, cik: str | int) -> Optional[Filing10K]:
    """La instancia iXBRL del 10-K más reciente de la empresa, o ``None``."""
    data = client.get_json(submissions_url(cik))
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    for i, form in enumerate(forms):
        if form != "10-K":
            continue
        acc = recent["accessionNumber"][i].replace("-", "")
        doc = recent["primaryDocument"][i]
        report_date = recent.get("reportDate", [None] * len(forms))[i] or ""
        filing_date = recent.get("filingDate", [None] * len(forms))[i] or ""
        year = int(report_date[:4]) if report_date[:4].isdigit() else None
        if year is None:
            continue
        cik_int = int(pad_cik(cik))
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc}/{doc}"
        return Filing10K(instancia_url=url, period_year=year, period_quarter=4,
                         filing_date=filing_date)
    return None


def costo_de_deuda(client, cik: str | int) -> Optional[tuple[CostoDeuda, Filing10K]]:
    """El Kd declarado de la empresa desde su último 10-K, o ``None`` si no taggea tasas."""
    filing = ultimo_10k(client, cik)
    if filing is None:
        return None
    html = client.get_text(filing.instancia_url)
    cd = costo_de_deuda_desde_instancia(html)
    if cd is None:
        return None
    return cd, filing
