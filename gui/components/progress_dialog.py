#!/usr/bin/env python3
"""
Diálogo de progreso para operaciones de descarga XBRL
"""

import tkinter as tk
from tkinter import ttk
import threading
import time


class ProgressDialog:
    """Ventana de progreso con información detallada"""
    
    def __init__(self, parent, title="Procesando...", total_steps=1):
        self.parent = parent
        self.total_steps = total_steps
        self.current_step = 0
        self.is_cancelled = False
        
        # Crear ventana modal
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("600x400")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centrar ventana
        self._center_window()
        
        # Variables
        self.progress_var = tk.DoubleVar()
        self.status_var = tk.StringVar(value="Preparando...")
        self.current_company_var = tk.StringVar(value="")
        self.files_downloaded_var = tk.StringVar(value="0")
        self.time_var = tk.StringVar(value="Calculando...")
        
        # Variables de control
        self.is_cancelled = False
        self.current_step = 0
        self.total_steps = 0
        self.total_companies = 0
        
        # Crear interfaz
        self._create_widgets()
        
        # Configurar cierre
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_closing)
        
        # Variables de tiempo
        self.start_time = time.time()
        
    def _center_window(self):
        """Centrar ventana en la pantalla"""
        self.dialog.update_idletasks()
        width = self.dialog.winfo_width()
        height = self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_widgets(self):
        """Crear widgets de la ventana"""
        # Frame principal
        main_frame = tk.Frame(self.dialog, bg='#f8f9fa', padx=20, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Título
        title_label = tk.Label(main_frame, 
                              text="🚀 Descarga de Archivos XBRL",
                              font=('Segoe UI', 16, 'bold'),
                              bg='#f8f9fa', fg='#2c3e50')
        title_label.pack(pady=(0, 20))
        
        # Frame de información
        info_frame = tk.LabelFrame(main_frame, 
                                  text="Estado del Proceso",
                                  font=('Segoe UI', 10, 'bold'),
                                  bg='#f8f9fa', fg='#2c3e50',
                                  padx=15, pady=10)
        info_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Estado actual
        status_label = tk.Label(info_frame, 
                               text="Estado:",
                               font=('Segoe UI', 9, 'bold'),
                               bg='#f8f9fa', fg='#2c3e50')
        status_label.grid(row=0, column=0, sticky='w', pady=2)
        
        status_value = tk.Label(info_frame, 
                               textvariable=self.status_var,
                               font=('Segoe UI', 9),
                               bg='#f8f9fa', fg='#3498db')
        status_value.grid(row=0, column=1, sticky='w', padx=(10, 0), pady=2)
        
        # Empresa actual
        company_label = tk.Label(info_frame, 
                                text="Empresa:",
                                font=('Segoe UI', 9, 'bold'),
                                bg='#f8f9fa', fg='#2c3e50')
        company_label.grid(row=1, column=0, sticky='w', pady=2)
        
        company_value = tk.Label(info_frame, 
                                textvariable=self.current_company_var,
                                font=('Segoe UI', 9),
                                bg='#f8f9fa', fg='#27ae60')
        company_value.grid(row=1, column=1, sticky='w', padx=(10, 0), pady=2)
        
        # Archivos descargados
        files_label = tk.Label(info_frame, 
                              text="Archivos:",
                              font=('Segoe UI', 9, 'bold'),
                              bg='#f8f9fa', fg='#2c3e50')
        files_label.grid(row=2, column=0, sticky='w', pady=2)
        
        files_value = tk.Label(info_frame, 
                              textvariable=self.files_downloaded_var,
                              font=('Segoe UI', 9),
                              bg='#f8f9fa', fg='#e74c3c')
        files_value.grid(row=2, column=1, sticky='w', padx=(10, 0), pady=2)
        
        # Tiempo estimado
        time_label = tk.Label(info_frame, 
                             text="Tiempo restante:",
                             font=('Segoe UI', 9, 'bold'),
                             bg='#f8f9fa', fg='#2c3e50')
        time_label.grid(row=3, column=0, sticky='w', pady=2)
        
        time_value = tk.Label(info_frame, 
                             textvariable=self.time_var,
                             font=('Segoe UI', 9),
                             bg='#f8f9fa', fg='#f39c12')
        time_value.grid(row=3, column=1, sticky='w', padx=(10, 0), pady=2)
        
        # Frame de progreso
        progress_frame = tk.LabelFrame(main_frame, 
                                      text="Progreso",
                                      font=('Segoe UI', 10, 'bold'),
                                      bg='#f8f9fa', fg='#2c3e50',
                                      padx=15, pady=10)
        progress_frame.pack(fill=tk.X, pady=(0, 15))
        
        # Barra de progreso
        self.progress_bar = ttk.Progressbar(progress_frame, 
                                           variable=self.progress_var,
                                           maximum=100,
                                           length=500,
                                           mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=(0, 10))
        
        # Etiqueta de porcentaje
        self.percentage_label = tk.Label(progress_frame, 
                                        text="0%",
                                        font=('Segoe UI', 10, 'bold'),
                                        bg='#f8f9fa', fg='#2c3e50')
        self.percentage_label.pack()
        
        # Frame de botones
        button_frame = tk.Frame(main_frame, bg='#f8f9fa')
        button_frame.pack(fill=tk.X, pady=(15, 0))
        
        # Botón cancelar
        self.cancel_button = ttk.Button(button_frame, 
                                       text="❌ Cancelar Proceso",
                                       command=self._cancel_process,
                                       style='Danger.TButton')
        self.cancel_button.pack(side=tk.RIGHT)
        
        # Información adicional
        info_text = (
            "💡 Información:\n"
            "• Los archivos XBRL se descargan directamente de la CMF\n"
            "• Cada archivo contiene múltiples períodos financieros\n"
            "• Los archivos se extraen automáticamente después de la descarga\n"
            "• Los archivos ZIP originales se eliminan para ahorrar espacio"
        )
        
        info_label = tk.Label(main_frame, 
                             text=info_text,
                             font=('Segoe UI', 8),
                             bg='#f8f9fa', fg='#7f8c8d',
                             justify=tk.LEFT)
        info_label.pack(anchor=tk.W, pady=(15, 0))
    
    def set_total_companies(self, total_companies):
        """Configurar el total de empresas a procesar"""
        self.total_companies = total_companies
        self.total_steps = total_companies
        self.status_var.set(f"Preparando descarga para {total_companies} empresas...")
    
    def update_progress(self, current=None, company_name="", status="", files_count=0):
        """Actualizar progreso de la operación (versión compatible)"""
        if current is not None:
            self.current_step = current
        
        # Usar total_companies si está disponible, sino usar total_steps
        total = getattr(self, 'total_companies', self.total_steps)
        
        # Calcular porcentaje
        progress_percent = (self.current_step / total) * 100 if total > 0 else 0
        
        # Actualizar variables
        self.progress_var.set(progress_percent)
        if status:
            self.status_var.set(status)
        if company_name:
            self.current_company_var.set(company_name)
        if files_count > 0:
            self.files_downloaded_var.set(f"{files_count} archivos descargados")
        
        # Actualizar etiqueta de porcentaje
        self.percentage_label.config(text=f"{progress_percent:.1f}%")
        
        # Calcular tiempo estimado
        elapsed_time = time.time() - self.start_time
        if self.current_step > 0:
            avg_time_per_step = elapsed_time / self.current_step
            remaining_steps = total - self.current_step
            estimated_remaining = remaining_steps * avg_time_per_step
            
            if estimated_remaining > 60:
                time_text = f"~{estimated_remaining/60:.1f} min restantes"
            else:
                time_text = f"~{estimated_remaining:.0f} seg restantes"
                
            self.time_var.set(time_text)
        
        # Forzar actualización de la ventana
        self.dialog.update_idletasks()
    
    def update_progress_legacy(self, step, total_steps, status, company_name="", files_count=0):
        """Actualizar progreso de la operación (método legacy)"""
        self.current_step = step
        self.total_steps = total_steps
        
        # Calcular porcentaje
        progress_percent = (step / total_steps) * 100 if total_steps > 0 else 0
        
        # Actualizar variables
        self.progress_var.set(progress_percent)
        self.status_var.set(status)
        self.current_company_var.set(company_name)
        self.files_downloaded_var.set(f"{files_count} archivos descargados")
        
        # Actualizar etiqueta de porcentaje
        self.percentage_label.config(text=f"{progress_percent:.1f}%")
        
        # Calcular tiempo estimado
        elapsed_time = time.time() - self.start_time
        if step > 0:
            avg_time_per_step = elapsed_time / step
            remaining_steps = total_steps - step
            estimated_remaining = remaining_steps * avg_time_per_step
            
            if estimated_remaining > 60:
                self.estimated_time_var.set(f"{estimated_remaining // 60:.0f} min {estimated_remaining % 60:.0f} seg")
            else:
                self.estimated_time_var.set(f"{estimated_remaining:.0f} segundos")
        else:
            self.estimated_time_var.set("Calculando...")
        
        # Actualizar interfaz
        self.dialog.update()
    
    def update_status(self, status):
        """Actualizar solo el estado"""
        self.status_var.set(status)
        self.dialog.update()
    
    def _cancel_process(self):
        """Cancelar el proceso"""
        result = tk.messagebox.askyesno(
            "Confirmar Cancelación",
            "¿Está seguro de que desea cancelar la descarga XBRL?\n\n"
            "El proceso se detendrá y los archivos ya descargados se conservarán.",
            parent=self.dialog
        )
        
        if result:
            self.is_cancelled = True
            self.status_var.set("Cancelando proceso...")
            self.cancel_button.config(state='disabled')
    
    def _on_closing(self):
        """Manejar cierre de ventana"""
        self._cancel_process()
    
    def show_completion(self, successful_companies, total_companies, total_files):
        """Mostrar mensaje de finalización"""
        self.cancel_button.config(text="✅ Cerrar", command=self.close)
        
        if successful_companies == total_companies:
            self.status_var.set("¡Proceso completado exitosamente!")
            completion_msg = (
                f"🎉 ¡Descarga XBRL completada!\n\n"
                f"✅ Empresas procesadas: {successful_companies}/{total_companies}\n"
                f"📁 Total de archivos: {total_files}\n"
                f"⏱️ Tiempo total: {time.time() - self.start_time:.0f} segundos"
            )
        else:
            self.status_var.set("Proceso completado con algunos errores")
            completion_msg = (
                f"⚠️ Descarga XBRL completada con errores\n\n"
                f"✅ Empresas exitosas: {successful_companies}/{total_companies}\n"
                f"❌ Empresas con errores: {total_companies - successful_companies}\n"
                f"📁 Total de archivos: {total_files}\n"
                f"⏱️ Tiempo total: {time.time() - self.start_time:.0f} segundos"
            )
        
        tk.messagebox.showinfo("Proceso Completado", completion_msg, parent=self.dialog)
    
    def close(self):
        """Cerrar ventana"""
        if hasattr(self, 'dialog') and self.dialog:
            self.dialog.destroy()
    
    def show(self):
        """Mostrar ventana de progreso"""
        if hasattr(self, 'dialog') and self.dialog:
            self.dialog.deiconify()
            self.dialog.lift()
            self.dialog.focus_force()
    
    def is_canceled(self):
        """Verificar si el proceso fue cancelado"""
        return self.is_cancelled
