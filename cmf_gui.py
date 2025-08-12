#!/usr/bin/env python3
"""    def __init__(self, root):
        self.root = root
        self.root.title("CMF Annual Reports Scraper - Professional Edition")
        self.root.geometry("1400x900")
        self.root.configure(bg='#f8f9fa')
        
        # Variables
        self.companies_df = None
        self.selected_companies = []
        self.is_running = False
        self.output_queue = queue.Queue()
        
        # Configurar captura de logs del scraper
        self.setup_scraper_logging()
        
        # Configurar el estilo
        self.setup_styles() Data Scraper - Professional GUI
Interfaz profesional para extraer datos financieros de la CMF
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import threading
import queue
import sys
import os
from datetime import datetime
import subprocess

# Importar nuestro scraper
try:
    from cmf_annual_reports_scraper import scrape_cmf_data, verify_data_order
except ImportError as e:
    print(f"Error importando el scraper: {e}")
    print("Asegúrate de que cmf_annual_reports_scraper.py esté en el mismo directorio")
    sys.exit(1)


class CMFScraperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("CMF Financial Data Scraper - Professional Edition")
        self.root.geometry("1400x900")
        self.root.configure(bg='#f8f9fa')
        
        # Variables
        self.companies_df = None
        self.selected_companies = []
        self.is_running = False
        self.output_queue = queue.Queue()
        
        # Configurar el estilo
        self.setup_styles()
        
        # Crear la interfaz
        self.create_widgets()
        
        # Cargar datos por defecto
        self.load_default_csv()
        
        # Configurar el monitoreo de la cola de output
        self.root.after(100, self.check_output_queue)
    
    def setup_scraper_logging(self):
        """Configurar captura de logs del scraper para mostrar en la GUI"""
        
        class GUILogHandler(logging.Handler):
            """Handler personalizado para capturar logs del scraper"""
            def __init__(self, output_queue):
                super().__init__()
                self.output_queue = output_queue
            
            def emit(self, record):
                log_entry = self.format(record)
                # Enviar a la cola con tipo 'scraper_log'
                self.output_queue.put(('scraper_log', log_entry))
        
        # Crear y configurar el handler
        self.gui_log_handler = GUILogHandler(self.output_queue)
        self.gui_log_handler.setLevel(logging.INFO)
        
        # Formato sin timestamp ya que el log viewer lo agregará
        formatter = logging.Formatter('%(message)s')
        self.gui_log_handler.setFormatter(formatter)
        
        # Agregar nuestro handler al logger raíz para capturar todos los logs
        import logging
        root_logger = logging.getLogger()
        root_logger.addHandler(self.gui_log_handler)
    
    def setup_styles(self):
        """Configurar estilos profesionales"""
        style = ttk.Style()
        style.theme_use('clam')
        
        # Colores profesionales
        primary_color = '#2c3e50'      # Azul oscuro
        secondary_color = '#34495e'     # Gris azulado
        accent_color = '#3498db'        # Azul claro
        success_color = '#27ae60'       # Verde
        warning_color = '#f39c12'       # Naranja
        danger_color = '#e74c3c'        # Rojo
        light_bg = '#ecf0f1'           # Gris muy claro
        white = '#ffffff'
        
        # Configurar estilos de etiquetas
        style.configure('Title.TLabel', 
                       font=('Segoe UI', 20, 'bold'), 
                       foreground=primary_color,
                       background='#f8f9fa')
        
        style.configure('Subtitle.TLabel', 
                       font=('Segoe UI', 14, 'bold'), 
                       foreground=secondary_color,
                       background='#f8f9fa')
        
        style.configure('Info.TLabel', 
                       font=('Segoe UI', 10), 
                       foreground='#7f8c8d',
                       background='#f8f9fa')
        
        style.configure('Success.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=success_color,
                       background='#f8f9fa')
        
        style.configure('Warning.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=warning_color,
                       background='#f8f9fa')
        
        style.configure('Error.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=danger_color,
                       background='#f8f9fa')
        
        # Configurar estilos de botones
        style.configure('Primary.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=white)
        style.map('Primary.TButton',
                 background=[('active', '#2980b9'), ('!active', accent_color)],
                 foreground=[('active', white), ('!active', white)])
        
        style.configure('Success.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=white)
        style.map('Success.TButton',
                 background=[('active', '#229954'), ('!active', success_color)],
                 foreground=[('active', white), ('!active', white)])
        
        style.configure('Warning.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=white)
        style.map('Warning.TButton',
                 background=[('active', '#d68910'), ('!active', warning_color)],
                 foreground=[('active', white), ('!active', white)])
        
        style.configure('Danger.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=white)
        style.map('Danger.TButton',
                 background=[('active', '#c0392b'), ('!active', danger_color)],
                 foreground=[('active', white), ('!active', white)])
        
        # Configurar LabelFrame
        style.configure('Card.TLabelframe',
                       background='#f8f9fa',
                       borderwidth=1,
                       relief='solid')
        style.configure('Card.TLabelframe.Label',
                       font=('Segoe UI', 11, 'bold'),
                       foreground=primary_color,
                       background='#f8f9fa')
        
        # Configurar Treeview
        style.configure('Professional.Treeview',
                       background=white,
                       foreground=primary_color,
                       fieldbackground=white,
                       font=('Segoe UI', 9))
        style.configure('Professional.Treeview.Heading',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=primary_color,
                       background=light_bg)
        
        # Configurar Entry y Combobox
        style.configure('Professional.TEntry',
                       font=('Segoe UI', 10),
                       fieldbackground=white,
                       borderwidth=1)
        style.configure('Professional.TCombobox',
                       font=('Segoe UI', 10),
                       fieldbackground=white,
                       borderwidth=1)
    
    def create_widgets(self):
        """Crear interfaz profesional con diseño moderno"""
        
        # Contenedor principal con padding
        main_container = tk.Frame(self.root, bg='#f8f9fa')
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header con título y logo
        header_frame = tk.Frame(main_container, bg='#f8f9fa', height=80)
        header_frame.pack(fill=tk.X, pady=(0, 20))
        header_frame.pack_propagate(False)
        
        # Título principal
        title_label = ttk.Label(header_frame, 
                               text="CMF Financial Data Scraper", 
                               style='Title.TLabel')
        title_label.pack(side=tk.LEFT, pady=20)
        
        # Información de versión
        version_label = ttk.Label(header_frame, 
                                 text="Professional Edition v1.0", 
                                 style='Info.TLabel')
        version_label.pack(side=tk.RIGHT, pady=25)
        
        # Panel principal dividido en dos columnas
        content_frame = tk.Frame(main_container, bg='#f8f9fa')
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Columna izquierda (60%)
        left_panel = tk.Frame(content_frame, bg='#f8f9fa')
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Columna derecha (40%)
        right_panel = tk.Frame(content_frame, bg='#f8f9fa', width=500)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_panel.pack_propagate(False)
        
        # === PANEL IZQUIERDO ===
        
        # Sección 1: Archivo de datos
        data_frame = ttk.LabelFrame(left_panel, 
                                   text="Archivo de Datos", 
                                   style='Card.TLabelframe',
                                   padding=15)
        data_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Fila para selección de archivo
        file_row = tk.Frame(data_frame, bg='#f8f9fa')
        file_row.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(file_row, text="Archivo CSV:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(side=tk.LEFT)
        
        self.csv_path_var = tk.StringVar()
        path_entry = ttk.Entry(file_row, 
                              textvariable=self.csv_path_var, 
                              state='readonly',
                              style='Professional.TEntry',
                              font=('Segoe UI', 10))
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 10))
        
        # Botones de archivo
        btn_frame = tk.Frame(file_row, bg='#f8f9fa')
        btn_frame.pack(side=tk.RIGHT)
        
        ttk.Button(btn_frame, text="Examinar", 
                  command=self.browse_csv,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(btn_frame, text="Recargar", 
                  command=self.reload_csv,
                  style='Primary.TButton').pack(side=tk.LEFT)
        
        # Información del archivo
        self.csv_info_label = ttk.Label(data_frame, text="", style='Info.TLabel')
        self.csv_info_label.pack(anchor=tk.W)
        
        # Sección 2: Selección de empresas
        companies_frame = ttk.LabelFrame(left_panel, 
                                        text="Selección de Empresas", 
                                        style='Card.TLabelframe',
                                        padding=15)
        companies_frame.pack(fill=tk.BOTH, expand=True)
        
        # Barra de herramientas superior
        toolbar = tk.Frame(companies_frame, bg='#f8f9fa', height=40)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        toolbar.pack_propagate(False)
        
        # Campo de búsqueda
        search_frame = tk.Frame(toolbar, bg='#f8f9fa')
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(search_frame, text="Buscar:", 
                font=('Segoe UI', 10), 
                bg='#f8f9fa', fg='#2c3e50').pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self.filter_companies)
        search_entry = ttk.Entry(search_frame, 
                               textvariable=self.search_var,
                               style='Professional.TEntry',
                               font=('Segoe UI', 10),
                               width=30)
        search_entry.pack(side=tk.LEFT, padx=(10, 20))
        
        # Botones de selección
        selection_buttons = tk.Frame(toolbar, bg='#f8f9fa')
        selection_buttons.pack(side=tk.RIGHT)
        
        ttk.Button(selection_buttons, text="Seleccionar Todo", 
                  command=self.select_all,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(selection_buttons, text="Limpiar Selección", 
                  command=self.deselect_all,
                  style='Primary.TButton').pack(side=tk.LEFT)
        
        # Información de selección
        self.selection_info_label = ttk.Label(companies_frame, 
                                            text="Seleccione empresas de la lista", 
                                            style='Info.TLabel')
        self.selection_info_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Contenedor del Treeview con scrollbars
        tree_container = tk.Frame(companies_frame, bg='#ffffff', relief=tk.SOLID, bd=1)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # Configurar Treeview
        columns = ('razon_social', 'rut', 'rut_sin_guion', 'anual')
        self.tree = ttk.Treeview(tree_container, 
                               columns=columns, 
                               show='tree headings', 
                               selectmode='extended',
                               style='Professional.Treeview')
        
        # Configurar columnas
        self.tree.heading('#0', text='Sel.')
        self.tree.heading('razon_social', text='Razón Social')
        self.tree.heading('rut', text='RUT')
        self.tree.heading('rut_sin_guion', text='RUT (Sin Guión)')
        self.tree.heading('anual', text='Reporte Anual')
        
        self.tree.column('#0', width=50, minwidth=50, anchor='center')
        self.tree.column('razon_social', width=350, minwidth=250, anchor='w')
        self.tree.column('rut', width=120, minwidth=100, anchor='center')
        self.tree.column('rut_sin_guion', width=120, minwidth=100, anchor='center')
        self.tree.column('anual', width=120, minwidth=100, anchor='center')
        
        # Scrollbars profesionales
        v_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid del Treeview
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        
        # Bind events
        self.tree.bind('<Button-1>', self.on_tree_click)
        self.tree.bind('<space>', self.toggle_selection)
        self.tree.bind('<Double-1>', self.on_tree_double_click)
        
        # === PANEL DERECHO ===
        
        # Sección 3: Configuración
        config_frame = ttk.LabelFrame(right_panel, 
                                     text="Configuración de Extracción", 
                                     style='Card.TLabelframe',
                                     padding=15)
        config_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Configuración de años
        tk.Label(config_frame, text="Rango de Años:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W, pady=(0, 10))
        
        years_grid = tk.Frame(config_frame, bg='#f8f9fa')
        years_grid.pack(fill=tk.X, pady=(0, 15))
        
        # Año inicial
        tk.Label(years_grid, text="Desde:", 
                font=('Segoe UI', 9), 
                bg='#f8f9fa', fg='#2c3e50').grid(row=0, column=0, sticky='w', padx=(0, 5))
        
        self.start_year_var = tk.StringVar(value="2024")
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
        
        self.end_year_var = tk.StringVar(value="2014")
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
        
        self.step_var = tk.StringVar(value="-2")
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
        
        tk.Label(config_frame, text=info_text, 
                font=('Segoe UI', 8), 
                bg='#f8f9fa', fg='#7f8c8d',
                justify=tk.LEFT).pack(anchor=tk.W, pady=(10, 0))
        
        # Sección 4: Control de ejecución
        control_frame = ttk.LabelFrame(right_panel, 
                                      text="Control de Ejecución", 
                                      style='Card.TLabelframe',
                                      padding=15)
        control_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Botones de control
        self.start_button = ttk.Button(control_frame, 
                                      text="Iniciar Extracción", 
                                      command=self.start_scraping,
                                      style='Success.TButton')
        self.start_button.pack(fill=tk.X, pady=(0, 5))
        
        self.stop_button = ttk.Button(control_frame, 
                                     text="Detener Proceso", 
                                     command=self.stop_scraping,
                                     style='Danger.TButton',
                                     state='disabled')
        self.stop_button.pack(fill=tk.X, pady=(0, 10))
        
        # Botón de resultados
        self.results_button = ttk.Button(control_frame, 
                                        text="Abrir Carpeta de Resultados", 
                                        command=self.open_results_folder,
                                        style='Primary.TButton')
        self.results_button.pack(fill=tk.X)
        
        # Estado del proceso
        status_frame = tk.Frame(control_frame, bg='#f8f9fa')
        status_frame.pack(fill=tk.X, pady=(15, 0))
        
        tk.Label(status_frame, text="Estado:", 
                font=('Segoe UI', 10, 'bold'), 
                bg='#f8f9fa', fg='#2c3e50').pack(anchor=tk.W)
        
        self.progress_var = tk.StringVar(value="Listo para comenzar")
        self.progress_label = ttk.Label(status_frame, 
                                       textvariable=self.progress_var, 
                                       style='Info.TLabel')
        self.progress_label.pack(anchor=tk.W, pady=(5, 10))
        
        # Barra de progreso profesional
        self.progress_bar = ttk.Progressbar(status_frame, 
                                          mode='indeterminate',
                                          style='TProgressbar')
        self.progress_bar.pack(fill=tk.X)
        
        # Sección 5: Log de actividad
        log_frame = ttk.LabelFrame(right_panel, 
                                  text="Registro de Actividad", 
                                  style='Card.TLabelframe',
                                  padding=15)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Crear log con estilo profesional
        log_container = tk.Frame(log_frame, bg='#ffffff', relief=tk.SOLID, bd=1)
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = scrolledtext.ScrolledText(log_container, 
                                                height=15, 
                                                font=('Consolas', 9),
                                                bg='#ffffff',
                                                fg='#2c3e50',
                                                insertbackground='#2c3e50',
                                                selectbackground='#3498db',
                                                selectforeground='#ffffff',
                                                wrap=tk.WORD,
                                                relief=tk.FLAT,
                                                bd=0)
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
    
    def load_default_csv(self):
        """Cargar el archivo CSV por defecto"""
        default_path = "./data/RUT_Chilean_Companies/RUT_Chilean_Companies.csv"
        if os.path.exists(default_path):
            self.csv_path_var.set(default_path)
            self.load_csv(default_path)
        else:
            self.log("ADVERTENCIA: Archivo CSV por defecto no encontrado: " + default_path)
    
    def browse_csv(self):
        """Examinar y seleccionar archivo CSV"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo CSV de empresas",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
            initialdir="./data"
        )
        
        if file_path:
            self.csv_path_var.set(file_path)
            self.load_csv(file_path)
    
    def reload_csv(self):
        """Recargar el archivo CSV actual"""
        if self.csv_path_var.get():
            self.load_csv(self.csv_path_var.get())
        else:
            messagebox.showwarning("Advertencia", "No hay archivo CSV cargado para recargar")
    
    def load_csv(self, file_path):
        """Cargar datos del archivo CSV"""
        try:
            self.companies_df = pd.read_csv(file_path)
            
            # Verificar columnas requeridas
            required_columns = ['Razón Social', 'RUT', 'RUT_Sin_Guión']
            missing_columns = [col for col in required_columns if col not in self.companies_df.columns]
            
            if missing_columns:
                raise ValueError(f"Columnas faltantes en el CSV: {missing_columns}")
            
            # Actualizar información
            num_companies = len(self.companies_df)
            self.csv_info_label.config(text=f"Archivo cargado correctamente: {num_companies} empresas encontradas")
            
            # Actualizar el Treeview
            self.populate_tree()
            
            self.log(f"CSV cargado exitosamente: {num_companies} empresas")
            
        except Exception as e:
            error_msg = f"Error cargando CSV: {str(e)}"
            self.csv_info_label.config(text=error_msg)
            self.log(f"ERROR: {error_msg}")
            messagebox.showerror("Error", error_msg)
    
    def populate_tree(self):
        """Poblar el Treeview con datos del CSV"""
        # Limpiar datos existentes
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        if self.companies_df is None:
            return
        
        # Agregar empresas al tree
        for idx, row in self.companies_df.iterrows():
            razon_social = row.get('Razón Social', '')
            rut = row.get('RUT', '')
            rut_sin_guion = row.get('RUT_Sin_Guión', '')
            anual = row.get('Anual (Diciembre)', 'N/A')
            
            # Insertar en el tree
            item_id = self.tree.insert('', 'end', text='☐', 
                                     values=(razon_social, rut, rut_sin_guion, anual),
                                     tags=(str(idx),))
            
            # Alternar colores de fila
            if idx % 2 == 0:
                self.tree.item(item_id, tags=('evenrow',))
            else:
                self.tree.item(item_id, tags=('oddrow',))
        
        # Configurar tags para colores alternados
        self.tree.tag_configure('evenrow', background='#f8f9fa')
        self.tree.tag_configure('oddrow', background='#ffffff')
        
        # Actualizar información de selección
        self.update_selection_info()
    
    def filter_companies(self, *args):
        """Filtrar empresas según el texto de búsqueda"""
        if self.companies_df is None:
            return
        
        search_text = self.search_var.get().lower()
        
        # Limpiar tree
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Filtrar y mostrar
        filtered_count = 0
        for idx, row in self.companies_df.iterrows():
            razon_social = row.get('Razón Social', '')
            rut = row.get('RUT', '')
            
            # Verificar si coincide con la búsqueda
            if (search_text in razon_social.lower() or 
                search_text in rut.lower() or 
                search_text == ''):
                
                rut_sin_guion = row.get('RUT_Sin_Guión', '')
                anual = row.get('Anual (Diciembre)', 'N/A')
                
                item_id = self.tree.insert('', 'end', text='☐', 
                                         values=(razon_social, rut, rut_sin_guion, anual),
                                         tags=(str(idx),))
                
                # Alternar colores
                if filtered_count % 2 == 0:
                    self.tree.item(item_id, tags=('evenrow',))
                else:
                    self.tree.item(item_id, tags=('oddrow',))
                
                filtered_count += 1
        
        # Actualizar información de selección
        self.update_selection_info()
    
    def on_tree_click(self, event):
        """Manejar clics en el tree"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "tree":
            item = self.tree.identify('item', event.x, event.y)
            if item:
                self.toggle_item_selection(item)
    
    def on_tree_double_click(self, event):
        """Manejar doble clic para mostrar detalles de la empresa"""
        item = self.tree.identify('item', event.x, event.y)
        if item:
            values = self.tree.item(item, 'values')
            if values:
                company_info = (
                    f"Detalles de la Empresa\n\n"
                    f"Razón Social: {values[0]}\n"
                    f"RUT: {values[1]}\n"
                    f"RUT (Sin Guión): {values[2]}\n"
                    f"Reporte Anual: {values[3]}"
                )
                messagebox.showinfo("Información de Empresa", company_info)
    
    def toggle_selection(self, event):
        """Alternar selección con tecla espacio"""
        selection = self.tree.selection()
        if selection:
            for item in selection:
                self.toggle_item_selection(item)
    
    def toggle_item_selection(self, item):
        """Alternar selección de un item"""
        current_text = self.tree.item(item, 'text')
        if current_text == '☐':
            self.tree.item(item, text='☑')
        else:
            self.tree.item(item, text='☐')
        
        self.update_selection_info()
    
    def select_all(self):
        """Seleccionar todas las empresas visibles"""
        for item in self.tree.get_children():
            self.tree.item(item, text='☑')
        self.update_selection_info()
    
    def deselect_all(self):
        """Deseleccionar todas las empresas"""
        for item in self.tree.get_children():
            self.tree.item(item, text='☐')
        self.update_selection_info()
    
    def update_selection_info(self):
        """Actualizar información de selección"""
        total_visible = len(self.tree.get_children())
        selected_count = sum(1 for item in self.tree.get_children() 
                           if self.tree.item(item, 'text') == '☑')
        
        if selected_count == 0:
            self.selection_info_label.config(text=f"Mostrando {total_visible} empresas - Ninguna seleccionada")
            self.start_button.config(state='disabled')
        else:
            self.selection_info_label.config(text=f"Mostrando {total_visible} empresas - {selected_count} seleccionadas")
            self.start_button.config(state='normal')
    
    def get_selected_companies(self):
        """Obtener lista de empresas seleccionadas"""
        selected = []
        for item in self.tree.get_children():
            if self.tree.item(item, 'text') == '☑':
                values = self.tree.item(item, 'values')
                selected.append({
                    'razon_social': values[0],
                    'rut': values[1],
                    'rut_sin_guion': values[2],
                    'anual': values[3]
                })
        return selected
    
    def start_scraping(self):
        """Iniciar el proceso de scraping"""
        if self.is_running:
            return
        
        selected_companies = self.get_selected_companies()
        if not selected_companies:
            messagebox.showwarning("Advertencia", "Seleccione al menos una empresa")
            return
        
        # Validar configuración
        try:
            start_year = int(self.start_year_var.get())
            end_year = int(self.end_year_var.get())
            step = int(self.step_var.get())
            
            if start_year <= end_year:
                messagebox.showerror("Error", "El año inicial debe ser mayor que el año final")
                return
                
        except ValueError:
            messagebox.showerror("Error", "Los años y el incremento deben ser números válidos")
            return
        
        # Configurar UI para ejecución
        self.is_running = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.progress_bar.start()
        
        self.log(f"\n{'='*60}")
        self.log("🚀 INICIANDO PROCESO DE SCRAPING")
        self.log(f"{'='*60}")
        self.log(f"📊 Empresas seleccionadas: {len(selected_companies)}")
        self.log(f"📅 Período: {start_year} a {end_year} (paso: {step})")
        self.log(f"⏰ Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Iniciar scraping en hilo separado
        self.scraping_thread = threading.Thread(
            target=self.run_scraping,
            args=(selected_companies, start_year, end_year, step),
            daemon=True
        )
        self.scraping_thread.start()
    
    def run_scraping(self, companies, start_year, end_year, step):
        """Ejecutar scraping en hilo separado"""
        try:
            results = []
            total_companies = len(companies)
            
            for i, company in enumerate(companies, 1):
                if not self.is_running:  # Verificar si se detuvo
                    break
                
                self.output_queue.put(('progress', f"Procesando {i}/{total_companies}: {company['razon_social']}"))
                
                try:
                    rut_sin_guion = company['rut_sin_guion']
                    
                    self.output_queue.put(('log', f"\n{'#'*50}"))
                    self.output_queue.put(('log', f"EMPRESA {i}/{total_companies}: {company['razon_social']}"))
                    self.output_queue.put(('log', f"RUT: {company['rut']} (Sin guión: {rut_sin_guion})"))
                    self.output_queue.put(('log', f"{'#'*50}"))
                    
                    # Ejecutar scraping en modo headless
                    output_file = scrape_cmf_data(
                        rut=rut_sin_guion,
                        start_year=start_year,
                        end_year=end_year,
                        step=step,
                        headless=True  # Modo headless para no interferir con la GUI
                    )
                    
                    results.append((company['razon_social'], rut_sin_guion, output_file, "SUCCESS"))
                    self.output_queue.put(('log', f"✅ {company['razon_social']}: Completado exitosamente"))
                    self.output_queue.put(('log', f"📁 Archivo: {output_file}"))
                    
                    # Verificar datos
                    verify_data_order(output_file)
                    
                except Exception as e:
                    error_msg = f"Error procesando {company['razon_social']}: {str(e)}"
                    results.append((company['razon_social'], company['rut_sin_guion'], None, f"ERROR: {str(e)}"))
                    self.output_queue.put(('log', error_msg))
                
                # Pausa entre empresas
                if i < total_companies and self.is_running:
                    self.output_queue.put(('log', "Esperando 3 segundos antes de la siguiente empresa..."))
                    for _ in range(30):  # 3 segundos en pasos de 0.1
                        if not self.is_running:
                            break
                        threading.Event().wait(0.1)
            
            # Resumen final
            if self.is_running:
                self.output_queue.put(('log', f"\n{'='*60}"))
                self.output_queue.put(('log', "RESUMEN DEL PROCESAMIENTO"))
                self.output_queue.put(('log', f"{'='*60}"))
                
                successful = sum(1 for _, _, _, status in results if status == "SUCCESS")
                self.output_queue.put(('log', f"Empresas procesadas exitosamente: {successful}/{len(results)}"))
                
                for razon_social, rut, file_path, status in results:
                    if status == "SUCCESS":
                        self.output_queue.put(('log', f"EXITOSO: {razon_social}: {file_path}"))
                    else:
                        self.output_queue.put(('log', f"ERROR: {razon_social}: {status}"))
                
                self.output_queue.put(('progress', f"Proceso completado: {successful}/{len(results)} empresas exitosas"))
            else:
                self.output_queue.put(('progress', "Proceso detenido por el usuario"))
            
        except Exception as e:
            self.output_queue.put(('log', f"Error fatal en el proceso: {str(e)}"))
            self.output_queue.put(('progress', f"Error fatal: {str(e)}"))
        
        finally:
            self.output_queue.put(('finished', None))
    
    def stop_scraping(self):
        """Detener el proceso de scraping"""
        self.is_running = False
        self.log("Deteniendo proceso de scraping...")
        self.progress_var.set("Deteniendo proceso...")
    
    def check_output_queue(self):
        """Verificar cola de output y actualizar UI"""
        try:
            while True:
                msg_type, message = self.output_queue.get_nowait()
                
                if msg_type == 'log':
                    self.log(message)
                elif msg_type == 'scraper_log':
                    # Logs del scraper en tiempo real
                    self.log(f"[SCRAPER] {message}")
                elif msg_type == 'progress':
                    self.progress_var.set(message)
                elif msg_type == 'finished':
                    self.finish_scraping()
                    break
                    
        except queue.Empty:
            pass
        
        # Programar siguiente verificación
        self.root.after(100, self.check_output_queue)
    
    def finish_scraping(self):
        """Finalizar proceso de scraping"""
        self.is_running = False
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.progress_bar.stop()
        
        self.log(f"\nProceso finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    def open_results_folder(self):
        """Abrir carpeta de resultados"""
        results_path = "./data/Reports"
        if os.path.exists(results_path):
            if sys.platform.startswith('linux'):
                subprocess.run(['xdg-open', results_path])
            elif sys.platform.startswith('darwin'):  # macOS
                subprocess.run(['open', results_path])
            elif sys.platform.startswith('win'):
                subprocess.run(['explorer', results_path])
            self.log(f"Abriendo carpeta de resultados: {results_path}")
        else:
            messagebox.showinfo("Información", f"La carpeta de resultados no existe aún: {results_path}")
    
    def log(self, message):
        """Agregar mensaje al log con timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        self.log_text.insert(tk.END, formatted_message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def on_closing(self):
        """Manejar cierre de aplicación"""
        if self.is_running:
            if messagebox.askyesno("Confirmar salida", 
                                 "Hay un proceso en ejecución. ¿Desea salir de todas formas?"):
                self.is_running = False
                self.root.destroy()
        else:
            self.root.destroy()


def main():
    """Función principal"""
    root = tk.Tk()
    app = CMFScraperGUI(root)
    
    # Configurar manejo del cierre
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Cargar CSV por defecto al inicio
    root.after(100, app.load_default_csv)
    
    # Iniciar verificación de cola de mensajes
    root.after(100, app.check_output_queue)
    
    root.mainloop()


if __name__ == "__main__":
    main()
