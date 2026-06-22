#!/usr/bin/env python3
import zipfile
import xml.etree.ElementTree as ET
import sys

def check_excel_content(xlsx_path):
    try:
        with zipfile.ZipFile(xlsx_path, 'r') as zip_file:
            # Leer strings compartidas
            shared_strings = {}
            try:
                with zip_file.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    for i, si in enumerate(root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}si')):
                        t = si.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
                        if t is not None:
                            shared_strings[str(i)] = t.text
            except:
                print("No se pudo leer sharedStrings.xml")
            
            # Buscar hojas
            try:
                with zip_file.open('xl/workbook.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    sheets = []
                    for sheet in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}sheet'):
                        name = sheet.get('name')
                        rid = sheet.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')
                        sheets.append((name, rid))
                    
                    print(f"Hojas encontradas: {[s[0] for s in sheets]}")
                    
                    # Buscar hoja de flujo
                    flujo_sheet = None
                    for name, rid in sheets:
                        if 'flujo' in name.lower() or 'cash' in name.lower():
                            flujo_sheet = (name, rid)
                            break
                    
                    if not flujo_sheet:
                        print("No se encontró hoja de flujo")
                        return
                    
                    print(f"Analizando hoja: {flujo_sheet[0]}")
                    
            except Exception as e:
                print(f"Error leyendo workbook: {e}")
                return
            
            # Leer contenido de la hoja de flujo
            try:
                sheet_path = f'xl/worksheets/sheet{flujo_sheet[1][3:]}.xml'  # rid = rId1 -> sheet1.xml
                with zip_file.open(sheet_path) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    
                    found_primas = False
                    row_count = 0
                    
                    for row in root.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row'):
                        row_count += 1
                        cells = row.findall('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}c')
                        
                        if cells:
                            # Obtener primera celda (columna A)
                            first_cell = cells[0]
                            v = first_cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                            
                            if v is not None:
                                value = v.text
                                # Si es referencia a string compartida
                                if first_cell.get('t') == 's':
                                    value = shared_strings.get(value, value)
                                
                                if value and 'primas' in str(value).lower():
                                    print(f"✅ ENCONTRADA en fila {row.get('r')}: {value}")
                                    found_primas = True
                                    
                                    # Mostrar valores de otras columnas
                                    for cell in cells[1:]:  # Skip primera columna
                                        v_cell = cell.find('.//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
                                        if v_cell is not None and v_cell.text:
                                            col = cell.get('r', '').replace(row.get('r', ''), '')
                                            val = v_cell.text
                                            if cell.get('t') == 's':
                                                val = shared_strings.get(val, val)
                                            print(f"  {col}: {val}")
                    
                    print(f"Total filas procesadas: {row_count}")
                    if not found_primas:
                        print("❌ No se encontró cuenta con 'primas'")
                        
            except Exception as e:
                print(f"Error leyendo hoja: {e}")
                
    except Exception as e:
        print(f"Error abriendo Excel: {e}")

if __name__ == "__main__":
    xlsx_path = "./data/XBRL/Total/76455830-8_WATTS_SA/out_consolidated_2025-2023/estados_76455830-8_202312-202503_es.xlsx"
    check_excel_content(xlsx_path)