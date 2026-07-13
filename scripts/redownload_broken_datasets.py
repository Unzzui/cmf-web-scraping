#!/usr/bin/env python3
"""Re-descarga los datasets XBRL a los que les falta el schema del emisor.

El .xbrl declara `<link:schemaRef href="<rut>_<yyyymm>_C_shell.xsd">` — un archivo
LOCAL que viene en el ZIP de la CMF. Si la extracción quedó incompleta y ese .xsd no
está, Arelle no puede resolver NINGÚN concepto (cl-ci:*), exporta cero hechos y
termina con exit 0. El validador de descarga no lo detectaba porque sólo exigía
"algún .xsd", y estos datasets traen el `_dimension.xsd` (que no sirve para esto).

Uso: python scripts/redownload_broken_datasets.py [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

BASE = ROOT / "data" / "XBRL" / "Total"
DS_RE = re.compile(r"Estados_financieros_\(XBRL\)(\d+)_(\d{6})_extracted$")
# El href puede venir con comillas dobles O simples: la CMF emite ambos estilos.
SCHEMA_RE = re.compile(r"""schemaRef[^>]*href=["']([^"']+\.xsd)["']""", re.I)


def schema_requerido(ds: Path) -> str | None:
    """Nombre del .xsd LOCAL que el .xbrl declara como schemaRef.

    Devuelve None si el schemaRef es remoto (http://www.svs.cl/...): esos son la
    taxonomía de la CMF y los resuelve Arelle desde su cache, no vienen en el ZIP.
    """
    xbrl = next(iter(ds.glob("*.xbrl")), None)
    if xbrl is None:
        return None
    try:
        cabecera = xbrl.read_bytes()[:4000].decode("utf-8", "ignore")
    except OSError:
        return None
    for m in SCHEMA_RE.finditer(cabecera):
        href = m.group(1)
        if href.startswith(("http://", "https://")):
            continue
        return Path(href).name
    return None


def roto(ds: Path) -> bool:
    """El dataset declara un schemaRef local que no está en la carpeta."""
    req = schema_requerido(ds)
    return bool(req) and not (ds / req).exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    from xbrl.cmf_xbrl_http_downloader import (
        _build_session, _entidad_url, _find_xbrl_link,
    )
    from xbrl.http_throttle import polite_request as _polite_request

    rotos = []
    for ds in BASE.glob("*/Estados_financieros_*_extracted"):
        m = DS_RE.search(ds.name)
        if m and roto(ds):
            rotos.append((ds, m.group(1), m.group(2)))
    rotos.sort()
    if args.limit:
        rotos = rotos[: args.limit]

    print(f"Datasets con schemaRef local ausente: {len(rotos)}")
    empresas = {ds.parent.name for ds, _, _ in rotos}
    print(f"Empresas afectadas: {len(empresas)}")
    if args.dry_run:
        for ds, rut, per in rotos[:15]:
            print(f"   {rut}_{per}  falta {schema_requerido(ds)}")
        return 0

    sess = _build_session(2)
    ok = fail = 0
    t0 = time.perf_counter()

    for i, (ds, rut, yyyymm) in enumerate(rotos, 1):
        year, month = yyyymm[:4], yyyymm[4:6]
        req = schema_requerido(ds)
        base = _entidad_url(rut)
        conseguido = False

        motivos = []
        for tipo in ("C", "I"):
            try:
                r = _polite_request(sess, "POST", base, data={
                    "forma": "P", "aa": year, "mm": month,
                    "tipo": tipo, "tipo_norma": "IFRS",
                }, timeout=60)
                href = _find_xbrl_link(r.text)
                if not href:
                    motivos.append(f"{tipo}:sin-enlace(HTTP {r.status_code})")
                    continue
                # El href es relativo a entidad.php ("../inc/..." sube a /institucional/).
                # Construirlo a mano da 404: hay que resolverlo contra la URL base.
                url = urljoin(base, href)
                z = _polite_request(sess, "GET", url, timeout=120)
                if z.status_code != 200 or not z.content:
                    motivos.append(f"{tipo}:zip-HTTP-{z.status_code}")
                    continue
                with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
                    nombres = zf.namelist()
                    if not any(Path(n).name == req for n in nombres):
                        motivos.append(f"{tipo}:zip-sin-{req}")
                        continue
                    zf.extractall(ds)
                conseguido = (ds / req).exists()
                if conseguido:
                    break
            except Exception as exc:
                motivos.append(f"{tipo}:{type(exc).__name__}:{str(exc)[:50]}")

        if conseguido:
            ok += 1
        else:
            fail += 1
            print(f"   FALLA {rut}_{yyyymm}: {' | '.join(motivos) or 'sin motivo'}",
                  flush=True)
        if i % 10 == 0 or i == len(rotos):
            el = time.perf_counter() - t0
            print(f"  [{i}/{len(rotos)}] {ok} reparados, {fail} fallan ({el/60:.1f} min)",
                  flush=True)

    print(f"\nReparados: {ok}/{len(rotos)}")
    print(f"Fallan   : {fail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
