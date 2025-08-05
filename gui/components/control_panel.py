#!/usr/bin/env python3
"""
Panel de control para el CMF Scraper
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable


class ControlPanel:
    """Panel de control para ejecutar el scraping"""
    
    def __init__(self, parent, 
                 on_start: Optional[Callable] = None,
                 on_stop: Optional[Callable] = None,
                 on_open_results: Optional[Callable] = None):
        self.parent = parent
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_open_results = on_open_results
        
        # Variables
        self.start_year_var = tk.StringVar(value="2024")
        self.end_year_var = tk.StringVar(value="2014")
        self.step_var = tk.StringVar(value="-2")
        self.progress_var = tk.StringVar(value="Listo para comenzar")
        
        # Widgets
        self.frame = None
        self.start_button = None
        self.stop_button = None
        self.progress_bar = None
        
        self._create_widgets()
    
    def _create_widgets(self):
        """Crear los widgets del panel de control"""
        # Frame principal
        self.frame = tk.Frame(self.parent, bg='#f8f9fa')
        
        # Sección de configuración
        config_frame = ttk.LabelFrame(self.frame, 
                                     text="Configuración de Extracción", 
                                     style='Card.TLabelframe',
                                     padding=15)
        config_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._create_config_section(config_frame)
        
        # Sección de control de ejecución
        control_frame = ttk.LabelFrame(self.frame, 
                                      text="Control de Ejecución", 
                                      style='Card.TLabelframe',
                                      padding=15)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        self._create_control_section(control_frame)
    
    def _create_config_section(self, parent):
        """Crear sección de configuración"""
        # Título de configuración
        tk.Label(parent, text="Rango de Años:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W, pady=(0, 10))
        
        # Grid para configuración de años
        years_grid = tk.Frame(parent, bg='#f8f9fa')
        years_grid.pack(fill=tk.X, pady=(0, 15))
        
        # Año inicial
        tk.Label(years_grid, text="Desde:", 
                font=('Segoe UI', 9), 
                bg='#f8f9fa', fg='#2c3e50').grid(row=0, column=0, sticky='w', padx=(0, 5))
        
        start_year_combo = ttk.Combobox(years_grid, 
                                       textvariable=self.start_year_var,
                                       values=[str(y) for y in range(2024, 2009, -1)],
                                       style='Professional.TCombobox',
                                       width=8, state='readonly')
        start_year_combo.grid(row=0, column=1, padx=(0, 15))
        
        # Año final
        tk.Label(years_grid, text="Hasta:", 
                font=('Segoe UI', 9), 
                bg='#f8f9fa', fg='#2c3e50').grid(row=0, column=2, sticky='w', padx=(0, 5))
        
        end_year_combo = ttk.Combobox(years_grid, 
                                     textvariable=self.end_year_var,
                                     values=[str(y) for y in range(2024, 2009, -1)],
                                     style='Professional.TCombobox',
                                     width=8, state='readonly')
        end_year_combo.grid(row=0, column=3, padx=(0, 15))
        
        # Incremento
        tk.Label(years_grid, text="Incremento:", 
                font=('Segoe UI', 9), 
                bg='#f8f9fa', fg='#2c3e50').grid(row=1, column=0, sticky='w', pady=(10, 0), padx=(0, 5))
        
        step_combo = ttk.Combobox(years_grid, 
                                 textvariable=self.step_var,
                                 values=["-1", "-2", "-3"],
                                 style='Professional.TCombobox',
                                 width=8, state='readonly')
        step_combo.grid(row=1, column=1, pady=(10, 0))
        
        # Información de configuración
        info_text = ("Configuración:\n"
                    "• Incremento -1: Todos los años\n"
                    "• Incremento -2: Cada 2 años\n"
                    "• Incremento -3: Cada 3 años")
        
        tk.Label(parent, text=info_text, 
                font=('Segoe UI', 8), 
                bg='#f8f9fa', fg='#7f8c8d',
                justify=tk.LEFT).pack(anchor=tk.W, pady=(10, 0))
    
    def _create_control_section(self, parent):
        """Crear sección de control de ejecución"""
        # Botones de control
        self.start_button = ttk.Button(parent, 
                                      text="Iniciar Extracción", 
                                      command=self._on_start_clicked,
                                      style='Success.TButton')
        self.start_button.pack(fill=tk.X, pady=(0, 5))
        
        self.stop_button = ttk.Button(parent, 
                                     text="Detener Proceso", 
                                     command=self._on_stop_clicked,
                                     style='Danger.TButton',
                                     state='disabled')
        self.stop_button.pack(fill=tk.X, pady=(0, 10))
        
        # Botón de resultados
        results_button = ttk.Button(parent, 
                                   text="Abrir Carpeta de Resultados", 
                                   command=self._on_open_results_clicked,
                                   style='Primary.TButton')
        results_button.pack(fill=tk.X)
        
        # Estado del proceso
        status_frame = tk.Frame(parent, bg='#f8f9fa')
        status_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Label(status_frame, text="Estado:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W)
        
        progress_label = ttk.Label(status_frame, 
                                  textvariable=self.progress_var, 
                                  style='Info.TLabel')
        progress_label.pack(anchor=tk.W, pady=(5, 10))
        
        # Barra de progreso
        self.progress_bar = ttk.Progressbar(status_frame, 
                                          mode='indeterminate',
                                          style='TProgressbar')
        self.progress_bar.pack(fill=tk.X)
    
    def _on_start_clicked(self):
        """Manejar clic en botón de inicio"""
        if self.on_start:
            config = self.get_config()
            self.on_start(config)
    
    def _on_stop_clicked(self):
        """Manejar clic en botón de detener"""
        if self.on_stop:
            self.on_stop()
    
    def _on_open_results_clicked(self):
        """Manejar clic en abrir resultados"""
        if self.on_open_results:
            self.on_open_results()
    
    def get_config(self) -> dict:
        """Obtener configuración actual"""
        try:
            return {
                'start_year': int(self.start_year_var.get()),
                'end_year': int(self.end_year_var.get()),
                'step': int(self.step_var.get())
            }
        except ValueError as e:
            messagebox.showerror("Error", f"Error en configuración: {e}")
            return None
    
    def set_running_state(self, is_running: bool):
        """Configurar estado de ejecución"""
        if is_running:
            self.start_button.config(state='disabled')
            self.stop_button.config(state='normal')
            self.progress_bar.start()
        else:
            self.start_button.config(state='normal')
            self.stop_button.config(state='disabled')
            self.progress_bar.stop()
    
    def update_progress(self, message: str):
        """Actualizar mensaje de progreso"""
        self.progress_var.set(message)
    
    def pack(self, **kwargs):
        """Empaquetar el componente"""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """Colocar el componente en grid"""
        self.frame.grid(**kwargs)
