#!/usr/bin/env python3
"""Análisis Razonado (PDF por período) -> Supabase Storage + tabla analisis_razonado.

El PDF cuelga del MISMO formulario del que ya se baja el XBRL
(``entidad.php?pestania=3``, POST con aa/mm/tipo), así que no hay que descubrir
nada nuevo: es otro ``<a>`` de la misma respuesta.

Importante: el enlace de la CMF lleva un token ``auth=`` EFÍMERO — cambia en cada
carga de la página. Guardar esa URL en la BD no sirve: se pudre. Por eso el PDF se
descarga y se re-hospeda en Supabase Storage, y en la BD queda la URL propia.

Casos que la CMF presenta y que aquí NO son errores:
  * el período no existe (empresa nueva, o trimestre aún no publicado)
  * el período existe pero el emisor no acompañó análisis razonado
  * la empresa reporta Individual en vez de Consolidado (se prueban ambos)

Uso:
    python scripts/scrape_analisis_razonado.py --quarters 8 --limit 3 --dry-run
    python scripts/scrape_analisis_razonado.py --quarters 8
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.gui.pipeline.supabase_uploader import (  # noqa: E402
    load_env_file,
    resolve_pg_conn,
)

ENTIDAD_URL = "https://www.cmfchile.cl/institucional/mercados/entidad.php"
USER_AGENT = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
LINK_TEXT = "análisis razonado"


@dataclass
class Pdf:
    rut: str
    year: int
    quarter: int
    content: bytes

    @property
    def key(self) -> str:
        """Ruta dentro del bucket."""
        rut_num = self.rut.split("-")[0]
        return f"{rut_num}/analisis_razonado_{rut_num}_{self.year}Q{self.quarter}.pdf"


def eeff_url(rut_numero: str) -> str:
    return (f"{ENTIDAD_URL}?mercado=V&rut={rut_numero}&grupo=&tipoentidad=RVEMI"
            f"&row=&vig=VI&control=svs&pestania=3")


def ruts_with_xbrl(xbrl_base_dir: Path) -> set[str]:
    """Parte numérica del RUT de las empresas con XBRL descargado.

    Sólo esas llegan a ser producto: bajar los PDF de las ~520 del registro CMF
    sería almacenamiento y carga sobre la CMF que nadie va a usar.
    """
    out: set[str] = set()
    if not xbrl_base_dir.is_dir():
        return out
    for d in xbrl_base_dir.iterdir():
        m = re.match(r"^(\d{4,9})-[\dkK]_", d.name)
        if d.is_dir() and m:
            out.add(m.group(1))
    return out


def recent_quarters(n: int, today: date | None = None) -> list[tuple[int, int]]:
    """Los `n` trimestres cerrados más recientes, del más nuevo al más viejo."""
    today = today or date.today()
    # Un trimestre sólo se publica una vez cerrado; se parte del anterior al actual.
    q = (today.month - 1) // 3 + 1
    year = today.year
    out: list[tuple[int, int]] = []
    for _ in range(n):
        q -= 1
        if q == 0:
            q = 4
            year -= 1
        out.append((year, q))
    return out


def find_pdf_link(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.find_all("a"):
        href = a.get("href") or ""
        text = (a.get_text(" ", strip=True) or "").strip().lower()
        if "verarchivo" in href.lower() and LINK_TEXT in text:
            return href
    return None


def fetch_pdf(session: requests.Session, rut: str, year: int,
              quarter: int) -> Pdf | None:
    """Baja el análisis razonado de un período. None si el emisor no lo publicó."""
    rut_num = rut.split("-")[0]
    base = eeff_url(rut_num)
    month = quarter * 3
    # Igual que el downloader de XBRL: primero Consolidado, luego Individual.
    for tipo in ("C", "I"):
        resp = session.post(base, data={
            "forma": "P", "aa": str(year), "mm": f"{month:02d}",
            "tipo": tipo, "tipo_norma": "IFRS",
        }, timeout=60)
        if resp.status_code != 200:
            continue
        href = find_pdf_link(resp.text)
        if not href:
            continue  # ese tipo no tiene análisis razonado para el período
        got = session.get(urljoin(base, href), timeout=90,
                          headers={"Referer": base})
        if got.status_code != 200 or got.content[:5] != b"%PDF-":
            continue  # enlace presente pero la descarga no fue un PDF
        return Pdf(rut=rut, year=year, quarter=quarter, content=got.content)
    return None


# ---------------------------------------------------------------------------
# Supabase Storage (S3)
# ---------------------------------------------------------------------------

def s3_client(env: dict[str, str]):
    import boto3
    from botocore.config import Config

    missing = [k for k in ("SUPABASE_S3_ENDPOINT", "SUPABASE_S3_ACCESS_KEY_ID",
                           "SUPABASE_S3_SECRET_ACCESS_KEY") if not env.get(k)]
    if missing:
        raise SystemExit(f"Faltan en el .env: {', '.join(missing)}")
    return boto3.client(
        "s3",
        endpoint_url=env["SUPABASE_S3_ENDPOINT"],
        region_name=env.get("SUPABASE_S3_REGION", "sa-east-1"),
        aws_access_key_id=env["SUPABASE_S3_ACCESS_KEY_ID"],
        aws_secret_access_key=env["SUPABASE_S3_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )


def ensure_bucket(client, bucket: str) -> None:
    from botocore.exceptions import ClientError
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError:
        client.create_bucket(Bucket=bucket)


def public_url(env: dict[str, str], bucket: str, key: str) -> str:
    """URL pública del objeto (el bucket debe ser público para servirlo en la web)."""
    # https://<ref>.storage.supabase.co/storage/v1/s3  ->  .../storage/v1/object/public
    root = env["SUPABASE_S3_ENDPOINT"].rsplit("/s3", 1)[0]
    return f"{root}/object/public/{bucket}/{key}"


def upload(client, bucket: str, pdf: Pdf) -> None:
    """Sube el PDF y verifica que quedó completo.

    No basta con que put_object no lance: se comprueba el tamaño con head_object.
    (Un put_object_acl contra el shim S3 de Supabase llegó a dejar un objeto en 0
    bytes devolviendo OK, y la URL pública servía un archivo vacío con HTTP 200.)
    """
    client.put_object(Bucket=bucket, Key=pdf.key, Body=pdf.content,
                      ContentType="application/pdf")
    stored = client.head_object(Bucket=bucket, Key=pdf.key)["ContentLength"]
    if stored != len(pdf.content):
        raise RuntimeError(
            f"subida corrupta: {pdf.key} quedó con {stored} bytes "
            f"y el PDF tiene {len(pdf.content)}")


def record(conn, pdf: Pdf, url: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO analisis_razonado
            (rut, company_id, period_year, period_quarter, file_url, file_size)
        VALUES (
            %(rut)s,
            (SELECT id FROM companies
              WHERE rut_numero::text = split_part(%(rut)s, '-', 1) LIMIT 1),
            %(year)s, %(q)s, %(url)s, %(size)s)
        ON CONFLICT (rut, period_year, period_quarter) DO UPDATE
           SET file_url   = EXCLUDED.file_url,
               file_size  = EXCLUDED.file_size,
               company_id = COALESCE(EXCLUDED.company_id,
                                     analisis_razonado.company_id),
               updated_at = NOW()
        """,
        {"rut": pdf.rut, "year": pdf.year, "q": pdf.quarter, "url": url,
         "size": len(pdf.content)},
    )


