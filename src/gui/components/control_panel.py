#!/usr/bin/env python3
"""
Panel de control para el CMF Scraper
"""

import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable
from datetime import datetime


class ControlPanel:
    """Panel de control para ejecutar el scraping"""
    
    def __init__(self, parent, 
                 on_start: Optional[Callable] = None,
                 on_stop: Optional[Callable] = None,
                 on_open_results: Optional[Callable] = None,
                 on_start_xbrl: Optional[Callable] = None):  # Nueva función para XBRL
        self.parent = parent
        self.on_start = on_start
        self.on_stop = on_stop
        self.on_open_results = on_open_results
        self.on_start_xbrl = on_start_xbrl  # Nueva callback para XBRL
        
        # Variables
        self.start_year_var = tk.StringVar(value=str(datetime.now().year))  # Año actual por defecto
        self.end_year_var = tk.StringVar(value="2014")
        self.step_var = tk.StringVar(value="-2")
        # Nueva variable de frecuencia con tres estados: 'annual' | 'quarterly' | 'total'
        self.frequency_var = tk.StringVar(value='annual')
        self.progress_var = tk.StringVar(value="Listo para comenzar")
        self.max_workers_var = tk.IntVar(value=8)  # Workers por defecto más altos para mayor throughput
        self.skip_existing_var = tk.BooleanVar(value=True)  # Omitir períodos existentes por defecto
            
        # Widgets
        self.frame = None
        self.start_button = None
        self.stop_button = None
        self.progress_bar = None
        self.step_combo = None
        
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

        # Grid para configuración de años y workers
        years_grid = tk.Frame(parent, bg='#f8f9fa')
        years_grid.pack(fill=tk.X, pady=(0, 15))

        current_year = datetime.now().year
        year_range = list(range(current_year, 2009, -1))
        year_values = [str(y) for y in year_range]

        # Año inicial
        tk.Label(years_grid, text="Desde:", font=('Segoe UI', 9), bg='#f8f9fa', fg='#2c3e50')\
            .grid(row=0, column=0, sticky='w', padx=(0, 5))
        start_year_combo = ttk.Combobox(years_grid, textvariable=self.start_year_var,
                                        values=year_values, style='Professional.TCombobox',
                                        width=8, state='readonly')
        start_year_combo.grid(row=0, column=1, padx=(0, 15))

        # Año final
        tk.Label(years_grid, text="Hasta:", font=('Segoe UI', 9), bg='#f8f9fa', fg='#2c3e50')\
            .grid(row=0, column=2, sticky='w', padx=(0, 5))
        end_year_combo = ttk.Combobox(years_grid, textvariable=self.end_year_var,
                                    values=year_values, style='Professional.TCombobox',
                                    width=8, state='readonly')
        end_year_combo.grid(row=0, column=3, padx=(0, 15))

        # Incremento
        tk.Label(years_grid, text="Incremento:", font=('Segoe UI', 9), bg='#f8f9fa', fg='#2c3e50')\
            .grid(row=1, column=0, sticky='w', pady=(10, 0), padx=(0, 5))
        self.step_combo = ttk.Combobox(years_grid, textvariable=self.step_var,
                                       values=["-1", "-2", "-3"], style='Professional.TCombobox',
                                       width=8, state='readonly')
        self.step_combo.grid(row=1, column=1, pady=(10, 0))

        # Workers
        tk.Label(years_grid, text="Workers:", font=('Segoe UI', 9), bg='#f8f9fa', fg='#2c3e50')\
            .grid(row=1, column=2, sticky='w', padx=(0, 5))
        workers_spin = tk.Spinbox(years_grid, from_=1, to=16, textvariable=self.max_workers_var, width=5)
        workers_spin.grid(row=1, column=3, pady=(10, 0), padx=(0, 15))

        # Separador
        ttk.Separator(parent, orient='horizontal').pack(fill=tk.X, pady=(15, 10))

        # Frecuencia
        tk.Label(parent, text="Frecuencia de Datos:",
                font=('Segoe UI', 10, 'bold'),
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W, pady=(0, 10))

        freq_frame = tk.Frame(parent, bg='#f8f9fa')
        freq_frame.pack(fill=tk.X, pady=(0, 15))

        self.annual_radio = ttk.Radiobutton(freq_frame, text="Anual (solo diciembre)",
                                            variable=self.frequency_var, value='annual',
                                            style='Professional.TRadiobutton',
                                            command=self._on_frequency_change)
        self.annual_radio.pack(anchor=tk.W, pady=(0, 5))

        self.quarterly_radio = ttk.Radiobutton(freq_frame,
                                            text="Trimestral (marzo, junio, septiembre, diciembre)",
                                            variable=self.frequency_var, value='quarterly',
                                            style='Professional.TRadiobutton',
                                            command=self._on_frequency_change)
        self.quarterly_radio.pack(anchor=tk.W)

        # Opción Total: descarga ambos (anual + trimestral) con paso automático -1
        self.total_radio = ttk.Radiobutton(freq_frame,
                                           text="Total (3,6,9,12 con paso automático -1)",
                                           variable=self.frequency_var, value='total',
                                           style='Professional.TRadiobutton',
                                           command=self._on_frequency_change)
        self.total_radio.pack(anchor=tk.W, pady=(5, 0))

        # Estrategia de descarga
        strat_frame = tk.Frame(parent, bg='#f8f9fa')
        strat_frame.pack(fill=tk.X, pady=(10, 10))
        tk.Label(strat_frame, text="Estrategia XBRL:", font=('Segoe UI', 10, 'bold'), bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W)
        self.strategy_var = tk.StringVar(value='browser')
        ttk.Radiobutton(strat_frame, text="Browser (recomendado)", variable=self.strategy_var, value='browser', style='Professional.TRadiobutton').pack(anchor=tk.W)
        ttk.Radiobutton(strat_frame, text="Direct (experimental)", variable=self.strategy_var, value='direct', style='Professional.TRadiobutton').pack(anchor=tk.W)

        # Opción: Omitir períodos ya existentes
        skip_frame = tk.Frame(parent, bg='#f8f9fa')
        skip_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Checkbutton(skip_frame, text="Omitir períodos ya existentes en disco (recomendado)", variable=self.skip_existing_var).pack(anchor=tk.W)

        # Info frecuencia
        freq_info_text = (f"Información:\n"
                        f"• Anual: Solo estado financiero de fin de año (diciembre)\n"
                        f"• Trimestral: Estados financieros de cada trimestre (3, 6, 9, 12)\n"
                        f"• Total: Igual que Trimestral pero fuerza paso -1 para cubrir todos los años\n"
                        f"• Año {current_year}: Puede tener datos parciales según la fecha\n"
                        f"• El sistema buscará automáticamente períodos disponibles")
        tk.Label(parent, text=freq_info_text, font=('Segoe UI', 8),
                bg='#f8f9fa', fg='#7f8c8d', justify=tk.LEFT)\
            .pack(anchor=tk.W, pady=(10, 0))

        # Info configuración
        info_text = (f"Configuración:\n"
                    f"• Año actual disponible: {current_year}\n"
                    f"• Incremento -1: Todos los años\n"
                    f"• Incremento -2: Cada 2 años\n"
                    f"• Incremento -3: Cada 3 años\n"
                    f"• El sistema detecta automáticamente períodos disponibles")
        tk.Label(parent, text=info_text, font=('Segoe UI', 8),
                bg='#f8f9fa', fg='#7f8c8d', justify=tk.LEFT)\
            .pack(anchor=tk.W, pady=(10, 0))

    
    def _create_control_section(self, parent):
        """Crear sección de control de ejecución"""
        # Botones de control principales
        self.start_button = ttk.Button(parent, 
                                      text="📊 Iniciar Extracción (Tablas HTML)", 
                                      command=self._on_start_clicked,
                                      style='Success.TButton')
        self.start_button.pack(fill=tk.X, pady=(0, 5))
        
        # Nuevo botón para XBRL
        self.start_xbrl_button = ttk.Button(parent, 
                                           text="📁 Descargar Archivos XBRL", 
                                           command=self._on_start_xbrl_clicked,
                                           style='Primary.TButton')
        self.start_xbrl_button.pack(fill=tk.X, pady=(0, 5))
        
        self.stop_button = ttk.Button(parent, 
                                     text="🛑 Detener Proceso", 
                                     command=self._on_stop_clicked,
                                     style='Danger.TButton',
                                     state='disabled')
        self.stop_button.pack(fill=tk.X, pady=(0, 10))
        
        # Separador
        separator = ttk.Separator(parent, orient='horizontal')
        separator.pack(fill=tk.X, pady=(5, 10))
        
        # Información sobre tipos de extracción
        info_frame = tk.Frame(parent, bg='#f8f9fa')
        info_frame.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(info_frame, text="Tipos de Extracción:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W)
        
        info_text = (
            "📊 Tablas HTML: Extrae datos y genera Excel con análisis\n"
            "📁 Archivos XBRL: Descarga archivos originales de la CMF\n\n"
            "💡 Los archivos XBRL contienen múltiples períodos por archivo\n"
            "   y se extraen automáticamente después de la descarga"
        )
        
        tk.Label(info_frame, text=info_text, 
                font=('Segoe UI', 8), 
                bg='#f8f9fa', fg='#7f8c8d',
                justify=tk.LEFT).pack(anchor=tk.W, pady=(5, 0))
        
        # Botón de resultados
        results_button = ttk.Button(parent, 
                                   text="📂 Abrir Carpeta de Resultados", 
                                   command=self._on_open_results_clicked,
                                   style='Secondary.TButton')
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
        """Manejar clic en botón de inicio (Tablas HTML)"""
        if self.on_start:
            config = self.get_config()
            self.on_start(config)
    
    def _on_start_xbrl_clicked(self):
        """Manejar clic en botón de inicio XBRL"""
        if self.on_start_xbrl:
            config = self.get_config()
            self.on_start_xbrl(config)
    
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
            frequency = self.frequency_var.get()
            # Forzar paso -1 cuando se selecciona Total
            step_value = int(self.step_var.get())
            if frequency == 'total':
                step_value = -1
            return {
                'start_year': int(self.start_year_var.get()),
                'end_year': int(self.end_year_var.get()),
                'step': step_value,
                # Compatibilidad: tratar 'total' como trimestral en flujos existentes
                'quarterly': (frequency != 'annual'),
                'frequency': frequency,
                'max_workers': int(self.max_workers_var.get()),
                'strategy': self.strategy_var.get(),
                'skip_existing': bool(self.skip_existing_var.get()),
            }
        except ValueError as e:
            messagebox.showerror("Error", f"Error en configuración: {e}")
            return None

    def _on_frequency_change(self):
        """Ajustar UI y step cuando cambia la frecuencia"""
        freq = self.frequency_var.get()
        if freq == 'total':
            self.step_var.set("-1")
            try:
                if self.step_combo is not None:
                    self.step_combo.config(state='disabled')
            except Exception:
                pass
        else:
            try:
                if self.step_combo is not None:
                    self.step_combo.config(state='readonly')
            except Exception:
                pass
    
    def set_running_state(self, is_running: bool):
        """Configurar estado de ejecución"""
        if is_running:
            self.start_button.config(state='disabled')
            self.start_xbrl_button.config(state='disabled')  # También deshabilitar XBRL
            self.stop_button.config(state='normal')
            self.progress_bar.start()
        else:
            self.start_button.config(state='normal')
            self.start_xbrl_button.config(state='normal')  # Rehabilitar XBRL
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
