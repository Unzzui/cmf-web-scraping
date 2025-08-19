#!/usr/bin/env python3
"""
Componente de log para el CMF Scraper
"""

import tkinter as tk
from tkinter import ttk, scrolledtext
from datetime import datetime
from typing import Optional


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
    
    def log(self, message: str, level: str = "INFO"):
        """Agregar mensaje al log con timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Formatear mensaje según nivel
        if level == "ERROR":
            prefix = "ERROR"
        elif level == "WARNING":
            prefix = "WARN"
        elif level == "SUCCESS":
            prefix = "OK"
        else:
            prefix = "INFO"
        
        formatted_message = f"[{timestamp}] [{prefix}] {message}"
        
        # Insertar al final del log
        self.log_text.insert(tk.END, formatted_message + "\n")
        
        # Auto-scroll al final
        self.log_text.see(tk.END)
        
        # Limitar número de líneas para rendimiento
        self._limit_log_lines()
        
        # Forzar actualización de la GUI
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
        self.log_text.delete(1.0, tk.END)
        self.log("Log limpiado")
    
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
                initialname=default_filename
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
