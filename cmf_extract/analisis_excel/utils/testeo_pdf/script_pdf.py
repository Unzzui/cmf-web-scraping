#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lee un PDF de EEFF, detecta números junto a las etiquetas (en ES) definidas en cuentas.json,
y en el Excel resultante pone el VALOR numérico; la fecha va en la columna 'Periodo'.

Requisitos: PyMuPDF (fitz), pandas, xlsxwriter

Uso:
  python script_pdf.py
"""

import json
import re
import unicodedata
from pathlib import Path
from datetime import datetime

import fitz  # PyMuPDF
import pandas as pd


# --------------------- CONFIGURACIÓN ---------------------
CUENTAS_JSON = "/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/cuentas.json"
PDF_PATH = "/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/testeo_pdf/Estados_financieros_(PDF)91297000_202506-1.pdf"
OUTPUT_DIR = "/home/unzzui/Documents/coding/CMF_extract/analisis_excel/utils/testeo_pdf/output"
PERIODO = "30.06.2025"  # Fecha a registrar en columna 'Periodo'

# Si tu PDF pone el periodo actual a la IZQUIERDA (lo más común), deja "left".
# Si estuviera a la derecha, cambia a "right".
CURRENT_PERIOD_POSITION = "left"  # "left" | "right"


# --------------------- helpers ---------------------

def strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )

def normalize(s: str) -> str:
    s = strip_accents(s)
    s = s.lower()
    s = re.sub(r"\s+", " ", s)
    return s.strip()

# Números estilo CL: 370.880 | 1.102.604 | (351.225) | 3,50
NUM_PAT = re.compile(r"\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?\)?")

def parse_number_cl(s: str):
    """Convierte texto estilo CL en float, soporta ( ) para negativos y '-' como 0."""
    st = s.strip()
    if st in ("-", "—", "–", ""):
        return 0.0
    neg = st.startswith("(") and st.endswith(")")
    if neg:
        st = st[1:-1]
    st = st.replace(".", "").replace(",", ".")
    try:
        v = float(st)
        return -v if neg else v
    except Exception:
        return None

def pick_amount(tokens: list[str], prefer="left"):
    """
    Elige un monto entre los tokens numéricos detectados en una línea.
    Heurísticas:
      1) Preferir tokens con separador de miles (.)
      2) O valor absoluto >= 1000
      3) Si nada calza, usar primer/último según 'prefer'
    """
    # Normalizar a pares (token, valor_parsed)
    parsed = []
    for t in tokens:
        v = parse_number_cl(t)
        if v is None:
            continue
        parsed.append((t.strip(), v))

    if not parsed:
        return None

    # candidatos “fuertes”
    strong = []
    for t, v in parsed:
        if "." in t and len(t) >= 5:
            strong.append((t, v))
        elif abs(v) >= 1000:
            strong.append((t, v))

    pool = strong if strong else parsed

    if prefer == "left":
        return pool[0][1]
    else:  # "right"
        return pool[-1][1]


# ------------------ PDF → líneas -------------------

def pdf_to_lines(pdf_path: Path) -> list[str]:
    """
    Reconstruye líneas a partir de 'words' de PyMuPDF agrupando por coordenada Y.
    """
    doc = fitz.open(str(pdf_path))
    all_lines = []
    for page in doc:
        words = page.get_text("words")  # [x0,y0,x1,y1,"word", block_no, line_no, word_no]
        words.sort(key=lambda w: (round(w[1], 1), w[0]))
        cur_y = None
        line_words = []
        for w in words:
            y = round(w[1], 1)
            text = w[4]
            if cur_y is None:
                cur_y = y
                line_words = [text]
            else:
                if abs(y - cur_y) <= 0.7:
                    line_words.append(text)
                else:
                    all_lines.append(" ".join(line_words))
                    cur_y = y
                    line_words = [text]
        if line_words:
            all_lines.append(" ".join(line_words))
    return all_lines


# --------------- mapeo de cuentas ES ---------------

def leer_mapeo_es(path_cuentas: Path) -> dict:
    cdict = json.loads(path_cuentas.read_text(encoding="utf-8"))
    for obligatorio in ("balance", "estado_resultados", "flujo_caja"):
        if obligatorio not in cdict:
            raise ValueError(f"Falta clave '{obligatorio}' en cuentas.json")
    return cdict

def es_encabezado(nombre: str) -> bool:
    return "[sinopsis]" in nombre

def es_total(nombre: str) -> bool:
    s = nombre.lower()
    return s.startswith("total ") or " totales" in s

def flatten_es_labels(cdict: dict) -> dict:
    out = {}
    for estado in ("balance", "estado_resultados", "flujo_caja"):
        labels = []
        for es_label in cdict[estado].keys():
            if es_encabezado(es_label) or es_total(es_label):
                continue
            labels.append(es_label)
        out[estado] = labels
    return out


# -------------- extracción de valores --------------

def extraer_valor(lines: list[str], etiqueta_es: str, prefer_side: str):
    """
    Busca la etiqueta en lines; si encuentra números en esa línea o las 2 siguientes,
    retorna el valor numérico elegido según heurística. Si no, None.
    """
    norm_lines = [normalize(ln) for ln in lines]
    nlabel = normalize(etiqueta_es)

    for idx, nln in enumerate(norm_lines):
        if nlabel in nln:
            # misma línea
            raw = lines[idx]
            nums = NUM_PAT.findall(raw)
            if nums:
                val = pick_amount(nums, prefer="left" if prefer_side == "left" else "right")
                if val is not None:
                    return val
            # mirar 1-2 líneas siguientes (cortes)
            for look in (1, 2):
                j = idx + look
                if j < len(lines):
                    raw2 = lines[j]
                    nums2 = NUM_PAT.findall(raw2)
                    if nums2:
                        val = pick_amount(nums2, prefer="left" if prefer_side == "left" else "right")
                        if val is not None:
                            return val
            break
    return None


def construir_tabla(lines: list[str], labels_es: list[str], periodo_str: str, prefer_side: str):
    filas = []
    for etiqueta in labels_es:
        val = extraer_valor(lines, etiqueta, prefer_side)
        filas.append({
            "Cuenta": etiqueta,      # SOLO etiqueta en español
            periodo_str: val         # fecha como nombre de columna, valor numérico
        })
    return filas


# ------------------- excel writer ------------------

def guardar_excel(tab_balance, tab_er, tab_flujo, salida: Path):
    with pd.ExcelWriter(str(salida), engine="xlsxwriter") as writer:
        pd.DataFrame(tab_balance).to_excel(writer, sheet_name="Balance", index=False)
        pd.DataFrame(tab_er).to_excel(writer, sheet_name="Estado_Resultados", index=False)
        pd.DataFrame(tab_flujo).to_excel(writer, sheet_name="Flujo_Efectivo", index=False)

        for sheet in ("Balance", "Estado_Resultados", "Flujo_Efectivo"):
            ws = writer.sheets[sheet]
            ws.set_column("A:A", 70)  # Cuenta (ES) - más ancha para nombres largos
            ws.set_column("B:B", 18)  # Valor (numérico) - columna de fecha como encabezado


# ---------------------- main -----------------------

def main():
    print("=== Script de Procesamiento de PDF de Estados Financieros ===")
    print(f"PDF: {PDF_PATH}")
    print(f"Cuentas: {CUENTAS_JSON}")
    print(f"Período: {PERIODO}")
    print(f"Directorio de salida: {OUTPUT_DIR}")
    print()

    # Verificar que los archivos existan
    pdf_path = Path(PDF_PATH)
    cuentas_path = Path(CUENTAS_JSON)
    output_dir = Path(OUTPUT_DIR)

    if not pdf_path.exists():
        print(f"❌ ERROR: No se encontró el PDF en {PDF_PATH}")
        return
    
    if not cuentas_path.exists():
        print(f"❌ ERROR: No se encontró el archivo de cuentas en {CUENTAS_JSON}")
        return
    
    if not output_dir.exists():
        print(f"⚠️  Creando directorio de salida: {OUTPUT_DIR}")
        output_dir.mkdir(parents=True, exist_ok=True)

    # Limpiar archivos Excel anteriores
    print("🧹 Limpiando archivos Excel anteriores...")
    excel_files = list(output_dir.glob("estados_financieros_*.xlsx"))
    if excel_files:
        for old_file in excel_files:
            try:
                old_file.unlink()
                print(f"🗑️  Eliminado: {old_file.name}")
            except Exception as e:
                print(f"⚠️  No se pudo eliminar {old_file.name}: {e}")
    else:
        print("✅ No hay archivos Excel anteriores para limpiar")

    # Generar nombre de archivo de salida con timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_filename = f"estados_financieros_{timestamp}.xlsx"
    out_path = output_dir / output_filename

    try:
        print("📖 Leyendo archivo de cuentas...")
        cdict = leer_mapeo_es(cuentas_path)
        labels = flatten_es_labels(cdict)
        print(f"✅ Etiquetas cargadas: Balance({len(labels['balance'])}), ER({len(labels['estado_resultados'])}), Flujo({len(labels['flujo_caja'])})")

        print("📄 Procesando PDF...")
        lines = pdf_to_lines(pdf_path)
        print(f"✅ PDF procesado: {len(lines)} líneas extraídas")

        print("🔍 Extrayendo datos...")
        tab_balance = construir_tabla(lines, labels["balance"], PERIODO, CURRENT_PERIOD_POSITION)
        tab_er      = construir_tabla(lines, labels["estado_resultados"], PERIODO, CURRENT_PERIOD_POSITION)
        tab_flujo   = construir_tabla(lines, labels["flujo_caja"], PERIODO, CURRENT_PERIOD_POSITION)

        print("💾 Guardando Excel...")
        guardar_excel(tab_balance, tab_er, tab_flujo, out_path)

        # Resumen consola
        marcados = sum(1 for f in (tab_balance + tab_er + tab_flujo) if f[PERIODO] is not None)
        total = len(tab_balance) + len(tab_er) + len(tab_flujo)
        print()
        print("🎉 PROCESAMIENTO COMPLETADO")
        print(f"📊 Filas con valor numérico: {marcados}/{total}")
        print(f"📁 Archivo generado: {out_path}")
        print(f"📈 Balance: {len(tab_balance)} items")
        print(f"📈 Estado de Resultados: {len(tab_er)} items")
        print(f"📈 Flujo de Efectivo: {len(tab_flujo)} items")

    except Exception as e:
        print(f"❌ ERROR durante el procesamiento: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
