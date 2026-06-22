#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Normaliza un facts_*.csv (Arelle) a un formato "plano":
 - Sin indentación/jerarquía: una fila por cuenta real con valores
 - Columnas: Label, RoleCode, SectionKey, y fechas YYYY-MM-DD
 - Coalescea valores cuando las fechas vienen con sufijos ("YYYY-MM-DD - ... [miembro]")
 - Elimina qname/Value/etc. innecesarios

Uso:
  • Un solo archivo:
      python normalize_facts_flat.py --facts data/X/.../out_XXXX/facts_XXXX_es.csv
  • Por empresa (todos los períodos):
      python normalize_facts_flat.py --company-dir data/XBRL/Total/<RUT_EMPRESA>

Salida:
  • facts_flat_<stem>_<lang>.csv junto al original (en la misma carpeta out_<stem>)
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd


DATE_RE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
DATE_RE_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})")
DATE_RE_DMY = re.compile(r"^(\d{1,2})-(\d{1,2})-(\d{4})")


def _parse_date_prefix(s: str) -> Optional[str]:
    s = str(s).strip()
    m = DATE_RE_ISO.match(s)
    if m:
        y, M, d = m.groups()
        return f"{int(y):04d}-{int(M):02d}-{int(d):02d}"
    m = DATE_RE_MDY.match(s)
    if m:
        M, d, y = m.groups()
        return f"{int(y):04d}-{int(M):02d}-{int(d):02d}"
    m = DATE_RE_DMY.match(s)
        # muy poco probable en CMF, pero se soporta
    if m:
        d, M, y = m.groups()
        return f"{int(y):04d}-{int(M):02d}-{int(d):02d}"
    return None


def _is_role_header(label: str) -> Optional[str]:
    m = re.match(r"^\s*\[(\d{6})\]", label or "")
    return m.group(1) if m else None


def _is_sinopsis(label: str) -> bool:
    s = (label or '').lower()
    return ('[sinopsis]' in s) or ('[abstract]' in s) or ('[resumen]' in s)


def _detect_super_section(label: str) -> Optional[str]:
    s = (label or '').lower()
    if 'actividades de operación' in s or 'actividades de la operación' in s:
        return 'Operación'
    if 'actividades de inversión' in s or 'actividades de inversion' in s:
        return 'Inversión'
    if 'actividades de financiación' in s or 'actividades de financiacion' in s or 'actividades de financiamiento' in s:
        return 'Financiación'
    return None


def _detect_main_section(label: str) -> Optional[str]:
    s = (label or '').lower()
    if 'negocios no bancarios' in s:
        return 'Negocios no bancarios [sinopsis]'
    if 'servicios bancarios' in s:
        return 'Servicios bancarios [sinopsis]'
    return None


def _build_section_key(super_sec: Optional[str], main: Optional[str], sub: Optional[str]) -> str:
    parts: List[str] = []
    if super_sec:
        parts.append(super_sec)
    if main:
        parts.append(main)
    if sub and (not main or main.lower() not in sub.lower()):
        parts.append(sub)
    return ' | '.join(parts)


