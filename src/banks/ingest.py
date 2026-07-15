"""Parsers puros: JSON de la API de bancos -> modelos."""

from src.banks.models import (
    AccountRow,
    CapitalAdequacy,
    Executive,
    Institution,
    Profile,
    Shareholder,
)
from src.banks.numbers import parse_spanish_number


def _to_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_instituciones(payload: dict) -> list[Institution]:
    items = payload.get("DescripcionesCodigosDeInstituciones", []) or []
    return [
        Institution(
            codigo_institucion=str(it.get("CodigoInstitucion")),
            nombre_institucion=it.get("NombreInstitucion", ""),
        )
        for it in items
    ]


def parse_accounts(payload: dict, statement: str) -> list[AccountRow]:
    key = "CodigosBalances" if statement == "balance" else "CodigosEstadosDeResultado"
    items = payload.get(key, []) or []
    rows: list[AccountRow] = []
    for it in items:
        rows.append(
            AccountRow(
                statement=statement,
                codigo_cuenta=str(it.get("CodigoCuenta")),
                descripcion_cuenta=it.get("DescripcionCuenta", ""),
                moneda_no_reajustable=parse_spanish_number(it.get("MonedaChilenaNoReajustable")),
                moneda_reajustable_ipc=parse_spanish_number(it.get("MonedaReajustablePorIPC")),
                moneda_reajustable_tc=parse_spanish_number(
                    it.get("MonedaReajustablePorTipoDeCambio")
                ),
                moneda_extranjera=parse_spanish_number(it.get("MonedaExtranjera")),
                moneda_total=parse_spanish_number(it.get("MonedaTotal")),
            )
        )
    return rows


def parse_adecuacion_componentes(payload: dict) -> CapitalAdequacy:
    items = payload.get("AdecuacionDeCapital", []) or []
    comp = (items[0].get("Componentes", {}) if items else {}) or {}
    activos = comp.get("Activos", {}) or {}
    patrimonio = comp.get("PatrimonioEfectivo", {}) or {}
    return CapitalAdequacy(
        activos_ponderados_riesgo=parse_spanish_number(activos.get("PonderadosPorRiesgo")),
        activos_totales=parse_spanish_number(activos.get("Totales")),
        capital_basico=parse_spanish_number(patrimonio.get("CapitalBasico")),
        patrimonio_efectivo=parse_spanish_number(patrimonio.get("Total")),
        provisiones_voluntarias=parse_spanish_number(patrimonio.get("ProvisionesVoluntarias")),
        bonos_subordinados=parse_spanish_number(patrimonio.get("BonosSubordinados")),
        interes_minoritario=parse_spanish_number(patrimonio.get("InteresMinoritario")),
        indice_irs=None,
        indice_ire=None,
        raw=payload,
    )


def parse_adecuacion_indicador(payload: dict) -> float | None:
    """Best-effort: busca una clave 'Valor'/'valor' numerica en el payload."""
    def _search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() == "valor":
                    parsed = parse_spanish_number(v) if isinstance(v, str) else v
                    if isinstance(parsed, (int, float)):
                        return float(parsed)
                found = _search(v)
                if found is not None:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = _search(item)
                if found is not None:
                    return found
        return None

    return _search(payload)


def parse_perfil(payload: dict) -> Profile | None:
    items = payload.get("Perfiles", []) or []
    if not items:
        return None
    p = items[0].get("Perfil", {}) or {}
    return Profile(
        codigo_swift=(p.get("codigoSWIFT") or "").strip() or None,
        rut=(p.get("rut") or "").strip() or None,
        direccion=(p.get("direccionPrincipal") or "").strip() or None,
        telefono=(p.get("telefono") or "").strip() or None,
        sitio_web=(p.get("direccionWeb") or "").strip() or None,
        sucursales=_to_int(p.get("sucursales")),
        oficinas=_to_int(p.get("oficinas")),
        cajeros=_to_int(p.get("cajeros")),
        empleados=_to_int(p.get("empleados")),
        emp_hombres_perm=_to_int(p.get("emp_hombres_perm")),
        emp_mujeres_perm=_to_int(p.get("emp_mujareres_perm", p.get("emp_mujeres_perm"))),
        emp_hombres_ext=_to_int(p.get("emp_hombres_ext")),
        emp_mujeres_ext=_to_int(p.get("emp_mujeres_ext")),
        fecha_publicacion=(p.get("fechaPublicacion") or "").strip() or None,
        raw=p,
    )


def parse_accionistas(payload: dict) -> list[Shareholder]:
    items = payload.get("Accionistas", []) or []
    out: list[Shareholder] = []
    for it in items:
        d = it.get("DescripcionAccionista", {}) or {}
        out.append(
            Shareholder(
                serie=d.get("Serie"),
                rut=d.get("Rut"),
                nombre=d.get("Nombre"),
                participacion=d.get("Participacion")
                if isinstance(d.get("Participacion"), (int, float))
                else parse_spanish_number(d.get("Participacion")),
                numero_acciones=parse_spanish_number(str(d.get("NumeroAcciones")))
                if d.get("NumeroAcciones") is not None
                else None,
            )
        )
    return out


def parse_integrantes(payload: dict) -> list[Executive]:
    items = payload.get("Integrantes", []) or []
    out: list[Executive] = []
    for it in items:
        d = it.get("DescripcionIntegrante", {}) or {}
        out.append(
            Executive(
                nombre=d.get("Nombre", ""),
                cargo=d.get("Cargo"),
                fecha_asuncion=d.get("FechaAsuncion"),
                tipo=d.get("Tipo"),
            )
        )
    return out
