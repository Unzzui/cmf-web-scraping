# -*- coding: utf-8 -*-
"""
IMPORTS TEMPORALMENTE COMENTADOS PARA REORGANIZACIÓN
==================================================
Este archivo será corregido automáticamente después de la reorganización.
Los imports comentados se restaurarán con las rutas correctas.

Cambios realizados:
# - Comentado: from cmf_xbrl_downloader import
"""

# -*- coding: utf-8 -*-
"""
IMPORTS TEMPORALMENTE COMENTADOS PARA REORGANIZACIÓN
==================================================
Este archivo será corregido automáticamente después de la reorganización.
Los imports comentados se restaurarán con las rutas correctas.

Cambios realizados:
# - Comentado: # from cmf_xbrl_downloader import  # FIXED: Mover a src/xbrl/
"""

#!/usr/bin/env python3
"""
Script de prueba para verificar la función corregida en cmf_xbrl_downloader.py
"""

import sys
import os

# Agregar el directorio actual al path para importar cmf_xbrl_downloader
sys.path.insert(0, '.')

try:
    # # from cmf_xbrl_downloader import  # FIXED: Mover a src/xbrl/  # FIXED: Mover a src/xbrl/ CMFXBRLDownloader
    print("✅ Importación exitosa de cmf_xbrl_downloader")
    
    # Crear una instancia para probar la función corregida
    downloader = CMFXBRLDownloader()
    
    # Probar la función corregida directamente
    print("\n🔍 Probando función corregida...")
    
    # Simular la llamada que hace el sistema principal
    rut = "91297000"
    rut_completo = "91297000-0"
    safe_company_name = "CAP_SA"
    target_dir = f"./data/XBRL/Total/{rut_completo}_{safe_company_name}"
    
    print(f"Directorio objetivo: {target_dir}")
    
    # Llamar a la función corregida
    existing_periods = downloader.discover_existing_periods(target_dir)
    
    print(f"📊 Períodos detectados: {len(existing_periods)}")
    print(f"📋 Lista de períodos: {sorted(list(existing_periods))}")
    
    # Verificar si 202412 está siendo detectado incorrectamente
    if "202412" in existing_periods:
        print("❌ PROBLEMA: 202412 está siendo detectado como existente")
    else:
        print("✅ CORRECTO: 202412 NO está siendo detectado como existente")
    
    # Verificar períodos recientes
    recent_periods = [p for p in existing_periods if p.startswith("2024")]
    print(f"📅 Períodos 2024: {sorted(recent_periods)}")
    
    if "202412" in recent_periods:
        print("❌ PROBLEMA: 202412 está en la lista de 2024")
    else:
        print("✅ CORRECTO: 202412 NO está en la lista de 2024")
        
except ImportError as e:
    print(f"❌ Error importando: {e}")
except Exception as e:
    print(f"❌ Error durante la prueba: {e}")
    import traceback
    traceback.print_exc()