def normalize_one_facts(facts_path: Path, out_path: Optional[Path] = None) -> Optional[Path]:
    try:
        df = pd.read_csv(facts_path, engine='python')
    except Exception as e:
        print(f"[flat] ⚠ No se pudo leer: {facts_path} ({e})")
        return None

    if 'Label' not in df.columns:
        print(f"[flat] ⚠ Archivo sin columna 'Label': {facts_path}")
        return None

    # Mapa fecha base -> columnas que inician con esa fecha (puras y con sufijo)
    date_groups: Dict[str, List[str]] = {}
    for col in df.columns:
        dk = _parse_date_prefix(col)
        if dk:
            date_groups.setdefault(dk, []).append(col)

    if not date_groups:
        print(f"[flat] ⚠ No se detectaron columnas de fecha en: {facts_path}")
        return None

    # Orden de fechas: más recientes primero
    ordered_dates = sorted(date_groups.keys(), reverse=True)

    current_role: Optional[str] = None
    current_super: Optional[str] = None
    current_main: Optional[str] = None
    current_sub: Optional[str] = None

    rows: List[dict] = []

    for idx, row in df.iterrows():
        raw_label = row.get('Label')
        label = str(raw_label).strip() if isinstance(raw_label, str) else (raw_label if raw_label is not None else '')
        if not label:
            continue

        # 1) Detectar cambio de role
        rc = _is_role_header(label)
        if rc:
            current_role = rc
            current_super = None
            current_main = None
            current_sub = None
            continue

        # 2) Detectar super sección (flujo)
        sup = _detect_super_section(label)
        if sup:
            current_super = sup
            current_sub = None
            # no reset de main para preservar NB/SB si está explícito
            continue

        # 3) Detectar categorías sinopsis (main/sub)
        if _is_sinopsis(label):
            main = _detect_main_section(label)
            if main:
                current_main = main
                current_sub = None
            else:
                # Sub categoría genérica (p. ej. "Clases de pagos [sinopsis]")
                current_sub = label
            continue

        # 4) Fila de cuenta real: colectar valores por fecha base
        #    Tomar el primer valor no vacío dentro del grupo de columnas de cada fecha
        vals: Dict[str, object] = {}
        non_empty = 0
        for d in ordered_dates:
            v = None
            for c in date_groups[d]:
                val = row.get(c)
                if val is None:
                    continue
                if isinstance(val, float) and pd.isna(val):
                    continue
                sv = str(val).strip()
                if sv == '' or sv == '-':
                    continue
                v = val
                break
            if v is not None:
                vals[d] = v
                non_empty += 1

        # 5) Emitir fila si hay algún valor
        if non_empty > 0 and current_role is not None:
            section_key = _build_section_key(current_super, current_main, current_sub)
            out = {
                'LabelKeyId': f"{current_role}||{label}",
                'LabelKeyIdExt': f"{current_role}||{label}||{section_key}",
                'RoleCode': current_role,
                'SectionKey': section_key,
                'Label': label,
            }
            out.update(vals)
            rows.append(out)

    if not rows:
        print(f"[flat] ⚠ No se generaron filas con datos en: {facts_path}")
        return None

    flat = pd.DataFrame(rows)
    # Orden básico: RoleCode, luego Label (estable); fechas de más reciente a más antigua
    meta = ['LabelKeyId', 'LabelKeyIdExt', 'RoleCode', 'SectionKey', 'Label']
    flat = flat[meta + ordered_dates]

    if out_path is None:
        # facts_XXXX_es.csv -> facts_flat_XXXX_es.csv en la misma carpeta
        out_path = facts_path.with_name(f"facts_flat_{facts_path.stem.split('_', 1)[1]}")
    flat.to_csv(out_path, index=False)
    print(f"[flat] Escrito: {out_path}")
    return out_path


def normalize_company(company_dir: Path) -> int:
    # Procesa todos los facts_*_es.csv dentro de out_* de la empresa
    count = 0
    for facts_path in sorted(company_dir.rglob('out_*/*facts_*_es.csv')):
        try:
            if normalize_one_facts(facts_path):
                count += 1
        except Exception as e:
            print(f"[flat] ⚠ Error normalizando {facts_path}: {e}")
    print(f"[flat] Archivos normalizados: {count}")
    return 0 if count > 0 else 1


def parse_args(argv: List[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description='Normaliza facts_*_es.csv a un CSV plano (Label + fechas)')
    ap.add_argument('--facts', type=Path, help='Ruta a facts_*_es.csv a normalizar')
    ap.add_argument('--company-dir', type=Path, help='Directorio de la empresa (procesa todos los períodos)')
    return ap.parse_args(argv)


def main(argv: List[str] | None = None) -> int:
    args = parse_args(argv)
    if args.facts and args.facts.exists():
        return 0 if normalize_one_facts(args.facts) else 1
    if args.company_dir and args.company_dir.exists():
        return normalize_company(args.company_dir)
    print('Uso: normalize_facts_flat.py (--facts <file> | --company-dir <dir>)')
    return 2


if __name__ == '__main__':
    raise SystemExit(main())

