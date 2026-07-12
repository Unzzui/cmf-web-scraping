#!/usr/bin/env python3
"""Subida de datos financieros consolidados a Supabase/Postgres.

Este módulo es el **motor reutilizable** de ingesta de tablas financieras.
Contiene toda la lógica de:
  - lectura de credenciales (``.env`` con vars ``PG*``),
  - parseo de los CSV de ``Product_v1/Total/TO_SQL/``,
  - upsert transaccional por empresa a ``financial_line_items`` +
    ``financial_data`` (clase :class:`Database`, función :func:`upload_company`),
  - recálculo post-upload de ratios y DCF por subprocess al repo FinDataChile.

El CLI ``scripts/upload_to_supabase.py`` es un wrapper delgado sobre este
módulo, y el orquestador del pipeline (:mod:`src.gui.pipeline.orchestrator`)
usa la fachada :class:`SupabaseUploader` para subir **una empresa** dentro de
la etapa UPLOAD, de forma atómica junto con el leg de blob/catálogo.

Convenios:
  - ``period_quarter = 0`` significa período anual (Diciembre).
  - Upsert idempotente vía ``ON CONFLICT DO UPDATE`` (no destructivo por
    defecto). ``override=True`` hace DELETE+INSERT por empresa (resuelve el
    caso *label rename split* de la CMF).

NOTA de concurrencia: una conexión psycopg2 no es thread-safe. Una instancia
de :class:`SupabaseUploader` mantiene una sola conexión; el llamador
(orquestador) debe serializar las llamadas o usar una instancia por worker.
"""

from __future__ import annotations

import csv
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

# Defaults independientes del repo (para la fachada)
DEFAULT_ENV_FILE = Path.home() / "Proyectos" / "FinDataChile" / ".env"
DEFAULT_FINDATACHILE = Path.home() / "Proyectos" / "FinDataChile"


# ---------------------------------------------------------------------------
# Log sink configurable (permite al orquestador capturar la salida)
# ---------------------------------------------------------------------------

_LOG_SINK: Callable[[str], None] = lambda msg: print(msg, flush=True)


def set_log_sink(fn: Optional[Callable[[str], None]]) -> Callable[[str], None]:
    """Fija el destino de ``log()``; devuelve el sink anterior (para restaurar)."""
    global _LOG_SINK
    prev = _LOG_SINK
    _LOG_SINK = fn if fn is not None else (lambda msg: print(msg, flush=True))
    return prev


def log(msg: str) -> None:
    _LOG_SINK(msg)


def log_section(title: str) -> None:
    log("\n" + "=" * 70)
    log(title)
    log("=" * 70)


# ---------------------------------------------------------------------------
# .env loader (minimo, sin dependencia de python-dotenv)
# ---------------------------------------------------------------------------

def load_env_file(path: Path) -> dict[str, str]:
    """Lee un .env tipo ``KEY=VALUE`` y devuelve un dict.

    Soporta valores entre comillas y lineas en blanco / comentarios.
    No interpola variables.
    """
    if not path.is_file():
        return {}
    env: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            env[key] = value
    return env


def resolve_pg_conn(env: dict[str, str]) -> dict[str, str]:
    """Construye el dict de conexion usando las vars PG* del .env."""
    cfg = {
        "host": env.get("PGHOST") or os.environ.get("PGHOST", ""),
        "port": env.get("PGPORT") or os.environ.get("PGPORT", "5432"),
        "dbname": env.get("PGDATABASE") or os.environ.get("PGDATABASE", ""),
        "user": env.get("PGUSER") or os.environ.get("PGUSER", ""),
        "password": env.get("PGPASSWORD") or os.environ.get("PGPASSWORD", ""),
    }
    missing = [k for k, v in cfg.items() if not v and k != "port"]
    if missing:
        raise SystemExit(
            f"Faltan vars de conexion en .env: {', '.join(missing)}.\n"
            f"   Esperadas: PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD"
        )
    return cfg


# ---------------------------------------------------------------------------
# Parsers
# ---------------------------------------------------------------------------

