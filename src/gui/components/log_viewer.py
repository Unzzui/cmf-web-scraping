#!/usr/bin/env python3
"""
Componente de log para el CMF Scraper
"""

import re
import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from typing import Optional

# Secuencias de escape ANSI (colores/cursor) que emiten librerías como Rich.
_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
# Caracteres de control restantes (salvo tab) y avances de línea sueltos.
_CTRL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

# Color por nivel para la consola de la GUI.
_LEVEL_COLOR = {
    "INFO": "#2c3e50",
    "SUCCESS": "#1e8449",
    "WARNING": "#b9770e",
    "ERROR": "#c0392b",
    "DETAIL": "#7f8c8d",
}
_LEVEL_TAG = {
    "INFO": "INFO",
    "SUCCESS": "OK",
    "WARNING": "WARN",
    "ERROR": "ERROR",
    "DETAIL": "",
}


class LogViewer:
    """Componente para mostrar logs de la aplicación"""
    
    def __init__(self, parent, height: int = 15):
        self.parent = parent
        self.height = height
        
        # Widgets
        self.frame = None
        self.log_text = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Crear los widgets del log"""
        # Frame principal
        self.frame = ttk.LabelFrame(self.parent, 
                                   text="Registro de Actividad", 
                                   style='Card.TLabelframe',
                                   padding=15)
        
        # Crear log con estilo profesional
        log_container = tk.Frame(self.frame, bg='#ffffff', relief=tk.SOLID, bd=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(
            log_container, 
            height=self.height, 
            font=('Consolas', 9),
            bg='#ffffff',
            fg='#2c3e50',
            insertbackground='#2c3e50',
            selectbackground='#3498db',
            selectforeground='#ffffff',
            wrap=tk.WORD,
            relief=tk.FLAT,
            bd=0
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Tags de color por nivel (consola legible, sin emojis)
        self.log_text.tag_configure("meta", foreground="#95a5a6", font=("Consolas", 9))
        for level, color in _LEVEL_COLOR.items():
            weight = "bold" if level in ("ERROR", "WARNING") else "normal"
            self.log_text.tag_configure(level, foreground=color,
                                        font=("Consolas", 9, weight))
        self.log_text.configure(state=tk.DISABLED)

        # Barra de herramientas del log
        toolbar = tk.Frame(self.frame, bg='#f8f9fa', height=30)
        toolbar.pack(fill=tk.X, pady=(10, 0))
        toolbar.pack_propagate(False)
        
        # Botones de acción
        ttk.Button(toolbar, text="Limpiar Log", 
                  command=self.clear_log,
                  style='Primary.TButton').pack(side=tk.RIGHT, padx=(5, 0))
        
        ttk.Button(toolbar, text="Guardar Log", 
                  command=self.save_log,
                  style='Primary.TButton').pack(side=tk.RIGHT)
    
    @staticmethod
    def _clean(message: str) -> str:
        """Quitar secuencias ANSI y caracteres de control (ruido de Rich, etc.)."""
        text = _ANSI_RE.sub("", str(message))
        text = _CTRL_RE.sub("", text)
        return text.rstrip()

    def log(self, message: str, level: str = "INFO"):
        """Agregar mensaje al log con timestamp, color por nivel y sin emojis."""
        message = self._clean(message)
        if not message:
            return
        level = level if level in _LEVEL_COLOR else "INFO"
        timestamp = datetime.now().strftime("%H:%M:%S")
        tag = _LEVEL_TAG.get(level, "")

        self.log_text.configure(state=tk.NORMAL)
        # Columna de metadatos alineada: hora + nivel
        meta = f"{timestamp}  {tag:<5} " if tag else f"{timestamp}        "
        self.log_text.insert(tk.END, meta, "meta")
        self.log_text.insert(tk.END, message + "\n", level)

        self.log_text.see(tk.END)
        self._limit_log_lines()
        self.log_text.configure(state=tk.DISABLED)
        self.parent.update_idletasks()
    
    def _limit_log_lines(self, max_lines: int = 1000):
        """Limitar número de líneas en el log"""
        lines = self.log_text.get(1.0, tk.END).count('\n')
        if lines > max_lines:
            # Eliminar las primeras 200 líneas
            content = self.log_text.get(1.0, tk.END)
            lines_list = content.split('\n')
            new_content = '\n'.join(lines_list[200:])
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(1.0, new_content)
    
    def clear_log(self):
        """Limpiar el log"""
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        self.log_text.configure(state=tk.DISABLED)
        self.log("Registro limpiado")
    
    def save_log(self):
        """Guardar log a archivo"""
        from tkinter import filedialog, messagebox
        
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_filename = f"cmf_scraper_log_{timestamp}.txt"
            
            file_path = filedialog.asksaveasfilename(
                title="Guardar log",
                defaultextension=".txt",
                filetypes=[("Archivos de texto", "*.txt"), ("Todos los archivos", "*.*")],
                initialfile=default_filename
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.log_text.get(1.0, tk.END))
                
                messagebox.showinfo("Log guardado", f"Log guardado exitosamente en:\n{file_path}")
                self.log(f"Log guardado en: {file_path}")
            
        except Exception as e:
            error_msg = f"Error guardando log: {str(e)}"
            messagebox.showerror("Error", error_msg)
            self.log(error_msg, "ERROR")
    
    def get_content(self) -> str:
        """Obtener contenido completo del log"""
        return self.log_text.get(1.0, tk.END)
    
    def pack(self, **kwargs):
        """Empaquetar el componente"""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """Colocar el componente en grid"""
        self.frame.grid(**kwargs)
