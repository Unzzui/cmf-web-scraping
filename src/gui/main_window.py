#!/usr/bin/env python3
"""
Ventana principal del CMF Financial Data Scraper - Versión Modular
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue
import logging
import sys
import os
from datetime import datetime

# Importar componentes locales
from .styles.professional_theme import ProfessionalStyles, get_font_config, get_color_config
from .components.company_table import CompanyTable
from .components.control_panel import ControlPanel
from .components.log_viewer import LogViewer
from .components.progress_dialog import ProgressDialog
from .components.xbrl_status_panel import XBRLStatusPanel
from .components.xbrl_confirmation_dialog import XBRLConfirmationDialog
from .utils.csv_manager import CSVManager
from .utils.system_utils import open_folder
from .utils.console_dashboard import ConsoleXBRLDashboard

# Importar módulos del proyecto
try:
    from ..xbrl.cmf_xbrl_downloader import download_cmf_xbrl
    XBRL_AVAILABLE = True
    print("✅ Módulo XBRL disponible")
except ImportError as e:
    print(f"⚠️ Error importando el descargador XBRL: {e}")
    print("La funcionalidad XBRL no estará disponible")
    XBRL_AVAILABLE = False
    download_cmf_xbrl = None

# Nota: cmf_annual_reports_scraper.py no existe en el proyecto actual
SCRAPER_AVAILABLE = False
scrape_cmf_data = None
verify_data_order = None


class CMFScraperGUI:
    """Ventana principal del CMF Scraper con arquitectura modular"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("CMF Financial Data Scraper - Professional Edition")
        
        # Configurar ventana responsiva
        self._setup_responsive_window()
        
        # Variables de estado
        self.is_running = False
        self.output_queue = queue.Queue()
        self.scraping_thread = None
        self.progress_data = {  # Datos compartidos para el progreso
            'current': 0,
            'total': 0,
            'company': '',
            'status': '',
            'files': 0
        }
        
        # Managers y utilidades
        self.csv_manager = CSVManager()
        
        # Componentes de la GUI
        self.company_table = None
        self.control_panel = None
        self.log_viewer = None
        self.xbrl_status_panel = None
        self.console_dashboard = None
        
        # Configurar la aplicación
        self._setup_application()
    
    def _setup_responsive_window(self):
        """Configurar ventana responsiva que se adapte al tamaño de pantalla"""
        # Obtener dimensiones de la pantalla
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # Calcular tamaño óptimo de ventana (80% de la pantalla)
        window_width = int(screen_width * 0.85)
        window_height = int(screen_height * 0.85)
        
        # Establecer tamaño mínimo
        min_width = 1200
        min_height = 800
        
        # Ajustar para pantallas pequeñas
        if screen_width < 1440:
            window_width = min(window_width, screen_width - 100)
            window_height = min(window_height, screen_height - 100)
            min_width = 1000
            min_height = 700
        
        # Centrar ventana
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        
        # Configurar geometría
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.minsize(min_width, min_height)
        
        # Maximizar automáticamente en pantallas muy pequeñas
        if screen_width < 1366 or screen_height < 768:
            self.root.state('zoomed')  # Maximizar en Linux
    
    def _setup_application(self):
        """Configurar la aplicación completa"""
        # Configurar captura de logs del scraper
        self._setup_scraper_logging()
        
        # Configurar estilos
        self._setup_styles()
        
        # Crear interfaz
        self._create_interface()
        
        # Configurar eventos
        self._setup_events()
        
        # Cargar datos iniciales
        self._load_initial_data()
        
        # Iniciar monitoreo
        self._start_monitoring()
    
    def _setup_scraper_logging(self):
        """Configurar captura de logs del scraper para mostrar en la GUI"""
        
        class GUILogHandler(logging.Handler):
            """Handler personalizado para capturar logs del scraper"""
            def __init__(self, output_queue):
                super().__init__()
                self.output_queue = output_queue
            
            def emit(self, record):
                # No interceptar logs si el usuario prefiere consola
                pass
        
        # Crear y configurar el handler
        self.gui_log_handler = GUILogHandler(self.output_queue)
        self.gui_log_handler.setLevel(logging.INFO)
        
        # Formato sin timestamp ya que el log viewer lo agregará
        formatter = logging.Formatter('%(message)s')
        self.gui_log_handler.setFormatter(formatter)
        
        # Obtener el logger del scraper y agregar nuestro handler
        root_logger = logging.getLogger()
        
        # Por preferencia del usuario, no agregamos handler a la GUI para no duplicar ni mover logs
        
        # También configurar el logger específico del scraper si existe
        try:
            scraper_logger = logging.getLogger('cmf_annual_reports_scraper')
            scraper_logger.addHandler(self.gui_log_handler)
        except:
            pass
    
    def _setup_styles(self):
        """Configurar estilos profesionales"""
        self.root.configure(bg=ProfessionalStyles.BACKGROUND)
        self.style = ProfessionalStyles.setup_styles()
        self.fonts = get_font_config()
        self.colors = get_color_config()
    
    def _create_interface(self):
        """Crear la interfaz principal"""
        # Contenedor principal con scrollbar para pantallas pequeñas
        main_container = tk.Frame(self.root, bg=self.colors['background'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Header
        self._create_header(main_container)
        
        # Panel principal dividido
        content_frame = tk.Frame(main_container, bg=self.colors['background'])
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Detectar tamaño de pantalla para layout responsivo
        screen_width = self.root.winfo_screenwidth()
        
        if screen_width >= 1440:
            # Layout horizontal para pantallas grandes
            self._create_horizontal_layout(content_frame)
        else:
            # Layout vertical para pantallas pequeñas
            self._create_vertical_layout(content_frame)
    
    def _create_horizontal_layout(self, parent):
        """Crear layout horizontal para pantallas grandes"""
        # Columna izquierda (60%)
        left_panel = tk.Frame(parent, bg=self.colors['background'])
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Columna derecha (40%)
        right_panel = tk.Frame(parent, bg=self.colors['background'], width=500)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_panel.pack_propagate(False)
        
        # Crear secciones
        self._create_data_section(left_panel)
        self._create_company_section(left_panel)
        self._create_control_section(right_panel)
        # Panel de estado XBRL justo antes del log
        self._create_status_section(right_panel)
        self._create_log_section(right_panel)
    
    def _create_vertical_layout(self, parent):
        """Crear layout vertical para pantallas pequeñas"""
        # Canvas con scrollbar para contenido vertical
        canvas = tk.Canvas(parent, bg=self.colors['background'])
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.colors['background'])
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Panel superior para datos y controles
        top_frame = tk.Frame(scrollable_frame, bg=self.colors['background'])
        top_frame.pack(fill=tk.X, pady=(0, 10))
        
        # Sección de datos (más compacta)
        data_frame = tk.Frame(top_frame, bg=self.colors['background'])
        data_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        self._create_data_section(data_frame)
        
        # Sección de control (más compacta)
        control_frame = tk.Frame(top_frame, bg=self.colors['background'], width=350)
        control_frame.pack(side=tk.RIGHT, fill=tk.Y)
        control_frame.pack_propagate(False)
        self._create_control_section(control_frame)
        
        # Panel inferior para tabla de empresas
        self._create_company_section(scrollable_frame)
        
        # Panel de estado XBRL antes del log
        self._create_status_section(scrollable_frame)

        # Panel de logs al final
        self._create_log_section(scrollable_frame)
        
        # Empaquetar canvas y scrollbar
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
    
    def _create_header(self, parent):
        """Crear header con título"""
        header_frame = tk.Frame(parent, bg=self.colors['background'], height=80)
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
    
    def _create_data_section(self, parent):
        """Crear sección de manejo de datos"""
        data_frame = ttk.LabelFrame(parent, 
                                   text="Archivo de Datos", 
                                   style='Card.TLabelframe',
                                   padding=15)
        data_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Fila para selección de archivo
        file_row = tk.Frame(data_frame, bg=self.colors['background'])
        file_row.pack(fill=tk.X, pady=(0, 10))
        
        tk.Label(file_row, text="Archivo CSV:", 
                font=self.fonts['header_font'], 
                bg=self.colors['background'], 
                fg=self.colors['primary']).pack(side=tk.LEFT)
        
        self.csv_path_var = tk.StringVar()
        path_entry = ttk.Entry(file_row, 
                              textvariable=self.csv_path_var, 
                              state='readonly',
                              style='Professional.TEntry',
                              font=self.fonts['body_font'])
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 10))
        
        # Botones de archivo
        btn_frame = tk.Frame(file_row, bg=self.colors['background'])
        btn_frame.pack(side=tk.RIGHT)
        
        ttk.Button(btn_frame, text="Examinar", 
                  command=self._browse_csv,
                  style='Primary.TButton').pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Button(btn_frame, text="Recargar", 
                  command=self._reload_csv,
                  style='Primary.TButton').pack(side=tk.LEFT)
        
        # Información del archivo
        self.csv_info_label = ttk.Label(data_frame, text="", style='Info.TLabel')
        self.csv_info_label.pack(anchor=tk.W)
    
    def _create_company_section(self, parent):
        """Crear sección de empresas"""
        self.company_table = CompanyTable(parent, on_selection_change=self._on_selection_change)
        self.company_table.pack(fill=tk.BOTH, expand=True)
    
    def _create_control_section(self, parent):
        """Crear sección de control"""
        self.control_panel = ControlPanel(
            parent,
            on_start=self._start_scraping,
            on_stop=self._stop_scraping,
            on_open_results=self._open_results_folder,
            on_start_xbrl=self._start_xbrl_download  # Agregar callback para XBRL
        )
        self.control_panel.pack(fill=tk.X, pady=(0, 15))
    
    def _create_log_section(self, parent):
        """Crear sección de log"""
        self.log_viewer = LogViewer(parent, height=15)
        self.log_viewer.pack(fill=tk.BOTH, expand=True)

    def _create_status_section(self, parent):
        """Crear sección de estado XBRL (tabla estática)"""
        try:
            self.xbrl_status_panel = XBRLStatusPanel(parent, style='Card.TLabelframe')
            self.xbrl_status_panel.pack(fill=tk.BOTH, expand=False, pady=(0, 10))
        except Exception:
            self.xbrl_status_panel = None
    
    def _setup_events(self):
        """Configurar eventos de la aplicación"""
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)
    
    def _load_initial_data(self):
        """Cargar datos iniciales"""
        self.root.after(100, self._load_default_csv)
    
    def _start_monitoring(self):
        """Iniciar monitoreo de colas y actualizaciones"""
        self.root.after(100, self._check_output_queue)
    
    # === MÉTODOS DE MANEJO DE CSV ===
    
    def _load_default_csv(self):
        """Cargar archivo CSV por defecto"""
        success, message = self.csv_manager.load_default()
        
        if success:
            self.csv_path_var.set(self.csv_manager.get_current_path())
            self.csv_info_label.config(text=message)
            self.company_table.load_data(self.csv_manager.get_companies_data())
            self.log_viewer.log(f"CSV cargado exitosamente: {self.csv_manager.get_company_count()} empresas")
        else:
            self.csv_info_label.config(text=message)
            self.log_viewer.log(f"ADVERTENCIA: {message}", "WARNING")
    
    def _browse_csv(self):
        """Examinar y seleccionar archivo CSV"""
        file_path = filedialog.askopenfilename(
            title="Seleccionar archivo CSV de empresas",
            filetypes=[("Archivos CSV", "*.csv"), ("Todos los archivos", "*.*")],
            initialdir="./data"
        )
        
        if file_path:
            success, message = self.csv_manager.load_csv(file_path)
            
            if success:
                self.csv_path_var.set(file_path)
                self.csv_info_label.config(text=message)
                self.company_table.load_data(self.csv_manager.get_companies_data())
                self.log_viewer.log(f"CSV cargado desde archivo: {file_path}")
            else:
                self.csv_info_label.config(text=message)
                self.log_viewer.log(f"ERROR: {message}", "ERROR")
                messagebox.showerror("Error", message)
    
    def _reload_csv(self):
        """Recargar el archivo CSV actual"""
        success, message = self.csv_manager.reload_current()
        
        if success:
            self.csv_info_label.config(text=message)
            self.company_table.load_data(self.csv_manager.get_companies_data())
            self.log_viewer.log("CSV recargado exitosamente")
        else:
            messagebox.showwarning("Advertencia", message)
            self.log_viewer.log(f"ERROR: {message}", "ERROR")
    
    # === MÉTODOS DE SCRAPING ===
    
    def _start_scraping(self, config):
        """Iniciar proceso de scraping"""
        if self.is_running or not config:
            return
        
        selected_companies = self.company_table.get_selected_companies()
        if not selected_companies:
            messagebox.showwarning("Advertencia", "Seleccione al menos una empresa")
            return
        
        # Validar configuración
        if config['start_year'] <= config['end_year']:
            messagebox.showerror("Error", "El año inicial debe ser mayor que el año final")
            return
        
        # Configurar estado de ejecución
        self.is_running = True
        self.control_panel.set_running_state(True)
        
        # Log inicial
        self.log_viewer.log("=" * 60)
        self.log_viewer.log("INICIANDO PROCESO DE SCRAPING")
        self.log_viewer.log("=" * 60)
        self.log_viewer.log(f"Empresas seleccionadas: {len(selected_companies)}")
        self.log_viewer.log(f"Período: {config['start_year']} a {config['end_year']} (paso: {config['step']})")
        mode_label = 'Anual'
        if config.get('frequency') == 'total':
            mode_label = 'Total'
        elif config.get('frequency') == 'quarterly' or config['quarterly']:
            mode_label = 'Trimestral'
        self.log_viewer.log(f"Modo: {mode_label}")
        self.log_viewer.log(f"Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Iniciar thread de scraping
        self.scraping_thread = threading.Thread(
            target=self._run_scraping,
            args=(selected_companies, config),
            daemon=True
        )
        self.scraping_thread.start()
    
    def _run_scraping(self, companies, config):
        """Ejecutar scraping en paralelo usando ThreadPoolExecutor"""
        try:
            results = []
            total_companies = len(companies)
            max_workers = config.get('max_workers', 4)  # Puedes ajustar el valor por defecto

            import threading
            def scrape_one(company):
                worker_id = threading.get_ident()
                if not self.is_running:
                    print(f"[WORKER {worker_id}] CANCELLED: {company['razon_social']} ({company['rut_sin_guion']})")
                    return (company['razon_social'], company['rut_sin_guion'], None, "CANCELLED")
                rut_sin_guion = company['rut_sin_guion']
                try:
                    print(f"[WORKER {worker_id}] Procesando: {company['razon_social']} ({rut_sin_guion})")
                    self.output_queue.put(('progress', f"Procesando: {company['razon_social']}"))
                    self.output_queue.put(('log', f"\n{'#' * 50}"))
                    self.output_queue.put(('log', f"EMPRESA: {company['razon_social']}"))
                    self.output_queue.put(('log', f"RUT: {company['rut']} (Sin guión: {rut_sin_guion})"))
                    self.output_queue.put(('log', f"{'#' * 50}"))
                    output_file = scrape_cmf_data(
                        rut=rut_sin_guion,
                        start_year=config['start_year'],
                        end_year=config['end_year'],
                        step=config['step'],
                        headless=True,
                        quarterly=config['quarterly']
                    )
                    print(f"[WORKER {worker_id}] Completado: {company['razon_social']} ({rut_sin_guion}) -> {output_file}")
                    self.output_queue.put(('log', f"{company['razon_social']}: Completado exitosamente", "SUCCESS"))
                    self.output_queue.put(('log', f"Archivo: {output_file}"))
                    verify_data_order(output_file)
                    return (company['razon_social'], rut_sin_guion, output_file, "SUCCESS")
                except Exception as e:
                    error_msg = f"Error procesando {company['razon_social']}: {str(e)}"
                    print(f"[WORKER {worker_id}] ERROR: {error_msg}")
                    self.output_queue.put(('log', error_msg, "ERROR"))
                    return (company['razon_social'], rut_sin_guion, None, f"ERROR: {str(e)}")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_company = {executor.submit(scrape_one, company): company for company in companies}
                for i, future in enumerate(as_completed(future_to_company), 1):
                    if not self.is_running:
                        break
                    result = future.result()
                    results.append(result)
                    self.output_queue.put(('progress', f"Procesados: {i}/{total_companies} (Workers: {max_workers})"))

            # Resumen final
            if self.is_running:
                self._generate_final_summary(results)
            else:
                self.output_queue.put(('progress', "Proceso detenido por el usuario"))
        except Exception as e:
            self.output_queue.put(('log', f"Error fatal en el proceso: {str(e)}", "ERROR"))
            self.output_queue.put(('progress', f"Error fatal: {str(e)}"))
        finally:
            self.output_queue.put(('finished', None))
    
    def _generate_final_summary(self, results):
        """Generar resumen final del procesamiento"""
        self.output_queue.put(('log', f"\n{'=' * 60}"))
        self.output_queue.put(('log', "RESUMEN DEL PROCESAMIENTO"))
        self.output_queue.put(('log', f"{'=' * 60}"))
        
        successful = sum(1 for _, _, _, status in results if status == "SUCCESS")
        self.output_queue.put(('log', f"Empresas procesadas exitosamente: {successful}/{len(results)}", "SUCCESS"))
        
        for razon_social, rut, file_path, status in results:
            if status == "SUCCESS":
                self.output_queue.put(('log', f"EXITOSO: {razon_social}: {file_path}", "SUCCESS"))
            else:
                self.output_queue.put(('log', f"ERROR: {razon_social}: {status}", "ERROR"))
        
        self.output_queue.put(('progress', f"Proceso completado: {successful}/{len(results)} empresas exitosas"))
    
    def _stop_scraping(self):
        """Detener el proceso de scraping"""
        if self.is_running:
            self.is_running = False
            self.log_viewer.log("Deteniendo proceso de scraping...", "WARNING")
            self.control_panel.update_progress("Deteniendo proceso...")
    
    def _start_xbrl_download(self, config):
        """Iniciar proceso de descarga XBRL con confirmación mejorada"""
        # Verificar si XBRL está disponible
        if not XBRL_AVAILABLE:
            messagebox.showerror("Error", 
                               "La funcionalidad XBRL no está disponible.\n"
                               "Asegúrese de tener instalado selenium:\n"
                               "pip install selenium")
            return
        
        if self.is_running or not config:
            return
        
        selected_companies = self.company_table.get_selected_companies()
        if not selected_companies:
            messagebox.showwarning("Advertencia", "Seleccione al menos una empresa")
            return
        
        # Validar configuración
        if config['start_year'] <= config['end_year']:
            messagebox.showerror("Error", "El año inicial debe ser mayor que el año final")
            return
        
        # Mostrar diálogo de confirmación
        confirmation_dialog = XBRLConfirmationDialog(self.root, selected_companies, config)
        confirmed = confirmation_dialog.show()
        
        if not confirmed:
            return
        
        # Iniciar panel de consola estático (preferido por el usuario)
        # Mute stdout logs mientras el dashboard está activo para evitar que el log de procesos
        # "ensucie" el render del tablero estático. Todo queda en ./data/debug/xbrl_run.log
        self.console_dashboard = ConsoleXBRLDashboard(selected_companies, mute_stdout_logs=True, log_to_file=True)
        self.console_dashboard.start()

        # Configurar estado de ejecución
        self.is_running = True
        self.control_panel.set_running_state(True)
        self.control_panel.update_progress("Iniciando descarga XBRL...")
        self.log_viewer.log(f"Iniciando descarga XBRL para {len(selected_companies)} empresas")
        
        # Iniciar thread de descarga directamente sin diálogo
        self.scraping_thread = threading.Thread(
            target=self._run_xbrl_download,
            args=(selected_companies, config),
            daemon=False
        )
        self.scraping_thread.start()
    
    def _run_xbrl_download(self, companies, config):
        """Ejecutar descarga XBRL en paralelo usando ThreadPoolExecutor"""
        try:
            results = []
            total_companies = len(companies)
            max_workers = config.get('max_workers', 4)

            def download_one(company):
                worker_id = threading.get_ident()
                if not self.is_running:
                    return (company['razon_social'], company['rut_sin_guion'], None, 0, "CANCELLED")
                rut_sin_guion = company['rut_sin_guion']
                try:
                    # Estado: en progreso (consola)
                    if self.console_dashboard is not None:
                        self.console_dashboard.update(rut_sin_guion, estado='En progreso', worker=worker_id)
                    self.output_queue.put(('progress', f"Descargando XBRL: {company['razon_social']} (Worker {worker_id})"))
                    self.output_queue.put(('log', f"\n{'#' * 50}"))
                    self.output_queue.put(('log', f"DESCARGA XBRL: {company['razon_social']} (Worker {worker_id})"))
                    self.output_queue.put(('log', f"RUT: {company['rut']} (Sin guión: {rut_sin_guion})"))
                    self.output_queue.put(('log', f"{'#' * 50}"))
                    if not XBRL_AVAILABLE or download_cmf_xbrl is None:
                        raise ImportError("El módulo cmf_xbrl_downloader no está disponible. Instale selenium: pip install selenium")
                    def hook(rut_cb, current, total, year, month, eta_sec, status):
                        # Refresca progreso/periodo/eta del tablero
                        if self.console_dashboard is not None:
                            prog = f"{current}/{total}" if total else '-'
                            per = f"{year}-{month:02d}" if (year and month) else '-'
                            # Actualizar estrategia si corresponde
                            if status == 'strategy_direct':
                                try:
                                    self.console_dashboard.update_strategy(rut_cb, 'Directa')
                                except Exception:
                                    pass
                            elif status == 'strategy_browser' or status == 'strategy_browser_fallback':
                                try:
                                    self.console_dashboard.update_strategy(rut_cb, 'Browser')
                                except Exception:
                                    pass
                            # Pequeños estados de diagnóstico vía status keywords
                            try:
                                if status == 'in_progress' and per != '-':
                                    self.console_dashboard.update_diag(rut_cb, note=f"Procesando {per}")
                                elif status == 'period_completed' and per != '-':
                                    self.console_dashboard.update_diag(rut_cb, note=f"Completado {per}")
                                elif isinstance(status, str) and status.startswith('diag_get|'):
                                    url_get = status.split('|', 1)[1] if '|' in status else ''
                                    self.console_dashboard.update_diag(rut_cb, get_url=url_get)
                                elif isinstance(status, str) and status.startswith('diag_http|'):
                                    parts = status.split('|')
                                    http = parts[1] if len(parts) > 1 else '-'
                                    ctype = parts[2] if len(parts) > 2 else '-'
                                    clen = parts[3] if len(parts) > 3 else '-'
                                    self.console_dashboard.update_diag(rut_cb, http_status=http, content_type=ctype, note=f"CL={clen}")
                            except Exception:
                                pass
                            self.console_dashboard.update(rut_cb,
                                progreso=prog,
                                periodo=per,
                                eta_seconds=eta_sec,
                                current=current,
                                total=total)

                    target_dir, downloaded_files = download_cmf_xbrl(
                        rut=rut_sin_guion,
                        start_year=config['start_year'],
                        end_year=config['end_year'],
                        step=config['step'],
                        headless=True,
                        quarterly=config['quarterly'],
                        mode=config.get('frequency'),
                        progress_hook=hook,
                        strategy=config.get('strategy', 'browser'),
                        skip_existing=config.get('skip_existing', True),
                        allow_direct_debug=(os.getenv('CMF_XBRL_ALLOW_DIRECT', '0') == '1' or config.get('strategy') == 'direct')
                    )
                    # Estado: completado (consola)
                    if self.console_dashboard is not None:
                        self.console_dashboard.update(rut_sin_guion, estado='Completado', worker=worker_id, archivos=len(downloaded_files))
                    self.output_queue.put(('log', f"Archivos descargados y extraídos: {len(downloaded_files)}"))
                    self.output_queue.put(('log', f"{company['razon_social']}: Descarga XBRL completada exitosamente (Worker {worker_id})", "SUCCESS"))
                    self.output_queue.put(('log', f"Directorio: {target_dir}"))
                    return (company['razon_social'], rut_sin_guion, target_dir, len(downloaded_files), "SUCCESS")
                except Exception as e:
                    error_msg = str(e)
                    # Estado: error (consola)
                    if self.console_dashboard is not None:
                        self.console_dashboard.update(rut_sin_guion, estado='Error', worker=worker_id)
                    self.output_queue.put(('log', f"ERROR en {company['razon_social']}: {error_msg} (Worker {worker_id})", "ERROR"))
                    return (company['razon_social'], rut_sin_guion, None, 0, f"ERROR: {error_msg}")

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_company = {executor.submit(download_one, company): company for company in companies}
                for i, future in enumerate(as_completed(future_to_company), 1):
                    if not self.is_running:
                        break
                    result = future.result()
                    results.append(result)
                    self.output_queue.put(('progress', f"Descargados: {i}/{total_companies} (Workers: {max_workers})"))

            # Finalizar proceso
            self.is_running = False
            self.output_queue.put(('finished', results))
            # Detener dashboard de consola
            if self.console_dashboard is not None:
                self.console_dashboard.stop()
                self.console_dashboard = None

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.is_running = False
            self.output_queue.put(('error', f"Error crítico en descarga XBRL: {str(e)}"))
            if self.console_dashboard is not None:
                self.console_dashboard.stop()
                self.console_dashboard = None
    
    def _process_xbrl_results(self, results):
        """Procesar resultados de la descarga XBRL"""
        successful = sum(1 for _, _, _, _, status in results if status == "SUCCESS")
        total_files = sum(files for _, _, _, files, status in results if status == "SUCCESS")
        
        self.control_panel.set_running_state(False)
        self.control_panel.update_progress(f"Descarga XBRL completada: {successful}/{len(results)} empresas exitosas")
        
        # Resumen final
        self.log_viewer.log("\n" + "="*70, "INFO")
        self.log_viewer.log("RESUMEN FINAL DE DESCARGA XBRL", "INFO")
        self.log_viewer.log("="*70, "INFO")
        self.log_viewer.log(f"Total de empresas procesadas: {len(results)}", "INFO")
        self.log_viewer.log(f"Descargas exitosas: {successful}", "SUCCESS")
        self.log_viewer.log(f"Errores: {len(results) - successful}", "ERROR")
        self.log_viewer.log(f"Total de archivos XBRL descargados: {total_files}", "INFO")
        
        # Mostrar mensaje de finalización
        if successful > 0:
            messagebox.showinfo(
                "Descarga XBRL Completada",
                f"Descarga finalizada exitosamente!\n\n"
                f"✅ Empresas procesadas: {successful}/{len(results)}\n"
                f"📁 Archivos XBRL descargados: {total_files}\n"
                f"📂 Ubicación: ./data/XBRL/\n\n"
                f"Puede abrir la carpeta de resultados desde el menú 'Archivos'."
            )
        else:
            messagebox.showerror(
                "Error en Descarga XBRL",
                f"No se pudieron descargar archivos XBRL.\n\n"
                f"❌ Todas las {len(results)} empresas fallaron\n\n"
                f"Revise el log para más detalles."
            )
        
        # Log detallado de resultados
        for razon_social, rut, target_dir, files, status in results:
            if status == "SUCCESS":
                self.log_viewer.log(f"EXITOSO: {razon_social}: {target_dir} ({files} archivos)", "SUCCESS")
            else:
                self.log_viewer.log(f"ERROR: {razon_social}: {status}", "ERROR")
    
    def _generate_xbrl_summary(self, results):
        """Generar resumen final de la descarga XBRL"""
        self.output_queue.put(('log', f"\n{'=' * 60}"))
        self.output_queue.put(('log', "RESUMEN DE DESCARGA XBRL"))
        self.output_queue.put(('log', f"{'=' * 60}"))
        
        successful = sum(1 for _, _, _, _, status in results if status == "SUCCESS")
        total_files = sum(file_count for _, _, _, file_count, status in results if status == "SUCCESS")
        
        self.output_queue.put(('log', f"Empresas procesadas exitosamente: {successful}/{len(results)}", "SUCCESS"))
        self.output_queue.put(('log', f"Total de archivos XBRL descargados: {total_files}", "SUCCESS"))
        
        for razon_social, rut, target_dir, file_count, status in results:
            if status == "SUCCESS":
                self.output_queue.put(('log', f"EXITOSO: {razon_social}: {file_count} archivos en {target_dir}", "SUCCESS"))
            else:
                self.output_queue.put(('log', f"ERROR: {razon_social}: {status}", "ERROR"))
        
        self.output_queue.put(('progress', f"Descarga XBRL completada: {successful}/{len(results)} empresas, {total_files} archivos"))
        
        # Información sobre ubicación de archivos
        self.output_queue.put(('log', f"\n📁 Los archivos XBRL se encuentran en: ./data/XBRL/"))
        self.output_queue.put(('log', f"🗂️ Cada empresa tiene su propia carpeta con archivos extraídos"))
        self.output_queue.put(('log', f"📋 Los archivos ZIP originales fueron eliminados después de la extracción"))
    
    def _check_output_queue(self):
        """Verificar cola de output y actualizar UI"""
        messages_processed = 0
        try:
            while True:
                msg_type, *args = self.output_queue.get_nowait()
                messages_processed += 1
                print(f"DEBUG: Procesando mensaje tipo '{msg_type}' (total: {messages_processed})")
                
                if msg_type == 'log':
                    message = args[0]
                    level = args[1] if len(args) > 1 else "INFO"
                    self.log_viewer.log(message, level)
                # elif msg_type == 'scraper_log':
                #     # Desactivado: logs quedan en consola según preferencia del usuario
                #     pass
                elif msg_type == 'progress':
                    self.control_panel.update_progress(args[0])
                elif msg_type == 'xbrl_status':
                    # Actualización del panel de estado XBRL desde workers
                    try:
                        if self.xbrl_status_panel is not None:
                            payload = args[0] if args else {}
                            rut = payload.get('rut')
                            estado = payload.get('estado')
                            worker = payload.get('worker')
                            archivos = payload.get('archivos')
                            if rut:
                                self.xbrl_status_panel.update_status(rut, estado=estado, worker=worker, archivos=archivos)
                    except Exception:
                        pass
                elif msg_type == 'progress_dialog_setup':
                    # Configurar diálogo de progreso desde el thread principal
                    print(f"DEBUG: Configurando diálogo de progreso con {args[0]} empresas")
                    if hasattr(self, 'progress_dialog') and self.progress_dialog:
                        total_companies = args[0]
                        self.progress_dialog.set_total_companies(total_companies)
                        print(f"DEBUG: Diálogo configurado correctamente")
                    else:
                        print("DEBUG: ERROR - progress_dialog no encontrado")
                elif msg_type == 'progress_dialog':
                    # Actualizar diálogo de progreso desde el thread principal
                    print(f"DEBUG: Actualizando progreso del diálogo: {args[0]}")
                    if hasattr(self, 'progress_dialog') and self.progress_dialog:
                        data = args[0]
                        self.progress_dialog.update_progress(
                            current=data['current'],
                            company_name=data['company_name'],
                            status=data['status']
                        )
                        print(f"DEBUG: Progreso actualizado correctamente")
                    else:
                        print("DEBUG: ERROR - progress_dialog no encontrado para actualización")
                elif msg_type == 'close_progress_dialog':
                    # Cerrar diálogo de progreso desde el thread principal
                    print("DEBUG: Cerrando diálogo de progreso")
                    if hasattr(self, 'progress_dialog') and self.progress_dialog:
                        self.progress_dialog.close()
                        self.progress_dialog = None
                        print("DEBUG: Diálogo cerrado correctamente")
                    else:
                        print("DEBUG: WARNING - progress_dialog ya estaba cerrado")
                elif msg_type == 'finished':
                    results = args[0] if len(args) > 0 and args[0] is not None else None
                    if results is not None:
                        # Es descarga XBRL
                        self._process_xbrl_results(results)
                    else:
                        # Es scraping normal
                        self._finish_scraping()
                    break
                elif msg_type == 'error':
                    error_msg = args[0] if len(args) > 0 else "Error desconocido"
                    self.log_viewer.log(error_msg, "ERROR")
                    self._finish_scraping()
                    break
                    
        except queue.Empty:
            if messages_processed > 0:
                print(f"DEBUG: Procesados {messages_processed} mensajes en este ciclo")
            pass
        
        # Programar siguiente verificación
        self.root.after(100, self._check_output_queue)
    
    def _finish_scraping(self):
        """Finalizar proceso de scraping"""
        self.is_running = False
        self.control_panel.set_running_state(False)
        self.log_viewer.log(f"Proceso finalizado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # === MÉTODOS DE EVENTOS ===
    
    def _on_selection_change(self):
        """Manejar cambio de selección en la tabla"""
        # Aquí se puede agregar lógica adicional cuando cambie la selección
        pass
    
    def _open_results_folder(self):
        """Abrir carpeta de resultados con opciones"""
        # Crear ventana de selección
        choice_window = tk.Toplevel(self.root)
        choice_window.title("Seleccionar Carpeta de Resultados")
        choice_window.geometry("400x200")
        choice_window.resizable(False, False)
        choice_window.transient(self.root)
        choice_window.grab_set()
        
        # Centrar ventana
        choice_window.update_idletasks()
        x = (choice_window.winfo_screenwidth() // 2) - (choice_window.winfo_width() // 2)
        y = (choice_window.winfo_screenheight() // 2) - (choice_window.winfo_height() // 2)
        choice_window.geometry(f"400x200+{x}+{y}")
        
        # Configurar estilo
        choice_window.configure(bg=self.colors['background'])
        
        # Título
        title_label = tk.Label(choice_window, 
                              text="Seleccionar Carpeta de Resultados",
                              font=self.fonts['header_font'],
                              bg=self.colors['background'],
                              fg=self.colors['primary'])
        title_label.pack(pady=20)
        
        # Frame para botones
        buttons_frame = tk.Frame(choice_window, bg=self.colors['background'])
        buttons_frame.pack(expand=True, fill='both', padx=20, pady=10)
        
        # Botón para carpeta Reports (Excel)
        reports_btn = ttk.Button(buttons_frame,
                                text="📊 Carpeta Reports (Archivos Excel)",
                                command=lambda: self._open_specific_folder("./data/Reports", choice_window),
                                style='Success.TButton')
        reports_btn.pack(fill='x', pady=5)
        
        # Botón para carpeta XBRL
        xbrl_btn = ttk.Button(buttons_frame,
                             text="📁 Carpeta XBRL (Archivos XBRL)",
                             command=lambda: self._open_specific_folder("./data/XBRL", choice_window),
                             style='Primary.TButton')
        xbrl_btn.pack(fill='x', pady=5)
        
        # Botón para cancelar
        cancel_btn = ttk.Button(buttons_frame,
                               text="❌ Cancelar",
                               command=choice_window.destroy,
                               style='Secondary.TButton')
        cancel_btn.pack(fill='x', pady=5)
    
    def _open_specific_folder(self, folder_path, parent_window=None):
        """Abrir una carpeta específica"""
        if parent_window:
            parent_window.destroy()
        
        if open_folder(folder_path):
            self.log_viewer.log(f"Abriendo carpeta: {folder_path}")
        else:
            if not os.path.exists(folder_path):
                messagebox.showinfo("Información", f"La carpeta no existe aún: {folder_path}")
            else:
                messagebox.showerror("Error", f"No se pudo abrir la carpeta: {folder_path}")
    
    def _on_closing(self):
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
    root.mainloop()


if __name__ == "__main__":
    main()
