"""
Procesador de archivos presentation para mantener jerarquía exacta del XBRL
"""
import pandas as pd
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set


class PresentationHierarchy:
    """
    Clase para procesar y mantener la jerarquía exacta de un archivo presentation XBRL
    """
    
    def __init__(self):
        self.hierarchy = {}  # role -> list of (label, level, is_synopsis, parent_synopsis)
        self.role_orders = {}  # role -> label -> position
        
    def load_presentation(self, presentation_path: Path) -> bool:
        """
        Carga un archivo presentation y extrae la jerarquía exacta
        """
        try:
            df = pd.read_csv(presentation_path, engine='python')
            
            current_role = None
            current_stack = []  # Stack de secciones [sinopsis] activas
            position = 0
            
            for _, row in df.iterrows():
                label = str(row.get('Label', '')).strip()
                if not label:
                    continue
                
                # Detectar encabezado de rol
                m = re.match(r'^\s*\[(\d{6})\]', label)
                if m:
                    current_role = m.group(1)
                    current_stack = []
                    position = 0
                    if current_role not in self.hierarchy:
                        self.hierarchy[current_role] = []
                        self.role_orders[current_role] = {}
                    continue
                
                if not current_role:
                    continue
                
                # Determinar nivel de indentación (si está disponible)
                indent_level = self._detect_indent_level(label, row)
                
                # Detectar si es [sinopsis]
                is_synopsis = '[sinopsis]' in label.lower()
                
                # Manejar stack de secciones
                if is_synopsis:
                    # Ajustar stack según nivel
                    if indent_level == 0:
                        # Sección principal
                        current_stack = [label]
                    elif indent_level > 0 and indent_level <= len(current_stack):
                        # Reemplazar en el nivel apropiado
                        current_stack = current_stack[:indent_level-1] + [label]
                    else:
                        # Agregar como subsección
                        current_stack.append(label)
                
                # Determinar sección padre
                parent_section = None
                if not is_synopsis and current_stack:
                    parent_section = ' | '.join(current_stack)
                elif is_synopsis and len(current_stack) > 1:
                    parent_section = ' | '.join(current_stack[:-1])
                
                # Agregar a la jerarquía
                self.hierarchy[current_role].append({
                    'position': position,
                    'label': label,
                    'level': indent_level,
                    'is_synopsis': is_synopsis,
                    'parent_section': parent_section,
                    'section_stack': current_stack.copy()
                })
                
                self.role_orders[current_role][label] = position
                position += 1
                
            return True
            
        except Exception as e:
            print(f"Error cargando presentation: {e}")
            return False
    
    def _detect_indent_level(self, label: str, row) -> int:
        """
        Detecta el nivel de indentación basado en espacios al inicio o estructura
        """
        # Intentar detectar por espacios iniciales
        stripped = label.lstrip()
        spaces = len(label) - len(stripped)
        
        # Normalizar a niveles (cada 2-4 espacios = 1 nivel)
        if spaces > 0:
            return spaces // 3
        
        # Heurística: secciones principales conocidas
        if any(x in label.lower() for x in [
            'flujos de efectivo procedentes de (utilizados en) actividades',
            'activos [sinopsis]',
            'pasivos [sinopsis]',
            'patrimonio [sinopsis]',
            'ganancia (pérdida) [sinopsis]'
        ]):
            return 0
        
        # Subsecciones conocidas
        if any(x in label.lower() for x in [
            'negocios no bancarios',
            'servicios bancarios',
            'clases de cobros',
            'clases de pagos',
            'corrientes [sinopsis]',
            'no corrientes [sinopsis]'
        ]):
            return 1
        
        # Por defecto, nivel 2 para cuentas normales
        return 2 if '[sinopsis]' not in label.lower() else 1
    
    def get_section_for_label(self, role: str, label: str) -> Optional[str]:
        """
        Obtiene la sección correcta para una cuenta basada en la jerarquía del presentation
        """
        if role not in self.hierarchy:
            return None
        
        for item in self.hierarchy[role]:
            if item['label'] == label:
                return item['parent_section']
        
        return None
    
    def get_all_sections(self, role: str) -> List[str]:
        """
        Obtiene todas las secciones [sinopsis] de un rol
        """
        if role not in self.hierarchy:
            return []
        
        return [item['label'] for item in self.hierarchy[role] if item['is_synopsis']]
    
    def merge_multiple_presentations(self, presentation_paths: List[Path]):
        """
        Combina múltiples presentations para tener una visión completa
        """
        combined_hierarchy = {}
        combined_orders = {}
        
        for pres_path in presentation_paths:
            temp_hierarchy = PresentationHierarchy()
            if temp_hierarchy.load_presentation(pres_path):
                # Combinar con lo existente
                for role, items in temp_hierarchy.hierarchy.items():
                    if role not in combined_hierarchy:
                        combined_hierarchy[role] = []
                        combined_orders[role] = {}
                    
                    # Agregar items únicos
                    existing_labels = {item['label'] for item in combined_hierarchy[role]}
                    for item in items:
                        if item['label'] not in existing_labels:
                            combined_hierarchy[role].append(item)
                            combined_orders[role][item['label']] = item['position']
        
        self.hierarchy = combined_hierarchy
        self.role_orders = combined_orders


def process_presentation_hierarchy(company_dir: Path, lang: str = 'es') -> PresentationHierarchy:
    """
    Procesa todos los presentations de una empresa y crea la jerarquía completa
    """
    hierarchy = PresentationHierarchy()
    
    # Buscar todos los presentation files
    presentation_files = []
    for dataset_dir in company_dir.glob("Estados_financieros_*"):
        for out_dir in dataset_dir.glob("out_*"):
            pres_files = list(out_dir.glob(f"presentation_*_{lang}.csv"))
            presentation_files.extend(pres_files)
    
    # Debug: mostrar cuántos archivos encontramos
    print(f"      ║ Archivos presentation encontrados: {len(presentation_files)}")
    
    if presentation_files:
        # Usar el más reciente como base
        presentation_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        success = hierarchy.load_presentation(presentation_files[0])
        
        if success:
            print(f"      ║ Presentation cargado: {presentation_files[0].name}")
        else:
            print(f"      ║ Error cargando: {presentation_files[0].name}")
        
        # Opcionalmente combinar con otros para completar
        if len(presentation_files) > 1 and success:
            hierarchy.merge_multiple_presentations(presentation_files[1:5])  # Siguientes 4 más recientes
    
    return hierarchy