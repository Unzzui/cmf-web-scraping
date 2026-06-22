#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple, List, Any
import re
import concurrent.futures
import threading

from analisis_excel.utils.reconcile_en_with_es import reconcile_en_with_es


PRETTY_RE = re.compile(
    r"^(?P<company>.+) - (?P<rut>\d{7,8}(?:-[0-9Kk])?) - (?P<title>.+) (?P<range>\d{4}-\d{4}(?:Q[1-4])?) \[(?P<lang>ES|EN)\]\.xlsx$"
)


def find_pairs(dir_path: Path) -> List[Tuple[Path, Path]]:
    files = list(dir_path.glob("*.xlsx"))
    by_key: Dict[Tuple[str, str], Dict[str, Path]] = {}
    for p in files:
        m = PRETTY_RE.match(p.name)
        if not m:
            continue
        key = (m.group("rut"), m.group("range"))
        lang = m.group("lang").upper()
        by_key.setdefault(key, {})[lang] = p
    pairs: List[Tuple[Path, Path]] = []
    for (rut, rg), mp in by_key.items():
        es = mp.get("ES")
        en = mp.get("EN")
        if es and en:
            pairs.append((es, en))
    return pairs


def reconcile_dir(base: Path) -> int:
    """Reconcilia en el directorio base si contiene archivos; si no, recorre subcarpetas conocidas."""
    count = 0
    # Si el base contiene archivos pretty, trabajar solo aquí
    pairs_here = find_pairs(base)
    if pairs_here:
        for es, en in pairs_here:
            if reconcile_en_with_es(en, es, blank_unmatched_en_rows=True):
                count += 1
        return count
    # Si no hay archivos en base, explorar subcarpetas conocidas
    for freq in ("Anual", "Trimestral", "Total"):
        d = base / freq
        if not d.exists():
            continue
        for es, en in find_pairs(d):
            if reconcile_en_with_es(en, es, blank_unmatched_en_rows=True):
                count += 1
    return count


def reconcile_dir_threaded(base: Path, *, dash: Any | None = None, max_workers: int = 4) -> int:
    """Reconcilia EN con ES en paralelo y opcionalmente actualiza un dashboard.

    - dash: instancia de ConsoleXBRLDashboard (opcional). Si se provee, mostrará progreso por archivo EN.
    - max_workers: tamaño del pool de hilos.
    """
    # Escaneando pares ES/EN
    all_pairs: List[Tuple[Path, Path]] = []
    # Si el base contiene archivos pretty, trabajar solo aquí
    pairs_here = find_pairs(base)
    if pairs_here:
        # Pares encontrados en base
        all_pairs.extend(pairs_here)
    else:
        for freq in ("Anual", "Trimestral", "Total"):
            d = base / freq
            if not d.exists():
                continue
            pairs = find_pairs(d)
            # Pares encontrados
            all_pairs.extend(pairs)
    # Total pares a reconciliar

    changed_count = 0

    def _empresa_from_path(p: Path) -> str:
        m = PRETTY_RE.match(p.name)
        if m:
            return m.group("company")
        return p.stem

    def _periodo_from_path(p: Path) -> str:
        m = PRETTY_RE.match(p.name)
        if m:
            return m.group("range")
        return "-"

    def _do_pair(es: Path, en: Path) -> tuple[Path, Path, bool, str | None]:
        key = str(en)
        if dash is not None:
            try:
                empresa = _empresa_from_path(en)
                periodo = _periodo_from_path(en)
                dash.update(key, estado="En progreso", progreso="reconciliar", current=0, total=1,
                            worker=threading.get_ident(), empresa_name=empresa, rut_display=en.name, periodo=periodo)
            except Exception:
                pass
        try:
            changed = reconcile_en_with_es(en, es, blank_unmatched_en_rows=True)
            return es, en, changed, None
        except Exception as ex:
            return es, en, False, str(ex)
        finally:
            if dash is not None:
                try:
                    empresa = _empresa_from_path(en)
                    periodo = _periodo_from_path(en)
                    dash.update(key, estado="Completado", progreso="listo", current=1, total=1,
                                empresa_name=empresa, rut_display=en.name, periodo=periodo)
                except Exception:
                    pass

    import time as _time
    # Iniciando reconciliación
    _t_all = _time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        def _timed_pair(es: Path, en: Path):
            t0 = _time.perf_counter()
            res = _do_pair(es, en)
            dt = _time.perf_counter() - t0
            return (*res, dt)
        futs = [ex.submit(_timed_pair, es, en) for (es, en) in all_pairs]
        total = len(futs)
        done = 0
        for fut in concurrent.futures.as_completed(futs):
            es, en, changed, err, elapsed = fut.result()
            done += 1
            if err is None and changed:
                changed_count += 1
                # Archivo actualizado
            elif err is None:
                # Sin cambios
            else:
                # Error en reconciliación
    # Reconciliación finalizada
    return changed_count


def main() -> int:
    base = Path(__file__).resolve().parents[2] / "Product_v1"
    if not base.exists():
        # Directorio base no existe
        return 2
    n = reconcile_dir(base)
    # Reconciliación completada
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


