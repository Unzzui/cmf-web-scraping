#!/usr/bin/env python3
"""CLI: sube los Excel de bancos a FindataChile como productos vendibles.

Etapa 3A del pipeline (blob + catálogo), equivalente a lo que hace el orquestador de la
GUI para las empresas IFRS, pero para los libros de ``Products/Bancos``.

**Esto publica productos A LA VENTA**, no sólo sube archivos: el endpoint
``/api/admin/process-files`` crea/actualiza el producto de la empresa (id = RUT) con un
``priceOverride``. Por eso el default es ``--dry-run`` y publicar exige ``--live``.

Credenciales: se leen de ``config/pipeline_settings.json`` (gitignoreado). Necesita
``fdc_base_url``, ``fdc_username`` y ``fdc_password``.

Ejemplos:
    python scripts/upload_banks_to_findatachile.py                 # dry-run, no sube nada
    python scripts/upload_banks_to_findatachile.py --only 001 --live
    python scripts/upload_banks_to_findatachile.py --live --precio 7500
"""

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from src.gui.pipeline.findatachile_uploader import FinDataChileUploader  # noqa: E402
from src.gui.pipeline.settings import PipelineSettings  # noqa: E402

# "BANCO DE CHILE - 97004000-5 - Análisis Financiero 2014-2026 [ES].xlsx"
_PATRON = re.compile(r"^(?P<nombre>.+?) - (?P<rut>[\dkK.\-]+) - .*?(?P<ini>\d{4})-(?P<fin>\d{4})")


def parse_nombre(fname: str) -> dict | None:
    m = _PATRON.match(fname)
    if not m:
        return None
    return {
        "nombre": m.group("nombre"),
        "rut": m.group("rut"),
        "start_year": int(m.group("ini")),
        "end_year": int(m.group("fin")),
    }


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Sube los Excel de bancos a FindataChile")
    p.add_argument("--dir", default="Products/Bancos", help="Directorio con los Excel")
    p.add_argument("--banks", default="", help="Filtra por texto en el nombre del archivo")
    p.add_argument("--only", default="", help="Alias de --banks")
    p.add_argument("--precio", type=int, default=None,
                   help="Precio CLP por producto (default: el de pipeline_settings)")
    p.add_argument("--live", action="store_true",
                   help="PUBLICA de verdad. Sin esto es dry-run y no sube nada.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    filtro = (args.banks or args.only).strip().lower()

    libros = sorted(Path(args.dir).glob("*.xlsx"))
    if filtro:
        libros = [p for p in libros if filtro in p.name.lower()]
    if not libros:
        print(f"No hay Excel en {args.dir}", file=sys.stderr)
        return 1

    settings = PipelineSettings.load()
    if args.precio:
        settings.fdc_price = args.precio

    faltan = [k for k in ("fdc_base_url", "fdc_username", "fdc_password")
              if not getattr(settings, k, "")]
    if faltan and args.live:
        print(f"Faltan credenciales en config/pipeline_settings.json: {', '.join(faltan)}",
              file=sys.stderr)
        return 2

    print(f"{'[LIVE]' if args.live else '[dry-run]'} destino: "
          f"{settings.fdc_base_url or '(sin configurar)'}  precio: {settings.fdc_price} CLP")
    print(f"{len(libros)} libros en {args.dir}\n")

    malos = [p.name for p in libros if not parse_nombre(p.name)]
    if malos:
        # El server deduce empresa/RUT del nombre: si no parsea acá, allá tampoco.
        print(f"Nombre no parseable ({len(malos)}), se abortaría la subida:", file=sys.stderr)
        for n in malos:
            print(f"  {n}", file=sys.stderr)
        return 2

    if not args.live:
        for p in libros:
            info = parse_nombre(p.name)
            print(f"  [dry-run] {info['rut']:12s} {info['nombre'][:38]:38s} "
                  f"{info['start_year']}-{info['end_year']}  ({p.stat().st_size // 1024} KB)")
        print(f"\nNada subido. Para publicar de verdad: --live")
        return 0

    uploader = FinDataChileUploader(settings)
    if not uploader.available:
        print("La librería 'requests' no está instalada", file=sys.stderr)
        return 2
    ok, msg = uploader.login()
    if not ok:
        print(f"Login falló: {msg}", file=sys.stderr)
        return 2

    subidos = fallidos = 0
    for p in libros:
        info = parse_nombre(p.name)
        ok, msg = uploader.upload_file(
            str(p), company_name=info["nombre"], rut_completo=info["rut"],
            start_year=info["start_year"], end_year=info["end_year"], quarterly=False,
        )
        if ok:
            subidos += 1
            print(f"  OK   {info['rut']:12s} {info['nombre'][:38]:38s} {msg}")
        else:
            fallidos += 1
            print(f"  FALLA {info['rut']:12s} {info['nombre'][:38]:38s} {msg}", file=sys.stderr)

    print(f"\nsubidos: {subidos} | fallidos: {fallidos}")
    return 0 if fallidos == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
