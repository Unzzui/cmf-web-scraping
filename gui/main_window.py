#!/usr/bin/env python3
"""
Ventana principal del CMF Financial Data Scraper - Versión Modular
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import queue
import sys
import os
from datetime import datetime

# Importar componentes locales
from .styles.professional_theme import ProfessionalStyles, get_font_config, get_color_config
from .components.company_table import CompanyTable
from .components.control_panel import ControlPanel
from .components.log_viewer import LogViewer
from .utils.csv_manager import CSVManager
from .utils.system_utils import open_folder

# Importar scraper
try:
    from cmf_annual_reports_scraper import scrape_cmf_data, verify_data_order
except ImportError as e:
    print(f"Error importando el scraper: {e}")
    print("Asegúrate de que cmf_annual_reports_scraper.py esté en el mismo directorio")
    sys.exit(1)


class CMFScraperGUI:
    """Ventana principal del CMF Scraper con arquitectura modular"""
    
    def __init__(self, root):
        self.root = root
        self.root.title("CMF Financial Data Scraper - Professional Edition")
        self.root.geometry("1400x900")
        
        # Variables de estado
        self.is_running = False
        self.output_queue = queue.Queue()
        self.scraping_thread = None
        
        # Managers y utilidades
        self.csv_manager = CSVManager()
        
        # Componentes de la GUI
        self.company_table = None
        self.control_panel = None
        self.log_viewer = None
        
        # Configurar la aplicación
        self._setup_application()
    
    def _setup_application(self):
        """Configurar la aplicación completa"""
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
    
    def _setup_styles(self):
        """Configurar estilos profesionales"""
        self.root.configure(bg=ProfessionalStyles.BACKGROUND)
        self.style = ProfessionalStyles.setup_styles()
        self.fonts = get_font_config()
        self.colors = get_color_config()
    
    def _create_interface(self):
        """Crear la interfaz principal"""
        # Contenedor principal
        main_container = tk.Frame(self.root, bg=self.colors['background'])
        main_container.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        
        # Header
        self._create_header(main_container)
        
        # Panel principal dividido
        content_frame = tk.Frame(main_container, bg=self.colors['background'])
        content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Columna izquierda (60%)
        left_panel = tk.Frame(content_frame, bg=self.colors['background'])
        left_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        # Columna derecha (40%)
        right_panel = tk.Frame(content_frame, bg=self.colors['background'], width=500)
        right_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))
        right_panel.pack_propagate(False)
        
        # Crear secciones
        self._create_data_section(left_panel)
        self._create_company_section(left_panel)
        self._create_control_section(right_panel)
        self._create_log_section(right_panel)
    
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
            on_open_results=self._open_results_folder
        )
        self.control_panel.pack(fill=tk.X, pady=(0, 15))
    
    def _create_log_section(self, parent):
        """Crear sección de log"""
        self.log_viewer = LogViewer(parent, height=15)
        self.log_viewer.pack(fill=tk.BOTH, expand=True)
    
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
        self.log_viewer.log(f"Hora de inicio: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Iniciar thread de scraping
        self.scraping_thread = threading.Thread(
            target=self._run_scraping,
            args=(selected_companies, config),
            daemon=True
        )
        self.scraping_thread.start()
    
    def _run_scraping(self, companies, config):
        """Ejecutar scraping en thread separado"""
        try:
            results = []
            total_companies = len(companies)
            
            for i, company in enumerate(companies, 1):
                if not self.is_running:
                    break
                
                # Actualizar progreso
                progress_msg = f"Procesando {i}/{total_companies}: {company['razon_social']}"
                self.output_queue.put(('progress', progress_msg))
                
                try:
                    rut_sin_guion = company['rut_sin_guion']
                    
                    self.output_queue.put(('log', f"\n{'#' * 50}"))
                    self.output_queue.put(('log', f"EMPRESA {i}/{total_companies}: {company['razon_social']}"))
                    self.output_queue.put(('log', f"RUT: {company['rut']} (Sin guión: {rut_sin_guion})"))
                    self.output_queue.put(('log', f"{'#' * 50}"))
                    
                    # Ejecutar scraping
                    output_file = scrape_cmf_data(
                        rut=rut_sin_guion,
                        start_year=config['start_year'],
                        end_year=config['end_year'],
                        step=config['step']
                    )
                    
                    results.append((company['razon_social'], rut_sin_guion, output_file, "SUCCESS"))
                    self.output_queue.put(('log', f"{company['razon_social']}: Completado exitosamente", "SUCCESS"))
                    self.output_queue.put(('log', f"Archivo: {output_file}"))
                    
                    # Verificar datos
                    verify_data_order(output_file)
                    
                except Exception as e:
                    error_msg = f"Error procesando {company['razon_social']}: {str(e)}"
                    results.append((company['razon_social'], rut_sin_guion, None, f"ERROR: {str(e)}"))
                    self.output_queue.put(('log', error_msg, "ERROR"))
                
                # Pausa entre empresas
                if i < total_companies and self.is_running:
                    self.output_queue.put(('log', "Esperando 3 segundos antes de la siguiente empresa..."))
                    for _ in range(30):  # 3 segundos en pasos de 0.1
                        if not self.is_running:
                            break
                        threading.Event().wait(0.1)
            
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
    
    def _check_output_queue(self):
        """Verificar cola de output y actualizar UI"""
        try:
            while True:
                msg_type, *args = self.output_queue.get_nowait()
                
                if msg_type == 'log':
                    message = args[0]
                    level = args[1] if len(args) > 1 else "INFO"
                    self.log_viewer.log(message, level)
                elif msg_type == 'progress':
                    self.control_panel.update_progress(args[0])
                elif msg_type == 'finished':
                    self._finish_scraping()
                    break
                    
        except queue.Empty:
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
        """Abrir carpeta de resultados"""
        results_path = "./data/Reports"
        
        if open_folder(results_path):
            self.log_viewer.log(f"Abriendo carpeta de resultados: {results_path}")
        else:
            if not os.path.exists(results_path):
                messagebox.showinfo("Información", f"La carpeta de resultados no existe aún: {results_path}")
            else:
                messagebox.showerror("Error", f"No se pudo abrir la carpeta: {results_path}")
    
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
