#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI Integrado Mejorado para procesar empresas CMF
=================================================

Flujo optimizado:
1. XBRL → Facts consolidados (batch_xbrl_to_excel.py)
2. Facts → Excel primario (primary_csv_to_excel.py) 
3. Excel → Análisis (analisis_excel/)

Características:
- Manejo eficiente de 40+ empresas con progress bars
- Integración completa sin duplicación de Excel
- Interfaz intuitiva con filtros y búsqueda
- Dashboard de progreso en tiempo real

Uso:
  python cmf_total_cli_v2.py
"""

from __future__ import annotations

import os
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Dict
from datetime import datetime
import threading
import queue

# Para colores en terminal
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def _clear():
    """Limpia la pantalla"""
    try:
        os.system('cls' if os.name == 'nt' else 'clear')
    except Exception:
        pass


def _format_company_name(d: Path) -> str:
    """Formatea el nombre de empresa para display"""
    try:
        raw = d.name
        rut = raw.split('_', 1)[0]
        company = raw.split('_', 1)[1].replace('_', ' ') if '_' in raw else raw
        return f"{rut} — {company}"
    except Exception:
        return d.name


def _print_header():
    """Imprime el header del CLI"""
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
    print(f"{Colors.BOLD}CMF Extract Total - CLI Integrado v2.1{Colors.ENDC}")
    print(f"{Colors.OKCYAN}Sistema completo de 4 fases: XBRL → Excel → Análisis → Hoja de Inicio{Colors.ENDC}")
    print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}\n")


def _print_progress(current: int, total: int, label: str = "", width: int = 50):
    """Imprime una barra de progreso"""
    progress = current / total if total > 0 else 0
    filled = int(width * progress)
    bar = '█' * filled + '░' * (width - filled)
    percentage = progress * 100
    print(f"\r{label}: {bar} {percentage:.1f}% ({current}/{total})", end='', flush=True)


class CompanyProcessor:
    """Procesador de empresas con tracking de progreso"""
    
    def __init__(self, base_dir: Path, arelle_dir: Path, products_dir: Path, product_v1_dir: Path):
        self.base_dir = base_dir
        self.arelle_dir = arelle_dir
        self.products_dir = products_dir
        self.product_v1_dir = product_v1_dir
        self.langs = ['es']
        self.workers = max(1, (os.cpu_count() or 8))
        
        # Configuración de entorno optimizada
        self._setup_environment()
        
    def _setup_environment(self):
        """Configura variables de entorno para procesamiento optimizado"""
        os.environ['CMF_ANALYSIS_COMBINED'] = '1'
        os.environ['X2E_COMBINED'] = '1'
        os.environ['X2E_KEEP_ALL_DATES'] = '1'
        os.environ.setdefault('CMF_COMBINED_TTM_LAST_N', '3')
        os.environ['CMF_SKIP_OLD_EXCEL'] = '1'  # Evitar Excel duplicado de xbrl_to_excel
        os.environ['CMF_WORKERS'] = str(self.workers)
        
    def process_batch_consolidation(self, companies: List[Path], show_progress: bool = True) -> Tuple[int, Dict[str, str]]:
        """
        Fase 1: Procesa XBRL → Facts consolidados para múltiples empresas
        """
        print(f"\n{Colors.OKBLUE}▶ FASE 1/4: Consolidación de Facts XBRL{Colors.ENDC}")
        print(f"  Procesando {len(companies)} empresa(s)...")
        
        errors = {}
        
        # Para empresas individuales, procesarlas directamente
        if len(companies) == 1:
            company_dir = companies[0]
            print(f"  Procesando empresa: {_format_company_name(company_dir)}")
            
            try:
                from batch_xbrl_to_excel import (
                    find_datasets,
                    find_xbrl_file,
                    run_arelle_exports_progress,
                    generate_consolidated_company,
                    generate_combined_company_from_total
                )
                
                # Encontrar datasets de la empresa
                ds_all = [ds for ds in find_datasets(self.base_dir) if ds.company_dir == company_dir]
                if not ds_all:
                    errors[company_dir.name] = "No se encontraron datasets"
                    return 1, errors
                
                # Exportar facts/presentation con Arelle
                for ds in sorted(ds_all, key=lambda d: d.yyyyymm):
                    xbrl = find_xbrl_file(ds.dataset_dir, ds.stem)
                    if not xbrl:
                        continue
                    out_dir = ds.dataset_dir / f"out_{ds.stem}"
                    try:
                        run_arelle_exports_progress(
                            self.arelle_dir, xbrl, out_dir, ds.stem, 
                            self.langs, facts_strategy="es_only", force=False
                        )
                    except Exception as ex:
                        print(f"    ⚠ Error exportando {ds.stem}: {ex}")
                
                # Generar consolidado
                repo_root = self.base_dir.parent.parent.parent
                generate_consolidated_company(
                    company_dir, 
                    sorted(ds_all, key=lambda d: d.yyyyymm),
                    repo_root,
                    self.langs,
                    self.products_dir
                )
                
            except Exception as e:
                errors[company_dir.name] = str(e)
                return 1, errors
                
        else:
            # Para múltiples empresas, ejecutar batch completo
            try:
                from batch_xbrl_to_excel import main as batch_main
                old_argv = sys.argv.copy()
                try:
                    sys.argv = [
                        "batch_xbrl_to_excel.py",
                        "--base-dir", str(self.base_dir),
                        "--arelle-dir", str(self.arelle_dir),
                        "--langs", *self.langs,
                        "--products-dir", str(self.products_dir),
                    ]
                    
                    result = batch_main()
                    if result != 0:
                        errors['batch'] = f"Código de salida: {result}"
                finally:
                    sys.argv = old_argv
                    
            except Exception as e:
                errors['batch'] = str(e)
                return 1, errors
            
        print(f"{Colors.OKGREEN}✓ Facts consolidados generados exitosamente{Colors.ENDC}")
        return 0, errors
        
    def generate_primary_excels(self, companies: List[Path], show_progress: bool = True) -> Tuple[int, Dict[str, str]]:
        """
        Fase 2: Genera Excel desde primary_csv para múltiples empresas
        """
        print(f"\n{Colors.OKBLUE}▶ FASE 2/4: Generación de Excel Primario{Colors.ENDC}")
        print(f"  Generando Excel para {len(companies)} empresa(s)...")
        
        errors = {}
        processed = 0
        
        # Asegurar que existe el directorio Products/Total
        products_total_dir = self.products_dir / "Total"
        products_total_dir.mkdir(parents=True, exist_ok=True)
        
        # LIMPIAR COMPLETAMENTE todos los archivos Excel antiguos para estas empresas
        print(f"  🧹 Limpiando archivos Excel antiguos...")
        cleaned_count = 0
        for company_dir in companies:
            rut_prefix = company_dir.name.split('_', 1)[0]
            for old_file in products_total_dir.glob(f"estados_{rut_prefix}_*"):
                try:
                    old_file.unlink()
                    cleaned_count += 1
                except Exception:
                    pass
        if cleaned_count > 0:
            print(f"    ✅ Eliminados {cleaned_count} archivos Excel antiguos")
        
        for i, company_dir in enumerate(companies, 1):
            company_name = _format_company_name(company_dir)
            
            if show_progress:
                _print_progress(i-1, len(companies), f"Procesando {company_name[:30]}")
            
            try:
                # MEJORA ESPECIAL PARA WATTS SA: poblar datos históricos ANTES de todo
                try:
                    from watts_data_enhancer import enhance_watts_data
                    if enhance_watts_data(company_dir):
                        if show_progress:
                            print(f"\n      🔧 Datos históricos mejorados para WATTS SA")
                except ImportError:
                    pass  # watts_data_enhancer no disponible
                except Exception as e:
                    if show_progress:
                        print(f"\n      ⚠️  Error mejorando datos WATTS: {e}")
                
                # Ahora generar primary_roles CSV (ya con datos mejorados)
                import generate_primary_roles_csv as gpr
                primary_csv = gpr._build_primary_roles_csv(company_dir, 'es')
                
                if primary_csv:
                    # ELIMINAR TODOS los archivos Excel antiguos para esta empresa
                    rut_prefix = company_dir.name.split('_', 1)[0]
                    patterns_to_clean = [
                        f"estados_{rut_prefix}_*",      # Cualquier formato
                        f"estados_{rut_prefix}-*",      # Con guión
                        f"*{rut_prefix}*estados*",      # Orden diferente
                        f"{rut_prefix}_*"               # Solo RUT al inicio
                    ]
                    
                    for pattern in patterns_to_clean:
                        for existing_file in products_total_dir.glob(pattern):
                            if existing_file.suffix in ['.xlsx', '.xls']:
                                try:
                                    existing_file.unlink()
                                    if show_progress:
                                        print(f"\n      🗑️  Eliminado archivo previo: {existing_file.name}")
                                except Exception:
                                    pass
                    
                    # Generar Excel desde primary CSV (sin especificar ruta - usa modo automático)
                    # primary_csv_to_excel.py extraerá el rango de fechas dinámicamente y copiará a Products/Total
                    from primary_csv_to_excel import generate_excel_from_primary_csv
                    excel_path = generate_excel_from_primary_csv(company_dir, 'es')
                    
                    if excel_path and excel_path.exists():
                        processed += 1
                        # Verificar que el archivo fue generado correctamente
                        file_size = excel_path.stat().st_size
                        print(f"\n      ✅ Excel generado: {excel_path.name} ({file_size:,} bytes)")
                        
                        # Buscar la copia en Products/Total que debería haber sido creada automáticamente
                        products_files = list(products_total_dir.glob(f"estados_{rut_prefix}_*_es.xlsx"))
                        if products_files:
                            products_file = products_files[0]
                            products_file.touch()  # Marcar timestamp
                            print(f"      📁 Disponible para análisis: Products/Total/{products_file.name}")
                        
                    else:
                        errors[company_name] = "No se pudo generar Excel o archivo no existe"
                else:
                    errors[company_name] = "No se pudo generar primary_roles CSV"
                    
            except Exception as e:
                errors[company_name] = str(e)
        
        if show_progress:
            _print_progress(len(companies), len(companies), "Completado" + " " * 30)
            print()  # Nueva línea
            
        print(f"{Colors.OKGREEN}✓ Excel primario generado: {processed}/{len(companies)} empresas{Colors.ENDC}")
        
        if errors:
            print(f"{Colors.WARNING}⚠ Errores en {len(errors)} empresa(s){Colors.ENDC}")
            
        return 0 if processed > 0 else 1, errors
        
    def run_analysis(self, companies: List[Path], show_progress: bool = True) -> Tuple[int, Dict[str, str]]:
        """
        Fase 3: Ejecuta análisis financiero para múltiples empresas
        """
        print(f"\n{Colors.OKBLUE}▶ FASE 3/4: Análisis Financiero{Colors.ENDC}")
        print(f"  Analizando {len(companies)} empresa(s)...")
        
        errors = {}
        processed = 0
        
        # Importar módulo de análisis
        try:
            from run_products_analysis import process_one, normalize_rut_with_dv
        except ImportError as e:
            errors['import'] = f"Error importando run_products_analysis: {e}"
            return 1, errors
            
        for i, company_dir in enumerate(companies, 1):
            company_name = _format_company_name(company_dir)
            
            if show_progress:
                _print_progress(i-1, len(companies), f"Analizando {company_name[:30]}")
            
            try:
                rut_prefix = company_dir.name.split('_', 1)[0]
                # Usar el RUT directo ya que primary_csv_to_excel genera con ese formato
                
                # Buscar archivos Excel para analizar (usando el RUT sin normalizar)
                products_total_dir = self.products_dir / "Total"
                excel_files = list(products_total_dir.glob(f"estados_{rut_prefix}_*_es.xlsx"))
                
                if excel_files:
                    # Usar el más reciente (probablemente del primary)
                    latest_file = max(excel_files, key=lambda f: f.stat().st_mtime)
                    
                    # Verificar que es un archivo reciente (generado en los últimos minutos)
                    import time
                    file_age_minutes = (time.time() - latest_file.stat().st_mtime) / 60
                    
                    if show_progress:
                        print(f"\n      📊 Analizando: {latest_file.name} (generado hace {file_age_minutes:.1f} min)")
                    
                    # Si el archivo es muy antiguo, advertir pero continuar
                    if file_age_minutes > 30:
                        if show_progress:
                            print(f"      ⚠️  ADVERTENCIA: Archivo parece antiguo (>30 min)")
                    
                    # Verificar que es un archivo del primary (revisando metadatos del Excel)
                    try:
                        import openpyxl
                        wb = openpyxl.load_workbook(latest_file, read_only=True)
                        is_from_primary = False
                        if hasattr(wb, 'properties') and wb.properties.subject:
                            is_from_primary = 'primary_roles' in wb.properties.subject
                        wb.close()
                        
                        if not is_from_primary and show_progress:
                            print(f"      ⚠️  ADVERTENCIA: Archivo NO parece ser del primary_csv_to_excel")
                        elif is_from_primary and show_progress:
                            print(f"      ✅ Confirmado: Archivo generado por primary_csv_to_excel")
                    except Exception:
                        if show_progress:
                            print(f"      ℹ️  No se pudo verificar origen del archivo")
                    
                    # Ejecutar análisis
                    out_path, err = process_one(
                        latest_file, 
                        self.product_v1_dir,
                        workers=2,
                        frequency="Total"
                    )
                    
                    if err:
                        errors[company_name] = err
                    else:
                        processed += 1
                        if show_progress:
                            print(f"      ✅ Análisis completado: {out_path.name if out_path else 'Sin salida'}")
                else:
                    errors[company_name] = f"No se encontró archivo Excel para analizar (buscando: estados_{rut_prefix}_*_es.xlsx)"
                    
            except Exception as e:
                errors[company_name] = str(e)
        
        if show_progress:
            _print_progress(len(companies), len(companies), "Completado" + " " * 30)
            print()  # Nueva línea
            
        print(f"{Colors.OKGREEN}✓ Análisis completado: {processed}/{len(companies)} empresas{Colors.ENDC}")
        
        if errors:
            print(f"{Colors.WARNING}⚠ Errores en {len(errors)} empresa(s){Colors.ENDC}")
            
        return 0 if processed > 0 else 1, errors
        
    def add_start_sheets(self, companies: List[Path], show_progress: bool = True) -> Tuple[int, Dict[str, str]]:
        """
        Fase 4: Agrega hojas de inicio profesionales a los archivos de análisis
        """
        print(f"\n{Colors.OKBLUE}▶ FASE 4/4: Hojas de Inicio Profesionales{Colors.ENDC}")
        print(f"  Procesando {len(companies)} archivo(s) de análisis...")
        
        errors = {}
        processed = 0
        
        # Importar módulo de hojas de inicio
        try:
            from add_start_sheet_v4 import process_excel_file
        except ImportError as e:
            return 1, {"ImportError": f"No se pudo importar add_start_sheet_v4: {e}"}
        
        for i, company_dir in enumerate(companies):
            company_name = company_dir.name.replace('_', ' ')
            
            if show_progress:
                _print_progress(i, len(companies), f"Procesando {company_name[:40]:<40}")
            
            try:
                # Buscar archivo de análisis para esta empresa
                rut_prefix = company_dir.name.split('_', 1)[0]
                
                # Buscar en Product_v1/Total - usar patrón más específico
                # En Python glob, [ES] es una clase de caracteres, necesitamos escapar o usar diferente patrón
                analysis_files = list(self.product_v1_dir.glob(f"*{rut_prefix}*ES*.xlsx"))
                
                # Filtrar para asegurar que terminan en [ES].xlsx
                analysis_files = [f for f in analysis_files if f.name.endswith('[ES].xlsx')]
                
                if not analysis_files:
                    errors[company_name] = f"No se encontró archivo de análisis para {rut_prefix}"
                    continue
                
                # Usar el archivo más reciente
                latest_file = max(analysis_files, key=lambda f: f.stat().st_mtime)
                
                # Procesar el archivo con add_start_sheet_v4
                success = process_excel_file(str(latest_file))
                
                if success:
                    processed += 1
                else:
                    errors[company_name] = "Error procesando hoja de inicio"
                    
            except Exception as e:
                errors[company_name] = str(e)
        
        if show_progress:
            _print_progress(len(companies), len(companies), "Completado" + " " * 30)
            print()  # Nueva línea
            
        print(f"{Colors.OKGREEN}✓ Hojas de inicio agregadas: {processed}/{len(companies)} empresas{Colors.ENDC}")
        
        if errors:
            print(f"{Colors.WARNING}⚠ Errores en {len(errors)} empresa(s){Colors.ENDC}")
            
        return 0 if processed > 0 else 1, errors
        
    def process_all(self, companies: List[Path]) -> int:
        """Ejecuta el flujo completo para las empresas seleccionadas"""
        start_time = time.time()
        total_errors = {}
        
        print(f"\n{Colors.BOLD}Iniciando procesamiento completo de {len(companies)} empresa(s){Colors.ENDC}")
        
        # Fase 1: Consolidación
        rc1, errors1 = self.process_batch_consolidation(companies)
        total_errors.update({f"Fase1-{k}": v for k, v in errors1.items()})
        
        # Fase 2: Excel primario
        rc2, errors2 = self.generate_primary_excels(companies)
        total_errors.update({f"Fase2-{k}": v for k, v in errors2.items()})
        
        # Fase 3: Análisis
        rc3, errors3 = self.run_analysis(companies)
        total_errors.update({f"Fase3-{k}": v for k, v in errors3.items()})
        
        # Fase 4: Hoja de inicio profesional
        rc4, errors4 = self.add_start_sheets(companies)
        total_errors.update({f"Fase4-{k}": v for k, v in errors4.items()})
        
        # Resumen final
        elapsed = time.time() - start_time
        print(f"\n{Colors.HEADER}{'='*80}{Colors.ENDC}")
        print(f"{Colors.BOLD}RESUMEN DE PROCESAMIENTO{Colors.ENDC}")
        print(f"  Tiempo total: {elapsed:.1f} segundos")
        print(f"  Empresas procesadas: {len(companies)}")
        
        if total_errors:
            print(f"\n{Colors.WARNING}Errores encontrados ({len(total_errors)}):{Colors.ENDC}")
            for key, error in list(total_errors.items())[:5]:
                print(f"  • {key}: {error[:100]}")
            if len(total_errors) > 5:
                print(f"  ... y {len(total_errors)-5} errores más")
        else:
            print(f"{Colors.OKGREEN}✓ Procesamiento completado sin errores{Colors.ENDC}")
            
        print(f"{Colors.HEADER}{'='*80}{Colors.ENDC}")
        
        return 0 if not total_errors else 1


def interactive_menu():
    """Menú interactivo principal"""
    _clear()
    _print_header()
    
    # Configuración de rutas
    repo_root = Path(__file__).resolve().parent
    base_dir = repo_root / "data/XBRL/Total"
    arelle_dir = Path.home() / "Documents" / "Arelle"
    products_dir = repo_root / "Products"
    product_v1_dir = repo_root / "Product_v1" / "Total"
    
    # Crear directorios si no existen
    products_dir.mkdir(parents=True, exist_ok=True)
    product_v1_dir.mkdir(parents=True, exist_ok=True)
    
    # Inicializar procesador
    processor = CompanyProcessor(base_dir, arelle_dir, products_dir, product_v1_dir)
    
    # Obtener lista de empresas
    companies = sorted([d for d in base_dir.iterdir() if d.is_dir()])
    
    if not companies:
        print(f"{Colors.FAIL}❌ No se encontraron empresas en {base_dir}{Colors.ENDC}")
        return 1
    
    # Variables de navegación
    page = 0
    page_size = 15
    filter_text = ""
    
    while True:
        _clear()
        _print_header()
        
        # Filtrar empresas
        filtered = companies
        if filter_text:
            filtered = [d for d in companies if filter_text.lower() in _format_company_name(d).lower()]
        
        # Calcular paginación
        total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
        page = max(0, min(page, total_pages - 1))
        start_idx = page * page_size
        end_idx = min(len(filtered), start_idx + page_size)
        
        # Mostrar información
        print(f"📁 Total empresas: {len(companies)}")
        if filter_text:
            print(f"🔍 Filtro activo: '{filter_text}' ({len(filtered)} coincidencias)")
        print(f"📄 Página {page + 1} de {total_pages}")
        print(f"\n{Colors.BOLD}Empresas disponibles:{Colors.ENDC}")
        print("-" * 80)
        
        # Mostrar lista de empresas
        print(f"  {Colors.OKGREEN}0. ► PROCESAR TODAS LAS EMPRESAS{Colors.ENDC} ({len(filtered)} empresas)")
        print()
        
        for i, company_dir in enumerate(filtered[start_idx:end_idx], start=start_idx + 1):
            company_name = _format_company_name(company_dir)
            print(f"  {i:3d}. {company_name}")
        
        # Mostrar opciones
        print("\n" + "-" * 80)
        print(f"{Colors.BOLD}Opciones:{Colors.ENDC}")
        print("  [n] Siguiente página | [p] Página anterior")
        print("  [f] <texto> Filtrar empresas | [c] Limpiar filtro")
        print("  [1-N] Procesar empresa específica")
        print("  [m] Procesar múltiples (ej: m 1,3,5-8)")
        print("  [q] Salir")
        print("-" * 80)
        
        # Solicitar entrada
        user_input = input(f"\n{Colors.OKCYAN}Seleccione opción:{Colors.ENDC} ").strip().lower()
        
        # Procesar entrada
        if user_input == 'q':
            print(f"\n{Colors.OKGREEN}¡Hasta luego!{Colors.ENDC}")
            return 0
            
        elif user_input == 'n':
            page += 1
            continue
            
        elif user_input == 'p':
            page -= 1
            continue
            
        elif user_input.startswith('f '):
            filter_text = user_input[2:].strip()
            page = 0
            continue
            
        elif user_input == 'c':
            filter_text = ""
            page = 0
            continue
            
        elif user_input == '0':
            # Procesar todas las empresas filtradas
            print(f"\n{Colors.WARNING}⚠ Procesará {len(filtered)} empresa(s). ¿Continuar? (s/n):{Colors.ENDC} ", end='')
            if input().strip().lower() == 's':
                processor.process_all(filtered)
                input(f"\n{Colors.OKCYAN}Presione Enter para continuar...{Colors.ENDC}")
            continue
            
        elif user_input.startswith('m '):
            # Procesar múltiples empresas
            selection_str = user_input[2:].strip()
            selected_indices = []
            
            try:
                # Parsear rangos y números individuales
                for part in selection_str.split(','):
                    part = part.strip()
                    if '-' in part:
                        start, end = map(int, part.split('-'))
                        selected_indices.extend(range(start, end + 1))
                    else:
                        selected_indices.append(int(part))
                
                # Validar y obtener empresas
                selected_companies = []
                for idx in selected_indices:
                    if 1 <= idx <= len(filtered):
                        selected_companies.append(filtered[idx - 1])
                
                if selected_companies:
                    print(f"\n{Colors.WARNING}Procesará {len(selected_companies)} empresa(s). ¿Continuar? (s/n):{Colors.ENDC} ", end='')
                    if input().strip().lower() == 's':
                        processor.process_all(selected_companies)
                        input(f"\n{Colors.OKCYAN}Presione Enter para continuar...{Colors.ENDC}")
                else:
                    print(f"{Colors.FAIL}❌ Selección inválida{Colors.ENDC}")
                    time.sleep(2)
            except Exception as e:
                print(f"{Colors.FAIL}❌ Error procesando selección: {e}{Colors.ENDC}")
                time.sleep(2)
            continue
            
        else:
            # Intentar procesar empresa individual
            try:
                idx = int(user_input)
                if 1 <= idx <= len(filtered):
                    selected_company = filtered[idx - 1]
                    print(f"\n{Colors.WARNING}Procesará: {_format_company_name(selected_company)}{Colors.ENDC}")
                    print(f"¿Continuar? (s/n): ", end='')
                    if input().strip().lower() == 's':
                        processor.process_all([selected_company])
                        input(f"\n{Colors.OKCYAN}Presione Enter para continuar...{Colors.ENDC}")
                else:
                    print(f"{Colors.FAIL}❌ Número fuera de rango{Colors.ENDC}")
                    time.sleep(2)
            except ValueError:
                if user_input:
                    print(f"{Colors.FAIL}❌ Opción no reconocida: {user_input}{Colors.ENDC}")
                    time.sleep(2)
            continue


def main():
    """Función principal"""
    print(f"\n{Colors.WARNING}AVISO: Este CLI esta deprecado. Usa 'python cmf_cli.py' para el nuevo CLI unificado.{Colors.ENDC}\n")
    try:
        return interactive_menu()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Proceso interrumpido por el usuario{Colors.ENDC}")
        return 1
    except Exception as e:
        print(f"\n{Colors.FAIL}❌ Error inesperado: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    raise SystemExit(main())