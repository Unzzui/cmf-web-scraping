#!/usr/bin/env python3
"""Motor del pipeline unificado con pipelining por etapa.

Cada empresa es un worker independiente que fluye:

    Descargar -> Consolidar -> Subir

Los workers comparten semáforos por etapa, de modo que mientras la empresa A
se consolida (Arelle, CPU), la empresa B ya está descargando (selenium, red) y
la empresa C ya se subió. Así solapamos las tres fases y el conjunto termina
mucho antes que haciéndolas en bloque.

La concurrencia real por etapa la fijan los semáforos (configurables):
  - descargas    : pocas (navegadores selenium)
  - consolidación: ~nº CPUs/2 (Arelle es intensivo)
  - subidas      : 2 (red)

Todos los cambios se publican como :class:`PipelineEvent` en una cola que la UI
consume desde el hilo principal de Tkinter.
"""

from __future__ import annotations

import csv
import os
import queue
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from .models import Stage, StageStatus, CompanyState, PipelineEvent, STAGE_ORDER
from .settings import PipelineSettings
from .cmf_extract_bridge import CmfExtractBridge
from .data_quality import check_company_csv
from .findatachile_uploader import FinDataChileUploader
from .supabase_uploader import (
    SupabaseUploader,
    find_company_csv,
    load_statement_types,
)


def _import_any(modpaths: list[str], attr: str):
    """Importar `attr` desde el primer módulo de la lista que cargue."""
    import importlib
    import sys
    root = Path(__file__).resolve().parents[3]
    # Añadir tanto la raíz (para `src.xbrl.*`) como `src/` (para `xbrl.*`),
    # ya que el downloader HTTP importa su sibling `xbrl.http_throttle` como
    # paquete top-level. Sin `src/` en el path, el import HTTP falla en
    # silencio y el pipeline cae al descargador Selenium (mucho más lento).
    for p in (str(root), str(root / "src")):
        if p not in sys.path:
            sys.path.insert(0, p)
    for mp in modpaths:
        try:
            mod = importlib.import_module(mp)
            return getattr(mod, attr)
        except Exception:
            continue
    return None


def _load_http_download_fn():
    """Descargador HTTP puro (rápido, sin navegador) — preferido."""
    return _import_any(
        ["src.xbrl.cmf_xbrl_http_downloader", "xbrl.cmf_xbrl_http_downloader"],
        "download_cmf_xbrl_http",
    )


def _load_browser_download_fn():
    """Descargador Selenium (fallback)."""
    return _import_any(
        ["src.xbrl.cmf_xbrl_downloader", "xbrl.cmf_xbrl_downloader"],
        "download_cmf_xbrl",
    )


def _load_download_fn():
    """Devuelve (fn, kind): HTTP si está disponible, si no Selenium."""
    fn = _load_http_download_fn()
    if fn is not None:
        return fn, "http"
    fn = _load_browser_download_fn()
    if fn is not None:
        return fn, "browser"
    return None, None


