#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para verificar la distribución de cuentas duplicadas en el Excel generado
"""

import pandas as pd

def check_excel_duplicates():
    """Verifica que los duplicados estén distribuidos correctamente en sus secciones"""
    
    # Cargar datos del CSV (orden actual después del sorting)
    df = pd.read_csv('data/XBRL/Total/91705000-7_QUIÑENCO_SA/out_consolidated_2025-2014/primary_roles_201403-202503_es.csv')
    cash_flow = df[df['RoleCode'] == 510000].copy()

    print('=== VERIFICACIÓN DE DISTRIBUCIÓN DE DUPLICADOS ===')
    print(f'Total cuentas Cash Flow: {len(cash_flow)}')
    print()

    # Identificar duplicados
    duplicates = cash_flow[cash_flow.duplicated(subset=['Label'], keep=False)]
    unique_duplicate_labels = duplicates['Label'].unique()
    
    print(f'Cuentas duplicadas encontradas: {len(unique_duplicate_labels)}')
    for label in unique_duplicate_labels:
        print(f'  - {label}')
    print()

    # Mostrar orden actual completo de Cash Flow con numeración
    print('ORDEN ACTUAL DEL CASH FLOW (primeras 50 cuentas):')
    print('Pos | Tipo     | Cuenta')
    print('-' * 80)
    
    for i, (_, row) in enumerate(cash_flow.head(50).iterrows()):
        label = row['Label']
        label_key_id = str(row.get('LabelKeyId', '')).strip()
        
        # Identificar tipo
        if '[sinopsis]' in label.lower():
            tipo = '📋 SIN'
        elif label in unique_duplicate_labels:
            tipo = '🔄 DUP'
        else:
            tipo = '💰 DAT'
            
        print(f'{i+1:3d} | {tipo}     | {label[:50]}')
        if label in unique_duplicate_labels:
            print(f'     |          | Key: {label_key_id[:40]}')
    
    print()
    print('ANÁLISIS DE DUPLICADOS:')
    
    # Analizar cada duplicado
    for label in unique_duplicate_labels:
        duplicate_rows = cash_flow[cash_flow['Label'] == label]
        positions = []
        keys = []
        
        for idx, (_, row) in enumerate(duplicate_rows.iterrows()):
            # Encontrar posición en la lista completa
            position = cash_flow[cash_flow['Label'] == label].index.tolist().index(row.name) + 1
            positions.append(cash_flow.index.tolist().index(row.name) + 1)
            keys.append(str(row.get('LabelKeyId', '')).strip())
        
        print(f'\n"{label}":')
        print(f'  Ocurrencias: {len(duplicate_rows)}')
        
        for i, (pos, key) in enumerate(zip(positions, keys)):
            section = 'Operación' if '510' in key else ('Inversión' if '520' in key else ('Financiación' if '530' in key else 'Otro'))
            print(f'    #{i+1}: Posición {pos:3d} - {section} - Key: {key[:30]}')
    
    return cash_flow, unique_duplicate_labels

if __name__ == '__main__':
    check_excel_duplicates()