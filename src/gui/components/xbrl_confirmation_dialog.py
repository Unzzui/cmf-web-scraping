#!/usr/bin/env python3
"""
Diálogo de confirmación para descarga XBRL
"""

import tkinter as tk
from tkinter import ttk


class XBRLConfirmationDialog:
    """Diálogo de confirmación minimalista para descarga XBRL"""
    
    def __init__(self, parent, companies, config):
        self.parent = parent
        self.companies = companies
        self.config = config
        self.result = False
        
        # Calcular estadísticas básicas
        self.total_companies = len(companies)
        
        # Crear ventana
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Confirmar Descarga XBRL")
        
        # Configurar tamaño responsivo
        screen_width = self.dialog.winfo_screenwidth()
        screen_height = self.dialog.winfo_screenheight()
        
        # Diálogo compacto y centrado
        window_width = 420
        window_height = 210
        
        self.dialog.geometry(f"{window_width}x{window_height}")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)
        self.dialog.grab_set()
        
        # Centrar ventana
        self._center_window()
        
        # Crear interfaz minimalista
        self._create_minimal_widgets()
        
        # Configurar cierre
        self.dialog.protocol("WM_DELETE_WINDOW", self._cancel)
    
    def _center_window(self, window_width=None, window_height=None):
        """Centrar ventana en la pantalla"""
        self.dialog.update_idletasks()
        width = window_width or self.dialog.winfo_width()
        height = window_height or self.dialog.winfo_height()
        x = (self.dialog.winfo_screenwidth() // 2) - (width // 2)
        y = (self.dialog.winfo_screenheight() // 2) - (height // 2)
        self.dialog.geometry(f"{width}x{height}+{x}+{y}")
    
    def _create_minimal_widgets(self):
        """Crear widgets simples: título, contador, botones Aceptar/Cancelar"""
        main_frame = tk.Frame(self.dialog, bg='#f8f9fa', padx=24, pady=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        title_label = tk.Label(
            main_frame,
            text="Confirmar Descarga XBRL",
            font=('Segoe UI', 14, 'bold'),
            bg='#f8f9fa', fg='#2c3e50'
        )
        title_label.pack(pady=(0, 10))

        info_label = tk.Label(
            main_frame,
            text=f"Empresas a procesar: {self.total_companies}",
            font=('Segoe UI', 11),
            bg='#f8f9fa', fg='#34495e'
        )
        info_label.pack(pady=(0, 20))

        button_frame = tk.Frame(main_frame, bg='#f8f9fa')
        button_frame.pack(fill=tk.X)

        cancel_btn = ttk.Button(
            button_frame,
            text="Cancelar",
            command=self._cancel,
            style='Secondary.TButton'
        )
        cancel_btn.pack(side=tk.RIGHT, padx=(10, 0))

        confirm_btn = ttk.Button(
            button_frame,
            text="Aceptar",
            command=self._confirm,
            style='Success.TButton'
        )
        confirm_btn.pack(side=tk.RIGHT)
    
    # Las secciones detalladas del diálogo anterior fueron removidas para cumplir
    # con el requerimiento de un diálogo mínimo (Aceptar / Cancelar + contador).
    
    def _confirm(self):
        """Confirmar descarga"""
        self.result = True
        # No usar quit() para no cerrar el mainloop de la app completa
        self.dialog.destroy()
    
    def _cancel(self):
        """Cancelar descarga"""
        self.result = False
        # No usar quit() para no cerrar el mainloop de la app completa
        self.dialog.destroy()
    
    def show(self):
        """Mostrar diálogo y esperar resultado"""
        # Centrar y mostrar diálogo
        self.dialog.deiconify()
        self.dialog.transient(self.parent)
        self.dialog.grab_set()
        
        # Esperar a que se cierre el diálogo
        self.dialog.wait_window()
        return self.result
