#!/usr/bin/env python3
"""
Componente de tabla de empresas para el CMF Scraper
"""

import tkinter as tk
from tkinter import ttk
from tkinter import messagebox
import os
import pandas as pd
from typing import Optional, List, Dict, Callable


class CompanyTable:
    """Componente para mostrar y manejar la tabla de empresas"""

    def __init__(self, parent, on_selection_change: Optional[Callable] = None,
                 data_paths_provider: Optional[Callable[[], dict]] = None):
        self.parent = parent
        self.on_selection_change = on_selection_change
        # Proveedor opcional de rutas reales (XBRL / Excel) para detectar
        # empresas que ya tienen datos en disco. Si no se pasa, se usa
        # ./data/XBRL/Total como fallback.
        self.data_paths_provider = data_paths_provider
        self.companies_df = None
        self.selected_companies_cache = set()  # Cache para mantener selecciones
        # Cache rut_sin_guion -> estado de datos en disco
        # {"xbrl": bool, "excel": bool}
        self._data_status: Dict[str, Dict[str, bool]] = {}

        # Crear el widget principal
        self.frame = None
        self.tree = None
        self.search_var = None
        self.selection_info_label = None

        self._create_widgets()
    
    def _create_widgets(self):
        """Crear los widgets del componente"""
        # Frame principal
        self.frame = ttk.LabelFrame(self.parent, 
                                   text="Selección de Empresas", 
                                   style='Card.TLabelframe',
                                   padding=15)
        
        # Barra de herramientas superior
        toolbar = tk.Frame(self.frame, bg='#f8f9fa', height=40)
        toolbar.pack(fill=tk.X, pady=(0, 10))
        toolbar.pack_propagate(False)
        
        # Campo de búsqueda
        search_frame = tk.Frame(toolbar, bg='#f8f9fa')
        search_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        tk.Label(search_frame, text="Buscar:", 
                font=('Segoe UI', 10), 
                bg='#f8f9fa', fg='#2c3e50').pack(side=tk.LEFT)
        
        self.search_var = tk.StringVar()
        self.search_var.trace('w', self._on_search_change)
        search_entry = ttk.Entry(search_frame, 
                               textvariable=self.search_var,
                               style='Professional.TEntry',
                               font=('Segoe UI', 10),
                               width=30)
        search_entry.pack(side=tk.LEFT, padx=(10, 20))
        
        # Botones de selección (dos filas para no apretar tanto)
        selection_buttons = tk.Frame(toolbar, bg='#f8f9fa')
        selection_buttons.pack(side=tk.RIGHT)

        row1 = tk.Frame(selection_buttons, bg='#f8f9fa')
        row1.pack(side=tk.TOP, anchor='e')
        row2 = tk.Frame(selection_buttons, bg='#f8f9fa')
        row2.pack(side=tk.TOP, anchor='e', pady=(4, 0))

        ttk.Button(row1, text="Todo (visible)",
                  command=self.select_all,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="Limpiar",
                  command=self.deselect_all,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="Invertir",
                  command=self.invert_selection,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="IPSA",
                  command=self.select_ipsa,
                  style='Primary.TButton').pack(side=tk.LEFT)

        ttk.Button(row2, text="Con XBRL descargado",
                  command=self.select_existing_xbrl,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="Con Excel listo",
                  command=self.select_existing_excel,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="Pendientes (sin Excel)",
                  command=self.select_pending,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row2, text="Refrescar datos",
                  command=self.refresh_data_status,
                  style='Secondary.TButton').pack(side=tk.LEFT)
        
        # Información de selección
        self.selection_info_label = ttk.Label(self.frame, 
                                            text="Seleccione empresas de la lista", 
                                            style='Info.TLabel')
        self.selection_info_label.pack(anchor=tk.W, pady=(0, 10))
        
        # Contenedor del Treeview con scrollbars
        tree_container = tk.Frame(self.frame, bg='#ffffff', relief=tk.SOLID, bd=1)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        # Configurar Treeview
        columns = ('razon_social', 'rut', 'rut_sin_guion', 'datos', 'anual')
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
        # X = XBRL descargado, E = Excel consolidado listo
        self.tree.heading('datos', text='Datos')
        self.tree.heading('anual', text='Reporte Anual')

        self.tree.column('#0', width=50, minwidth=50, anchor='center')
        self.tree.column('razon_social', width=300, minwidth=220, anchor='w')
        self.tree.column('rut', width=110, minwidth=90, anchor='center')
        self.tree.column('rut_sin_guion', width=110, minwidth=90, anchor='center')
        self.tree.column('datos', width=80, minwidth=70, anchor='center')
        self.tree.column('anual', width=110, minwidth=90, anchor='center')
        
        # Scrollbars
        v_scrollbar = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self.tree.yview)
        h_scrollbar = ttk.Scrollbar(tree_container, orient=tk.HORIZONTAL, command=self.tree.xview)
        self.tree.configure(yscrollcommand=v_scrollbar.set, xscrollcommand=h_scrollbar.set)
        
        # Grid del Treeview
        self.tree.grid(row=0, column=0, sticky='nsew')
        v_scrollbar.grid(row=0, column=1, sticky='ns')
        h_scrollbar.grid(row=1, column=0, sticky='ew')
        
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)
        
        # Configurar tags para colores alternados
        self.tree.tag_configure('evenrow', background='#f8f9fa')
        self.tree.tag_configure('oddrow', background='#ffffff')
        
        # Bind events
        self.tree.bind('<Button-1>', self._on_tree_click)
        self.tree.bind('<space>', self._on_toggle_selection)
        self.tree.bind('<Double-1>', self._on_tree_double_click)
    
    def load_data(self, companies_df):
        """Cargar datos del DataFrame de empresas"""
        self.companies_df = companies_df
        # Limpiar cache de selecciones cuando se cargan nuevos datos
        self.selected_companies_cache.clear()
        # Re-escanear estado en disco con la nueva lista
        self._scan_data_status()
        self._populate_tree()

    # ------------------------------------------------------------------ #
    # Detección de empresas con datos en disco
    # ------------------------------------------------------------------ #
    def _get_data_paths(self) -> dict:
        """Resolver rutas reales (XBRL dirs + Excel dir) desde el proveedor
        o caer a defaults relativos al cwd."""
        if self.data_paths_provider is not None:
            try:
                paths = self.data_paths_provider() or {}
            except Exception:
                paths = {}
        else:
            paths = {}
        xbrl_dirs = paths.get('xbrl_dirs') or []
        if not xbrl_dirs:
            # Fallback: todos los subdirs estándar de data/XBRL
            base = os.path.join('.', 'data', 'XBRL')
            for sub in ('Total', 'Anual', 'Trimestral'):
                p = os.path.join(base, sub)
                if os.path.isdir(p):
                    xbrl_dirs.append(p)
        excel_dir = paths.get('excel_dir') or ''
        return {'xbrl_dirs': xbrl_dirs, 'excel_dir': excel_dir}

    def _scan_xbrl_ruts(self, xbrl_dirs) -> set:
        """RUTs (solo dígitos) con carpeta XBRL en cualquiera de los dirs."""
        ruts: set = set()
        for d in xbrl_dirs:
            if not d or not os.path.isdir(d):
                continue
            try:
                entries = os.listdir(d)
            except OSError:
                continue
            for item in entries:
                if not os.path.isdir(os.path.join(d, item)):
                    continue
                # Formato esperado: <RUT-DV>_<EMPRESA>
                if '_' in item:
                    rut_part = item.split('_', 1)[0]
                    rut_num = rut_part.split('-')[0] if '-' in rut_part else rut_part
                    rut_num = ''.join(ch for ch in rut_num if ch.isdigit())
                    if rut_num:
                        ruts.add(rut_num)
        return ruts

    def _scan_excel_ruts(self, excel_dir) -> set:
        """RUTs (solo dígitos) con Excel consolidado en product_v1_dir."""
        ruts: set = set()
        if not excel_dir or not os.path.isdir(excel_dir):
            return ruts
        try:
            entries = os.listdir(excel_dir)
        except OSError:
            return ruts
        import re
        # Buscar RUT en cualquier parte del nombre: "NN.NNN.NNN-D" o "NNNNNNN-D"
        pat = re.compile(r'(\d{6,9})[-\s]?[\dKk]')
        for item in entries:
            if not item.lower().endswith('.xlsx'):
                continue
            m = pat.search(item)
            if m:
                ruts.add(m.group(1))
        return ruts

    def _scan_data_status(self) -> None:
        """Construye self._data_status para todas las empresas cargadas."""
        self._data_status = {}
        if self.companies_df is None:
            return
        paths = self._get_data_paths()
        xbrl_ruts = self._scan_xbrl_ruts(paths['xbrl_dirs'])
        excel_ruts = self._scan_excel_ruts(paths['excel_dir'])
        rut_col = self._find_column(self.companies_df,
                                    ['RUT_Sin_Guión', 'rut_sin_guion', 'rut_sin_guión'])
        if not rut_col:
            return
        for _, row in self.companies_df.iterrows():
            rut_val = str(row.get(rut_col, ''))
            rut_digits = ''.join(ch for ch in rut_val if ch.isdigit())
            if not rut_digits:
                continue
            self._data_status[rut_digits] = {
                'xbrl': rut_digits in xbrl_ruts,
                'excel': rut_digits in excel_ruts,
            }

    def refresh_data_status(self) -> None:
        """Re-escanea disco y repinta la columna 'Datos'."""
        self._scan_data_status()
        self._on_search_change()
        n_xbrl = sum(1 for s in self._data_status.values() if s['xbrl'])
        n_excel = sum(1 for s in self._data_status.values() if s['excel'])
        messagebox.showinfo(
            "Datos en disco",
            f"Empresas con XBRL descargado: {n_xbrl}\n"
            f"Empresas con Excel listo: {n_excel}")

    def _data_badge(self, rut_digits: str) -> str:
        """Texto compacto para la columna 'Datos'."""
        s = self._data_status.get(rut_digits)
        if not s:
            return '—'
        parts = []
        if s['xbrl']:
            parts.append('X')
        if s['excel']:
            parts.append('E')
        return '+'.join(parts) if parts else '—'

    def _find_column(self, df, candidates):
        """Encontrar columna en df de forma tolerante a mayúsculas/acentos"""
        lower_map = {c.lower(): c for c in df.columns}
        for cand in candidates:
            if cand in df.columns:
                return cand
            if cand.lower() in lower_map:
                return lower_map[cand.lower()]
        return None

    def select_ipsa(self):
        """Seleccionar automáticamente empresas presentes en companies_ipsa.csv por RUT_Sin_Guión"""
        try:
            if self.companies_df is None:
                messagebox.showwarning("Advertencia", "Primero cargue el CSV principal de empresas")
                return

            ipsa_path = os.path.join('.', 'data', 'RUT_Chilean_Companies', 'companies_ipsa.csv')
            if not os.path.exists(ipsa_path):
                messagebox.showerror("Error", f"No se encontró el archivo IPSA en: {ipsa_path}")
                return

            ipsa_df = pd.read_csv(ipsa_path)

            # Detectar columna RUT_Sin_Guión en ambos formatos
            ipsa_rut_col = self._find_column(ipsa_df, ['rut_sin_guion', 'rut_sin_guión', 'RUT_Sin_Guión'])
            main_rut_col = self._find_column(self.companies_df, ['RUT_Sin_Guión', 'rut_sin_guion', 'rut_sin_guión'])

            if not ipsa_rut_col or not main_rut_col:
                messagebox.showerror("Error", "No se encontró la columna RUT_Sin_Guión en uno de los CSV")
                return

            # Normalizar a str y tomar solo dígitos
            ipsa_ruts = set(
                ipsa_df[ipsa_rut_col].astype(str).str.replace("[^0-9]", "", regex=True)
            )

            # Actualizar cache para todas las coincidencias (incluye filas filtradas)
            selected_count = 0
            for _, row in self.companies_df.iterrows():
                rut_val = str(row.get(main_rut_col, ''))
                rut_digits = ''.join(ch for ch in rut_val if ch.isdigit())
                if rut_digits and rut_digits in ipsa_ruts:
                    razon = row.get('Razón Social', '')
                    company_key = f"{rut_digits}_{razon}"
                    if company_key not in self.selected_companies_cache:
                        self.selected_companies_cache.add(company_key)
                        selected_count += 1

            # Refrescar la vista actual respetando el filtro de búsqueda
            self._on_search_change()
            self._update_selection_info()

            if selected_count == 0:
                messagebox.showinfo("Información", "No se encontraron coincidencias IPSA en la lista actual")
            else:
                messagebox.showinfo("IPSA", f"Se marcaron {selected_count} empresas del IPSA")
        except Exception as e:
            messagebox.showerror("Error", f"Error seleccionando IPSA: {str(e)}")
    
    def select_existing_xbrl(self):
        """Seleccionar empresas con XBRL descargado en disco (cualquier subdir)."""
        self._select_by_disk_state(want_xbrl=True, want_excel=None,
                                   label="con XBRL descargado")

    def select_existing_excel(self):
        """Seleccionar empresas con Excel consolidado listo en product_v1_dir."""
        self._select_by_disk_state(want_xbrl=None, want_excel=True,
                                   label="con Excel listo")

    def select_pending(self):
        """Seleccionar empresas SIN Excel listo — lo que falta por procesar."""
        self._select_by_disk_state(want_xbrl=None, want_excel=False,
                                   label="pendientes (sin Excel)")

    def _select_by_disk_state(self, want_xbrl, want_excel, label: str) -> None:
        """Marcar en el cache todas las empresas del CSV que cumplan el filtro.

        `want_xbrl` y `want_excel`: True exige presencia, False exige ausencia,
        None ignora ese eje. La selección es aditiva (no limpia previas).
        """
        try:
            if self.companies_df is None:
                messagebox.showwarning("Advertencia", "Primero cargue el CSV principal de empresas")
                return
            # Asegurar estado actualizado antes de filtrar
            if not self._data_status:
                self._scan_data_status()
            rut_col = self._find_column(
                self.companies_df,
                ['RUT_Sin_Guión', 'rut_sin_guion', 'rut_sin_guión'])
            if not rut_col:
                messagebox.showerror("Error", "No se encontró la columna RUT_Sin_Guión en el CSV principal")
                return
            selected_count = 0
            for _, row in self.companies_df.iterrows():
                rut_val = str(row.get(rut_col, ''))
                rut_digits = ''.join(ch for ch in rut_val if ch.isdigit())
                if not rut_digits:
                    continue
                st = self._data_status.get(rut_digits, {'xbrl': False, 'excel': False})
                if want_xbrl is not None and st['xbrl'] != want_xbrl:
                    continue
                if want_excel is not None and st['excel'] != want_excel:
                    continue
                razon = row.get('Razón Social', '')
                company_key = f"{rut_digits}_{razon}"
                if company_key not in self.selected_companies_cache:
                    self.selected_companies_cache.add(company_key)
                    selected_count += 1
            self._on_search_change()
            self._update_selection_info()
            if self.on_selection_change:
                self.on_selection_change()
            if selected_count == 0:
                messagebox.showinfo("Información",
                                    f"No se encontraron empresas {label}")
            else:
                messagebox.showinfo("Selección automática",
                                    f"Se marcaron {selected_count} empresas {label}")
        except Exception as e:
            messagebox.showerror("Error", f"Error seleccionando empresas: {str(e)}")

    def invert_selection(self):
        """Invertir la selección dentro de las filas VISIBLES (respeta búsqueda)."""
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            if not values:
                continue
            # values[2] = rut_sin_guion, values[0] = razon_social
            company_key = f"{values[2]}_{values[0]}"
            if self.tree.item(item, 'text') == '☑':
                self.tree.item(item, text='☐')
                self.selected_companies_cache.discard(company_key)
            else:
                self.tree.item(item, text='☑')
                self.selected_companies_cache.add(company_key)
        self._update_selection_info()
        if self.on_selection_change:
            self.on_selection_change()
    
    def _populate_tree(self):
        """Poblar el Treeview con datos del CSV manteniendo selecciones"""
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

            # Crear clave única para la empresa
            company_key = f"{rut_sin_guion}_{razon_social}"
            rut_digits = ''.join(ch for ch in str(rut_sin_guion) if ch.isdigit())
            datos_badge = self._data_badge(rut_digits)

            # Verificar si estaba seleccionada antes
            is_selected = company_key in self.selected_companies_cache
            selection_text = '☑' if is_selected else '☐'

            # Insertar en el tree
            item_id = self.tree.insert('', 'end', text=selection_text,
                                     values=(razon_social, rut, rut_sin_guion, datos_badge, anual),
                                     tags=(str(idx),))

            # Alternar colores de fila
            if idx % 2 == 0:
                self.tree.item(item_id, tags=('evenrow',))
            else:
                self.tree.item(item_id, tags=('oddrow',))
        
        # Actualizar información de selección
        self._update_selection_info()
    
    def _on_search_change(self, *args):
        """Filtrar empresas según el texto de búsqueda manteniendo selecciones"""
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

                # Crear clave única para la empresa
                company_key = f"{rut_sin_guion}_{razon_social}"
                rut_digits = ''.join(ch for ch in str(rut_sin_guion) if ch.isdigit())
                datos_badge = self._data_badge(rut_digits)

                # Verificar si estaba seleccionada antes
                is_selected = company_key in self.selected_companies_cache
                selection_text = '☑' if is_selected else '☐'

                item_id = self.tree.insert('', 'end', text=selection_text,
                                         values=(razon_social, rut, rut_sin_guion, datos_badge, anual),
                                         tags=(str(idx),))

                # Alternar colores
                if filtered_count % 2 == 0:
                    self.tree.item(item_id, tags=('evenrow',))
                else:
                    self.tree.item(item_id, tags=('oddrow',))

                filtered_count += 1
        
        # Actualizar información de selección
        self._update_selection_info()
    
    def _on_tree_click(self, event):
        """Manejar clics en el tree"""
        region = self.tree.identify("region", event.x, event.y)
        if region == "tree":
            item = self.tree.identify('item', event.x, event.y)
            if item:
                self._toggle_item_selection(item)
    
    def _on_tree_double_click(self, event):
        """Manejar doble clic para mostrar detalles de la empresa"""
        from tkinter import messagebox

        item = self.tree.identify('item', event.x, event.y)
        if item:
            values = self.tree.item(item, 'values')
            if values:
                # values = (razon_social, rut, rut_sin_guion, datos, anual)
                anual_val = values[4] if len(values) > 4 else values[-1]
                company_info = (
                    f"Detalles de la Empresa\n\n"
                    f"Razón Social: {values[0]}\n"
                    f"RUT: {values[1]}\n"
                    f"RUT (Sin Guión): {values[2]}\n"
                    f"Datos en disco: {values[3] if len(values) > 3 else '—'}\n"
                    f"Reporte Anual: {anual_val}"
                )
                messagebox.showinfo("Información de Empresa", company_info)
    
    def _on_toggle_selection(self, event):
        """Alternar selección con tecla espacio"""
        selection = self.tree.selection()
        if selection:
            for item in selection:
                self._toggle_item_selection(item)
    
    def _toggle_item_selection(self, item):
        """Alternar selección de un item y mantener cache"""
        current_text = self.tree.item(item, 'text')
        values = self.tree.item(item, 'values')
        
        if values:
            # Crear clave única para la empresa
            company_key = f"{values[2]}_{values[0]}"  # rut_sin_guion_razon_social
            
            if current_text == '☐':
                self.tree.item(item, text='☑')
                self.selected_companies_cache.add(company_key)
            else:
                self.tree.item(item, text='☐')
                self.selected_companies_cache.discard(company_key)
        
        self._update_selection_info()
        
        # Notificar cambio de selección
        if self.on_selection_change:
            self.on_selection_change()
    
    def select_all(self):
        """Seleccionar todas las empresas visibles"""
        for item in self.tree.get_children():
            values = self.tree.item(item, 'values')
            if values:
                self.tree.item(item, text='☑')
                # Agregar al cache
                company_key = f"{values[2]}_{values[0]}"  # rut_sin_guion_razon_social
                self.selected_companies_cache.add(company_key)
        
        self._update_selection_info()
        
        if self.on_selection_change:
            self.on_selection_change()
    
    def deselect_all(self):
        """Deseleccionar todas las empresas"""
        # Limpiar cache completamente
        self.selected_companies_cache.clear()
        
        # Limpiar selecciones visibles
        for item in self.tree.get_children():
            self.tree.item(item, text='☐')
        
        self._update_selection_info()
        
        if self.on_selection_change:
            self.on_selection_change()
    
    def _update_selection_info(self):
        """Actualizar información de selección"""
        total_visible = len(self.tree.get_children())
        visible_selected = sum(1 for item in self.tree.get_children() 
                              if self.tree.item(item, 'text') == '☑')
        total_selected = len(self.selected_companies_cache)
        
        if total_selected == 0:
            self.selection_info_label.config(
                text=f"Mostrando {total_visible} empresas - Ninguna seleccionada"
            )
        elif total_selected == visible_selected:
            self.selection_info_label.config(
                text=f"Mostrando {total_visible} empresas - {total_selected} seleccionadas"
            )
        else:
            self.selection_info_label.config(
                text=f"Mostrando {total_visible} empresas - {visible_selected} visibles de {total_selected} seleccionadas"
            )
    
    def get_selected_companies(self) -> List[Dict]:
        """Devuelve TODAS las empresas marcadas en el cache, no solo las visibles.

        Esto importa cuando se aplica un filtro de búsqueda y luego se quiere
        ejecutar el pipeline sobre todas las marcadas (caso bulk de 500 empresas).
        """
        selected: List[Dict] = []
        if self.companies_df is None or not self.selected_companies_cache:
            return selected
        rut_col = self._find_column(
            self.companies_df,
            ['RUT_Sin_Guión', 'rut_sin_guion', 'rut_sin_guión']) or 'RUT_Sin_Guión'
        for _, row in self.companies_df.iterrows():
            razon = row.get('Razón Social', '')
            rut_sin_guion = row.get(rut_col, '')
            company_key = f"{rut_sin_guion}_{razon}"
            if company_key in self.selected_companies_cache:
                selected.append({
                    'razon_social': razon,
                    'rut': row.get('RUT', ''),
                    'rut_sin_guion': rut_sin_guion,
                    'anual': row.get('Anual (Diciembre)', 'N/A'),
                })
        return selected
    
    def pack(self, **kwargs):
        """Empaquetar el componente"""
        self.frame.pack(**kwargs)
    
    def grid(self, **kwargs):
        """Colocar el componente en grid"""
        self.frame.grid(**kwargs)
