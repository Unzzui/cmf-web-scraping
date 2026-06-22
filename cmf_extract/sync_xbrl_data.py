#!/usr/bin/env python3
"""
Script para sincronizar archivos XBRL desde cmf-web-scraping a CMF_extract
"""

import os
import shutil
import sys
from pathlib import Path
from typing import List, Tuple, Set

def get_source_and_dest_paths() -> Tuple[Path, Path]:
    """Obtiene las rutas de origen y destino"""
    source_path = Path("/home/unzzui/Documents/coding/cmf-web-scraping/data/XBRL/Total")
    dest_path = Path("/home/unzzui/Documents/coding/CMF_extract/data/XBRL/Total")
    
    if not source_path.exists():
        print(f"❌ Error: La ruta de origen no existe: {source_path}")
        sys.exit(1)
    
    if not dest_path.exists():
        print(f"❌ Error: La ruta de destino no existe: {dest_path}")
        sys.exit(1)
    
    return source_path, dest_path

def scan_directory(path: Path) -> Tuple[Set[str], Set[str], Set[str]]:
    """Escanea un directorio y retorna un conjunto de rutas relativas de archivos, carpetas principales y subcarpetas"""
    files = set()
    main_directories = set()
    all_subdirectories = set()
    
    for root, dirs, filenames in os.walk(path):
        root_path = Path(root)
        
        # Agregar carpetas principales (primer nivel)
        if root_path == path:
            for dir_name in dirs:
                main_directories.add(dir_name)
        
        # Agregar todas las subcarpetas (incluyendo anidadas)
        for dir_name in dirs:
            dir_path = root_path / dir_name
            rel_dir_path = dir_path.relative_to(path)
            all_subdirectories.add(str(rel_dir_path))
        
        # Agregar archivos
        for filename in filenames:
            rel_path = root_path.relative_to(path) / filename
            files.add(str(rel_path))
    
    return files, main_directories, all_subdirectories

def get_file_info(path: Path) -> Tuple[int, str]:
    """Obtiene información del archivo (tamaño y fecha de modificación)"""
    stat = path.stat()
    return stat.st_size, str(stat.st_mtime)

def compare_files(source_file: Path, dest_file: Path) -> bool:
    """Compara si dos archivos son idénticos"""
    if not dest_file.exists():
        return False
    
    try:
        source_size, source_mtime = get_file_info(source_file)
        dest_size, dest_mtime = get_file_info(dest_file)
        
        # Comparar tamaño y fecha de modificación
        if source_size != dest_size:
            return False
        
        # Si los tamaños son iguales, comparar contenido
        with open(source_file, 'rb') as f1, open(dest_file, 'rb') as f2:
            return f1.read() == f2.read()
    except Exception:
        return False

def copy_file_with_backup(source_file: Path, dest_file: Path, backup_dir: Path) -> None:
    """Copia un archivo creando un backup si es necesario"""
    # Crear directorio de backup si no existe
    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # Crear backup del archivo existente
    if dest_file.exists():
        backup_path = backup_dir / dest_file.name
        shutil.copy2(dest_file, backup_path)
        print(f"   💾 Backup creado: {backup_path}")
    
    # Copiar archivo
    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, dest_file)
    print(f"   ✅ Copiado: {dest_file}")

