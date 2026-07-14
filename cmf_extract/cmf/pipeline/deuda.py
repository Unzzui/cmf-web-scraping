"""La deuda financiera de la empresa, préstamo por préstamo, lista para el Excel.

POR QUÉ
-------
El DCF estima el costo de la deuda así:

    Kd = costos financieros del período / deuda financiera

Es una aproximación cruda, y en muchas empresas simplemente se rompe. Cuando la empresa
tiene poca deuda financiera pero sí costos financieros -- intereses de arrendamientos, por
ejemplo -- el cociente se dispara:

    FORUS              Kd estimado 958,41%   ·   Kd declarado 0,52%
    SOPROCAL           Kd estimado 198,01%   ·   Kd declarado 0,88%
    SODIMAC            Kd estimado  91,18%   ·   Kd declarado 3,24%
    TELEFÓNICA CHILE   Kd estimado  60,73%   ·   Kd declarado 7,64%

Con un Kd de 958% el WACC no significa nada, y el modelo caía al `IFERROR(...,0.10)`: un
10% inventado, presentado como si fuera el costo de capital de la empresa.

Pero la empresa YA DECLARA la tasa. En la nota de préstamos del XBRL cada crédito viene
con su acreedor, su moneda, su vencimiento y su TASA EFECTIVA. Arauco declara 137 créditos,
uno por uno; Aguas Andinas, 65. 163 de las 232 empresas traen esta nota.

    Kd = promedio de las tasas efectivas, ponderado por el monto contable de cada crédito

Eso no es una estimación: es lo que la empresa firma ante la CMF.

DÓNDE QUEDA
-----------
En `out_consolidated_*/deuda.json`, junto al resto de lo que produce la fase 2. La fase 3
lo lee para armar el bloque de WACC y la hoja de deuda del Excel. Se calcula una vez por
corrida y no en cada hoja: parsear la instancia XBRL cuesta ~1 segundo, y hacerlo tres
veces por empresa se nota.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path


def _xbrl_mas_reciente(company_dir: Path) -> Path | None:
    """La instancia XBRL del cierre más reciente que la empresa haya presentado."""
    instancias = sorted(company_dir.glob("Estados*_extracted/*.xbrl"))
    return instancias[-1] if instancias else None


def extraer_deuda(company_dir: Path, out_dir: Path,
                  enable_log: bool = False) -> dict | None:
    """Mina la nota de préstamos y la deja en `out_dir/deuda.json`.

    Devuelve None -- y no escribe nada -- si la empresa no declara tasas. Un hueco es
    preferible a un Kd inventado: quien lo consuma decide si cae a la estimación.
    """
    try:
        from cmf_extract import xbrl_deuda as xd
    except ImportError:
        import xbrl_deuda as xd

    xbrl = _xbrl_mas_reciente(company_dir)
    if xbrl is None:
        return None

    try:
        costo = xd.costo_de_deuda(xbrl)
        creditos = [c for c in xd.creditos(xbrl) if c.utilizable]
    except Exception as exc:
        if enable_log:
            print(f"[deuda] {company_dir.name}: no se pudo leer la nota de préstamos: {exc}")
        return None

    if costo is None:
        return None

    datos = {
        "fuente": xbrl.name,
        "kd": costo.kd,
        "deuda_cubierta": costo.deuda_cubierta,
        "n_creditos": costo.n_creditos,
        "por_moneda": costo.por_moneda,
        # Cuánto hay que refinanciar dentro de doce meses, y cuánto es bono, préstamo o
        # arriendo. Bajo IFRS 16 un arriendo ES deuda: en SMU son el 58,6% del total.
        "corriente": costo.corriente,
        "no_corriente": costo.no_corriente,
        "por_instrumento": costo.por_instrumento,
        # El perfil de vencimientos. Dice si la empresa tiene un muro de deuda el año que
        # viene o si lo tiene repartido a diez años -- dos empresas con la misma deuda y el
        # mismo Kd pueden ser riesgos completamente distintos, y eso no se ve en el balance.
        #
        # Cuadra al peso contra la deuda total (verificado en Arauco y Aguas Andinas), que
        # es la prueba de que sólo se están sumando los tramos hoja y no los agregados.
        "vencimientos": costo.vencimientos,
        # El detalle, ordenado de mayor a menor: es lo que se muestra en la hoja de deuda,
        # y lo primero que un analista quiere ver es dónde está el grueso del pasivo.
        "creditos": [
            asdict(c) for c in sorted(
                creditos, key=lambda c: c.monto_contable or 0, reverse=True
            )
        ],
    }

    destino = out_dir / "deuda.json"
    destino.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")

    if enable_log:
        print(f"[deuda] {company_dir.name}: Kd={costo.kd:.2%} sobre "
              f"{costo.n_creditos} crédito(s), monedas {sorted(costo.por_moneda)}")

    return datos


def leer_deuda(company_dir: Path) -> dict | None:
    """Lo que dejó `extraer_deuda`, o None si esta empresa no declara tasas."""
    for out in sorted(company_dir.glob("out_consolidated_*")):
        f = out / "deuda.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                return None
    return None
