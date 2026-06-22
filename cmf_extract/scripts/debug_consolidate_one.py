#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import sys
import traceback
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Uso: python scripts/debug_consolidate_one.py <company_dir> [langs es,en] [products_dir]")
        return 1

    company_dir = Path(argv[1]).resolve()
    langs = tuple((argv[2] if len(argv) > 2 else "es,en").split(','))
    products_dir = Path(argv[3]).resolve() if len(argv) > 3 else (Path(__file__).resolve().parents[1] / 'Products')

    # Raíz del repo (cmf_dir)
    cmf_dir = Path(__file__).resolve().parents[1]

    print(f"[debug] company_dir={company_dir}")
    print(f"[debug] langs={langs}")
    print(f"[debug] products_dir={products_dir}")
    print(f"[debug] cmf_dir={cmf_dir}")

    try:
        sys.path.insert(0, str(cmf_dir))
        import batch_xbrl_to_excel as b
    except Exception as ex:
        print(f"[debug] Error importando batch_xbrl_to_excel: {ex}")
        traceback.print_exc()
        return 2

    try:
        datasets = b.find_datasets(company_dir)
        print(f"[debug] datasets encontrados: {len(datasets)}")
        for ds in datasets[:3]:
            try:
                print(f"  - {ds.dataset_dir}  stem={ds.stem}")
            except Exception:
                pass
    except Exception as ex:
        print(f"[debug] Error buscando datasets: {ex}")
        traceback.print_exc()
        return 3

    try:
        b.generate_consolidated_company(company_dir, datasets, cmf_dir, langs, products_dir)
        print("[debug] generate_consolidated_company terminó sin excepción")
        return 0
    except Exception as ex:
        print(f"[debug] Excepción en generate_consolidated_company: {ex}")
        traceback.print_exc()
        return 4


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))


