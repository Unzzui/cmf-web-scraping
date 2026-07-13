#!/usr/bin/env python3
"""Runner ejecutado DENTRO del entorno de CMF_EXTRACT (vía subprocess).

La GUI (cmf-web-scraping) y CMF_EXTRACT pueden vivir en intérpretes distintos
(pyenv, venv, etc.) con dependencias incompatibles (pandas 2.1 vs 2.3, Arelle...).
Por eso NO importamos CMF_EXTRACT en el proceso de la GUI: lo ejecutamos con su
propio python y nos comunicamos por un protocolo de líneas JSON (JSONL) sobre stdout.

Contrato
--------
- stdout: SOLO objetos JSON, uno por línea (protocolo).
- stderr: logs/diagnóstico de las librerías (la GUI los muestra como log).

Eventos emitidos (stdout):
  {"event":"stage","stage":"consolidate","status":"running"}
  {"event":"progress","stage":"consolidate","current":1,"total":3,"message":"..."}
  {"event":"stage","stage":"consolidate","status":"done","elapsed":12.3,"errors":{}}
  {"event":"final","status":"ok|error","outputs":[{"path":..,"start_year":..,"end_year":..}],"error":""}

Uso:
  python cmf_extract_runner.py --repo-root DIR --company-dir DIR \
      --xbrl-base-dir DIR --products-dir DIR --product-v1-dir DIR \
      --arelle-dir DIR --langs es --workers 4 \
      --phases consolidate,excel,analysis [--skip-existing] [--debug]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# stdout queda reservado para el protocolo JSONL; cualquier print de librerías
# (Rich, pandas, Arelle) lo desviamos a stderr para no corromper el canal.
_PROTO = sys.stdout
sys.stdout = sys.stderr

_YEAR_RANGE = re.compile(r"(\d{4})\s*-\s*(\d{4})")


def emit(obj: dict) -> None:
    try:
        _PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
        _PROTO.flush()
    except Exception:
        pass


def _parse_year_range(name: str) -> tuple[int | None, int | None]:
    m = _YEAR_RANGE.search(name)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


_DATASET_RE = re.compile(r"_(\d{6})_extracted$")
# Rango del nombre del Excel de análisis: "… 2014-2025Q4 [ES].xlsx" / "… 2014-2025 [ES].xlsx"
_COVERED_RE = re.compile(r"(\d{4})(?:Q[1-4])?\s*-\s*(\d{4})(?:Q([1-4]))?")


def _newest_dataset_period(company_dir: Path) -> str | None:
    """Último período (yyyymm) con dataset XBRL en disco para la empresa."""
    best: str | None = None
    for d in company_dir.iterdir():
        if not d.is_dir():
            continue
        m = _DATASET_RE.search(d.name)
        if m and (best is None or m.group(1) > best):
            best = m.group(1)
    return best


def _covered_period(analysis_name: str) -> str | None:
    """Último período (yyyymm) que cubre un Excel de análisis, según su nombre."""
    m = _COVERED_RE.search(analysis_name)
    if not m:
        return None
    year = m.group(2)
    quarter = int(m.group(3) or 4)  # sin trimestre en el nombre => cierre anual
    return f"{year}{quarter * 3:02d}"


def _analysis_is_current(outputs: list[dict], company_dir: Path) -> bool:
    """¿El análisis ya generado cubre el período más reciente descargado?

    Sin esto, ``skip_existing`` salta la empresa por el solo hecho de tener un
    Excel, y el trimestre recién descargado no entra nunca al consolidado: la
    serie queda congelada hasta que alguien borre Product_v1 a mano.
    """
    newest = _newest_dataset_period(company_dir)
    if newest is None:
        return True  # sin XBRL en disco no hay nada que recalcular
    covered = [c for c in (_covered_period(o["name"]) for o in outputs) if c]
    if not covered:
        return False  # no se pudo leer el rango: recalcular es lo seguro
    return max(covered) >= newest


def _find_analysis_outputs(product_v1_dir: Path, rut: str, rut_completo: str) -> list[dict]:
    """Buscar Excel de análisis ya generados para este RUT."""
    outputs: list[dict] = []
    if not product_v1_dir.exists():
        return outputs
    keys = {rut, rut_completo}
    seen: set[str] = set()
    for p in product_v1_dir.rglob("*.xlsx"):
        if p.name.startswith("~$"):
            continue
        if any(k and k in p.name for k in keys):
            if p.name in seen:
                continue
            seen.add(p.name)
            sy, ey = _parse_year_range(p.name)
            outputs.append({
                "path": str(p), "name": p.name,
                "start_year": sy, "end_year": ey,
                "mtime": p.stat().st_mtime,
            })
    outputs.sort(key=lambda o: o["mtime"], reverse=True)
    return outputs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-root", required=True)
    ap.add_argument("--company-dir", required=True)
    ap.add_argument("--rut", default="")
    ap.add_argument("--rut-completo", default="")
    ap.add_argument("--xbrl-base-dir", required=True)
    ap.add_argument("--products-dir", required=True)
    ap.add_argument("--product-v1-dir", required=True)
    ap.add_argument("--arelle-dir", default="")
    ap.add_argument("--companies-csv", default="")
    ap.add_argument("--langs", default="es")
    ap.add_argument("--workers", type=int, default=0)
    ap.add_argument("--phases", default="consolidate,excel,analysis")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve()
    company_dir = Path(args.company_dir).resolve()
    product_v1_dir = Path(args.product_v1_dir).resolve()
    rut = args.rut or company_dir.name.split("_", 1)[0].split("-")[0]
    rut_completo = args.rut_completo or company_dir.name.split("_", 1)[0]
    phases = [p.strip() for p in args.phases.split(",") if p.strip()]
    langs = [l.strip() for l in args.langs.split(",") if l.strip()]

    # Asegurar que tanto el paquete cmf como los módulos top-level
    # (run_products_analysis, primary_csv_to_excel, ...) resuelvan.
    sys.path.insert(0, str(repo_root))

    # Configurar entorno ANTES de importar cmf.config para que tome las rutas.
    os.environ["CMF_ARELLE_DIR"] = args.arelle_dir or os.environ.get("CMF_ARELLE_DIR", "")
    os.environ["CMF_XBRL_BASE_DIR"] = args.xbrl_base_dir
    os.environ["CMF_PRODUCTS_DIR"] = args.products_dir
    os.environ["CMF_PRODUCT_V1_DIR"] = str(product_v1_dir)
    if args.companies_csv:
        os.environ["CMF_COMPANIES_CSV"] = args.companies_csv
    if args.workers > 0:
        os.environ["CMF_WORKERS"] = str(args.workers)
    if args.debug:
        os.environ["X2E_DEBUG"] = "1"

    # --- Atajo skip_existing: si el análisis ya cubre el último período XBRL
    #     descargado, no recalculamos nada. Si hay un trimestre nuevo en disco
    #     que el Excel no cubre, se recalcula aunque el Excel exista.
    if args.skip_existing:
        existing = _find_analysis_outputs(product_v1_dir, rut, rut_completo)
        if existing and _analysis_is_current(existing, company_dir):
            for ph in phases:
                emit({"event": "stage", "stage": ph, "status": "skipped"})
            emit({"event": "final", "status": "ok", "outputs": existing, "skipped": True, "error": ""})
            return 0

    # --- Importar el pipeline de CMF_EXTRACT ---
    try:
        from cmf.config import CMFConfig
        from cmf.pipeline import consolidation, excel_gen, analysis
    except Exception as e:  # pragma: no cover
        emit({"event": "final", "status": "error",
              "error": f"No se pudo importar cmf.pipeline: {e}", "outputs": []})
        return 2

    config = CMFConfig(
        repo_root=repo_root,
        arelle_dir=Path(args.arelle_dir) if args.arelle_dir else None,  # type: ignore[arg-type]
        xbrl_base_dir=Path(args.xbrl_base_dir),
        products_dir=Path(args.products_dir),
        product_v1_dir=product_v1_dir,
        companies_csv=Path(args.companies_csv) if args.companies_csv else None,  # type: ignore[arg-type]
        workers=args.workers if args.workers > 0 else 0,
        langs=langs,
        debug=args.debug,
    )
    try:
        config.apply_env()
        config.ensure_dirs()
    except Exception as e:
        emit({"event": "final", "status": "error",
              "error": f"Config inválida: {e}", "outputs": []})
        return 2

    company_dirs = [company_dir]

    runners = {
        "consolidate": consolidation.run,
        "excel": excel_gen.run,
        "analysis": analysis.run,
    }

    for ph in phases:
        run_fn = runners.get(ph)
        if run_fn is None:
            continue
        emit({"event": "stage", "stage": ph, "status": "running"})

        def cb(message: str = "", current: int = 0, total: int = 0, _ph=ph) -> None:
            emit({"event": "progress", "stage": _ph,
                  "current": int(current or 0), "total": int(total or 0),
                  "message": str(message)})

        t0 = time.time()
        try:
            result = run_fn(config, company_dirs, progress_callback=cb)
        except Exception as e:
            emit({"event": "stage", "stage": ph, "status": "error",
                  "elapsed": round(time.time() - t0, 1), "error": str(e)})
            emit({"event": "final", "status": "error",
                  "error": f"Fallo en etapa '{ph}': {e}", "outputs": []})
            return 1

        errors = dict(getattr(result, "errors", {}) or {})
        elapsed = round(getattr(result, "elapsed", time.time() - t0), 1)
        if errors:
            emit({"event": "stage", "stage": ph, "status": "error",
                  "elapsed": elapsed, "errors": errors})
            first = next(iter(errors.values()))
            emit({"event": "final", "status": "error",
                  "error": f"Etapa '{ph}': {first}", "outputs": []})
            return 1
        emit({"event": "stage", "stage": ph, "status": "done",
              "elapsed": elapsed, "errors": {}})

    outputs = _find_analysis_outputs(product_v1_dir, rut, rut_completo)
    # Si pedimos análisis pero no se generó ningún Excel, es un fallo real
    # (aunque las fases no lo hayan reportado): no devolver un "ok" engañoso.
    if "analysis" in phases and not outputs:
        emit({"event": "final", "status": "error", "outputs": [],
              "error": "El análisis no produjo ningún Excel (revisa el log de detalle)."})
        return 1
    emit({"event": "final", "status": "ok", "outputs": outputs, "error": ""})
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        emit({"event": "final", "status": "error", "error": "Interrumpido", "outputs": []})
        sys.exit(130)
