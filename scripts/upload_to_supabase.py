#!/usr/bin/env python3
"""Upload de datos financieros consolidados a Supabase/Postgres (CLI).

Wrapper delgado sobre el motor reutilizable
``src/gui/pipeline/supabase_uploader.py`` (misma lógica que usa el orquestador
del pipeline en su etapa UPLOAD). Aquí solo vive la orquestación de la
línea de comandos: correr la pipeline CMF (fases 1-4), regenerar CSVs, iterar
las empresas y refrescar ratios/DCF.

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
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CMF_EXTRACT = PROJECT_ROOT / "cmf_extract"

# Permitir importar el motor reutilizable (src/gui/pipeline/supabase_uploader.py)
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.gui.pipeline.supabase_uploader import (  # noqa: E402
    Database,
    UploadStats,
    load_env_file,
    log,
    log_section,
    list_companies,
    resolve_pg_conn,
    run_dcf_for_company,
    run_ratios_for_company,
    upload_company,
)

# Defaults razonables; sobrescribibles por CLI
DEFAULT_INPUT_DIR = CMF_EXTRACT / "Product_v1" / "Total"
DEFAULT_TO_SQL_DIR = DEFAULT_INPUT_DIR / "TO_SQL"
DEFAULT_STRUCTURE_JSON = CMF_EXTRACT / "new_eeff_estructura.json"
DEFAULT_ENV_FILE = Path.home() / "Proyectos" / "FinDataChile" / ".env"
DEFAULT_FINDATACHILE = Path.home() / "Proyectos" / "FinDataChile"


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
    quarantined = [r for r in results if getattr(r, "quarantined", False)]
    skipped = [r for r in results if r.skipped and not getattr(r, "quarantined", False)]
    log(f"OK: {len(ok)}   Errores: {len(errs)}   "
        f"Cuarentena: {len(quarantined)}   Omitidas: {len(skipped)}   "
        f"Tiempo: {elapsed:.1f}s")
    if errs:
        log("\nErrores:")
        for r in errs:
            log(f"  - {r.company}: {r.error}")
    if quarantined:
        log("\nEn cuarentena (NO subidas a produccion):")
        for r in quarantined:
            log(f"  - {r.company}: {r.quality_summary}")
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
