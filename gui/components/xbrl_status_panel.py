#!/usr/bin/env python3
"""
Panel de estado para descargas XBRL: tabla estática que se actualiza
"""

import tkinter as tk
from tkinter import ttk


class XBRLStatusPanel:
    """Tabla de estado por empresa para descargas XBRL"""

    def __init__(self, parent, style: str = 'Card.TLabelframe'):
        self.parent = parent
        self.frame = ttk.LabelFrame(parent, text="Estado de Descarga XBRL", style=style, padding=10)

        # Treeview con columnas
        columns = ("empresa", "rut", "estado", "worker", "archivos")
        self.tree = ttk.Treeview(self.frame, columns=columns, show='headings', height=10)

        self.tree.heading("empresa", text="Empresa")
        self.tree.heading("rut", text="RUT")
        self.tree.heading("estado", text="Estado")
        self.tree.heading("worker", text="Worker")
        self.tree.heading("archivos", text="Archivos")

        self.tree.column("empresa", width=220, anchor='w')
        self.tree.column("rut", width=110, anchor='center')
        self.tree.column("estado", width=120, anchor='center')
        self.tree.column("worker", width=90, anchor='center')
        self.tree.column("archivos", width=90, anchor='center')

        # Scrollbar vertical
        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')

        # Expansión
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(0, weight=1)

        # Índice por RUT para actualizaciones rápidas
        self._rut_to_item = {}

    def pack(self, **kwargs):
        self.frame.pack(**kwargs)

    def grid(self, **kwargs):
        self.frame.grid(**kwargs)

    def clear(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._rut_to_item.clear()

    def load_companies(self, companies):
        """Inicializar filas con estado 'En cola'"""
        self.clear()
        for company in companies:
            empresa = company.get('razon_social', '')
            rut = company.get('rut_sin_guion') or company.get('rut') or ''
            item_id = self.tree.insert('', 'end', values=(empresa, rut, 'En cola', '-', '-'))
            self._rut_to_item[str(rut)] = item_id

    def update_status(self, rut: str, estado: str | None = None, worker: str | int | None = None,
                      archivos: int | None = None):
        """Actualizar columnas para un RUT existente"""
        key = str(rut)
        item_id = self._rut_to_item.get(key)
        if not item_id:
            return
        empresa, rut_val, estado_val, worker_val, archivos_val = self.tree.item(item_id, 'values')
        if estado is not None:
            estado_val = estado
        if worker is not None:
            worker_val = str(worker)
        if archivos is not None:
            archivos_val = str(archivos)
        self.tree.item(item_id, values=(empresa, rut_val, estado_val, worker_val, archivos_val))


