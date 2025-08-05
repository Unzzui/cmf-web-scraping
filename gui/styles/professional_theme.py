#!/usr/bin/env python3
"""
Configuración de estilos profesionales para la GUI del CMF Scraper
"""

from tkinter import ttk


class ProfessionalStyles:
    """Clase para manejar estilos profesionales de la aplicación"""
    
    # Colores profesionales
    PRIMARY_COLOR = '#2c3e50'      # Azul oscuro
    SECONDARY_COLOR = '#34495e'     # Gris azulado
    ACCENT_COLOR = '#3498db'        # Azul claro
    SUCCESS_COLOR = '#27ae60'       # Verde
    WARNING_COLOR = '#f39c12'       # Naranja
    DANGER_COLOR = '#e74c3c'        # Rojo
    LIGHT_BG = '#ecf0f1'           # Gris muy claro
    WHITE = '#ffffff'
    BACKGROUND = '#f8f9fa'
    TEXT_MUTED = '#7f8c8d'
    
    @classmethod
    def setup_styles(cls):
        """Configurar todos los estilos de la aplicación"""
        style = ttk.Style()
        style.theme_use('clam')
        
        cls._setup_label_styles(style)
        cls._setup_button_styles(style)
        cls._setup_frame_styles(style)
        cls._setup_tree_styles(style)
        cls._setup_entry_styles(style)
        
        return style
    
    @classmethod
    def _setup_label_styles(cls, style):
        """Configurar estilos de etiquetas"""
        # Títulos
        style.configure('Title.TLabel', 
                       font=('Segoe UI', 20, 'bold'), 
                       foreground=cls.PRIMARY_COLOR,
                       background=cls.BACKGROUND)
        
        style.configure('Subtitle.TLabel', 
                       font=('Segoe UI', 14, 'bold'), 
                       foreground=cls.SECONDARY_COLOR,
                       background=cls.BACKGROUND)
        
        # Estados
        style.configure('Info.TLabel', 
                       font=('Segoe UI', 10), 
                       foreground=cls.TEXT_MUTED,
                       background=cls.BACKGROUND)
        
        style.configure('Success.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=cls.SUCCESS_COLOR,
                       background=cls.BACKGROUND)
        
        style.configure('Warning.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=cls.WARNING_COLOR,
                       background=cls.BACKGROUND)
        
        style.configure('Error.TLabel', 
                       font=('Segoe UI', 10, 'bold'), 
                       foreground=cls.DANGER_COLOR,
                       background=cls.BACKGROUND)
    
    @classmethod
    def _setup_button_styles(cls, style):
        """Configurar estilos de botones"""
        # Botón primario
        style.configure('Primary.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=cls.WHITE)
        style.map('Primary.TButton',
                 background=[('active', '#2980b9'), ('!active', cls.ACCENT_COLOR)],
                 foreground=[('active', cls.WHITE), ('!active', cls.WHITE)])
        
        # Botón de éxito
        style.configure('Success.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=cls.WHITE)
        style.map('Success.TButton',
                 background=[('active', '#229954'), ('!active', cls.SUCCESS_COLOR)],
                 foreground=[('active', cls.WHITE), ('!active', cls.WHITE)])
        
        # Botón de advertencia
        style.configure('Warning.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=cls.WHITE)
        style.map('Warning.TButton',
                 background=[('active', '#d68910'), ('!active', cls.WARNING_COLOR)],
                 foreground=[('active', cls.WHITE), ('!active', cls.WHITE)])
        
        # Botón de peligro
        style.configure('Danger.TButton',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=cls.WHITE)
        style.map('Danger.TButton',
                 background=[('active', '#c0392b'), ('!active', cls.DANGER_COLOR)],
                 foreground=[('active', cls.WHITE), ('!active', cls.WHITE)])
    
    @classmethod
    def _setup_frame_styles(cls, style):
        """Configurar estilos de marcos"""
        style.configure('Card.TLabelframe',
                       background=cls.BACKGROUND,
                       borderwidth=1,
                       relief='solid')
        style.configure('Card.TLabelframe.Label',
                       font=('Segoe UI', 11, 'bold'),
                       foreground=cls.PRIMARY_COLOR,
                       background=cls.BACKGROUND)
    
    @classmethod
    def _setup_tree_styles(cls, style):
        """Configurar estilos del Treeview"""
        style.configure('Professional.Treeview',
                       background=cls.WHITE,
                       foreground=cls.PRIMARY_COLOR,
                       fieldbackground=cls.WHITE,
                       font=('Segoe UI', 9))
        style.configure('Professional.Treeview.Heading',
                       font=('Segoe UI', 10, 'bold'),
                       foreground=cls.PRIMARY_COLOR,
                       background=cls.LIGHT_BG)
    
    @classmethod
    def _setup_entry_styles(cls, style):
        """Configurar estilos de campos de entrada"""
        style.configure('Professional.TEntry',
                       font=('Segoe UI', 10),
                       fieldbackground=cls.WHITE,
                       borderwidth=1)
        style.configure('Professional.TCombobox',
                       font=('Segoe UI', 10),
                       fieldbackground=cls.WHITE,
                       borderwidth=1)


def get_font_config():
    """Obtener configuración de fuentes para widgets de tkinter"""
    return {
        'title_font': ('Segoe UI', 20, 'bold'),
        'subtitle_font': ('Segoe UI', 14, 'bold'),
        'header_font': ('Segoe UI', 11, 'bold'),
        'body_font': ('Segoe UI', 10),
        'small_font': ('Segoe UI', 9),
        'code_font': ('Consolas', 9),
    }


def get_color_config():
    """Obtener configuración de colores"""
    return {
        'primary': ProfessionalStyles.PRIMARY_COLOR,
        'secondary': ProfessionalStyles.SECONDARY_COLOR,
        'accent': ProfessionalStyles.ACCENT_COLOR,
        'success': ProfessionalStyles.SUCCESS_COLOR,
        'warning': ProfessionalStyles.WARNING_COLOR,
        'danger': ProfessionalStyles.DANGER_COLOR,
        'light_bg': ProfessionalStyles.LIGHT_BG,
        'white': ProfessionalStyles.WHITE,
        'background': ProfessionalStyles.BACKGROUND,
        'text_muted': ProfessionalStyles.TEXT_MUTED,
    }
