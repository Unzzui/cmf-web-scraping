#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Construye `taxonomy_label_renames.json` a partir de la identidad real de los
elementos en el PRESENTATION linkbase de los XBRL (API de Arelle).

Motivo: la taxonomía CMF renombra el preferred-label de un mismo elemento entre
versiones (p. ej. `cl-hb:InstrumentosDeudaEmitidosBancos` fue "Instrumentos de
deuda emitidos" hasta 2021 y "Instrumentos financieros de deuda emitidos" desde
2022). Como el pipeline identifica cuentas por el TEXTO del label, esos renames
parten la serie de tiempo en dos filas. Este mapa permite unificarlas
(`label_rename.unify_renamed_accounts`) conservando el label MÁS RECIENTE.

Estrategia:
  1. Recorre las instancias .xbrl bajo --base-dir (una por (empresa, período)).
  2. Con Arelle carga el DTS y camina el árbol de presentación de los roles de
     estados (210000/310000/320000/510000), emitiendo (role_code, element_qname,
     preferred_label, período).
  3. Agrupa por (role_code, element_localname): si un elemento tuvo >1 label a lo
     largo del tiempo => rename. Canónico = label del período MÁS RECIENTE.
  4. Escribe { role_code: { label_viejo: label_canónico } }.

El rename es propiedad de la TAXONOMÍA (namespaces cl-hb/cl-ci/ifrs compartidos),
así que basta muestrear pocas instancias por año; pero procesar todas es seguro.

Uso:
  python build_label_rename_map.py \
      --base-dir data/XBRL/Total \
      --out taxonomy_label_renames.json \
      [--per-year 3] [--lang es-CL] [--offline]

Requiere el paquete Arelle importable (PYTHONPATH a tools/Arelle) y el .venv de
Arelle. Corre ONLINE por defecto para resolver taxonomías viejas no cacheadas.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

STATEMENT_ROLES = {"210000", "310000", "320000", "510000"}


def _role_code(uri: str) -> str:
    m = re.search(r"role-(\d{6})", uri) or re.search(r"_(\d{6})(?:$|[^0-9])", uri)
    return m.group(1) if m else ""


def _period_of(xbrl_path: Path) -> str:
    m = re.search(r"_(\d{6})_C\.xbrl$", xbrl_path.name)
    return m.group(1) if m else xbrl_path.name


def find_instances(base_dir: Path, per_year: int | None) -> list[Path]:
    """Instancias .xbrl. Si per_year, limita a `per_year` instancias por
    (empresa, año de taxonomía) para acelerar (el label es por año)."""
    all_x = sorted(base_dir.glob("*/Estados_financieros_*_extracted/*_C.xbrl"))
    if not per_year:
        return all_x
    seen: dict[tuple[str, str], int] = defaultdict(int)
    out = []
    for x in all_x:
        rutm = re.search(r"/(\d{7,8}-[0-9kK])_", str(x))
        rut = rutm.group(1) if rutm else ""
        year = _period_of(x)[:4]
        key = (rut, year)
        if seen[key] < per_year:
            seen[key] += 1
            out.append(x)
    return out


def extract(instances: list[Path], lang: str, offline: bool):
    """Devuelve dict (role_code, localname) -> {period: label} vía Arelle."""
    from arelle import Cntlr, XbrlConst  # import diferido (requiere PYTHONPATH)

    cntlr = Cntlr.Cntlr(logFileName="logToPrint")
    cntlr.webCache.workOffline = offline
    groups: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)

    for i, xp in enumerate(instances, 1):
        period = _period_of(xp)
        try:
            modelXbrl = cntlr.modelManager.load(str(xp))
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f"[{i}/{len(instances)}] LOAD FAIL {xp.name}: {e}\n")
            continue
        prel = modelXbrl.relationshipSet(XbrlConst.parentChild)
        for roleURI in prel.linkRoleUris:
            rc = _role_code(roleURI)
            if rc not in STATEMENT_ROLES:
                continue
            relSet = modelXbrl.relationshipSet(XbrlConst.parentChild, roleURI)

            def walk(concept, rel=None):
                if concept is None or concept.qname is None:
                    return
                ln = concept.qname.localName
                pref = rel.preferredLabel if rel is not None else None
                try:
                    lbl = concept.label(preferredLabel=pref, lang=lang, fallbackToQname=False)
                except Exception:  # noqa: BLE001
                    lbl = ""
                if ln and lbl:
                    # el período más reciente gana si un mismo elemento/rol aparece 2x
                    groups[(rc, ln)][period] = lbl
                for r in relSet.fromModelObject(concept):
                    walk(r.toModelObject, r)

            for root in relSet.rootConcepts:
                walk(root, None)
        cntlr.modelManager.close()
        sys.stderr.write(f"[{i}/{len(instances)}] OK {xp.name}\n")
    cntlr.close()
    return groups


def build_map(groups) -> dict[str, dict[str, str]]:
    rename_map: dict[str, dict[str, str]] = defaultdict(dict)
    for (rc, ln), by_period in groups.items():
        labels = set(by_period.values())
        if len(labels) <= 1:
            continue
        canon = by_period[max(by_period)]  # período máximo = más reciente
        for v in labels - {canon}:
            rename_map[rc][v] = canon
    return {k: dict(sorted(v.items())) for k, v in sorted(rename_map.items())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-dir", default="data/XBRL/Total")
    ap.add_argument("--out", default=str(Path(__file__).parent / "taxonomy_label_renames.json"))
    ap.add_argument("--per-year", type=int, default=None,
                    help="Máx instancias por (empresa, año). Default: todas.")
    ap.add_argument("--lang", default="es-CL")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--merge", action="store_true",
                    help="Fusiona con el JSON existente en --out en vez de sobrescribir.")
    args = ap.parse_args()

    instances = find_instances(Path(args.base_dir), args.per_year)
    sys.stderr.write(f"Instancias a procesar: {len(instances)}\n")
    if not instances:
        sys.stderr.write("Sin instancias .xbrl.\n")
        return 1

    groups = extract(instances, args.lang, args.offline)
    rename_map = build_map(groups)

    if args.merge:
        try:
            existing = json.loads(Path(args.out).read_text(encoding="utf-8"))
            for rc, m in existing.items():
                rename_map.setdefault(rc, {})
                for k, v in m.items():
                    rename_map[rc].setdefault(k, v)
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    Path(args.out).write_text(json.dumps(rename_map, ensure_ascii=False, indent=2), encoding="utf-8")
    n = sum(len(v) for v in rename_map.values())
    sys.stderr.write(f"Mapa escrito: {args.out}  ({n} renames en roles {sorted(rename_map)})\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
