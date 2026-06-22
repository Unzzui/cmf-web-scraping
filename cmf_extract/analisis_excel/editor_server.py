#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor local para el editor de estructura de EEFF.

Sirve archivos estáticos desde la carpeta analisis_excel/ y expone:
  - GET  /api/estructura  → devuelve el JSON de estructura
  - PUT  /api/estructura  → guarda el JSON recibido (backup automático)

Uso:
  python analisis_excel/editor_server.py --host 127.0.0.1 --port 8000
  Luego abre: http://127.0.0.1:8000/editor_estructura.html
"""
from __future__ import annotations
import argparse
import json
import os
import re
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
from typing import Tuple, List, Dict


ROOT = Path(__file__).parent.resolve()  # analisis_excel/
JSON_PATH = ROOT / "estructura_eeff_empresas.json"
INFO_PATH = ROOT / ".editor_server_info.json"
XBRL_PATH = ROOT.parent / "data" / "XBRL" / "Total"


def atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Backup previo
    if path.exists():
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            path.replace(backup)
        except Exception:
            pass
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def normalize_rut(rut: str) -> str:
    """Normaliza un RUT removiendo puntos y espacios"""
    if not rut:
        return ""
    # Remover puntos y espacios, mantener solo números y guión
    clean_rut = re.sub(r'[.\s]', '', rut.strip())
    return clean_rut.upper()  # Asegurar que 'k' sea mayúscula


def scan_xbrl_companies() -> List[Dict[str, str]]:
    """Escanea el directorio XBRL y extrae información de empresas"""
    companies = []
    
    if not XBRL_PATH.exists():
        return companies
    
    try:
        # Patrón para extraer RUT y nombre de empresa del directorio
        # Formato: RUT_NOMBRE_EMPRESA/
        for company_dir in XBRL_PATH.iterdir():
            if not company_dir.is_dir():
                continue
                
            dir_name = company_dir.name
            
            # Buscar patrón RUT_NOMBRE más flexible
            # Formato: numero-numero_NOMBRE o numero_NOMBRE
            match = re.match(r'^(\d{7,9}-[\dkK])_(.+)$', dir_name)
            if not match:
                # Intentar formato sin guión
                match = re.match(r'^(\d{7,9})_(.+)$', dir_name)
                if match:
                    # Agregar guión si no lo tiene
                    rut_num = match.group(1)
                    if len(rut_num) >= 8:
                        rut = rut_num[:-1] + '-' + rut_num[-1]
                    else:
                        rut = rut_num + '-?'  # RUT inválido, pero seguir
                    nombre_raw = match.group(2)
                else:
                    continue
            else:
                rut = match.group(1)
                nombre_raw = match.group(2)
            
            # Limpiar el nombre de empresa
            # Reemplazar _ con espacios y limpiar sufijos comunes
            nombre = nombre_raw.replace('_', ' ')
            nombre = re.sub(r'\s+(SA|LTDA|SADP)$', r' \1', nombre)  # Normalizar sufijos
            
            # Normalizar RUT (sin puntos para consistencia)
            rut = normalize_rut(rut)
            
            companies.append({
                'rut': rut,
                'nombre': nombre,
                'directorio': str(company_dir.relative_to(XBRL_PATH))
            })
            
    except Exception as e:
        print(f"Error escaneando directorio XBRL: {e}")
    
    # Ordenar por RUT
    companies.sort(key=lambda x: x['rut'])
    return companies


def get_missing_companies() -> List[Dict[str, str]]:
    """Obtiene las empresas que están en XBRL pero no en estructura_eeff_empresas.json"""
    try:
        # Cargar empresas existentes y normalizar RUTs
        existing_ruts = set()
        if JSON_PATH.exists():
            with JSON_PATH.open("r", encoding="utf-8") as f:
                data = json.load(f)
                for empresa in data.get('empresas', []):
                    if empresa.get('empresa', {}).get('rut'):
                        rut = normalize_rut(empresa['empresa']['rut'])
                        existing_ruts.add(rut)
        
        # Obtener todas las empresas XBRL
        all_xbrl = scan_xbrl_companies()
        
        # Filtrar las que faltan comparando RUTs normalizados
        missing = []
        for company in all_xbrl:
            xbrl_rut = normalize_rut(company['rut'])
            if xbrl_rut not in existing_ruts:
                # Guardar el RUT en formato sin puntos para consistencia
                company['rut'] = xbrl_rut
                missing.append(company)
        
        return missing
        
    except Exception as e:
        print(f"Error obteniendo empresas faltantes: {e}")
        return []


class EditorHandler(SimpleHTTPRequestHandler):
    server_version = "EditorEEFF/1.0"

    def log_message(self, fmt: str, *args) -> None:  # menos ruido
        print("[srv]", self.address_string(), "-", fmt % args)

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> Tuple[dict, str]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        text = raw.decode("utf-8") if raw else "{}"
        try:
            data = json.loads(text)
        except Exception as e:
            raise ValueError(f"JSON inválido: {e}")
        return data, text

    def do_GET(self):  # noqa: N802
        # Extraer la ruta sin query parameters
        path_no_query = self.path.split('?')[0].rstrip("/")
        
        if path_no_query == "/api/estructura":
            try:
                if not JSON_PATH.exists():
                    data = {"version": 1, "empresas": []}
                else:
                    with JSON_PATH.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                self._send_json(200, data)
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return
        elif path_no_query == "/api/empresas-xbrl":
            try:
                companies = scan_xbrl_companies()
                self._send_json(200, {"empresas": companies})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return
        elif path_no_query == "/api/empresas-faltantes":
            try:
                missing = get_missing_companies()
                self._send_json(200, {"faltantes": missing, "total": len(missing)})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return
        return super().do_GET()

    def do_PUT(self):  # noqa: N802
        path_no_query = self.path.split('?')[0].rstrip("/")
        if path_no_query == "/api/estructura":
            try:
                data, _ = self._read_json_body()
                if not isinstance(data, dict) or not isinstance(data.get("empresas"), list):
                    self._send_json(400, {"error": "Formato inválido: se espera objeto con 'empresas': []"})
                    return
                atomic_write_json(JSON_PATH, data)
                self._send_json(200, {"ok": True})
            except ValueError as e:
                self._send_json(400, {"error": str(e)})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
            return
        self.send_error(404, "Not Found")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    handler = partial(EditorHandler, directory=str(ROOT))
    # Intentar enlazar desde el puerto solicitado, con fallback incremental
    host = args.host
    port = args.port
    last_err = None
    for _ in range(200):  # intentar hasta +200 puertos
        try:
            httpd = ThreadingHTTPServer((host, port), handler)
            break
        except OSError as e:
            last_err = e
            # EADDRINUSE → probar siguiente puerto
            port += 1
    else:
        # No se pudo enlazar en el rango
        raise last_err or OSError("No se pudo enlazar a ningún puerto")

    # Escribir archivo de info con la URL final para que el lanzador la lea
    try:
        INFO_PATH.write_text(
            json.dumps({
                "host": host,
                "port": port,
                "url": f"http://{host}:{port}/editor_estructura.html",
                "api": f"http://{host}:{port}/api/estructura",
                "root": str(ROOT),
                "json_path": str(JSON_PATH),
            }, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception:
        pass

    print(f"Sirviendo {ROOT} en http://{host}:{port}")
    print("API: GET/PUT /api/estructura →", JSON_PATH)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCerrando servidor…")
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
