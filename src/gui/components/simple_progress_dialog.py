#!/usr/bin/env python3
"""
Diálogo de progreso simple para descarga XBRL
"""

import tkinter as tk
from tkinter import ttk
import time


class SimpleProgressDialog:
    """Diálogo de progreso simple y confiable"""
    
    def __init__(self, parent, title="Progreso"):
        self.parent = parent
        self.title = title
        
        # Crear ventana
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("500x300")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centrar ventana
        self._center_window()
        
        # Variables
        self.status_text = tk.StringVar(value="Iniciando...")
        self.company_text = tk.StringVar(value="")
        self.progress_text = tk.StringVar(value="0/0")
        
        # Crear interfaz
        self._create_widgets()
        
        # Variables de control
        self.is_cancelled = False
        self.start_time = time.time()
        
    def _center_window(self):
        """Centrar ventana en la pantalla"""
        self.dialog.update_idletasks()
        x = (self.dialog.winfo_screenwidth() // 2) - (250)
        y = (self.dialog.winfo_screenheight() // 2) - (150)
        self.dialog.geometry(f"500x300+{x}+{y}")
    
    def _create_widgets(self):
        """Crear widgets del diálogo"""
        # Frame principal
        main_frame = tk.Frame(self.dialog, bg='#f8f9fa', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = tk.Label(main_frame, 
                              text="🚀 Descarga de Archivos XBRL",
                              font=('Segoe UI', 16, 'bold'),
                              bg='#f8f9fa', fg='#2c3e50')
        title_label.pack(pady=(0, 20))
        
        # Estado actual
        status_frame = tk.LabelFrame(main_frame, 
                                    text="Estado Actual",
                                    font=('Segoe UI', 10, 'bold'),
                                    bg='#f8f9fa', fg='#2c3e50',
                                    padx=15, pady=10)
        status_frame.pack(fill=tk.X, pady=(0, 15))
        
        status_label = tk.Label(status_frame, 
                               textvariable=self.status_text,
                               font=('Segoe UI', 11),
                               bg='#f8f9fa', fg='#3498db',
                               wraplength=400)
        status_label.pack()
        
        # Empresa actual
        company_frame = tk.LabelFrame(main_frame, 
                                     text="Empresa en Proceso",
                                     font=('Segoe UI', 10, 'bold'),
                                     bg='#f8f9fa', fg='#2c3e50',
                                     padx=15, pady=10)
        company_frame.pack(fill=tk.X, pady=(0, 15))
        
        company_label = tk.Label(company_frame, 
                                textvariable=self.company_text,
                                font=('Segoe UI', 11, 'bold'),
                                bg='#f8f9fa', fg='#27ae60',
                                wraplength=400)
        company_label.pack()
        
        # Progreso
        progress_frame = tk.LabelFrame(main_frame, 
                                      text="Progreso",
                                      font=('Segoe UI', 10, 'bold'),
                                      bg='#f8f9fa', fg='#2c3e50',
                                      padx=15, pady=10)
        progress_frame.pack(fill=tk.X, pady=(0, 15))
        
        progress_label = tk.Label(progress_frame, 
                                 textvariable=self.progress_text,
                                 font=('Segoe UI', 12, 'bold'),
                                 bg='#f8f9fa', fg='#e74c3c')
        progress_label.pack()
        
        # Botones
        button_frame = tk.Frame(main_frame, bg='#f8f9fa')
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.cancel_button = ttk.Button(button_frame, 
                                       text="❌ Cancelar",
                                       command=self._cancel_process)
        self.cancel_button.pack(side=tk.RIGHT)
        
        # Información
        info_text = (
            "💡 Los archivos XBRL se están descargando en segundo plano.\n"
            "Este proceso puede tomar varios minutos dependiendo del número de empresas."
        )
        
        info_label = tk.Label(main_frame, 
                             text=info_text,
                             font=('Segoe UI', 8),
                             bg='#f8f9fa', fg='#7f8c8d',
                             justify=tk.LEFT)
        info_label.pack(anchor=tk.W, pady=(15, 0))
    
    def update_status(self, status, company="", current=0, total=0):
        """Actualizar estado del diálogo"""
        try:
            self.status_text.set(status)
            if company:
                self.company_text.set(company)
            if total > 0:
                percentage = (current / total) * 100
                self.progress_text.set(f"{current}/{total} ({percentage:.1f}%)")
            
            # Forzar actualización
            self.dialog.update_idletasks()
        except:
            pass  # Si hay error, ignorar
    
    def _cancel_process(self):
        """Cancelar proceso"""
        self.is_cancelled = True
        self.status_text.set("Cancelando proceso...")
        self.cancel_button.config(state='disabled')
    
    def close(self):
        """Cerrar diálogo"""
        try:
            if hasattr(self, 'dialog') and self.dialog:
                self.dialog.destroy()
        except:
            pass
    
    def show(self):
        """Mostrar diálogo"""
        try:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
        except:
            pass
    
    def is_canceled(self):
        """Verificar si fue cancelado"""
        return self.is_cancelled