RUT_FILENAME_RE = re.compile(r"(\d{7,8}-[\dKk])")
PERIOD_QUARTER_RE = re.compile(r"^(\d{4})Q([1-4])$")
PERIOD_YEAR_RE = re.compile(r"^(\d{4})$")


def extract_rut_from_filename(name: str) -> str | None:
    m = RUT_FILENAME_RE.search(name)
    return m.group(1).upper() if m else None


def parse_period(period_str: str) -> tuple[int, int] | None:
    """Devuelve (year, quarter) o None.

    quarter=0 indica anual (mismo convenio que el JS).
    """
    if not period_str or period_str in {"Label", "RoleCode"}:
        return None
    period_str = period_str.strip()
    m = PERIOD_QUARTER_RE.match(period_str)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = PERIOD_YEAR_RE.match(period_str)
    if m:
        return int(m.group(1)), 0
    return None


def category_from_role(role_code: str, label: str = "") -> str:
    """Misma logica que la funcion JS ``getCategoryFromRoleCode``."""
    if not role_code:
        return "unknown"
    code = str(role_code).strip()
    if code == "000000":
        return "miscellaneous"
    if code.startswith(("21", "22")):
        return "balance_sheet"
    if code.startswith(("31", "32")):
        return "income_statement"
    if code.startswith("51"):
        return "cash_flow"
    # Filas de RATIOS & KPIs traen codigos custom (p. ej. 'RATIO_LIQ_CORR').
    # No matchean ninguno de los prefijos numericos -> 'other'. Si el label
    # sugiere indicador, lo marcamos como tal para que la BD lo identifique.
    if code.startswith(("RATIO_", "KPI_")):
        return "ratios_kpis"
    return "other"


