"""Dataclasses de las filas parseadas desde la API de bancos."""

from dataclasses import dataclass


@dataclass
class Institution:
    codigo_institucion: str
    nombre_institucion: str


@dataclass
class AccountRow:
    statement: str  # 'balance' | 'resultado'
    codigo_cuenta: str
    descripcion_cuenta: str
    moneda_no_reajustable: float | None
    moneda_reajustable_ipc: float | None
    moneda_reajustable_tc: float | None
    moneda_extranjera: float | None
    moneda_total: float | None


@dataclass
class CapitalAdequacy:
    activos_ponderados_riesgo: float | None
    activos_totales: float | None
    capital_basico: float | None
    patrimonio_efectivo: float | None
    provisiones_voluntarias: float | None
    bonos_subordinados: float | None
    interes_minoritario: float | None
    indice_irs: float | None
    indice_ire: float | None
    raw: dict


@dataclass
class Profile:
    codigo_swift: str | None
    rut: str | None
    direccion: str | None
    telefono: str | None
    sitio_web: str | None
    sucursales: int | None
    oficinas: int | None
    cajeros: int | None
    empleados: int | None
    emp_hombres_perm: int | None
    emp_mujeres_perm: int | None
    emp_hombres_ext: int | None
    emp_mujeres_ext: int | None
    fecha_publicacion: str | None
    raw: dict


@dataclass
class Shareholder:
    serie: str | None
    rut: str | None
    nombre: str | None
    participacion: float | None
    numero_acciones: float | None


@dataclass
class Executive:
    nombre: str
    cargo: str | None
    fecha_asuncion: str | None
    tipo: str | None