class PipelineOrchestrator:
    def __init__(self, settings: PipelineSettings, event_queue: "queue.Queue[PipelineEvent]"):
        self.settings = settings
        self.events = event_queue
        self.states: dict[str, CompanyState] = {}
        self._cancel = threading.Event()
        self._control_thread: Optional[threading.Thread] = None
        self._bridges: dict[str, CmfExtractBridge] = {}
        self._uploader: Optional[FinDataChileUploader] = None
        self._uploader_lock = threading.Lock()
        self._supa: Optional[SupabaseUploader] = None
        self._supa_lock = threading.Lock()  # psycopg2 no es thread-safe
        self.running = False

    # ------------------------------------------------------------------ #
    def _emit(self, evt: PipelineEvent) -> None:
        self.events.put(evt)

    def _log(self, message: str, level: str = "INFO", rut: Optional[str] = None) -> None:
        self._emit(PipelineEvent(kind="log", message=message, level=level, rut=rut))

    def _set_stage(self, rut: str, stage: Stage, status: StageStatus,
                   detail: str = "", error: str = "") -> None:
        st = self.states[rut]
        st.stages[stage] = status
        if detail:
            st.detail = detail
        if error:
            st.error = error
        self._emit(PipelineEvent(kind="stage", rut=rut, stage=stage,
                                 status=status, message=detail, level="ERROR" if error else "INFO"))

    # ------------------------------------------------------------------ #
    def _find_analysis_excel(self, st: CompanyState) -> str | None:
        """Localiza en Product_v1 el Excel de análisis ya generado para la empresa.

        Permite correr la etapa de subida por separado (--stages upload) sin volver a
        regenerar el análisis, que tarda horas. Si hay varios (rangos distintos de
        corridas previas), gana el más reciente.
        """
        try:
            base = Path(self.settings.product_v1_dir)
            if not base.is_dir():
                return None
            rut = (st.rut_completo or "").strip()
            if not rut:
                return None
            cands = [p for p in base.glob("*.xlsx")
                     if rut.upper() in p.name.upper() and not p.name.startswith("~$")]
            if not cands:
                return None
            return str(max(cands, key=lambda p: p.stat().st_mtime))
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    def _quality_gate(self, st: CompanyState):
        """Evalúa el CSV a subir contra el gate de calidad.

        Devuelve None si no se puede evaluar (sin CSV): en ese caso el leg 3B
        reporta el error de forma explícita y no hay nada que poner en cuarentena.
        """
        try:
            csv_data = find_company_csv(
                Path(self.settings.product_v1_dir) / "TO_SQL", st.rut_completo)
            if csv_data is None:
                return None
            return check_company_csv(
                csv_data,
                statement_types=load_statement_types(
                    csv_data, self.settings.xbrl_base_dir),
            )
        except Exception as exc:  # el gate nunca debe tumbar el pipeline
            self._log(f"No se pudo evaluar calidad de {st.name}: {exc}", "WARN")
            return None

    def _record_quarantine(self, st: CompanyState, report) -> None:
        """Deja constancia de la empresa retenida en un CSV junto a los productos."""
        try:
            path = Path(self.settings.product_v1_dir) / "CUARENTENA.csv"
            new_file = not path.exists()
            with path.open("a", encoding="utf-8", newline="") as fh:
                w = csv.writer(fh)
                if new_file:
                    w.writerow(["rut", "empresa", "ultimo_periodo", "filas_er",
                                "filas_balance", "datapoints", "motivos"])
                w.writerow([
                    st.rut_completo, st.name, report.last_period or "",
                    report.income_statement_rows, report.balance_sheet_rows,
                    report.data_points,
                    " | ".join(i.message for i in report.blocking_issues),
                ])
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    def start(self, companies: list[dict], config: dict, stages: list[Stage]) -> None:
        if self.running:
            return
        self._cancel.clear()
        self.running = True
        self.states = {}
        for c in companies:
            rut = str(c.get("rut_sin_guion") or c.get("rut", "")).strip()
            st = CompanyState(
                rut=rut,
                rut_completo=str(c.get("rut", rut)).strip(),
                name=str(c.get("razon_social", "")).strip(),
            )
            # Marcar como omitidas las etapas no seleccionadas
            for s in STAGE_ORDER:
                if s not in stages:
                    st.stages[s] = StageStatus.SKIPPED
            # Detectar desde ya qué períodos ya están descargados en disco
            existing = self._scan_existing_periods(rut, st.rut_completo)
            st.disk_periods = len(existing)
            if existing:
                st.detail = f"{len(existing)} periodos en disco"
            self.states[rut] = st

        self._control_thread = threading.Thread(
            target=self._run_all, args=(companies, config, stages), daemon=True
        )
        self._control_thread.start()

    def stop(self) -> None:
        self._cancel.set()
        for b in list(self._bridges.values()):
            try:
                b.cancel()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    def _run_all(self, companies: list[dict], config: dict, stages: list[Stage]) -> None:
        start_ts = time.time()
        self._emit(PipelineEvent(kind="started", total=len(companies),
                                 message=f"Iniciando pipeline para {len(companies)} empresa(s)"))

        # Resumen de lo ya disponible en disco (skip inteligente)
        if self.settings.skip_existing:
            with_data = [(s.name or s.rut_completo, s.disk_periods)
                         for s in self.states.values() if s.disk_periods]
            if with_data:
                self._log(f"Periodos ya en disco (no se vuelven a descargar): "
                          + "; ".join(f"{n}: {p}" for n, p in with_data), "INFO")
            else:
                self._log("No hay periodos previos en disco; se descargara todo lo disponible.", "INFO")

        download_fn, download_kind = (None, None)
        if Stage.DOWNLOAD in stages:
            download_fn, download_kind = _load_download_fn()
            if download_fn is None:
                self._log("No se pudo cargar ningún descargador XBRL. Se omitirá la descarga.",
                          "WARNING")
            else:
                self._log(f"Descarga: modo {'HTTP rápido' if download_kind == 'http' else 'navegador'}.")

        if Stage.UPLOAD in stages and self.settings.fdc_enabled:
            self._uploader = FinDataChileUploader(self.settings)
            if not self._uploader.available:
                self._log("La librería 'requests' no está disponible; la subida fallará.", "WARNING")

        if Stage.UPLOAD in stages and self.settings.supabase_enabled:
            self._supa = SupabaseUploader(
                env_file=Path(self.settings.pg_env_file) if self.settings.pg_env_file else None,
                findatachile_repo=Path(self.settings.findatachile_repo) if self.settings.findatachile_repo else None,
                dcf_python=Path(self.settings.dcf_python) if self.settings.dcf_python else None,
            )
            if not self._supa.available:
                self._log("Supabase: falta psycopg2 o credenciales PG*; el leg de "
                          "tablas fallará.", "WARNING")
                self._supa = None
            else:
                mode = "DRY-RUN" if self.settings.supabase_dry_run else "LIVE"
                self._log(f"Supabase: leg de tablas financieras activo ({mode}).")

        sem_dl = threading.Semaphore(max(1, self.settings.download_workers))
        sem_co = threading.Semaphore(max(1, self.settings.effective_consolidate_workers()))
        sem_up = threading.Semaphore(max(1, self.settings.upload_workers))

        pool_size = (self.settings.download_workers
                     + self.settings.effective_consolidate_workers()
                     + self.settings.upload_workers + 1)
        pool_size = min(pool_size, max(1, len(companies)))

        with ThreadPoolExecutor(max_workers=pool_size) as ex:
            futures = [
                ex.submit(self._process_company, c, config, stages,
                          download_fn, download_kind, sem_dl, sem_co, sem_up)
                for c in companies
            ]
            for f in futures:
                try:
                    f.result()
                except Exception as e:  # pragma: no cover
                    self._log(f"Worker falló: {e}", "ERROR")

        elapsed = time.time() - start_ts
        ok = sum(1 for s in self.states.values() if not s.has_error)
        err = sum(1 for s in self.states.values() if s.has_error)
        uploaded = sum(1 for s in self.states.values()
                       if s.stages.get(Stage.UPLOAD) == StageStatus.DONE)
        self.running = False
        self._emit(PipelineEvent(
            kind="finished",
            message=("Cancelado por el usuario" if self._cancel.is_set()
                     else "Pipeline completado"),
            payload={"ok": ok, "errors": err, "uploaded": uploaded,
                     "elapsed": elapsed, "cancelled": self._cancel.is_set()},
        ))

    # ------------------------------------------------------------------ #
    _PERIOD_RE = re.compile(r"_(\d{6})_extracted$")

    def periods_on_disk(self, rut: str, rut_completo: str) -> list[str]:
        """Público: períodos YYYYMM ya descargados (para vista previa en la UI)."""
        return self._scan_existing_periods(rut, rut_completo)

    def _scan_existing_periods(self, rut: str, rut_completo: str) -> list[str]:
        """Devuelve los YYYYMM ya descargados en disco para esta empresa."""
        company_dir = self._resolve_company_dir(rut, rut_completo)
        if company_dir is None or not company_dir.is_dir():
            return []
        periods: set[str] = set()
        for d in company_dir.iterdir():
            if d.is_dir():
                m = self._PERIOD_RE.search(d.name)
                if m:
                    periods.add(m.group(1))
        return sorted(periods)

    def _resolve_company_dir(self, rut: str, rut_completo: str) -> Optional[Path]:
        base = Path(self.settings.xbrl_base_dir)
        candidates = [base]
        parent = base.parent
        for sub in ("Total", "Anual", "Trimestral"):
            p = parent / sub
            if p != base:
                candidates.append(p)
        for b in candidates:
            if not b.is_dir():
                continue
            for d in sorted(b.iterdir()):
                if not d.is_dir():
                    continue
                head = d.name.split("_", 1)[0]
                if head == rut_completo or head.split("-")[0] == rut:
                    return d
        return None

    def _process_company(self, company: dict, config: dict, stages: list[Stage],
                         download_fn, download_kind, sem_dl, sem_co, sem_up) -> None:
        rut = str(company.get("rut_sin_guion") or company.get("rut", "")).strip()
        st = self.states[rut]
        st.started_at = time.time()
        company_dir: Optional[Path] = None

        try:
            # ---------------- ETAPA 1: DESCARGAR ----------------
            if Stage.DOWNLOAD in stages and download_fn is not None and not self._cancel.is_set():
                with sem_dl:
                    if self._cancel.is_set():
                        return
                    self._set_stage(rut, Stage.DOWNLOAD, StageStatus.RUNNING, "Descargando XBRL…")

                    def hook(rut_cb, current, total, year, month, eta_sec, status):
                        if total:
                            st.progress = (current or 0) / total
                            st.progress_text = f"{current}/{total}"
                        if eta_sec is not None:
                            st.eta_seconds = eta_sec
                        per = f"{year}-{int(month):02d}" if (year and month) else ""
                        self._emit(PipelineEvent(
                            kind="progress", rut=rut, stage=Stage.DOWNLOAD,
                            current=current or 0, total=total or 0,
                            eta_seconds=eta_sec,
                            message=f"Período {per}" if per else (str(status) or "")))

                    try:
                        if download_kind == "http":
                            target_dir, downloaded = download_fn(
                                rut=rut,
                                start_year=config["start_year"],
                                end_year=config["end_year"],
                                step=config["step"],
                                quarterly=config.get("quarterly", False),
                                mode=config.get("frequency"),
                                progress_hook=hook,
                                skip_existing=self.settings.skip_existing,
                                # Workers por empresa; el cap real cross-empresa
                                # lo aplica el semáforo global del downloader.
                                max_workers=max(1, self.settings.download_workers),
                                companies_csv=self.settings.companies_csv,
                            )
                        else:
                            target_dir, downloaded = download_fn(
                                rut=rut,
                                start_year=config["start_year"],
                                end_year=config["end_year"],
                                step=config["step"],
                                headless=True,
                                quarterly=config.get("quarterly", False),
                                mode=config.get("frequency"),
                                progress_hook=hook,
                                strategy=config.get("strategy", "browser"),
                                skip_existing=self.settings.skip_existing,
                            )
                        company_dir = Path(target_dir).resolve() if target_dir else None
                        n = len(downloaded) if downloaded else 0
                        self._set_stage(rut, Stage.DOWNLOAD, StageStatus.DONE,
                                        f"{n} archivo(s) descargado(s)")
                    except Exception as e:
                        self._set_stage(rut, Stage.DOWNLOAD, StageStatus.ERROR,
                                        error=f"Descarga falló: {e}")
                        return
            elif Stage.DOWNLOAD in stages and download_fn is None:
                self._set_stage(rut, Stage.DOWNLOAD, StageStatus.SKIPPED, "Descargador no disponible")

            if self._cancel.is_set():
                return

            # Resolver carpeta de XBRL si no vino de la descarga
            if company_dir is None:
                company_dir = self._resolve_company_dir(rut, st.rut_completo)

            # ---------------- ETAPA 2: CONSOLIDAR ----------------
            if Stage.CONSOLIDATE in stages and not self._cancel.is_set():
                if company_dir is None or not company_dir.is_dir():
                    self._set_stage(rut, Stage.CONSOLIDATE, StageStatus.ERROR,
                                    error="No se encontró carpeta XBRL para consolidar")
                    return
                with sem_co:
                    if self._cancel.is_set():
                        return
                    self._set_stage(rut, Stage.CONSOLIDATE, StageStatus.RUNNING, "Consolidando (Arelle)…")
                    bridge = CmfExtractBridge(self.settings)
                    self._bridges[rut] = bridge

                    def on_stage(stage_name, status, info):
                        # sub-etapas internas (consolidate/excel/analysis) -> detalle
                        st.detail = f"{stage_name}: {status}"
                        if status == "error" and info.get("errors"):
                            st.detail = f"{stage_name}: {next(iter(info['errors'].values()))}"
                        self._emit(PipelineEvent(kind="progress", rut=rut, stage=Stage.CONSOLIDATE,
                                                 message=st.detail))

                    def on_progress(stage_name, cur, tot, msg):
                        if tot:
                            st.progress = (cur or 0) / tot
                            st.progress_text = f"{cur}/{tot}"
                        self._emit(PipelineEvent(kind="progress", rut=rut, stage=Stage.CONSOLIDATE,
                                                 current=cur, total=tot,
                                                 message=f"{stage_name}: {msg}" if msg else stage_name))

                    def on_log(line):
                        # Salida cruda de CMF_EXTRACT/Arelle: nivel DETAIL (gris).
                        self._log(line, "DETAIL", rut=rut)

                    final = bridge.run(
                        company_dir=str(company_dir),
                        rut=rut, rut_completo=st.rut_completo,
                        phases=["consolidate", "excel", "analysis"],
                        on_stage=on_stage, on_progress=on_progress, on_log=on_log,
                        xbrl_base_dir=str(company_dir.parent),
                    )
                    self._bridges.pop(rut, None)

                    if final.get("status") != "ok":
                        self._set_stage(rut, Stage.CONSOLIDATE, StageStatus.ERROR,
                                        error=final.get("error", "Error en consolidación"))
                        return
                    outputs = final.get("outputs") or []
                    if outputs:
                        best = outputs[0]
                        st.output_file = best.get("path")
                        st.start_year = best.get("start_year")
                        st.end_year = best.get("end_year")
                    detail = "Excel listo" + (" (omitido, ya existía)" if final.get("skipped") else "")
                    self._set_stage(rut, Stage.CONSOLIDATE, StageStatus.DONE, detail)

            if self._cancel.is_set():
                return

            # ---------------- ETAPA 3: SUBIR ----------------
            # Dos sub-pasos atómicos por empresa, dentro del mismo semáforo:
            #   3A. blob + catálogo FinDataChile (crea/asegura la empresa)
            #   3B. tablas financieras Supabase + ratios + DCF
            # Orden 3A->3B obligatorio: 3A crea la empresa que 3B necesita.
            do_upload = (Stage.UPLOAD in stages and not self._cancel.is_set()
                         and (self.settings.fdc_enabled or self.settings.supabase_enabled))
            if do_upload:
                with sem_up:
                    if self._cancel.is_set():
                        return
                    self._set_stage(rut, Stage.UPLOAD, StageStatus.RUNNING, "Subiendo…")

                    # `output_file` sólo lo rellena la etapa CONSOLIDATE. Cuando se corre
                    # sólo la etapa de subida (--stages upload), viene vacío y 3A abortaba
                    # con "no hay Excel de análisis para subir" aunque el Excel estuviera
                    # en disco. Se resuelve desde Product_v1 por RUT.
                    if not st.output_file:
                        st.output_file = self._find_analysis_excel(st)

                    # Gate de calidad ANTES de ambos legs: 3A publica el Excel en
                    # la tienda y 3B escribe las tablas; las dos son producción.
                    # Una serie congelada (el emisor dejó de publicar consolidado)
                    # o un estado de resultados sin línea de ingresos no llega a
                    # producción por ninguna de las dos vías.
                    qa = self._quality_gate(st)
                    if qa is not None and not qa.ok:
                        self._log(f"CUARENTENA {st.name}: {qa.summary()}", "WARN", rut=rut)
                        self._record_quarantine(st, qa)
                        self._set_stage(rut, Stage.UPLOAD, StageStatus.SKIPPED,
                                        detail=f"Cuarentena: {qa.summary()}")
                        return
                    if qa is not None:
                        for issue in qa.warnings:
                            self._log(f"{st.name}: {issue.message}", "WARN", rut=rut)

                    errors: list[str] = []
                    details: list[str] = []

                    # -------- 3A: blob + catálogo FinDataChile --------
                    if self.settings.fdc_enabled:
                        if self.settings.supabase_dry_run:
                            # El endpoint no tiene dry-run: en modo seguro se omite.
                            details.append("3A blob omitido (dry-run)")
                        elif not st.output_file:
                            errors.append("3A: no hay Excel de análisis para subir")
                        else:
                            with self._uploader_lock:
                                uploader = self._uploader
                            if uploader is None:
                                errors.append("3A: uploader no inicializado")
                            else:
                                ok, msg = uploader.upload_file(
                                    st.output_file,
                                    company_name=st.name,
                                    rut_completo=st.rut_completo,
                                    start_year=st.start_year or config.get("end_year"),
                                    end_year=st.end_year or config.get("start_year"),
                                    quarterly=config.get("quarterly", False),
                                )
                                st.upload_blob_ok = bool(ok)
                                if ok:
                                    details.append(f"3A {msg}")
                                else:
                                    errors.append(f"3A: {msg}")

                    if self._cancel.is_set():
                        return

                    # -------- 3B: tablas financieras + ratios + DCF --------
                    if self.settings.supabase_enabled:
                        if self._supa is None:
                            errors.append("3B: uploader Supabase no disponible (psycopg2/creds)")
                        else:
                            to_sql_dir = Path(self.settings.product_v1_dir) / "TO_SQL"
                            # psycopg2 no es thread-safe: serializar el leg de tablas.
                            with self._supa_lock:
                                res = self._supa.upload_company_tables(
                                    st.rut_completo,  # RUT-DV: identidad en companies/CSV
                                    to_sql_dir=to_sql_dir,
                                    override=self.settings.supabase_override,
                                    dry_run=self.settings.supabase_dry_run,
                                    with_ratios=self.settings.upload_with_ratios,
                                    with_dcf=self.settings.upload_with_dcf,
                                    annual_only=self.settings.upload_ratios_annual_only,
                                    on_log=lambda line: self._log(line, "DETAIL", rut=rut),
                                )
                            if res.error:
                                errors.append(f"3B: {res.error}")
                            else:
                                st.upload_datapoints = res.data_points
                                st.upload_ratios_ok = res.ratios_ok
                                st.upload_dcf_ok = res.dcf_ok
                                partial: list[str] = []
                                if self.settings.upload_with_ratios and res.ratios_ok is False:
                                    partial.append("ratios")
                                if self.settings.upload_with_dcf and res.dcf_ok is False:
                                    partial.append("dcf")
                                msg3b = f"3B {res.data_points} datapoints"
                                if partial:
                                    msg3b += f" (parcial: {'/'.join(partial)} falló)"
                                details.append(msg3b)

                    # -------- estado final de la etapa UPLOAD --------
                    if errors:
                        self._set_stage(rut, Stage.UPLOAD, StageStatus.ERROR,
                                        detail="; ".join(details),
                                        error="; ".join(errors))
                    else:
                        self._set_stage(rut, Stage.UPLOAD, StageStatus.DONE,
                                        "; ".join(details) or "Subido")
        finally:
            st.finished_at = time.time()
            self._emit(PipelineEvent(kind="company_done", rut=rut))
