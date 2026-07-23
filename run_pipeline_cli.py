#!/usr/bin/env python3
"""Pipeline CMF headless: descarga XBRL, consolida (Arelle) y analiza, sin GUI.

Front-end de línea de comandos del mismo motor que usa la GUI
(``src/gui/pipeline/PipelineOrchestrator``): apto para systemd/cron.

Ejemplos::

    # Corrida completa (solo empresas IFRS; bancos/AFP/seguros se omiten)
    python run_pipeline_cli.py

    # Empresas puntuales, solo descarga, 2020 en adelante
    python run_pipeline_cli.py --companies 96874030,76675290 \
        --stages download --end-year 2020

    # Ver qué haría sin ejecutar
    python run_pipeline_cli.py --dry-run

    # Eventos JSONL (para journald / procesamiento posterior)
    python run_pipeline_cli.py --json

Códigos de salida: 0 ok, 1 hubo empresas con error, 2 preflight/config inválida.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import queue
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
# El downloader usa rutas relativas ./data/XBRL/ — mismo cwd que la GUI.
os.chdir(PROJECT_ROOT)

from src.gui.pipeline.models import Stage, StageStatus, PipelineEvent  # noqa: E402
from src.gui.pipeline.settings import PipelineSettings  # noqa: E402
from src.gui.pipeline.orchestrator import PipelineOrchestrator  # noqa: E402

DEFAULT_CSV = "data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"


# ---------------------------------------------------------------------------
# Empresas
# ---------------------------------------------------------------------------

def load_companies(csv_path: str, categorias: set[str], ruts: set[str] | None,
                   limit: int | None) -> tuple[list[dict], list[dict]]:
    """Lee el CSV y devuelve (empresas a procesar, omitidas con motivo)."""
    with open(csv_path, newline="", encoding="utf-8-sig") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        raise SystemExit(f"CSV vacío o ilegible: {csv_path}")

    has_categoria = "Categoria" in rows[0]
    selected: list[dict] = []
    skipped: list[dict] = []
    for row in rows:
        rut_sg = str(row.get("RUT_Sin_Guión", "")).strip()
        if not rut_sg.isdigit():
            continue
        company = {
            "razon_social": str(row.get("Razón Social", "")).strip(),
            "rut": str(row.get("RUT", "")).strip(),
            "rut_sin_guion": rut_sg,
            "categoria": (row.get("Categoria") or "ifrs").strip() or "ifrs",
        }
        if ruts is not None and rut_sg not in ruts:
            continue
        if has_categoria and "all" not in categorias \
                and company["categoria"] not in categorias:
            skipped.append({**company,
                            "reason": f"categoria={company['categoria']} (flujo no-XBRL)"})
            continue
        selected.append(company)

    if not has_categoria:
        print("ADVERTENCIA: el CSV no tiene columna 'Categoria'; no se filtran "
              "bancos/AFP/seguros. Corre scripts/classify_companies.py.",
              file=sys.stderr)
    if limit:
        selected = selected[:limit]
    return selected, skipped


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------

class Reporter:
    def __init__(self, as_json: bool, verbose: bool):
        self.as_json = as_json
        self.verbose = verbose

    def event(self, ev: PipelineEvent) -> None:
        if self.as_json:
            print(json.dumps({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "kind": ev.kind,
                "rut": ev.rut,
                "stage": ev.stage.value if ev.stage else None,
                "status": ev.status.value if ev.status else None,
                "level": ev.level,
                "message": ev.message,
                "current": ev.current, "total": ev.total,
                **({"payload": ev.payload} if ev.payload else {}),
            }, ensure_ascii=False), flush=True)
            return
        # Modo humano: el progreso fino solo con --verbose; DETAIL es ruido
        # crudo de Arelle.
        if ev.kind == "progress" and not self.verbose:
            return
        if ev.level == "DETAIL" and not self.verbose:
            return
        ts = datetime.now().strftime("%H:%M:%S")
        rut = f" [{ev.rut}]" if ev.rut else ""
        stage = f" {ev.stage.label}:" if ev.stage else ""
        status = f" {ev.status.badge}" if ev.status else ""
        msg = f" {ev.message}" if ev.message else ""
        print(f"{ts} {ev.level:7s}{rut}{stage}{status}{msg}", flush=True)

    def line(self, message: str, level: str = "INFO") -> None:
        self.event(PipelineEvent(kind="log", message=message, level=level))


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight(settings: PipelineSettings, stages: list[Stage]) -> list[str]:
    problems: list[str] = []
    try:
        checks = {c["name"]: c for c in settings.verify()}
    except Exception as exc:
        return [f"settings.verify() falló: {exc}"]
    if Stage.CONSOLIDATE in stages:
        for key in ("Repo CMF_EXTRACT", "Import cmf.pipeline", "Directorio Arelle",
                    "xlsxwriter disponible"):
            c = checks.get(key)
            if c and not c["ok"]:
                problems.append(f"{key}: {c['detail']}")
    if Stage.UPLOAD in stages:
        c = checks.get("Credenciales FinDataChile")
        if c and not c["ok"]:
            problems.append(f"FinDataChile: {c['detail']}")
        # Leg Supabase (solo aparecen en verify() si supabase_enabled)
        for key in ("psycopg2 disponible", "Conexión Supabase (PG*)",
                    "Repo FinDataChile (ratios/DCF)"):
            c = checks.get(key)
            if c and not c["ok"]:
                problems.append(f"{key}: {c['detail']}")
    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="Pipeline CMF headless (descarga XBRL + consolidación + análisis)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    ap.add_argument("--start-year", type=int, default=datetime.now().year,
                    help="Año más reciente a descargar")
    ap.add_argument("--end-year", type=int, default=2014,
                    help="Año más antiguo a descargar")
    ap.add_argument("--frequency", choices=["annual", "quarterly", "total"],
                    default="total")
    ap.add_argument("--step", type=int, default=-1)
    ap.add_argument("--stages", default="download,consolidate",
                    help="Etapas separadas por coma: download,consolidate,upload")
    ap.add_argument("--csv", default=DEFAULT_CSV, help="CSV de empresas")
    ap.add_argument("--companies", default="",
                    help="Subconjunto de RUTs sin guión, separados por coma")
    ap.add_argument("--categorias", default="ifrs",
                    help="Categorías del CSV a procesar (coma; 'all' = todas)")
    ap.add_argument("--limit", type=int, default=0,
                    help="Procesar solo las primeras N empresas (para pruebas)")
    ap.add_argument("--json", action="store_true",
                    help="Emitir eventos como JSONL en stdout")
    ap.add_argument("--verbose", action="store_true",
                    help="Incluir progreso fino y logs crudos de Arelle")
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostrar el plan y salir sin ejecutar")
    ap.add_argument("--force", action="store_true",
                    help="Ejecutar aunque el preflight detecte problemas")
    ap.add_argument("--rebuild", action="store_true",
                    help="Regenerar el consolidado aunque el Excel ya exista y ya "
                         "cubra el último período descargado. Necesario cuando cambió "
                         "el CÓDIGO (fórmulas, estilos) y no los datos: el chequeo de "
                         "frescura compara períodos, no versiones, así que sin esto un "
                         "arreglo del generador nunca llega a los Excel ya escritos.")
    ap.add_argument("--backup", action="store_true",
                    help="Al terminar, correr scripts/backup_to_drive.sh")
    # --- Publicación (etapa UPLOAD) ---
    ap.add_argument("--fdc", action="store_true",
                    help="Habilitar el leg 3A: subir el Excel a FinDataChile "
                         "(Vercel Blob + products/product_versions).")
    ap.add_argument("--fdc-url", default="",
                    help="URL base de FinDataChile para el leg 3A "
                         "(ej: https://www.findatachile.com). Si se omite, usa la "
                         "configurada (default http://localhost:3000).")
    ap.add_argument("--supabase", action="store_true",
                    help="Habilitar el leg 3B: upsert de datos financieros a "
                         "Supabase (financial_data/line_items) + ratios + DCF.")
    ap.add_argument("--supabase-live", action="store_true",
                    help="Desactivar el dry-run del leg Supabase (por defecto es "
                         "dry-run seguro: no escribe en la BD). En modo dry-run el "
                         "leg 3A (blob) también se omite.")
    ap.add_argument("--no-ratios", action="store_true",
                    help="No recalcular ratios financieros tras subir los datos.")
    ap.add_argument("--no-dcf", action="store_true",
                    help="No recalcular DCF tras subir los datos.")
    ap.add_argument("--ratios-annual-only", action="store_true",
                    help="Recalcular ratios solo para períodos anuales (más rápido).")
    ap.add_argument("--supabase-no-override", action="store_true",
                    help="Forzar upsert NO destructivo en el leg Supabase (nunca "
                         "borra: solo inserta/actualiza). Más seguro para pilotos; "
                         "no resuelve el caso label-rename-split.")
    ap.add_argument("--supabase-override", action="store_true",
                    help="Forzar override (DELETE+INSERT por empresa) en el leg "
                         "Supabase. Resuelve label-rename-split pero reemplaza los "
                         "datos de la empresa por los del CSV.")
    return ap.parse_args()


def main() -> int:
    args = parse_args()
    rep = Reporter(as_json=args.json, verbose=args.verbose)

    try:
        stages = [Stage(s.strip().lower()) for s in args.stages.split(",") if s.strip()]
    except ValueError as exc:
        print(f"Etapa inválida en --stages: {exc}", file=sys.stderr)
        return 2
    if not stages:
        print("Sin etapas seleccionadas", file=sys.stderr)
        return 2

    sy, ey = max(args.start_year, args.end_year), min(args.start_year, args.end_year)
    config = {
        "start_year": sy,
        "end_year": ey,
        "step": -1 if args.frequency == "total" else args.step,
        "quarterly": args.frequency != "annual",
        "frequency": args.frequency,
        "strategy": "browser",
    }

    settings = PipelineSettings.load()
    if args.rebuild:
        settings.skip_existing = False
    config["skip_existing"] = settings.skip_existing
    settings.companies_csv = str(Path(args.csv).resolve())

    # Overrides de publicación desde flags (no se persisten a disco).
    if args.fdc:
        settings.fdc_enabled = True
        if args.fdc_url:
            settings.fdc_base_url = args.fdc_url.rstrip("/")
        # Auto-leer credenciales admin del .env de FinDataChile (ADMIN_USERNAME/
        # ADMIN_PASSWORD) si no están seteadas. Así no hace falta hardcodear la
        # contraseña en este repo: vive solo en FinDataChile/.env.
        if not (settings.fdc_username and settings.fdc_password):
            from src.gui.pipeline.supabase_uploader import load_env_file
            fdc_env = (load_env_file(Path(settings.pg_env_file))
                       if settings.pg_env_file else {})
            settings.fdc_username = settings.fdc_username or fdc_env.get("ADMIN_USERNAME", "")
            settings.fdc_password = settings.fdc_password or fdc_env.get("ADMIN_PASSWORD", "")
    if args.supabase:
        settings.supabase_enabled = True
    # dry-run seguro por defecto; --supabase-live lo desactiva.
    settings.supabase_dry_run = not args.supabase_live
    if args.no_ratios:
        settings.upload_with_ratios = False
    if args.no_dcf:
        settings.upload_with_dcf = False
    if args.ratios_annual_only:
        settings.upload_ratios_annual_only = True
    if args.supabase_no_override:
        settings.supabase_override = False
    elif args.supabase_override:
        settings.supabase_override = True

    ruts = {r.strip() for r in args.companies.split(",") if r.strip()} or None
    categorias = {c.strip().lower() for c in args.categorias.split(",") if c.strip()}
    companies, skipped = load_companies(args.csv, categorias, ruts,
                                        args.limit or None)

    for c in skipped:
        rep.line(f"OMITIDA {c['rut']} {c['razon_social']} — {c['reason']}", "WARNING")
    rep.line(f"Plan: {len(companies)} empresa(s), {len(skipped)} omitida(s) | "
             f"etapas: {', '.join(s.label for s in stages)} | "
             f"{sy}→{ey} ({args.frequency})")
    if not companies:
        print("Ninguna empresa seleccionada", file=sys.stderr)
        return 2
    if args.dry_run:
        for c in companies:
            rep.line(f"  {c['rut']:14s} {c['razon_social']}")
        return 0

    problems = preflight(settings, stages)
    if problems:
        for p in problems:
            rep.line(f"PREFLIGHT: {p}", "ERROR" if not args.force else "WARNING")
        if not args.force:
            rep.line("Aborta por preflight (usa --force para ejecutar igual)", "ERROR")
            return 2

    events: "queue.Queue[PipelineEvent]" = queue.Queue()
    orch = PipelineOrchestrator(settings, events)

    def _stop(signum, _frame):
        rep.line(f"Señal {signal.Signals(signum).name} recibida; deteniendo…", "WARNING")
        orch.stop()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    started = time.time()
    orch.start(companies, config, stages)

    finished_payload: dict = {}
    while True:
        try:
            ev = events.get(timeout=1.0)
        except queue.Empty:
            if not orch.running:
                break
            continue
        rep.event(ev)
        if ev.kind == "finished":
            finished_payload = ev.payload or {}
            break

    # Drenar lo que quede en cola tras "finished"
    while True:
        try:
            rep.event(events.get_nowait())
        except queue.Empty:
            break

    # ------------------------- resumen final -------------------------
    failed = [s for s in orch.states.values() if s.has_error]
    ok = [s for s in orch.states.values() if not s.has_error]
    elapsed = finished_payload.get("elapsed", time.time() - started)
    rep.line(f"RESUMEN: {len(ok)} ok, {len(failed)} con error, "
             f"{len(skipped)} omitidas, {elapsed:.0f}s")
    if Stage.UPLOAD in stages:
        vals = list(orch.states.values())
        total_dp = sum(s.upload_datapoints for s in vals)
        blob_ok = sum(1 for s in vals if s.upload_blob_ok is True)
        rat_ok = sum(1 for s in vals if s.upload_ratios_ok is True)
        rat_fail = sum(1 for s in vals if s.upload_ratios_ok is False)
        dcf_ok = sum(1 for s in vals if s.upload_dcf_ok is True)
        dcf_fail = sum(1 for s in vals if s.upload_dcf_ok is False)
        mode = "dry-run" if settings.supabase_dry_run else "live"
        rep.line(f"UPLOAD ({mode}): {total_dp} datapoints | blob {blob_ok} | "
                 f"ratios {rat_ok} ok/{rat_fail} fallidos | "
                 f"dcf {dcf_ok} ok/{dcf_fail} fallidos")
    for s in failed:
        first_error = s.error or next(
            (f"{st.label}" for st, v in s.stages.items() if v == StageStatus.ERROR),
            "error desconocido")
        rep.line(f"  ERROR {s.rut_completo} {s.name}: {first_error}", "ERROR")
    if args.json:
        summary = {
            "kind": "summary",
            "ok": [s.rut_completo for s in ok],
            "failed": {s.rut_completo: (s.error or "error") for s in failed},
            "skipped": [c["rut"] for c in skipped],
            "elapsed": elapsed,
        }
        if Stage.UPLOAD in stages:
            summary["upload_mode"] = "dry-run" if settings.supabase_dry_run else "live"
            summary["upload"] = {
                s.rut_completo: {
                    "blob_ok": s.upload_blob_ok,
                    "datapoints": s.upload_datapoints,
                    "ratios_ok": s.upload_ratios_ok,
                    "dcf_ok": s.upload_dcf_ok,
                }
                for s in orch.states.values()
            }
        print(json.dumps(summary, ensure_ascii=False), flush=True)

    if args.backup:
        rep.line("Iniciando respaldo a Google Drive…")
        rc = subprocess.call([str(PROJECT_ROOT / "scripts/backup_to_drive.sh")])
        if rc != 0:
            rep.line(f"Respaldo terminó con código {rc}", "ERROR")
            return 1

    return 1 if failed or finished_payload.get("cancelled") else 0


if __name__ == "__main__":
    sys.exit(main())