def sync_directories(source_path: Path, dest_path: Path) -> None:
    """Sincroniza los directorios"""
    print(f"🔍 Escaneando directorio origen: {source_path}")
    source_files, source_main_dirs, source_all_subdirs = scan_directory(source_path)
    
    print(f"🔍 Escaneando directorio destino: {dest_path}")
    dest_files, dest_main_dirs, dest_all_subdirs = scan_directory(dest_path)
    
    print(f"\n📊 Resumen de archivos y carpetas:")
    print(f"   Origen: {len(source_files)} archivos, {len(source_main_dirs)} carpetas principales")
    print(f"   Destino: {len(dest_files)} archivos, {len(dest_main_dirs)} carpetas principales")
    
    # Archivos que están en origen pero no en destino
    new_files = source_files - dest_files
    
    # Archivos que están en ambos directorios
    common_files = source_files & dest_files
    
    # Archivos que están solo en destino
    dest_only_files = dest_files - source_files
    
    # Carpetas principales que están en origen pero no en destino
    new_main_dirs = source_main_dirs - dest_main_dirs
    
    # Carpetas principales que están solo en destino
    dest_only_main_dirs = dest_main_dirs - source_main_dirs
    
    # Subcarpetas que están en origen pero no en destino
    new_subdirs = source_all_subdirs - dest_all_subdirs
    
    # Subcarpetas que están solo en destino
    dest_only_subdirs = dest_all_subdirs - source_all_subdirs
    
    print(f"\n📋 Archivos nuevos (no existen en destino): {len(new_files)}")
    print(f"📋 Archivos en común: {len(common_files)}")
    print(f"📋 Archivos solo en destino: {len(dest_only_files)}")
    print(f"📁 Carpetas principales nuevas: {len(new_main_dirs)}")
    print(f"📁 Carpetas principales solo en destino: {len(dest_only_main_dirs)}")
    print(f"📁 Subcarpetas nuevas: {len(new_subdirs)}")
    print(f"📁 Subcarpetas solo en destino: {len(dest_only_subdirs)}")
    
    if not new_files and not common_files and not new_main_dirs and not new_subdirs:
        print("\n✅ No hay archivos ni carpetas para sincronizar")
        return
    
    # Crear directorio de backup
    backup_dir = dest_path.parent / "backup_sync"
    
    # Procesar carpetas principales nuevas
    if new_main_dirs:
        print(f"\n🆕 Carpetas principales nuevas encontradas ({len(new_main_dirs)}):")
        for main_dir in sorted(new_main_dirs):
            print(f"   📁 {main_dir}")
        
        response = input(f"\n¿Desea copiar estas carpetas principales y todo su contenido? (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            print(f"\n🆕 Copiando {len(new_main_dirs)} carpetas principales nuevas...")
            for main_dir in sorted(new_main_dirs):
                source_dir = source_path / main_dir
                dest_dir = dest_path / main_dir
                
                print(f"   📁 Copiando carpeta principal: {main_dir}")
                try:
                    shutil.copytree(source_dir, dest_dir, dirs_exist_ok=True)
                    print(f"   ✅ Carpeta principal copiada: {dest_dir}")
                except Exception as e:
                    print(f"   ❌ Error copiando carpeta principal {main_dir}: {e}")
        else:
            print("   ⏭️  Carpetas principales nuevas no fueron copiadas")
    
    # Procesar subcarpetas nuevas
    if new_subdirs:
        print(f"\n🆕 Subcarpetas nuevas encontradas ({len(new_subdirs)}):")
        for subdir in sorted(new_subdirs)[:20]:  # Mostrar solo las primeras 20
            print(f"   📁 {subdir}")
        if len(new_subdirs) > 20:
            print(f"   ... y {len(new_subdirs) - 20} más")
        
        response = input(f"\n¿Desea copiar estas subcarpetas y su contenido? (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            print(f"\n🆕 Copiando {len(new_subdirs)} subcarpetas nuevas...")
            for subdir in sorted(new_subdirs):
                source_subdir = source_path / subdir
                dest_subdir = dest_path / subdir
                
                print(f"   📁 Copiando subcarpeta: {subdir}")
                try:
                    shutil.copytree(source_subdir, dest_subdir, dirs_exist_ok=True)
                    print(f"   ✅ Subcarpeta copiada: {dest_subdir}")
                except Exception as e:
                    print(f"   ❌ Error copiando subcarpeta {subdir}: {e}")
        else:
            print("   ⏭️  Subcarpetas nuevas no fueron copiadas")
    
    # Procesar archivos nuevos
    if new_files:
        print(f"\n🆕 Copiando {len(new_files)} archivos nuevos...")
        for rel_file in sorted(new_files):
            source_file = source_path / rel_file
            dest_file = dest_path / rel_file
            
            print(f"   📁 {rel_file}")
            copy_file_with_backup(source_file, dest_file, backup_dir)
    
    # Procesar archivos en común
    if common_files:
        print(f"\n🔄 Verificando {len(common_files)} archivos existentes...")
        
        files_to_overwrite = []
        files_identical = []
        files_different = []
        
        for rel_file in sorted(common_files):
            source_file = source_path / rel_file
            dest_file = dest_path / rel_file
            
            if compare_files(source_file, dest_file):
                files_identical.append(rel_file)
            else:
                files_different.append(rel_file)
        
        print(f"   ✅ Archivos idénticos: {len(files_identical)}")
        print(f"   ⚠️  Archivos diferentes: {len(files_different)}")
        
        if files_different:
            print(f"\n⚠️  Se encontraron {len(files_different)} archivos diferentes:")
            for rel_file in files_different[:10]:  # Mostrar solo los primeros 10
                print(f"   - {rel_file}")
            if len(files_different) > 10:
                print(f"   ... y {len(files_different) - 10} más")
            
            response = input(f"\n¿Desea sobrescribir estos archivos? (s/n): ").lower().strip()
            if response in ['s', 'si', 'sí', 'y', 'yes']:
                print(f"\n🔄 Sobrescribiendo {len(files_different)} archivos...")
                for rel_file in sorted(files_different):
                    source_file = source_path / rel_file
                    dest_file = dest_path / rel_file
                    
                    print(f"   📁 {rel_file}")
                    copy_file_with_backup(source_file, dest_file, backup_dir)
            else:
                print("   ⏭️  Archivos diferentes no fueron sobrescritos")
    
    # Mostrar archivos solo en destino
    if dest_only_files:
        print(f"\n📁 Archivos solo en destino ({len(dest_only_files)}):")
        for rel_file in sorted(dest_only_files)[:10]:  # Mostrar solo los primeros 10
            print(f"   - {rel_file}")
        if len(dest_only_files) > 10:
            print(f"   ... y {len(dest_only_files) - 10} más")
        
        response = input(f"\n¿Desea eliminar estos archivos del destino? (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            print(f"\n🗑️  Eliminando {len(dest_only_files)} archivos...")
            for rel_file in sorted(dest_only_files):
                dest_file = dest_path / rel_file
                try:
                    dest_file.unlink()
                    print(f"   🗑️  Eliminado: {rel_file}")
                except Exception as e:
                    print(f"   ❌ Error eliminando {rel_file}: {e}")
        else:
            print("   ⏭️  Archivos solo en destino no fueron eliminados")
    
    # Mostrar carpetas principales solo en destino
    if dest_only_main_dirs:
        print(f"\n📁 Carpetas principales solo en destino ({len(dest_only_main_dirs)}):")
        for main_dir in sorted(dest_only_main_dirs)[:10]:  # Mostrar solo los primeros 10
            print(f"   - {main_dir}")
        if len(dest_only_main_dirs) > 10:
            print(f"   ... y {len(dest_only_main_dirs) - 10} más")
        
        response = input(f"\n¿Desea eliminar estas carpetas principales del destino? (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            print(f"\n🗑️  Eliminando {len(dest_only_main_dirs)} carpetas principales...")
            for main_dir in sorted(dest_only_main_dirs):
                dest_dir = dest_path / main_dir
                try:
                    shutil.rmtree(dest_dir)
                    print(f"   🗑️  Carpeta principal eliminada: {main_dir}")
                except Exception as e:
                    print(f"   ❌ Error eliminando carpeta principal {main_dir}: {e}")
        else:
            print("   ⏭️  Carpetas principales solo en destino no fueron eliminadas")
    
    # Mostrar subcarpetas solo en destino
    if dest_only_subdirs:
        print(f"\n📁 Subcarpetas solo en destino ({len(dest_only_subdirs)}):")
        for subdir in sorted(dest_only_subdirs)[:20]:  # Mostrar solo las primeras 20
            print(f"   - {subdir}")
        if len(dest_only_subdirs) > 20:
            print(f"   ... y {len(dest_only_subdirs) - 20} más")
        
        response = input(f"\n¿Desea eliminar estas subcarpetas del destino? (s/n): ").lower().strip()
        if response in ['s', 'si', 'sí', 'y', 'yes']:
            print(f"\n🗑️  Eliminando {len(dest_only_subdirs)} subcarpetas...")
            for subdir in sorted(dest_only_subdirs):
                dest_subdir = dest_path / subdir
                try:
                    shutil.rmtree(dest_subdir)
                    print(f"   🗑️  Subcarpeta eliminada: {subdir}")
                except Exception as e:
                    print(f"   ❌ Error eliminando subcarpeta {subdir}: {e}")
        else:
            print("   ⏭️  Subcarpetas solo en destino no fueron eliminadas")
    
    print(f"\n✅ Sincronización completada!")
    if backup_dir.exists():
        print(f"💾 Backups guardados en: {backup_dir}")

def main():
    """Función principal"""
    print("🚀 Iniciando sincronización de archivos XBRL...")
    print("=" * 60)
    
    try:
        source_path, dest_path = get_source_and_dest_paths()
        
        print(f"📁 Origen: {source_path}")
        print(f"📁 Destino: {dest_path}")
        print("=" * 60)
        
        # Confirmar antes de proceder
        response = input("¿Desea continuar con la sincronización? (s/n): ").lower().strip()
        if response not in ['s', 'si', 'sí', 'y', 'yes']:
            print("❌ Sincronización cancelada")
            return
        
        sync_directories(source_path, dest_path)
        
    except KeyboardInterrupt:
        print("\n\n❌ Sincronización interrumpida por el usuario")
    except Exception as e:
        print(f"\n❌ Error durante la sincronización: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