def existing_keys(conn) -> set[tuple[str, int, int]]:
    cur = conn.cursor()
    cur.execute("SELECT rut, period_year, period_quarter FROM analisis_razonado")
    return {(r, y, q) for r, y, q in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--env-file", default="/home/unzzui/Proyectos/FinDataChile/.env")
    ap.add_argument("--quarters", type=int, default=8,
                    help="Cuántos trimestres cerrados hacia atrás (default: 8 = 2 años)")
    ap.add_argument("--only", default="", help="RUTs separados por coma")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--xbrl-base-dir", default="data/XBRL/Total",
                    help="Sólo empresas con XBRL descargado aquí (las que llegan a "
                         "ser producto). '' = todo el catálogo CMF")
    ap.add_argument("--delay", type=float, default=0.5)
    ap.add_argument("--force", action="store_true",
                    help="Re-descargar aunque el período ya esté en la BD")
    ap.add_argument("--dry-run", action="store_true",
                    help="Descargar y reportar, sin subir ni escribir en la BD")
    args = ap.parse_args()

    import psycopg2

    env = load_env_file(Path(args.env_file))
    bucket = env.get("SUPABASE_STORAGE_BUCKET", "analisis-razonado")
    conn = psycopg2.connect(**resolve_pg_conn(env))

    cur = conn.cursor()
    only = [r.strip().split("-")[0] for r in args.only.split(",") if r.strip()]
    xbrl_dir = Path(args.xbrl_base_dir) if args.xbrl_base_dir else None
    if only:
        wanted = only
    elif xbrl_dir is not None:
        wanted = sorted(ruts_with_xbrl(xbrl_dir))
        if not wanted:
            raise SystemExit(f"No hay empresas con XBRL en {xbrl_dir}")
    else:
        wanted = None

    if wanted is None:
        cur.execute("SELECT rut, razon_social FROM companies ORDER BY razon_social")
    else:
        cur.execute("""SELECT rut, razon_social FROM companies
                        WHERE rut_numero::text = ANY(%s) ORDER BY razon_social""",
                    (wanted,))
    targets = cur.fetchall()
    if args.limit:
        targets = targets[:args.limit]

    quarters = recent_quarters(args.quarters)
    print(f"{len(targets)} empresa(s) x {len(quarters)} trimestres "
          f"({quarters[-1][0]}Q{quarters[-1][1]} .. {quarters[0][0]}Q{quarters[0][1]})\n")

    done = set() if args.force else existing_keys(conn)

    client = None
    if not args.dry_run:
        client = s3_client(env)
        ensure_bucket(client, bucket)

    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    n_ok = n_missing = n_skip = n_err = 0
    total_bytes = 0
    for i, (rut, razon) in enumerate(targets, 1):
        found = []
        for year, quarter in quarters:
            if (rut, year, quarter) in done:
                n_skip += 1
                continue
            try:
                pdf = fetch_pdf(session, rut, year, quarter)
            except Exception as exc:
                n_err += 1
                print(f"      {rut} {year}Q{quarter} ERROR: {str(exc)[:60]}")
                continue
            if pdf is None:
                # Que un período no traiga análisis razonado es normal, no un error.
                n_missing += 1
                continue
            total_bytes += len(pdf.content)
            found.append(f"{year}Q{quarter}")
            if not args.dry_run:
                try:
                    upload(client, bucket, pdf)
                    record(conn, pdf, public_url(env, bucket, pdf.key))
                    conn.commit()
                except Exception as exc:
                    conn.rollback()
                    n_err += 1
                    print(f"      {rut} {year}Q{quarter} fallo al subir: "
                          f"{str(exc)[:70]}")
                    continue
            n_ok += 1
            time.sleep(args.delay)

        estado = ", ".join(found) if found else "sin análisis razonado"
        print(f"  [{i}/{len(targets)}] {razon[:34]:36s} {estado}")

    print(f"\nPDFs: {n_ok} subidos | {n_missing} períodos sin documento | "
          f"{n_skip} ya estaban | {n_err} errores")
    print(f"Volumen: {total_bytes / 1024 / 1024:.1f} MB")
    if args.dry_run:
        print("dry-run -> no se subió nada")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
