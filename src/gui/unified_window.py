#!/usr/bin/env python3
"""Ventana unificada del pipeline CMF: Descargar → Consolidar → Subir.

Una sola GUI que orquesta el flujo completo y desatendido, con una vista viva
de todas las etapas por empresa. Reutiliza los componentes existentes
(CompanyTable, LogViewer, tema profesional) y añade la capa de pipeline.
"""

from __future__ import annotations

import queue
import tkinter as tk
from datetime import datetime
from tkinter import ttk, filedialog, messagebox

from .styles.professional_theme import ProfessionalStyles, get_font_config, get_color_config
from .components.company_table import CompanyTable
from .components.log_viewer import LogViewer
from .components.pipeline_view import PipelineView
from .utils.csv_manager import CSVManager
from .utils.system_utils import open_folder

from .pipeline.models import Stage, StageStatus, PipelineEvent, STAGE_ORDER
from .pipeline.settings import PipelineSettings
from .pipeline.orchestrator import PipelineOrchestrator
from .settings_dialog import SettingsDialog


class UnifiedPipelineGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CMF Pipeline - Descarga / Consolidacion / Publicacion")

        self.settings = PipelineSettings.load()
        self.csv_manager = CSVManager()
        self.events: "queue.Queue[PipelineEvent]" = queue.Queue()
        self.orchestrator = PipelineOrchestrator(self.settings, self.events)
        self.is_running = False
        self._run_started_at: float | None = None
        self._total_companies = 0
        self._done_companies = 0

        self._setup_window()
        self.colors = get_color_config()
        self.fonts = get_font_config()
        self.root.configure(bg=self.colors["background"])
        self.style = ProfessionalStyles.setup_styles()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._load_default_csv)
        self.root.after(150, self._poll_events)
        self.root.after(1000, self._tick_timer)

    # ------------------------------------------------------------------ #
    def _setup_window(self) -> None:
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = int(sw * 0.9), int(sh * 0.88)
        x, y = (sw - w) // 2, (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")
        self.root.minsize(1100, 720)

    def _build_ui(self) -> None:
        main = tk.Frame(self.root, bg=self.colors["background"])
        main.pack(fill=tk.BOTH, expand=True, padx=12, pady=10)

        self._build_toolbar(main)

        body = tk.Frame(main, bg=self.colors["background"])
        body.pack(fill=tk.BOTH, expand=True, pady=(10, 0))

        # Columna izquierda: selección + configuración
        left = tk.Frame(body, bg=self.colors["background"], width=430)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 10))
        left.pack_propagate(False)
        self._build_config(left)
        self._build_company_section(left)

        # Columna derecha: pipeline + log
        right = tk.Frame(body, bg=self.colors["background"])
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.pipeline_view = PipelineView(right)
        self.pipeline_view.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        self.log_viewer = LogViewer(right, height=10)
        self.log_viewer.pack(fill=tk.BOTH, expand=False)

    def _build_toolbar(self, parent) -> None:
        bar = tk.Frame(parent, bg=self.colors["background"])
        bar.pack(fill=tk.X)

        ttk.Label(bar, text="CMF Pipeline", style="Title.TLabel").pack(side=tk.LEFT)

        right = tk.Frame(bar, bg=self.colors["background"])
        right.pack(side=tk.RIGHT)

        self.run_btn = ttk.Button(right, text="Ejecutar pipeline",
                                  style="Success.TButton", command=self._on_run)
        self.run_btn.pack(side=tk.LEFT, padx=(0, 6))
        self.stop_btn = ttk.Button(right, text="Detener", style="Danger.TButton",
                                   command=self._on_stop, state="disabled")
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(right, text="Resultados", style="Secondary.TButton",
                   command=self._open_results).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(right, text="Configuración", style="Primary.TButton",
                   command=self._open_settings).pack(side=tk.LEFT)

    def _build_config(self, parent) -> None:
        frame = ttk.LabelFrame(parent, text="Configuración", style="Card.TLabelframe", padding=12)
        frame.pack(fill=tk.X, pady=(0, 10))

        cur = datetime.now().year
        years = [str(y) for y in range(cur, 2009, -1)]

        self.start_year = tk.StringVar(value=str(cur))
        self.end_year = tk.StringVar(value="2014")
        self.step = tk.StringVar(value="-1")
        self.frequency = tk.StringVar(value="total")

        grid = tk.Frame(frame, bg=self.colors["background"])
        grid.pack(fill=tk.X)
        tk.Label(grid, text="Desde:", bg=self.colors["background"], font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w")
        ttk.Combobox(grid, textvariable=self.start_year, values=years, width=8,
                     state="readonly", style="Professional.TCombobox").grid(row=0, column=1, padx=(4, 14))
        tk.Label(grid, text="Hasta:", bg=self.colors["background"], font=("Segoe UI", 9)).grid(row=0, column=2, sticky="w")
        ttk.Combobox(grid, textvariable=self.end_year, values=years, width=8,
                     state="readonly", style="Professional.TCombobox").grid(row=0, column=3, padx=(4, 0))

        freq = tk.Frame(frame, bg=self.colors["background"])
        freq.pack(fill=tk.X, pady=(10, 0))
        tk.Label(freq, text="Frecuencia:", bg=self.colors["background"],
                 font=("Segoe UI", 9, "bold")).pack(anchor="w")
        for val, label in (("annual", "Anual (diciembre)"),
                           ("quarterly", "Trimestral (3,6,9,12)"),
                           ("total", "Total (anual + trimestral)")):
            ttk.Radiobutton(freq, text=label, variable=self.frequency, value=val).pack(anchor="w")

        # Toggles de etapa
        stages = ttk.LabelFrame(parent, text="Etapas a ejecutar", style="Card.TLabelframe", padding=12)
        stages.pack(fill=tk.X, pady=(0, 10))
        self.do_download = tk.BooleanVar(value=True)
        self.do_consolidate = tk.BooleanVar(value=True)
        self.do_upload = tk.BooleanVar(value=False)
        ttk.Checkbutton(stages, text="1) Descargar XBRL desde la CMF",
                        variable=self.do_download).pack(anchor="w")
        ttk.Checkbutton(stages, text="2) Consolidar a Excel (CMF_EXTRACT)",
                        variable=self.do_consolidate).pack(anchor="w")
        # La subida a FinDataChile queda diferida (se publicará aparte para el
        # usuario real). El toggle se muestra deshabilitado para dejarlo a la vista.
        ttk.Checkbutton(stages, text="3) Subir a FinDataChile (proximamente)",
                        variable=self.do_upload, state="disabled").pack(anchor="w")
        tk.Label(stages, text="El pipeline solapa etapas: mientras una empresa\n"
                              "se consolida, otra ya está descargando. La subida\n"
                              "a FinDataChile se hará por separado más adelante.",
                 bg=self.colors["background"], fg=self.colors["text_muted"],
                 font=("Segoe UI", 8), justify=tk.LEFT).pack(anchor="w", pady=(6, 0))

    def _build_company_section(self, parent) -> None:
        data = ttk.LabelFrame(parent, text="Empresas", style="Card.TLabelframe", padding=8)
        data.pack(fill=tk.BOTH, expand=True)

        top = tk.Frame(data, bg=self.colors["background"])
        top.pack(fill=tk.X, pady=(0, 6))
        self.csv_path = tk.StringVar()
        ttk.Entry(top, textvariable=self.csv_path, state="readonly",
                  style="Professional.TEntry").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(top, text="Examinar", style="Primary.TButton",
                   command=self._browse_csv).pack(side=tk.LEFT)

        self.company_table = CompanyTable(data, on_selection_change=self._on_selection_change)
        self.company_table.pack(fill=tk.BOTH, expand=True)

    # ------------------------------------------------------------------ #
    def _load_default_csv(self) -> None:
        ok, msg = self.csv_manager.load_default()
        if ok:
            self.csv_path.set(self.csv_manager.get_current_path())
            self.company_table.load_data(self.csv_manager.get_companies_data())
            self.log_viewer.log(f"CSV cargado: {self.csv_manager.get_company_count()} empresas")
        else:
            self.log_viewer.log(f"ADVERTENCIA: {msg}", "WARNING")

    def _browse_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Seleccionar CSV de empresas",
            filetypes=[("CSV", "*.csv"), ("Todos", "*.*")], initialdir="./data")
        if not path:
            return
        ok, msg = self.csv_manager.load_csv(path)
        if ok:
            self.csv_path.set(path)
            self.company_table.load_data(self.csv_manager.get_companies_data())
            self.log_viewer.log(f"CSV cargado desde {path}")
        else:
            messagebox.showerror("Error", msg)

    # ------------------------------------------------------------------ #
    def _build_config_dict(self) -> dict:
        freq = self.frequency.get()
        try:
            sy, ey = int(self.start_year.get()), int(self.end_year.get())
        except ValueError:
            return {}
        step = -1 if freq == "total" else int(self.step.get())
        return {
            "start_year": sy,
            "end_year": ey,
            "step": step,
            "quarterly": freq != "annual",
            "frequency": freq,
            "strategy": "browser",
            "skip_existing": self.settings.skip_existing,
        }

    def _selected_stages(self) -> list[Stage]:
        stages = []
        if self.do_download.get():
            stages.append(Stage.DOWNLOAD)
        if self.do_consolidate.get():
            stages.append(Stage.CONSOLIDATE)
        if self.do_upload.get():
            stages.append(Stage.UPLOAD)
        return stages

    def _on_selection_change(self) -> None:
        """Vista previa: al seleccionar, mostrar qué periodos ya hay en disco."""
        if self.is_running:
            return
        from .pipeline.models import CompanyState
        try:
            companies = self.company_table.get_selected_companies()
        except Exception:
            return
        if not companies:
            self.pipeline_view.load({})
            self.pipeline_view.set_summary("Selecciona empresas para comenzar")
            return
        states: dict = {}
        with_data = 0
        total_periods = 0
        for c in companies:
            rut = str(c.get("rut_sin_guion") or c.get("rut", "")).strip()
            st = CompanyState(rut=rut, rut_completo=str(c.get("rut", rut)).strip(),
                              name=str(c.get("razon_social", "")).strip())
            periods = self.orchestrator.periods_on_disk(rut, st.rut_completo)
            st.disk_periods = len(periods)
            if periods:
                with_data += 1
                total_periods += len(periods)
                st.detail = f"{len(periods)} periodos ya descargados"
            states[rut] = st
        self.pipeline_view.load(states)
        self.pipeline_view.set_summary(
            f"Seleccionadas: {len(companies)} | con datos en disco: {with_data} "
            f"({total_periods} periodos no se re-descargaran)")

    def _on_run(self) -> None:
        if self.is_running:
            return
        companies = self.company_table.get_selected_companies()
        if not companies:
            messagebox.showwarning("Atención", "Seleccione al menos una empresa")
            return
        stages = self._selected_stages()
        if not stages:
            messagebox.showwarning("Atención", "Seleccione al menos una etapa")
            return
        config = self._build_config_dict()
        if not config:
            messagebox.showerror("Error", "Configuración de años inválida")
            return
        if config["start_year"] <= config["end_year"]:
            messagebox.showerror("Error", "El año 'Desde' debe ser mayor que 'Hasta'")
            return

        # Validación previa de entorno para las etapas elegidas
        problems = self._preflight(stages)
        if problems:
            if not messagebox.askyesno(
                "Entorno incompleto",
                "Se detectaron problemas:\n\n• " + "\n• ".join(problems) +
                "\n\n¿Ejecutar de todas formas?"):
                return

        self.is_running = True
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self._total_companies = len(companies)
        self._done_companies = 0
        from time import time as _t
        self._run_started_at = _t()

        self.log_viewer.log("=" * 60)
        self.log_viewer.log(f"PIPELINE: {len(companies)} empresa(s) | etapas: "
                            f"{', '.join(s.label for s in stages)}")
        self.orchestrator.start(companies, config, stages)
        # Inicializar la tabla con los estados creados por el orquestador
        self.root.after(50, lambda: self.pipeline_view.load(self.orchestrator.states))

    def _preflight(self, stages: list[Stage]) -> list[str]:
        problems: list[str] = []
        checks = {c["name"]: c for c in self.settings.verify()}
        if Stage.CONSOLIDATE in stages:
            for key in ("Repo CMF_EXTRACT", "Import cmf.pipeline", "Directorio Arelle"):
                c = checks.get(key)
                if c and not c["ok"]:
                    problems.append(f"{key}: {c['detail']}")
        if Stage.UPLOAD in stages:
            c = checks.get("Credenciales FinDataChile")
            if c and not c["ok"]:
                problems.append(f"FinDataChile: {c['detail']}")
        return problems

    def _on_stop(self) -> None:
        if not self.is_running:
            return
        self.log_viewer.log("Deteniendo pipeline…", "WARNING")
        self.stop_btn.config(state="disabled")
        self.orchestrator.stop()

    # ------------------------------------------------------------------ #
    def _poll_events(self) -> None:
        try:
            while True:
                evt = self.events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass
        self.root.after(120, self._poll_events)

    def _handle_event(self, evt: PipelineEvent) -> None:
        if evt.kind == "log":
            self.log_viewer.log(evt.message, evt.level)
            return
        if evt.kind == "started":
            self.pipeline_view.set_summary(evt.message)
            return
        if evt.kind == "progress":
            if evt.rut and evt.rut in self.orchestrator.states:
                self.pipeline_view.update_company(self.orchestrator.states[evt.rut])
            return
        if evt.kind == "stage":
            if evt.rut and evt.rut in self.orchestrator.states:
                st = self.orchestrator.states[evt.rut]
                self.pipeline_view.update_company(st)
                self._log_stage(st, evt)
            return
        if evt.kind == "company_done":
            self._done_companies += 1
            if evt.rut and evt.rut in self.orchestrator.states:
                self.pipeline_view.update_company(self.orchestrator.states[evt.rut])
            frac = self._done_companies / max(1, self._total_companies)
            self.pipeline_view.set_global_progress(frac)
            self.pipeline_view.set_summary(
                f"Completadas {self._done_companies}/{self._total_companies}")
            return
        if evt.kind == "finished":
            self._finish(evt)
            return

    def _log_stage(self, st, evt: PipelineEvent) -> None:
        """Narrar transiciones de etapa por empresa en el registro, sin emojis."""
        if evt.status is None or evt.stage is None:
            return
        name = st.name or st.rut_completo
        etapa = evt.stage.label
        detail = (evt.message or st.detail or "").strip()
        if evt.status == StageStatus.RUNNING:
            self.log_viewer.log(f"{name}: {etapa} en curso" + (f" - {detail}" if detail else ""), "DETAIL")
        elif evt.status == StageStatus.DONE:
            self.log_viewer.log(f"{name}: {etapa} completado" + (f" ({detail})" if detail else ""), "SUCCESS")
        elif evt.status == StageStatus.SKIPPED:
            self.log_viewer.log(f"{name}: {etapa} omitido" + (f" - {detail}" if detail else ""), "INFO")
        elif evt.status == StageStatus.ERROR:
            self.log_viewer.log(f"{name}: {etapa} con error - {st.error or detail}", "ERROR")

    def _finish(self, evt: PipelineEvent) -> None:
        self.is_running = False
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        p = evt.payload
        self.pipeline_view.set_global_progress(1.0)
        summary = (f"{evt.message} — OK: {p.get('ok', 0)} | "
                   f"Errores: {p.get('errors', 0)} | Subidas: {p.get('uploaded', 0)}")
        self.pipeline_view.set_summary(summary)
        self.log_viewer.log("=" * 60)
        self.log_viewer.log(summary, "SUCCESS" if not p.get("errors") else "WARNING")
        self.log_viewer.log(f"Tiempo total: {int(p.get('elapsed', 0))}s")
        if not p.get("cancelled"):
            messagebox.showinfo("Pipeline finalizado", summary)

    def _tick_timer(self) -> None:
        if self.is_running and self._run_started_at is not None:
            from time import time as _t
            elapsed = int(_t() - self._run_started_at)
            m, s = divmod(elapsed, 60)
            self.pipeline_view.set_timer(f"Tiempo: {m}:{s:02d}")
        self.root.after(1000, self._tick_timer)

    # ------------------------------------------------------------------ #
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.root, self.settings)
        new_settings = dlg.show()
        if new_settings is not None:
            self.settings = new_settings
            self.orchestrator.settings = new_settings
            self.do_upload.set(new_settings.fdc_enabled)
            self.log_viewer.log("Configuración guardada.", "SUCCESS")

    def _open_results(self) -> None:
        path = self.settings.product_v1_dir
        if open_folder(path):
            self.log_viewer.log(f"Abriendo {path}")
        else:
            messagebox.showinfo("Info", f"Carpeta no disponible aún:\n{path}")

    def _on_close(self) -> None:
        if self.is_running:
            if not messagebox.askyesno("Salir", "Hay un pipeline en ejecución. ¿Salir igual?"):
                return
            self.orchestrator.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    UnifiedPipelineGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
