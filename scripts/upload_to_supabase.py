#!/usr/bin/env python3
"""Upload de datos financieros consolidados a Supabase/Postgres.

Equivalente en Python de
``FinDataChile/scripts/import-financial-data-fast.js`` pensado para correr
sobre los Excels que produce este repo en
``cmf_extract/Product_v1/Total/*.xlsx``.

Flujo:
  1. (opcional) Correr la pipeline completa CMF (fases 1-4) que produce
     desde XBRL -> Excels consolidados -> CSVs en ``TO_SQL/``.
        Fase 1: Consolidacion XBRL  (Arelle facts -> CSV consolidado)
        Fase 2: Generacion Excel    (CSV -> Excel primario)
        Fase 3: Analisis financiero (Excel primario -> Excel analisis)
        Fase 4: Export a CSV        (Excel analisis -> CSV TO_SQL)
  2. (opcional) Solo regenerar CSVs en ``Product_v1/Total/TO_SQL/`` desde los
     Excels consolidados ya existentes, via
     ``excel_to_csv_mapping.process_excel_files``.
  3. Para cada CSV:
        - extraer RUT del nombre del archivo
        - buscar la empresa en ``companies`` por RUT
        - mostrar diff con lo ya cargado en BD (periodos, conteos)
        - hacer UPSERT (line_items + financial_data) en transaccion
  4. (opcional) Recalcular ratios financieros y DCF post-upload.

Diseno "inteligente" (sin asumir nada destructivo por defecto):
  - Por defecto NO borra los datos existentes: hace upsert con
    ``ON CONFLICT DO UPDATE``.
  - ``--override`` replica la semantica del JS (DELETE + INSERT por empresa).
  - ``--dry-run`` muestra el diff sin tocar la BD.
  - ``--only RUT1,RUT2`` filtra empresas (tambien en pipeline cuando aplica).
  - ``--full-pipeline`` corre las 4 fases CMF antes de subir.
  - ``--regenerate-csv`` solo corre el mapper (fase 4) antes del upload.
  - ``--full`` = ``--full-pipeline --with-all``: pipeline completa + upload +
    ratios + DCF en un solo comando.
  - ``--env-file <path>`` permite apuntar a otro ``.env`` (default: el de
    ``FinDataChile`` que ya tiene las credenciales).

Uso tipico:
    python scripts/upload_to_supabase.py --dry-run
    python scripts/upload_to_supabase.py --only 61808000-5
    python scripts/upload_to_supabase.py --regenerate-csv --only all
    python scripts/upload_to_supabase.py --full-pipeline
    python scripts/upload_to_supabase.py --full
    python scripts/upload_to_supabase.py --full --only 61808000-5
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CMF_EXTRACT = PROJECT_ROOT / "cmf_extract"

# Defaults razonables; sobrescribibles por CLI
DEFAULT_INPUT_DIR = CMF_EXTRACT / "Product_v1" / "Total"
DEFAULT_TO_SQL_DIR = DEFAULT_INPUT_DIR / "TO_SQL"
DEFAULT_STRUCTURE_JSON = CMF_EXTRACT / "new_eeff_estructura.json"
DEFAULT_ENV_FILE = Path.home() / "Proyectos" / "FinDataChile" / ".env"
DEFAULT_FINDATACHILE = Path.home() / "Proyectos" / "FinDataChile"


# ---------------------------------------------------------------------------
# Helpers de presentacion
# ---------------------------------------------------------------------------

def log(msg: str) -> None:
    print(msg, flush=True)


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


# ---------------------------------------------------------------------------
# Pipeline completo CMF (fases 1-4): XBRL -> Excels -> CSVs (opcional)
# ---------------------------------------------------------------------------

def run_full_pipeline(filter_ruts: set[str] | None,
                      phases: list[int] | None = None) -> bool:
    """Corre las fases 1-4 del pipeline CMF en proceso.

    Importa los runners de ``cmf.pipeline`` y los ejecuta secuencialmente:
        Fase 1: consolidacion XBRL    (Arelle facts -> CSV consolidado)
        Fase 2: generacion Excel      (CSV consolidado -> Excel primario)
        Fase 3: analisis financiero   (Excel primario -> Excel analisis)
        Fase 4: export a CSV          (Excel analisis -> CSV TO_SQL)

    ``filter_ruts`` permite restringir el set de empresas a procesar (se
    matchean por rut completo o por rut number). Si es ``None`` se procesan
    todas las empresas con datos XBRL en disco. Devuelve ``True`` si todas
    las fases terminaron sin errores fatales.
    """
    sys.path.insert(0, str(CMF_EXTRACT))
    try:
        from cmf.config import CMFConfig  # type: ignore
        from cmf.companies import CompanyRegistry  # type: ignore
        from cmf.pipeline import consolidation as p_consolidation  # type: ignore
        from cmf.pipeline import excel_gen as p_excel_gen  # type: ignore
        from cmf.pipeline import analysis as p_analysis  # type: ignore
        from cmf.pipeline import to_sql as p_to_sql  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            f"No se pudo importar el pipeline CMF desde {CMF_EXTRACT}: {exc}"
        )

    runners = {
        1: ("Fase 1 - Consolidacion XBRL", p_consolidation),
        2: ("Fase 2 - Generacion Excel", p_excel_gen),
        3: ("Fase 3 - Analisis Financiero", p_analysis),
        4: ("Fase 4 - Export a CSV (TO_SQL)", p_to_sql),
    }
    selected = sorted(phases or [1, 2, 3, 4])

    config = CMFConfig()
    config.apply_env()
    config.ensure_dirs()

    registry = CompanyRegistry(config)
    companies = registry.companies_with_xbrl
    if filter_ruts:
        wanted = {r.upper() for r in filter_ruts}
        companies = [
            c for c in companies
            if c.rut.upper() in wanted
            or (c.rut_number and c.rut_number.upper() in wanted)
        ]
    if not companies:
        log("[warn] Pipeline: no hay empresas con XBRL en disco que coincidan; "
            "se omite la pipeline")
        return True

    company_dirs = [c.xbrl_dir for c in companies if c.xbrl_dir]
    log_section(f"Pipeline CMF: {len(company_dirs)} empresa(s), "
                f"fases {selected}")

    def _cb(message: str, current: int = 0, total: int = 0) -> None:
        if total:
            log(f"     [{current}/{total}] {message}")
        elif message:
            log(f"     {message}")

    all_ok = True
    for phase_num in selected:
        title, runner = runners[phase_num]
        log_section(title)
        try:
            result = runner.run(config, company_dirs, progress_callback=_cb)
        except Exception as exc:
            log(f"[error] {title} fallo: {exc}")
            all_ok = False
            break
        n_ok = len(result.success)
        n_err = len(result.errors)
        log(f"   [ok] {title}: {n_ok} ok, {n_err} errores, "
            f"{result.elapsed:.1f}s")
        if n_err:
            all_ok = False
            for name, err in list(result.errors.items())[:10]:
                log(f"      - {name}: {err}")
            if len(result.errors) > 10:
                log(f"      ... {len(result.errors) - 10} mas")
    if all_ok:
        log("[ok] Pipeline CMF completa sin errores")
    else:
        log("[warn] Pipeline CMF termino con errores (revisa el log)")
    return all_ok


# ---------------------------------------------------------------------------
# Generacion de CSVs desde Excels (opcional)
# ---------------------------------------------------------------------------

def regenerate_csvs(input_dir: Path, json_path: Path, output_dir: Path,
                   filter_ruts: set[str] | None) -> None:
    sys.path.insert(0, str(CMF_EXTRACT))
    try:
        from excel_to_csv_mapping import process_excel_files  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            f"No se pudo importar excel_to_csv_mapping desde {CMF_EXTRACT}: {exc}"
        )
    log(f"Regenerando CSVs en {output_dir} desde {input_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    def _cb(message: str, current: int = 0, total: int = 0) -> None:
        if total:
            log(f"  [{current}/{total}] {message}")
        else:
            log(f"  {message}")

    process_excel_files(
        input_dir=str(input_dir),
        json_path=str(json_path),
        output_dir=str(output_dir),
        progress_callback=_cb,
        filter_ruts=filter_ruts,
    )
    log("Regeneracion de CSVs finalizada")


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
# DCF refresh (Fase 2: persistir DCF Excel-aligned tras el upload)
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
        res = subprocess.run(cmd, cwd=str(scripts_dir), env=sub_env,
                             capture_output=True, text=True, timeout=300)
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
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Sube datos financieros consolidados a Supabase/Postgres. "
            "Hace upsert inteligente por defecto (no destructivo)."
        )
    )
    p.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE,
                   help=f"Ruta al .env (default: {DEFAULT_ENV_FILE})")
    p.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR,
                   help="Carpeta de Excels finales (Product_v1/Total)")
    p.add_argument("--to-sql-dir", type=Path, default=DEFAULT_TO_SQL_DIR,
                   help="Carpeta donde estan / se generan los CSV (TO_SQL)")
    p.add_argument("--structure-json", type=Path, default=DEFAULT_STRUCTURE_JSON,
                   help="JSON de estructura de roles (new_eeff_estructura.json)")
    p.add_argument("--regenerate-csv", action="store_true",
                   help="Regenerar los CSVs en TO_SQL antes de subir "
                        "(solo fase 4 del pipeline). Util si los Excels "
                        "consolidados ya existen y solo necesitas refrescar "
                        "los CSV.")
    p.add_argument("--full-pipeline", action="store_true",
                   help="Correr las fases 1-4 del pipeline CMF antes de "
                        "subir: XBRL -> Excels -> CSVs. Si se pasa, ignora "
                        "--regenerate-csv (la fase 4 ya hace eso).")
    p.add_argument("--pipeline-phases", default="1-4",
                   help="Fases a correr cuando --full-pipeline esta activo "
                        "(ej: '1-4', '2,3', '4'). Default: 1-4.")
    p.add_argument("--full", action="store_true",
                   help="Atajo: equivalente a --full-pipeline --with-all. "
                        "Hace TODO de una: pipeline completa + upload + "
                        "ratios + DCF.")
    p.add_argument("--only", default="",
                   help="Lista CSV de RUTs a procesar (ej: 61808000-5,76129263-3)")
    p.add_argument("--dry-run", action="store_true",
                   help="Mostrar diff sin tocar la BD")
    p.add_argument("--override", action="store_true",
                   help="DELETE de datos previos por empresa antes de insertar "
                        "(replica el comportamiento del JS).")
    p.add_argument("--list", action="store_true",
                   help="Solo listar empresas/CSVs disponibles y salir")
    p.add_argument("--with-dcf", action="store_true",
                   help="Tras subir los datos, recalcular DCF (metodo "
                        "excel-aligned) y persistir en dcf_analysis para cada "
                        "empresa procesada con exito.")
    p.add_argument("--with-ratios", action="store_true",
                   help="Tras subir los datos, recalcular ratios financieros "
                        "(Liquidez, Solvencia, Rentabilidad, Eficiencia, etc.) "
                        "y persistir en financial_ratios. La hoja RATIOS & KPIs "
                        "del Excel usa formulas que openpyxl no evalua, asi "
                        "que la unica via solida es recalcular sobre los datos "
                        "base ya subidos.")
    p.add_argument("--with-all", action="store_true",
                   help="Atajo: equivalente a --with-dcf --with-ratios.")
    p.add_argument("--ratios-annual-only", action="store_true",
                   help="Si --with-ratios esta activo, procesar solo periodos "
                        "anuales (Q4) + ano corriente (mas rapido).")
    p.add_argument("--findatachile-repo", type=Path, default=DEFAULT_FINDATACHILE,
                   help=f"Ruta al repo FinDataChile que contiene scripts/dcf/ "
                        f"y scripts/ratio_calculator_postgresql.py "
                        f"(default: {DEFAULT_FINDATACHILE}).")
    p.add_argument("--dcf-python", type=Path, default=None,
                   help="Python con psycopg2 para correr DCF/ratios (default: "
                        "el mismo interprete que ejecuta este script).")
    return p.parse_args()


def parse_only(only: str) -> set[str] | None:
    if not only:
        return None
    parts = [p.strip().upper() for p in only.split(",") if p.strip()]
    return set(parts) or None


def parse_pipeline_phases(phases_str: str) -> list[int]:
    """Convierte '1-4' o '2,3' en una lista de ints en [1,4]."""
    result: set[int] = set()
    for part in phases_str.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return sorted(n for n in result if 1 <= n <= 4)


def main() -> int:
    args = parse_args()

    # --full = atajo a "haz todo de una"
    if args.full:
        args.full_pipeline = True
        args.with_all = True

    log_section("CMF -> Supabase upload")
    log(f"Working dir: {PROJECT_ROOT}")
    log(f"Env file:    {args.env_file}")
    log(f"Input dir:   {args.input_dir}")
    log(f"TO_SQL dir:  {args.to_sql_dir}")
    if args.dry_run:
        log("Mode:        DRY-RUN (no modifica la BD)")
    if args.override:
        log("Mode:        OVERRIDE (delete previo por empresa)")
    if args.full_pipeline:
        log(f"Pipeline:    FULL (fases {args.pipeline_phases})")
    elif args.regenerate_csv:
        log("Pipeline:    Solo fase 4 (regenerar CSVs)")

    only_ruts = parse_only(args.only)
    if only_ruts:
        log(f"Filtro RUT:  {sorted(only_ruts)}")

    env = load_env_file(args.env_file)
    if not env:
        log(f"[warn] No se pudo leer {args.env_file}; usando variables de "
            f"entorno del sistema")

    # 1. Pipeline completa (fases 1-4) o solo regeneracion de CSVs (fase 4).
    #    --full-pipeline tiene prioridad sobre --regenerate-csv porque la
    #    fase 4 ya genera los CSVs.
    if args.full_pipeline:
        phases = parse_pipeline_phases(args.pipeline_phases)
        if not phases:
            log(f"[error] --pipeline-phases invalido: {args.pipeline_phases!r}")
            return 2
        run_full_pipeline(only_ruts, phases=phases)
    elif args.regenerate_csv:
        if not args.input_dir.is_dir():
            log(f"[error] No existe input dir: {args.input_dir}")
            return 2
        if not args.structure_json.is_file():
            log(f"[error] No existe structure JSON: {args.structure_json}")
            return 2
        regenerate_csvs(args.input_dir, args.structure_json, args.to_sql_dir,
                        only_ruts)

    # 2. Listar CSVs
    if not args.to_sql_dir.is_dir():
        log(f"[error] No hay carpeta de CSVs en {args.to_sql_dir}. "
            f"Corre con --regenerate-csv o --full-pipeline para crearlos.")
        return 2

    companies = list_companies(args.to_sql_dir)
    if only_ruts:
        companies = [c for c in companies if c.rut.upper() in only_ruts]
    if not companies:
        log("[error] Sin CSVs que procesar")
        return 2

    log_section(f"Empresas a procesar: {len(companies)}")
    for c in companies:
        log(f"  - {c.rut}  <-  {c.filename}  ({len(c.rows)} filas, "
            f"{len(c.periods)} periodos)")

    if args.list:
        return 0

    # 3. Conectar a BD y procesar
    conn_kwargs = resolve_pg_conn(env)
    db = Database(conn_kwargs)
    results: list[UploadStats] = []
    start = time.time()
    try:
        for c in companies:
            results.append(upload_company(db, c, override=args.override,
                                          dry_run=args.dry_run))
    finally:
        db.close()
    elapsed = time.time() - start

    # 3b. Refrescar derivados (ratios + DCF) sobre los datos ya subidos.
    #     Importante: ratios PRIMERO, DCF DESPUES - el DCF puede usar el
    #     mismo Python pero conceptualmente los ratios son base "instantanea"
    #     y el DCF es proyeccion futura.
    do_ratios = args.with_ratios or args.with_all
    do_dcf = args.with_dcf or args.with_all
    py_bin = args.dcf_python or Path(sys.executable)

    if do_ratios and not args.dry_run:
        log_section("Recalculando ratios financieros")
        for r in results:
            if r.error or r.skipped or r.company_id is None:
                continue
            r.ratios_ok = run_ratios_for_company(
                args.findatachile_repo, py_bin, env,
                r.company_id, r.company_name,
                annual_only=args.ratios_annual_only)

    if do_dcf and not args.dry_run:
        log_section("Recalculando DCF (Excel-aligned)")
        for r in results:
            if r.error or r.skipped or r.company_id is None:
                continue
            r.dcf_ok = run_dcf_for_company(
                args.findatachile_repo, py_bin, env,
                r.company_id, r.company_name)

    # 4. Resumen
    log_section("Resumen")
    ok = [r for r in results if not r.error and not r.skipped]
    errs = [r for r in results if r.error]
    skipped = [r for r in results if r.skipped]
    log(f"OK: {len(ok)}   Errores: {len(errs)}   Omitidas: {len(skipped)}   "
        f"Tiempo: {elapsed:.1f}s")
    if errs:
        log("\nErrores:")
        for r in errs:
            log(f"  - {r.company}: {r.error}")
    if not args.dry_run and ok:
        total_data = sum(r.data_points for r in ok)
        total_items = sum(r.line_items for r in ok)
        log(f"\nTotal upserts: {total_data} data, {total_items} line_items")
    if do_ratios and not args.dry_run:
        r_ok = sum(1 for r in results if r.ratios_ok is True)
        r_fail = sum(1 for r in results if r.ratios_ok is False)
        log(f"Ratios refrescados: {r_ok} ok, {r_fail} fallidos")
    if do_dcf and not args.dry_run:
        dcf_ok = sum(1 for r in results if r.dcf_ok is True)
        dcf_fail = sum(1 for r in results if r.dcf_ok is False)
        log(f"DCF refrescados: {dcf_ok} ok, {dcf_fail} fallidos")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
