#!/usr/bin/env python3
"""Genera el META-INF/catalog.xml de cada paquete de taxonomia CMF.

POR QUE
-------
Arelle resuelve las taxonomias por URL (`http://www.cmfchile.cl/cl/fr/ci/2018-01-02/...`).
Sin un catalogo local las descarga de internet, y la CMF responde 403 y throttea: el
propio `cmf/pipeline/arelle_cache.py` lleva un set de URLs muertas para no reintentarlas.
Cuando una taxonomia no resuelve, Arelle NO falla -- exporta cero hechos y termina con
exit 0. El hueco aparece recien en el Excel.

El `catalog.xml` mapea esa URL a los archivos en disco. Con el, el pipeline es
reproducible y no depende de que cmfchile.cl este arriba.

LOS TRES HOSTS
--------------
Los paquetes que publica la CMF traen un catalogo que declara UN solo prefijo:

    https://www.cmfchile.cl/cl/fr/hb/2026-01-02/

Pero los XBRL reales referencian tres formas: `https://www.cmfchile.cl`,
`http://www.cmfchile.cl` y -- en los ejercicios viejos -- `http://www.svs.cl`, el
organismo que precedio a la CMF. El match de `rewriteURI` es por prefijo exacto, asi que
el catalogo oficial no resuelve nada anterior a ~2018. Aqui se declaran los tres.

LAYOUTS
-------
Los paquetes recientes traen los archivos bajo `archivos/`; los viejos, en la raiz. El
`rewritePrefix` se ajusta a lo que haya en disco.

Uso:
    python scripts/build_taxonomy_catalogs.py            # escribe los catalogos
    python scripts/build_taxonomy_catalogs.py --dry-run  # solo muestra que haria
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RAIZ = REPO / "docs" / "taxonomias_cmf"

# El shell es el unico .xsd que TODOS los paquetes nombran igual, en todas las familias
# y todos los anios: "cl-ci_shell_2018-01-02.xsd". El .xsd "raiz" no sirve como marcador
# porque cambia de nombre segun la familia (`cl-ci_cor_...` vs `cl-hb_...` vs
# `cl-hb-2014-03-15.xsd`, con guion, en 2014).
_SHELL_XSD = re.compile(r"^cl-([a-z]{2})_shell_(\d{4}-\d{2}-\d{2})\.xsd$")

# Los hosts que los XBRL usan para referirse a la MISMA taxonomia.
_HOSTS = (
    "https://www.cmfchile.cl",
    "http://www.cmfchile.cl",
    "https://www.svs.cl",
    "http://www.svs.cl",
)

_CATALOG = """<?xml version="1.0" encoding="UTF-8"?>
<!-- Generado por scripts/build_taxonomy_catalogs.py -- no editar a mano. -->
<catalog xmlns="urn:oasis:names:tc:entity:xmlns:xml:catalog">
{entradas}
</catalog>
"""

_ENTRADA = ('   <rewriteURI uriStartString="{uri}"\n'
            '               rewritePrefix="{prefix}"/>')

_PACKAGE = """<?xml version="1.0" encoding="UTF-8"?>
<tp:taxonomyPackage xmlns:tp="http://xbrl.org/2016/taxonomy-package"
                    xml:lang="es">
  <tp:identifier>http://www.cmfchile.cl/cl/fr/{familia}/{version}/</tp:identifier>
  <tp:name>CMF CL-{FAMILIA} {version}</tp:name>
  <tp:description>Taxonomia CMF {FAMILIA} version {version}</tp:description>
  <tp:version>{version}</tp:version>
  <tp:publisher>Comision para el Mercado Financiero</tp:publisher>
</tp:taxonomyPackage>
"""


def identificar(pkg: Path) -> tuple[str, str, str] | None:
    """(familia, version, rewritePrefix) del paquete, o None si no se reconoce.

    La familia y la version salen del shell del paquete (`cl-ci_shell_2018-01-02.xsd`).
    El prefijo depende de donde esten realmente los archivos: los paquetes recientes los
    traen bajo `archivos/`, los viejos en la raiz.
    """
    for base, prefix in ((pkg / "archivos", "../archivos/"), (pkg, "../")):
        if not base.is_dir():
            continue
        for xsd in base.glob("cl-*_shell_*.xsd"):
            m = _SHELL_XSD.match(xsd.name)
            if m:
                return m.group(1), m.group(2), prefix
    return None


def escribir(pkg: Path, familia: str, version: str, prefix: str, dry: bool) -> None:
    entradas = "\n".join(
        _ENTRADA.format(uri=f"{host}/cl/fr/{familia}/{version}/", prefix=prefix)
        for host in _HOSTS
    )
    catalog = _CATALOG.format(entradas=entradas)
    package = _PACKAGE.format(familia=familia, FAMILIA=familia.upper(), version=version)

    meta = pkg / "META-INF"
    if dry:
        print(f"    [dry-run] escribiria {meta}/catalog.xml y taxonomyPackage.xml")
        return
    meta.mkdir(exist_ok=True)
    (meta / "catalog.xml").write_text(catalog, encoding="utf-8")
    (meta / "taxonomyPackage.xml").write_text(package, encoding="utf-8")


def limpiar_zone_identifier(dry: bool) -> int:
    """Los `:Zone.Identifier` que Windows deja al copiar. Basura pura."""
    basura = [p for p in RAIZ.rglob("*Zone.Identifier") if p.is_file()]
    if not dry:
        for p in basura:
            p.unlink()
    return len(basura)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true",
                    help="mostrar que haria, sin escribir nada")
    args = ap.parse_args()

    if not RAIZ.is_dir():
        print(f"[error] no existe {RAIZ}", file=sys.stderr)
        return 1

    n = limpiar_zone_identifier(args.dry_run)
    if n:
        verbo = "se borrarian" if args.dry_run else "borrados"
        print(f"[taxonomias] {verbo} {n} archivos Zone.Identifier")

    paquetes = sorted(p for p in RAIZ.glob("*/*") if p.is_dir())
    ok = desconocidos = 0

    for pkg in paquetes:
        ident = identificar(pkg)
        if ident is None:
            print(f"  [?] {pkg.relative_to(RAIZ)}: no encuentro el .xsd raiz "
                  f"(cl-<fam>_<version>.xsd); se omite")
            desconocidos += 1
            continue
        familia, version, prefix = ident
        print(f"  [ok] {str(pkg.relative_to(RAIZ)):28} cl-{familia} {version}  -> {prefix}")
        escribir(pkg, familia, version, prefix, args.dry_run)
        ok += 1

    print(f"\n[taxonomias] {ok} paquete(s) con catalogo, {desconocidos} sin identificar")
    return 0 if desconocidos == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
