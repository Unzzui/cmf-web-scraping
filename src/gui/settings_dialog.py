#!/usr/bin/env python3
"""Diálogo de configuración del pipeline + verificación de entorno."""

from __future__ import annotations

import tkinter as tk
from dataclasses import asdict
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from .pipeline.settings import PipelineSettings


class SettingsDialog:
    def __init__(self, parent: tk.Misc, settings: PipelineSettings):
        self.parent = parent
        self.settings = settings
        self.result: Optional[PipelineSettings] = None
        self._vars: dict[str, tk.Variable] = {}

    # ------------------------------------------------------------------ #
    def show(self) -> Optional[PipelineSettings]:
        self.win = tk.Toplevel(self.parent)
        self.win.title("Configuración del Pipeline")
        self.win.transient(self.parent)
        self.win.grab_set()
        self.win.geometry("720x640")

        nb = ttk.Notebook(self.win)
        nb.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._build_paths_tab(nb)
        self._build_fdc_tab(nb)
        self._build_perf_tab(nb)
        self._build_verify_tab(nb)

        btns = tk.Frame(self.win)
        btns.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btns, text="Guardar", style="Success.TButton",
                   command=self._save).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(btns, text="Cancelar", command=self.win.destroy).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Verificar entorno",
                   command=self._run_verify).pack(side=tk.LEFT)

        self.parent.wait_window(self.win)
        return self.result

    # ------------------------------------------------------------------ #
    def _field(self, parent, label: str, key: str, browse: str = "") -> None:
        row = tk.Frame(parent)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text=label, width=22, anchor="w").pack(side=tk.LEFT)
        var = tk.StringVar(value=str(getattr(self.settings, key) or ""))
        self._vars[key] = var
        ttk.Entry(row, textvariable=var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        if browse:
            ttk.Button(row, text="…", width=3,
                       command=lambda: self._browse(var, browse)).pack(side=tk.LEFT)

    def _browse(self, var: tk.StringVar, kind: str) -> None:
        if kind == "dir":
            p = filedialog.askdirectory(initialdir=var.get() or ".")
        else:
            p = filedialog.askopenfilename(initialdir=".")
        if p:
            var.set(p)

    def _build_paths_tab(self, nb) -> None:
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Rutas / Entorno")
        self._field(tab, "Repo CMF_EXTRACT", "cmf_extract_repo", "dir")
        self._field(tab, "Python CMF_EXTRACT", "cmf_extract_python", "file")
        ttk.Button(tab, text="Auto-detectar interprete (importa cmf.pipeline)",
                   command=self._autodetect_python).pack(anchor="w", pady=(0, 6))
        self._field(tab, "Directorio Arelle", "arelle_dir", "dir")
        self._field(tab, "Carpeta XBRL base", "xbrl_base_dir", "dir")
        self._field(tab, "Carpeta Products", "products_dir", "dir")
        self._field(tab, "Carpeta Product_v1", "product_v1_dir", "dir")
        self._field(tab, "CSV de empresas", "companies_csv", "file")

    def _build_fdc_tab(self, nb) -> None:
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="FinDataChile")
        self._vars["fdc_enabled"] = tk.BooleanVar(value=self.settings.fdc_enabled)
        ttk.Checkbutton(tab, text="Subir automáticamente a FinDataChile",
                        variable=self._vars["fdc_enabled"]).pack(anchor="w", pady=(0, 8))
        self._field(tab, "URL base", "fdc_base_url")
        self._field(tab, "Usuario admin", "fdc_username")
        # Password con asteriscos
        row = tk.Frame(tab)
        row.pack(fill=tk.X, pady=4)
        tk.Label(row, text="Contraseña admin", width=22, anchor="w").pack(side=tk.LEFT)
        var = tk.StringVar(value=self.settings.fdc_password or "")
        self._vars["fdc_password"] = var
        ttk.Entry(row, textvariable=var, show="•").pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(tab, text="El Excel se sube con nombre normalizado para que\n"
                          "FinDataChile detecte empresa, RUT, sector y años.",
                 fg="#7f8c8d", justify=tk.LEFT).pack(anchor="w", pady=(10, 0))

    def _build_perf_tab(self, nb) -> None:
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Rendimiento")

        def intfield(label, key):
            row = tk.Frame(tab)
            row.pack(fill=tk.X, pady=4)
            tk.Label(row, text=label, width=28, anchor="w").pack(side=tk.LEFT)
            var = tk.IntVar(value=int(getattr(self.settings, key)))
            self._vars[key] = var
            tk.Spinbox(row, from_=0, to=64, textvariable=var, width=6).pack(side=tk.LEFT)

        intfield("Descargas en paralelo", "download_workers")
        intfield("Consolidaciones en paralelo", "consolidate_workers")
        intfield("Subidas en paralelo", "upload_workers")
        intfield("Workers Arelle (0 = auto)", "arelle_workers")

        self._vars["skip_existing"] = tk.BooleanVar(value=self.settings.skip_existing)
        ttk.Checkbutton(tab, text="Omitir lo ya descargado/consolidado (más rápido)",
                        variable=self._vars["skip_existing"]).pack(anchor="w", pady=(10, 2))
        self._vars["debug"] = tk.BooleanVar(value=self.settings.debug)
        ttk.Checkbutton(tab, text="Modo debug (logs detallados)",
                        variable=self._vars["debug"]).pack(anchor="w")

    def _build_verify_tab(self, nb) -> None:
        tab = ttk.Frame(nb, padding=12)
        nb.add(tab, text="Verificación")
        ttk.Button(tab, text="Verificar entorno ahora",
                   command=self._run_verify).pack(anchor="w", pady=(0, 8))
        self.verify_box = tk.Text(tab, height=18, wrap="word", font=("Consolas", 9))
        self.verify_box.pack(fill=tk.BOTH, expand=True)
        self.verify_box.insert("1.0", "Pulsa 'Verificar entorno' para comprobar rutas,\n"
                                       "interprete, Arelle y conexion a FinDataChile.")
        self.verify_box.config(state="disabled")

    # ------------------------------------------------------------------ #
    def _collect(self) -> PipelineSettings:
        data = asdict(self.settings)
        for key, var in self._vars.items():
            data[key] = var.get()
        # langs y scraping_repo se mantienen
        return PipelineSettings(**data)

    def _autodetect_python(self) -> None:
        from .pipeline.settings import probe_cmf_extract_python
        repo = self._vars["cmf_extract_repo"].get()
        interp, detail = probe_cmf_extract_python(repo)
        if interp:
            self._vars["cmf_extract_python"].set(interp)
            messagebox.showinfo("Auto-detectar", f"Intérprete encontrado:\n{interp}")
        else:
            messagebox.showwarning("Auto-detectar", detail)

    def _run_verify(self) -> None:
        settings = self._collect()
        self.verify_box.config(state="normal")
        self.verify_box.delete("1.0", tk.END)
        self.verify_box.insert(tk.END, "Verificando…\n\n")
        self.verify_box.update_idletasks()
        lines = []
        for c in settings.verify():
            mark = "[ OK ]" if c["ok"] else "[FALLA]"
            lines.append(f"{mark}  {c['name']}\n        {c['detail']}")
        self.verify_box.delete("1.0", tk.END)
        self.verify_box.insert(tk.END, "\n".join(lines))
        self.verify_box.config(state="disabled")

    def _save(self) -> None:
        settings = self._collect()
        try:
            settings.save()
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo guardar: {e}")
            return
        self.result = settings
        self.win.destroy()
