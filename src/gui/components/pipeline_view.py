#!/usr/bin/env python3
"""Vista de pipeline: estado vivo por empresa a través de las etapas.

Tabla con una fila por empresa y una columna por etapa (Descargar / Consolidar
/ Subir), con semáforos de color, progreso y ETA de la etapa en curso, más una
cabecera de contadores globales. Nada se pierde: el log completo vive aparte.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from ..pipeline.models import Stage, StageStatus, CompanyState, STAGE_ORDER

# Colores de fondo por estado global de la fila
_ROW_COLORS = {
    "pending": "#ffffff",
    "running": "#eaf4fb",   # azul muy claro
    "done": "#e9f7ef",      # verde muy claro
    "error": "#fdecea",     # rojo muy claro
    "skipped": "#f4f6f7",   # gris
}


def _fmt_eta(seconds) -> str:
    if seconds is None or seconds <= 0:
        return ""
    seconds = int(seconds)
    m, s = divmod(seconds, 60)
    if m >= 60:
        h, m = divmod(m, 60)
        return f"{h}h{m:02d}m"
    return f"{m}:{s:02d}"


class PipelineView(ttk.LabelFrame):
    """Componente Tkinter que muestra el avance del pipeline."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, text="Progreso del Pipeline", padding=10, **kwargs)
        self._row_by_rut: dict[str, str] = {}   # rut -> iid del Treeview
        self._build()

    # ------------------------------------------------------------------ #
    def _build(self) -> None:
        # Cabecera de contadores globales
        header = tk.Frame(self, bg="#f8f9fa")
        header.pack(fill=tk.X, pady=(0, 8))

        self.var_summary = tk.StringVar(value="Listo para ejecutar")
        tk.Label(header, textvariable=self.var_summary, font=("Segoe UI", 11, "bold"),
                 bg="#f8f9fa", fg="#2c3e50").pack(side=tk.LEFT)

        self.var_timer = tk.StringVar(value="")
        tk.Label(header, textvariable=self.var_timer, font=("Segoe UI", 10),
                 bg="#f8f9fa", fg="#7f8c8d").pack(side=tk.RIGHT)

        # Barra de progreso global
        self.global_bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.global_bar.pack(fill=tk.X, pady=(0, 8))

        # Tabla
        cols = ("rut", "disk", "download", "consolidate", "upload", "progress", "eta", "detail")
        container = tk.Frame(self)
        container.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(container, columns=cols, show="tree headings",
                                 style="Professional.Treeview", height=12)
        self.tree.heading("#0", text="Empresa")
        self.tree.heading("rut", text="RUT")
        self.tree.heading("disk", text="En disco")
        self.tree.heading("download", text="Descargar")
        self.tree.heading("consolidate", text="Consolidar")
        self.tree.heading("upload", text="Subir")
        self.tree.heading("progress", text="Progreso")
        self.tree.heading("eta", text="ETA")
        self.tree.heading("detail", text="Detalle")

        self.tree.column("#0", width=210, anchor=tk.W, stretch=True)
        self.tree.column("rut", width=95, anchor=tk.W)
        self.tree.column("disk", width=70, anchor=tk.CENTER)
        self.tree.column("download", width=90, anchor=tk.W)
        self.tree.column("consolidate", width=95, anchor=tk.W)
        self.tree.column("upload", width=80, anchor=tk.W)
        self.tree.column("progress", width=70, anchor=tk.CENTER)
        self.tree.column("eta", width=55, anchor=tk.CENTER)
        self.tree.column("detail", width=240, anchor=tk.W, stretch=True)

        vsb = ttk.Scrollbar(container, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        for key, color in _ROW_COLORS.items():
            self.tree.tag_configure(key, background=color)

    # ------------------------------------------------------------------ #
    def _row_state_key(self, st: CompanyState) -> str:
        if st.has_error:
            return "error"
        vals = list(st.stages.values())
        if any(v == StageStatus.RUNNING for v in vals):
            return "running"
        if all(v in (StageStatus.DONE, StageStatus.SKIPPED) for v in vals):
            # ¿al menos una hecha de verdad?
            if any(v == StageStatus.DONE for v in vals):
                return "done"
            return "skipped"
        return "pending"

    def _row_values(self, st: CompanyState) -> tuple:
        prog = f"{int(st.progress * 100)}%" if st.progress else (st.progress_text or "")
        return (
            st.rut_completo,
            str(st.disk_periods) if st.disk_periods else "-",
            st.stages.get(Stage.DOWNLOAD, StageStatus.PENDING).badge,
            st.stages.get(Stage.CONSOLIDATE, StageStatus.PENDING).badge,
            st.stages.get(Stage.UPLOAD, StageStatus.PENDING).badge,
            prog,
            _fmt_eta(st.eta_seconds),
            (st.error or st.detail or "")[:80],
        )

    # ------------------------------------------------------------------ #
    def load(self, states: dict[str, CompanyState]) -> None:
        """Inicializar la tabla con las empresas seleccionadas."""
        self.tree.delete(*self.tree.get_children())
        self._row_by_rut.clear()
        for rut, st in states.items():
            iid = self.tree.insert("", tk.END, text=st.name or rut,
                                   values=self._row_values(st), tags=(self._row_state_key(st),))
            self._row_by_rut[rut] = iid
        self.global_bar["value"] = 0

    def update_company(self, st: CompanyState) -> None:
        iid = self._row_by_rut.get(st.rut)
        if not iid:
            return
        self.tree.item(iid, values=self._row_values(st), tags=(self._row_state_key(st),))

    def set_summary(self, text: str) -> None:
        self.var_summary.set(text)

    def set_timer(self, text: str) -> None:
        self.var_timer.set(text)

    def set_global_progress(self, fraction: float) -> None:
        self.global_bar["value"] = max(0, min(100, fraction * 100))