def parse_value(raw: str) -> float | None:
    """Convierte un string del CSV a float; devuelve None si no es numerico."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = s.replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Estructuras de trabajo
# ---------------------------------------------------------------------------

@dataclass
class CompanyCSV:
    rut: str
    filename: str
    path: Path
    rows: list[dict[str, str]] = field(default_factory=list)
    periods: list[tuple[int, int]] = field(default_factory=list)


def read_company_csv(csv_path: Path) -> CompanyCSV | None:
    rut = extract_rut_from_filename(csv_path.name)
    if not rut:
        log(f"[warn] No se pudo extraer RUT de {csv_path.name}; se omite")
        return None
    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        rows = [r for r in reader]
        if not rows:
            log(f"[warn] CSV vacio: {csv_path.name}")
            return CompanyCSV(rut=rut, filename=csv_path.name, path=csv_path,
                              rows=[], periods=[])
        headers = list(rows[0].keys())
    periods: list[tuple[int, int]] = []
    for h in headers:
        p = parse_period(h)
        if p is not None:
            periods.append(p)
    return CompanyCSV(rut=rut, filename=csv_path.name, path=csv_path,
                      rows=rows, periods=periods)


def list_companies(to_sql_dir: Path) -> list[CompanyCSV]:
    if not to_sql_dir.is_dir():
        return []
    items: list[CompanyCSV] = []
    for f in sorted(to_sql_dir.glob("*.csv")):
        c = read_company_csv(f)
        if c is not None:
            items.append(c)
    return items


def _rut_numeric(rut: str) -> str:
    """Parte numérica del RUT (antes del DV): '90222000-3' / '90222000' -> '90222000'."""
    return (rut or "").upper().split("-", 1)[0]


def find_company_csv(to_sql_dir: Path, rut: str) -> CompanyCSV | None:
    """Localiza el CSV de un RUT en ``to_sql_dir``.

    Tolera que ``rut`` venga con o sin DV: los nombres de archivo traen el
    RUT-DV completo (p. ej. '..._90222000-3_...'), pero el llamador podría
    pasar solo la parte numérica. Se compara por la parte numérica.
    """
    if not to_sql_dir.is_dir():
        return None
    target = _rut_numeric(rut)
    for f in sorted(to_sql_dir.glob("*.csv")):
        r = extract_rut_from_filename(f.name)
        if r and _rut_numeric(r) == target:
            return read_company_csv(f)
    return None


# ---------------------------------------------------------------------------
# Capa BD
# ---------------------------------------------------------------------------

class Database:
    def __init__(self, conn_kwargs: dict[str, str]):
        import psycopg2  # type: ignore
        self.psycopg2 = psycopg2
        log(f"Conectando a {conn_kwargs['host']}:{conn_kwargs['port']}/"
            f"{conn_kwargs['dbname']} como {conn_kwargs['user']}...")
        self.conn = psycopg2.connect(**conn_kwargs)
        self.conn.autocommit = False
        with self.conn.cursor() as cur:
            cur.execute("SET search_path TO public")
        log("Conectado")

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    # -- Empresa --
    def find_company(self, rut: str) -> tuple[int, str] | None:
        # Match case-insensitive porque algunos RUTs en BD tienen el DV en
        # minuscula (ej. '77465741-k' vs el archivo que viene como
        # '77465741-K'). Hay 3 filas asi en la BD; este normaliza ambos lados.
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT id, razon_social FROM companies "
                "WHERE UPPER(rut) = UPPER(%s)",
                (rut,),
            )
            row = cur.fetchone()
        return (row[0], row[1]) if row else None

    # -- Periodo existente --
    def existing_periods(self, company_id: int) -> list[tuple[int, int, int]]:
        """Devuelve [(year, quarter, n_records), ...] ordenado desc."""
        with self.conn.cursor() as cur:
            cur.execute(
                """
                SELECT fd.period_year, fd.period_quarter, COUNT(*)
                FROM financial_data fd
                JOIN financial_line_items fli ON fd.line_item_id = fli.id
                WHERE fli.company_id = %s
                GROUP BY fd.period_year, fd.period_quarter
                ORDER BY fd.period_year DESC, fd.period_quarter DESC
                """,
                (company_id,),
            )
            return [(int(r[0]), int(r[1]), int(r[2])) for r in cur.fetchall()]

    # -- Override (delete + insert) --
    def delete_company_data(self, company_id: int) -> tuple[int, int]:
        with self.conn.cursor() as cur:
            cur.execute("DELETE FROM financial_data WHERE company_id = %s",
                        (company_id,))
            n_data = cur.rowcount
            cur.execute("DELETE FROM financial_line_items WHERE company_id = %s",
                        (company_id,))
            n_items = cur.rowcount
        return n_data, n_items

    # -- Line items --
    def upsert_line_items(self, company_id: int,
                          items: list[tuple[str, str, str, int]]
                          ) -> dict[int, int]:
        """Inserta/actualiza line_items; devuelve {display_order: line_item_id}.

        ``items`` es lista de ``(label, role_code, category, display_order)``.
        """
        mapping: dict[int, int] = {}
        sql = (
            "INSERT INTO financial_line_items "
            "(company_id, label, role_code, category, display_order) "
            "VALUES (%s, %s, %s, %s, %s) "
            "ON CONFLICT (company_id, display_order) DO UPDATE SET "
            "  label = EXCLUDED.label, "
            "  role_code = EXCLUDED.role_code, "
            "  category = EXCLUDED.category "
            "RETURNING id, display_order"
        )
        # Hacemos uno por uno para preservar la respuesta RETURNING; el
        # volumen no justifica execute_values aqui (<= ~200 lineas/empresa).
        with self.conn.cursor() as cur:
            for label, role_code, category, display_order in items:
                cur.execute(sql, (company_id, label, role_code, category,
                                  display_order))
                row = cur.fetchone()
                mapping[int(row[1])] = int(row[0])
        return mapping

    # -- Financial data en lotes --
    def upsert_financial_data(self,
                              records: Iterable[tuple[int, int, int, int, float]],
                              batch_size: int = 1000) -> int:
        """Upsert masivo de (company_id, line_item_id, year, quarter, value)."""
        from psycopg2.extras import execute_values  # type: ignore
        batch: list[tuple[int, int, int, int, float]] = []
        total = 0
        sql = (
            "INSERT INTO financial_data "
            "(company_id, line_item_id, period_year, period_quarter, value) "
            "VALUES %s "
            "ON CONFLICT (company_id, line_item_id, period_year, period_quarter) "
            "DO UPDATE SET value = EXCLUDED.value"
        )
        with self.conn.cursor() as cur:
            for rec in records:
                batch.append(rec)
                if len(batch) >= batch_size:
                    execute_values(cur, sql, batch, page_size=batch_size)
                    total += len(batch)
                    batch.clear()
            if batch:
                execute_values(cur, sql, batch, page_size=batch_size)
                total += len(batch)
        return total

    # -- Import record --
    def start_import(self, company_id: int, filename: str) -> int | None:
        """Registra el inicio del import en ``financial_data_imports``.

        Es opcional: si la tabla no existe (esquema antiguo), devuelve None
        y seguimos. No queremos abortar el upload por esto.
        """
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO financial_data_imports
                        (company_id, file_name, import_status, imported_by)
                    VALUES (%s, %s, 'processing', 'python_uploader')
                    RETURNING id
                    """,
                    (company_id, filename),
                )
                return int(cur.fetchone()[0])
        except self.psycopg2.Error:
            self.conn.rollback()
            return None

    def finish_import(self, import_id: int | None, total: int, ok: int,
                      failed: int, status: str = "completed") -> None:
        if import_id is None:
            return
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE financial_data_imports
                    SET total_records = %s, successful_records = %s,
                        failed_records = %s, import_status = %s,
                        completed_at = NOW()
                    WHERE id = %s
                    """,
                    (total, ok, failed, status, import_id),
                )
        except self.psycopg2.Error:
            self.conn.rollback()


# ---------------------------------------------------------------------------
# Logica de upload por empresa
# ---------------------------------------------------------------------------

@dataclass
class UploadStats:
    company: str = ""
    company_id: int | None = None  # util para invocar el DCF post-upload
    company_name: str = ""
    rows_total: int = 0
    line_items: int = 0
    data_points: int = 0
    new_periods: list[str] = field(default_factory=list)
    existing_periods: list[str] = field(default_factory=list)
    deleted_data: int = 0
    deleted_items: int = 0
    skipped: bool = False
    error: str = ""
    dcf_ok: bool | None = None  # None=no se intento, True/False=resultado
    ratios_ok: bool | None = None  # idem para ratios financieros


def fmt_period(year: int, quarter: int) -> str:
    return str(year) if quarter == 0 else f"{year}Q{quarter}"


# ---------------------------------------------------------------------------
# DCF / ratios refresh (persistir derivados tras el upload, por subprocess)
# ---------------------------------------------------------------------------

def run_dcf_for_company(findatachile_repo: Path, python_bin: Path,
                        env: dict[str, str], company_id: int,
                        company_name: str) -> bool:
    """Invoca ``python -m dcf --save --company-id N --method excel-aligned``.

    Los conceptos del DCF (FCFF top-down) ya viven en
    ``FinDataChile/scripts/dcf/excel_aligned.py`` y reproducen 1:1 las
    formulas de la hoja DCF del Excel consolidado. Como openpyxl no
    evalua formulas, recalcular en Python con la misma logica es la unica
    via robusta de mantener la BD alineada con el Excel.
    """
    import subprocess

    scripts_dir = findatachile_repo / "scripts"
    if not (scripts_dir / "dcf" / "calculator.py").is_file():
        log(f"   [warn] No se encontro {scripts_dir/'dcf'/'calculator.py'}; "
            f"se omite recalculo DCF")
        return False

    cmd = [str(python_bin), "-m", "dcf",
           "--save",
           "--method", "excel-aligned",
           "--company-id", str(company_id)]
    # Las credenciales se pasan por env, no se imprimen
    sub_env = {**os.environ, **{k: v for k, v in env.items() if k.startswith("PG")}}
    log(f"   DCF: {company_name} (id={company_id})...")
    try:
        res = subprocess.run(cmd, cwd=str(scripts_dir), env=sub_env,
                             capture_output=True, text=True, timeout=180)
        if res.returncode != 0:
            tail = (res.stdout + "\n" + res.stderr).strip().splitlines()[-6:]
            log(f"      [error] DCF fallo (rc={res.returncode}):")
            for line in tail:
                log(f"         {line}")
            return False
        # Tomar las lineas mas informativas de la salida
        keep_keys = ("WACC", "Terminal", "FCF Final", "Free Cash Flow",
                     "Net Debt", "Enterprise V", "Equity V", "Precio",
                     "RECOMENDACION", "DCF calculado")
        for line in res.stdout.splitlines():
            if any(k in line for k in keep_keys):
                log(f"      {line.strip()}")
        log("      [ok] DCF guardado en dcf_analysis")
        return True
    except subprocess.TimeoutExpired:
        log("      [error] DCF timeout (>180s)")
        return False
    except Exception as exc:
        log(f"      [error] DCF error: {exc}")
        return False


def run_ratios_for_company(findatachile_repo: Path, python_bin: Path,
                           env: dict[str, str], company_id: int,
                           company_name: str, annual_only: bool) -> bool:
    """Invoca ``ratio_calculator_postgresql.py --company-id N --save``.

    Calcula y persiste 30+ ratios (Liquidez, Solvencia, Rentabilidad,
    Eficiencia, Calidad de utilidades) sobre la data ya subida. Cubre los
    mismos KPIs que la hoja "RATIOS & KPIs" del Excel.
    """
    import subprocess

    scripts_dir = findatachile_repo / "scripts"
    calc = scripts_dir / "ratio_calculator_postgresql.py"
    if not calc.is_file():
        log(f"   [warn] No se encontro {calc}; se omite calculo de ratios")
        return False

    cmd = [str(python_bin), str(calc),
           "--save", "--company-id", str(company_id)]
    if annual_only:
        cmd.append("--annual-only")
    sub_env = {**os.environ, **{k: v for k, v in env.items() if k.startswith("PG")}}
    log(f"   Ratios: {company_name} (id={company_id})...")
    try:
        # 900s: una empresa con ~49 períodos (trimestral) tarda ~5 min. Para el
        # masivo conviene --ratios-annual-only (mucho más rápido).
        res = subprocess.run(cmd, cwd=str(scripts_dir), env=sub_env,
                             capture_output=True, text=True, timeout=900)
        if res.returncode != 0:
            tail = (res.stdout + "\n" + res.stderr).strip().splitlines()[-6:]
            log(f"      [error] Ratios fallo (rc={res.returncode}):")
            for line in tail:
                log(f"         {line}")
            return False
        # Resumir totales si los reporta
        ok_lines = [ln.strip() for ln in res.stdout.splitlines()
                    if "guardados" in ln or "Total" in ln]
        for ln in ok_lines[-5:]:
            log(f"      {ln}")
        log("      [ok] Ratios guardados en financial_ratios")
        return True
    except subprocess.TimeoutExpired:
        log("      [error] Ratios timeout (>300s)")
        return False
    except Exception as exc:
        log(f"      [error] Ratios error: {exc}")
        return False


def upload_company(db: Database, csv_data: CompanyCSV, override: bool,
                   dry_run: bool) -> UploadStats:
    stats = UploadStats(company=csv_data.rut)
    company = db.find_company(csv_data.rut)
    if company is None:
        stats.error = f"Empresa no encontrada (RUT={csv_data.rut})"
        log(f"[error] {stats.error}")
        return stats
    company_id, company_name = company
    stats.company = f"{company_name} ({csv_data.rut})"
    stats.company_id = company_id
    stats.company_name = company_name

    # Diff con BD
    db_periods = db.existing_periods(company_id)
    db_periods_set = {(y, q) for y, q, _ in db_periods}
    csv_periods_set = set(csv_data.periods)
    new_periods = sorted(csv_periods_set - db_periods_set)
    common_periods = sorted(csv_periods_set & db_periods_set)
    stats.new_periods = [fmt_period(y, q) for y, q in new_periods]
    stats.existing_periods = [fmt_period(y, q) for y, q in common_periods]
    stats.rows_total = len(csv_data.rows)

    log(f"\n{company_name} (RUT {csv_data.rut}, id={company_id})")
    log(f"   CSV: {csv_data.filename}")
    log(f"   Filas en CSV: {stats.rows_total}  -  Periodos CSV: "
        f"{len(csv_data.periods)}")
    if db_periods:
        total_db_records = sum(n for _, _, n in db_periods)
        log(f"   En BD: {len(db_periods)} periodos, {total_db_records} registros")
        recent = ", ".join(fmt_period(y, q) for y, q, _ in db_periods[:5])
        log(f"      ultimos: {recent}{'...' if len(db_periods) > 5 else ''}")
    else:
        log("   En BD: (sin datos previos)")
    log(f"   Periodos nuevos: {len(new_periods)}  a actualizar: "
        f"{len(common_periods)}")

    if dry_run:
        log("   dry-run -> no se modifica nada")
        return stats

    if not csv_data.rows or not csv_data.periods:
        log("   [warn] CSV vacio o sin periodos validos; se omite")
        stats.skipped = True
        return stats

    import_id = db.start_import(company_id, csv_data.filename)
    try:
        if override:
            n_data, n_items = db.delete_company_data(company_id)
            stats.deleted_data = n_data
            stats.deleted_items = n_items
            log(f"   Override: borrados {n_data} data + {n_items} line_items")

        # Construir line_items en orden CSV (display_order = indice+1)
        items: list[tuple[str, str, str, int]] = []
        skipped_rows: list[int] = []
        for idx, row in enumerate(csv_data.rows, start=1):
            label = (row.get("Label") or "").strip()
            role = (row.get("RoleCode") or "").strip()
            if not label or not role:
                skipped_rows.append(idx)
                continue
            category = category_from_role(role, label)
            items.append((label, role, category, idx))
        if skipped_rows:
            log(f"   [warn] {len(skipped_rows)} filas sin Label/RoleCode "
                f"(se ignoran)")
        line_item_ids = db.upsert_line_items(company_id, items)
        stats.line_items = len(line_item_ids)
        log(f"   line_items procesados: {stats.line_items}")

        # Construir financial_data, deduplicando dentro del batch
        seen: set[tuple[int, int, int]] = set()
        records: list[tuple[int, int, int, int, float]] = []
        for idx, row in enumerate(csv_data.rows, start=1):
            lid = line_item_ids.get(idx)
            if lid is None:
                continue
            for year, quarter in csv_data.periods:
                key = fmt_period(year, quarter)
                raw = row.get(key)
                value = parse_value(raw)
                if value is None:
                    continue
                dedup = (lid, year, quarter)
                if dedup in seen:
                    continue
                seen.add(dedup)
                records.append((company_id, lid, year, quarter, value))
        n = db.upsert_financial_data(records)
        stats.data_points = n
        log(f"   financial_data upserts: {n}")

        db.conn.commit()
        db.finish_import(import_id, stats.rows_total, stats.rows_total, 0,
                         "completed")
        log("   commit ok")
    except Exception as exc:
        db.conn.rollback()
        db.finish_import(import_id, stats.rows_total, 0, stats.rows_total,
                         "failed")
        stats.error = str(exc)
        log(f"   [error] rollback: {exc}")
    return stats


# ---------------------------------------------------------------------------
# Fachada por empresa para el orquestador
# ---------------------------------------------------------------------------

@dataclass
class SupabaseUploadResult:
    rut: str
    company_id: int | None = None
    company_name: str = ""
    data_points: int = 0
    line_items: int = 0
    new_periods: list[str] = field(default_factory=list)
    updated_periods: list[str] = field(default_factory=list)
    override: bool = False
    ratios_ok: bool | None = None
    dcf_ok: bool | None = None
    skipped: bool = False
    dry_run: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


class SupabaseUploader:
    """Sube las tablas financieras de UNA empresa (para la etapa UPLOAD).

    Mantiene una única conexión psycopg2 reutilizable entre empresas dentro de
    un mismo worker. NO es thread-safe: el orquestador debe serializar las
    llamadas (o crear una instancia por worker).
    """

    def __init__(self, *, env_file: Optional[Path] = None,
                 findatachile_repo: Optional[Path] = None,
                 dcf_python: Optional[Path] = None) -> None:
        self.env_file = Path(env_file) if env_file else DEFAULT_ENV_FILE
        self.findatachile_repo = (Path(findatachile_repo) if findatachile_repo
                                  else DEFAULT_FINDATACHILE)
        self.dcf_python = Path(dcf_python) if dcf_python else Path(sys.executable)
        self.env: dict[str, str] = load_env_file(self.env_file)
        self._db: Optional[Database] = None

    # -- disponibilidad --
    @property
    def available(self) -> bool:
        """True si psycopg2 está instalado y hay credenciales PG* resolubles."""
        try:
            import psycopg2  # noqa: F401  # type: ignore
        except Exception:
            return False
        try:
            resolve_pg_conn(self.env)
        except SystemExit:
            return False
        return True

    def connect(self) -> None:
        if self._db is None:
            self._db = Database(resolve_pg_conn(self.env))

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None

    # -- subida por empresa --
    def upload_company_tables(
        self,
        rut: str,
        *,
        to_sql_dir: Path,
        override: Optional[bool] = None,
        dry_run: bool = False,
        with_ratios: bool = True,
        with_dcf: bool = True,
        annual_only: bool = False,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> SupabaseUploadResult:
        """Sube ``financial_data``/``financial_line_items`` de una empresa y
        (opcional) recalcula ratios/DCF.

        ``override``: None => auto (override si el CSV es superconjunto de los
        períodos ya en BD; si la BD tiene períodos que el CSV no trae, se cae a
        upsert no destructivo para no perder historia).
        """
        prev_sink = set_log_sink(on_log) if on_log is not None else None
        result = SupabaseUploadResult(rut=rut.upper(), dry_run=dry_run)
        try:
            to_sql_dir = Path(to_sql_dir)
            csv_data = find_company_csv(to_sql_dir, rut)
            if csv_data is None:
                result.error = f"No se encontró CSV para RUT {rut} en {to_sql_dir}"
                log(f"[error] {result.error}")
                return result

            try:
                self.connect()
            except Exception as exc:
                result.error = f"No se pudo conectar a la BD: {exc}"
                log(f"[error] {result.error}")
                return result
            assert self._db is not None

            company = self._db.find_company(rut)
            if company is None:
                result.error = (f"Empresa no encontrada en 'companies' "
                                f"(RUT={rut}). El leg blob/catálogo debe crearla "
                                f"antes (etapa 3A).")
                log(f"[error] {result.error}")
                return result
            company_id, company_name = company
            result.company_id = company_id
            result.company_name = company_name

            # Decisión de override (auto por defecto)
            eff_override = override
            if eff_override is None:
                db_set = {(y, q) for y, q, _ in self._db.existing_periods(company_id)}
                csv_set = set(csv_data.periods)
                if db_set <= csv_set:
                    eff_override = True  # CSV ⊇ BD: override limpio (resuelve label-rename-split)
                else:
                    eff_override = False
                    missing = sorted(db_set - csv_set)
                    log(f"   [warn] La BD tiene {len(missing)} período(s) que el "
                        f"CSV no trae ({', '.join(fmt_period(y, q) for y, q in missing[:6])}"
                        f"{'...' if len(missing) > 6 else ''}); se usa upsert no "
                        f"destructivo para no perder historia.")
            result.override = eff_override

            stats = upload_company(self._db, csv_data, override=eff_override,
                                   dry_run=dry_run)
            result.data_points = stats.data_points
            result.line_items = stats.line_items
            result.new_periods = stats.new_periods
            result.updated_periods = stats.existing_periods
            result.skipped = stats.skipped
            if stats.error:
                result.error = stats.error
                return result

            # Derivados post-commit (solo si escribimos y hubo empresa válida)
            if not dry_run and not stats.skipped and stats.company_id is not None:
                if with_ratios:
                    result.ratios_ok = run_ratios_for_company(
                        self.findatachile_repo, self.dcf_python, self.env,
                        company_id, company_name, annual_only)
                if with_dcf:
                    result.dcf_ok = run_dcf_for_company(
                        self.findatachile_repo, self.dcf_python, self.env,
                        company_id, company_name)
            return result
        finally:
            if prev_sink is not None:
                set_log_sink(prev_sink)
