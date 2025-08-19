#!/usr/bin/env python3
"""
Enriquecedor de empresas chilenas con datos de CMF:
- Lee Excel/CSV generado por rut_chilean_companies.py
- Para cada RUT_Sin_Guión, visita CMF (pestaña Identificación) y extrae datos.
- Guarda un Excel/CSV enriquecido con información de CMF únicamente.
- Para datos de Bolsa de Santiago, usar test_bolsa_ticker.py por separado.
"""

import os
import sys
import time
import logging
import unicodedata
import difflib
from typing import Dict, Optional, Tuple, List
import random

import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException, NoSuchElementException

CMF_ENTITY_URL = ("https://www.cmfchile.cl/institucional/mercados/entidad.php?mercado=V&rut={rut}&grupo=&tipoentidad=RVEMI&row=&vig=VI&control=svs&pestania=1")


def _norm_key(s: str) -> str:
    if s is None:
        return ""
    s = " ".join(s.split())
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
    return s.strip().lower()


class CMFCompanyEnricher:
    def __init__(self, input_path: str = None, output_dir: str = "./data/RUT_Chilean_Companies", sleep_between: float = 1.0, max_rows: Optional[int] = None):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.input_path = input_path or os.path.join(self.output_dir, "RUT_Chilean_Companies.xlsx")
        self.sleep_between = sleep_between
        self.max_rows = max_rows
        self.driver = None
        self._setup_logging()
        self.stats = {
            'processed': 0,
            'cmf_ok': 0,
            'cmf_timeout': 0,
            'cmf_error': 0
        }


    # --- Matching helpers (Reports <-> Razón Social) ---
    def _normalize_match_key(self, s: str) -> str:
        if not s:
            return ""
        s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode('ascii')
        s = s.lower().replace('_', ' ')
        # keep alnum as tokens, replace others by space
        s = ''.join(ch if ch.isalnum() else ' ' for ch in s)
        tokens = [t for t in s.split() if t]
        # Merge consecutive single-letter tokens into acronyms (e.g., "c a p" -> "cap")
        merged: list[str] = []
        i = 0
        while i < len(tokens):
            if len(tokens[i]) == 1:
                acc = []
                while i < len(tokens) and len(tokens[i]) == 1:
                    acc.append(tokens[i])
                    i += 1
                if acc:
                    merged.append(''.join(acc))
            else:
                merged.append(tokens[i])
                i += 1
        tokens = merged
        # common corporate stopwords
        stop = {
            # Mantener SAC/SACI; sí remover SA/SPA/LTDA
            'sa','spa','ltda','cia','companias','compania','sociedad','anonima','anonimo',
            'grupo','holding','industria','industrias','corporacion','corp','company','co','the','de','del','la','el','los','las','y','e'
        }
        # Remove stopwords and legal-form single letters if any remained
        legal_single = {'s','a','d','p','e','i'}
        tokens = [t for t in tokens if (t not in stop) and (len(t) > 1 or t not in legal_single)]
        return ' '.join(tokens)

    def _index_reports(self, reports_dir: str) -> dict:
        mapping: dict[str, dict] = {}
        if not os.path.isdir(reports_dir):
            return mapping
        for fname in os.listdir(reports_dir):
            if not fname.lower().endswith('.xlsx'):
                continue
            base = fname.rsplit('.', 1)[0]
            # Tomar parte del nombre antes de marcadores conocidos
            cut_markers = ['_EEFF', '_Anual', '_Trimestral', '_ACUM', '_ACUMULATIVO']
            idxs = [base.find(m) for m in cut_markers if m in base]
            if idxs:
                cut = min([i for i in idxs if i >= 0])
                name_stem = base[:cut]
            else:
                name_stem = base
            name_part = name_stem.replace('_', ' ')
            name_part = name_part.replace('_', ' ')
            key = self._normalize_match_key(name_part)
            if not key:
                continue
            mapping[key] = {
                'file': os.path.join(reports_dir, fname),
                'name_part': name_part,
            }
        return mapping

    def _setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("cmf_enricher.log")]
        )
        self.logger = logging.getLogger(__name__)

    def _setup_driver(self) -> bool:
        try:
            browser = getattr(self, 'browser', 'chrome').lower()
            if browser == 'firefox':
                fopts = FirefoxOptions()
                fopts.headless = True
                try:
                    fopts.page_load_strategy = 'eager'
                except Exception:
                    pass
                self.driver = webdriver.Firefox(options=fopts)
            else:
                opts = ChromeOptions()
                # Use new headless for better compatibility
                opts.add_argument("--headless=new")
                opts.add_argument("--no-sandbox")
                opts.add_argument("--disable-dev-shm-usage")
                opts.add_argument("--disable-gpu")
                opts.add_argument("--window-size=1920,1080")
                opts.add_argument("--lang=es-CL")
                opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36")
                prefs = {
                    "profile.managed_default_content_settings.images": 2,
                    "profile.default_content_setting_values.cookies": 1
                }
                opts.add_experimental_option("prefs", prefs)
                try:
                    opts.page_load_strategy = 'eager'
                except Exception:
                    pass
                self.driver = webdriver.Chrome(options=opts)
            try:
                # Limitar tiempos de carga de página
                self.driver.set_page_load_timeout(30)
                self.driver.set_script_timeout(30)
            except Exception:
                pass
            self.driver.implicitly_wait(5)
            self.logger.info("WebDriver listo (headless)")
            return True
        except WebDriverException as e:
            self.logger.error(f"Error iniciando WebDriver: {e}")
            return False

    def _load_input(self) -> pd.DataFrame:
        if os.path.isfile(self.input_path):
            self.logger.info(f"Leyendo: {self.input_path}")
            if self.input_path.lower().endswith(".csv"):
                df = pd.read_csv(self.input_path)
            else:
                df = pd.read_excel(self.input_path)
        else:
            # fallback a CSV en el mismo directorio
            csv_candidate = os.path.join(self.output_dir, "RUT_Chilean_Companies.csv")
            if os.path.isfile(csv_candidate):
                self.logger.info(f"Leyendo: {csv_candidate}")
                df = pd.read_csv(csv_candidate)
            else:
                raise FileNotFoundError(f"No se encontró archivo de entrada en {self.input_path} ni {csv_candidate}")

        # Asegurar columnas claves
        if "RUT_Sin_Guión" not in df.columns:
            # crear desde RUT con regex robusta
            rut_num = df['RUT'].astype(str).str.extract(r'^\s*([0-9\.]+)\s*-\s*([0-9Kk])\s*$', expand=True)
            df['RUT_Numero'] = rut_num[0].str.replace(r'\.', '', regex=True)
            df['DV'] = rut_num[1].str.upper()
            df['RUT_Sin_Guión'] = df['RUT_Numero']

        return df

    def _cmf_identificacion(self, rut_sin: str, timeout: int = 12) -> Dict[str, str]:
        """Extrae la tabla Identificación desde la CMF para un RUT."""
        data: Dict[str, str] = {}
        url = CMF_ENTITY_URL.format(rut=rut_sin)
        try:
            self.driver.get(url)
            # Esperar que cargue la sección/tab de Identificación (busca una tabla con th/td)
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, "//table[.//th and .//td]"))
            )
            # Mapear todos los th->td
            ths = self.driver.find_elements(By.XPATH, "//table//th")
            for th in ths:
                try:
                    key_raw = th.text.strip()
                    val_el = th.find_element(By.XPATH, "following-sibling::td[1]")
                    val_raw = val_el.text.strip()
                    key = _norm_key(key_raw)
                    data[key] = val_raw
                except Exception:
                    continue

            # Normalizar a columnas destino
            normalized = {
                'RUT_CMF': data.get('rut', ''),
                'Razon Social CMF': data.get('razon social', ''),
                'Nombre Fantasia': data.get('nombre de fantasia', ''),
                'Vigencia': data.get('vigencia', ''),
                'Telefono': data.get('telefono', ''),
                'Fax': data.get('fax', ''),
                'Domicilio': data.get('domicilio', ''),
                'Region': data.get('region', ''),
                'Ciudad': data.get('ciudad', ''),
                'Comuna': data.get('comuna', ''),
                'Email Contacto': data.get('e-mail de contacto', ''),
                'Sitio Web CMF': data.get('sitio web', ''),
                'Codigo Postal': data.get('codigo postal', ''),
                # Variantes del label para ticker:
                'Ticker': data.get('nombre con que transa en la bolsa 2', '') or data.get('nombre con que transa en la bolsa', '')
            }

            # Valores faltantes -> vacío
            for k, v in normalized.items():
                if v is None or str(v).strip() == "":
                    normalized[k] = ""

            return normalized
        except TimeoutException:
            self.logger.warning(f"Timeout Identificación CMF para RUT {rut_sin}")
            self.stats['cmf_timeout'] += 1
            return {}
        except Exception as e:
            self.logger.error(f"Error Identificación CMF para RUT {rut_sin}: {e}")
            self.stats['cmf_error'] += 1
            return {}

    def enrich(self) -> bool:
        if not self._setup_driver():
            return False

        try:
            df = self._load_input()

            # Recortar si se indicó max_rows (debug)
            if self.max_rows:
                df = df.head(self.max_rows).copy()

            # Filtrar por empresas presentes en data/Reports si así se solicita
            only_reports = getattr(self, 'only_reports', True)
            reports_dir = getattr(self, 'reports_dir', os.path.join('data', 'Reports'))
            fuzzy_threshold = float(getattr(self, 'fuzzy_threshold', 0.80))
            report_index = {}
            if only_reports:
                report_index = self._index_reports(reports_dir)
                if not report_index:
                    self.logger.warning(f"No se hallaron reportes en {reports_dir}; no se filtrará por reports")
                    only_reports = False
            if only_reports:
                kept_rows = []
                matched_info = []
                matched_keys: set[str] = set()
                report_keys = list(report_index.keys())
                total_reports = len(report_keys)
                for i, row in df.iterrows():
                    cand_names = []
                    for col in ['Razón Social', 'Razon Social', 'Razon Social CMF', 'Nombre Fantasia']:
                        if col in df.columns:
                            val = str(row.get(col, '') or '')
                            if val:
                                cand_names.append(val)
                    matched = False
                    best_match = None
                    for nm in cand_names:
                        key = self._normalize_match_key(nm)
                        if key in report_index:
                            matched = True
                            best_match = (nm, key)
                            break
                    if not matched and cand_names:
                        # Fuzzy on normalized
                        for nm in cand_names:
                            key = self._normalize_match_key(nm)
                            if not key:
                                continue
                            close = difflib.get_close_matches(key, report_keys, n=1, cutoff=fuzzy_threshold)
                            if close:
                                matched = True
                                best_match = (nm, close[0])
                                break
                    if not matched and cand_names:
                        # Fallback: similitud Jaccard entre tokens
                        def jac(a: str, b: str) -> float:
                            sa, sb = set(a.split()), set(b.split())
                            inter = len(sa & sb)
                            uni = len(sa | sb) or 1
                            return inter / uni
                        best_score = 0.0
                        best_key = None
                        best_src = None
                        for nm in cand_names:
                            key = self._normalize_match_key(nm)
                            for repk in report_keys:
                                sc = jac(key, repk)
                                if sc > best_score:
                                    best_score, best_key, best_src = sc, repk, nm
                        if best_score >= 0.60 and best_key:
                            matched = True
                            best_match = (best_src or cand_names[0], best_key)
                    if matched:
                        kept_rows.append((i, row))
                        if best_match:
                            src, rep_key = best_match
                            matched_info.append((src, report_index[rep_key]['name_part']))
                            matched_keys.add(rep_key)
                if kept_rows:
                    coverage = f"coverage vs reports ~ {len(matched_keys)}/{total_reports}"
                    self.logger.info(f"Filtrado por Reports: {len(kept_rows)}/{len(df)} filas coinciden con archivos en {reports_dir} ({coverage})")
                    for sample in matched_info[:10]:
                        self.logger.info(f"Match ejemplo: DF='{sample[0]}' <-> Report='{sample[1]}'")
                    # Unmatched report names (muestra hasta 10)
                    if total_reports:
                        remaining = [report_index[k]['name_part'] for k in report_keys if k not in matched_keys]
                        if remaining:
                            self.logger.info(f"Reports sin match (~{len(remaining)}): {', '.join(remaining[:10])}{'…' if len(remaining)>10 else ''}")
                    # rebuild df
                    df = pd.DataFrame([r for _, r in kept_rows])
                else:
                    self.logger.warning("No hubo coincidencias con Reports; no se filtrará")

            # Asegurar columnas destino
            add_cols = [
                'RUT_CMF', 'Razon Social CMF', 'Nombre Fantasia', 'Vigencia',
                'Telefono', 'Fax', 'Domicilio', 'Region', 'Ciudad', 'Comuna',
                'Email Contacto', 'Sitio Web CMF', 'Codigo Postal', 'Ticker',
                'Descripcion Empresa', 'Sitio Empresa'
            ]
            for c in add_cols:
                if c not in df.columns:
                    df[c] = ""

            total = len(df)
            self.logger.info(f"Enriqueciendo {total} empresas...")
            checkpoint_every = getattr(self, 'checkpoint_every', 25)
            start_ts = time.time()
            try:
                for idx, (i, row) in enumerate(df.iterrows(), start=1):
                    rut_sin = str(row.get('RUT_Sin_Guión', '')).strip()
                    razon = str(row.get('Razón Social', '')).strip()
                    if not rut_sin.isdigit() or len(rut_sin) < 7:
                        self.logger.debug(f"[{idx}/{total}] RUT inválido: {rut_sin} - {razon}")
                        continue

                    elapsed = time.time() - start_ts
                    rate = idx / elapsed if elapsed > 0 else 0
                    remaining = total - idx
                    eta_sec = remaining / rate if rate > 0 else 0
                    self.logger.info(f"[{idx}/{total}] Procesando RUT={rut_sin} | Empresa='{razon}' | rate={rate:.2f} it/s | ETA~{eta_sec/60:.1f} min")

                    # CMF con 2 reintentos simples
                    info = {}
                    for attempt in range(1, 3):
                        info = self._cmf_identificacion(rut_sin)
                        if info:
                            self.stats['cmf_ok'] += 1
                            break
                        # backoff
                        time.sleep(0.5 * attempt)

                    for k, v in info.items():
                        # crea la columna si no existe
                        if k not in df.columns:
                            df[k] = ""
                        df.at[i, k] = v

                    self.stats['processed'] += 1

                    # Espera breve configurable para no sobrecargar
                    try:
                        time.sleep(float(getattr(self, 'sleep_between', 1.0)))
                    except Exception:
                        time.sleep(1.0)

                    # Guardado incremental
                    if idx % checkpoint_every == 0:
                        tmp_path = os.path.join(self.output_dir, f"RUT_Chilean_Companies_Enriched_partial_{idx}.csv")
                        try:
                            df.head(idx).to_csv(tmp_path, index=False, encoding="utf-8")
                            self.logger.info(f"Checkpoint guardado: {tmp_path}")
                        except Exception as e:
                            self.logger.warning(f"No se pudo guardar checkpoint {idx}: {e}")
            except KeyboardInterrupt:
                # Guardar un checkpoint al interrumpir
                tmp_path = os.path.join(self.output_dir, f"RUT_Chilean_Companies_Enriched_interrupted_{self.stats['processed']}.csv")
                try:
                    df.head(self.stats['processed']).to_csv(tmp_path, index=False, encoding="utf-8")
                    self.logger.info(f"Interrupción: checkpoint guardado en {tmp_path}")
                except Exception as e:
                    self.logger.warning(f"Interrupción: no se pudo guardar checkpoint: {e}")
                raise

            # Guardar
            out_xlsx = os.path.join(self.output_dir, "RUT_Chilean_Companies_Enriched.xlsx")
            out_csv = os.path.join(self.output_dir, "RUT_Chilean_Companies_Enriched.csv")
            try:
                df.to_excel(out_xlsx, index=False)
                self.logger.info(f"Excel enriquecido: {out_xlsx}")
            except Exception as e:
                self.logger.error(f"Error guardando Excel: {e}")
            try:
                df.to_csv(out_csv, index=False, encoding="utf-8")
                self.logger.info(f"CSV enriquecido: {out_csv}")
            except Exception as e:
                self.logger.error(f"Error guardando CSV: {e}")

            # Resumen
            self.logger.info(f"==== RESUMEN ENRIQUECIMIENTO ====")
            self.logger.info(f"Procesadas: {self.stats['processed']} / {total}")
            self.logger.info(f"CMF -> OK: {self.stats['cmf_ok']}, Timeouts: {self.stats['cmf_timeout']}, Errores: {self.stats['cmf_error']}")

            return True
        except Exception as e:
            self.logger.error(f"Error general enriqueciendo: {e}")
            return False
        finally:
            if self.driver:
                self.driver.quit()
                self.logger.info("WebDriver cerrado")


def main():
    import argparse
    p = argparse.ArgumentParser(description="Enriquecer empresas desde CMF (usar test_bolsa_ticker.py para datos de Bolsa de Santiago)")
    p.add_argument("--input", help="Ruta al Excel/CSV base (default: ./data/RUT_Chilean_Companies/RUT_Chilean_Companies.xlsx)")
    p.add_argument("--outdir", default="./data/RUT_Chilean_Companies", help="Directorio de salida")
    p.add_argument("--sleep", type=float, default=1.0, help="Espera entre solicitudes (seg)")
    p.add_argument("--max-rows", type=int, default=None, help="Procesar sólo N primeras filas (debug)")
    p.add_argument("--checkpoint-every", type=int, default=25, help="Guardar checkpoint cada N filas")
    p.add_argument("--cmf-timeout", type=int, default=12, help="Timeout en segundos para CMF Identificación")
    p.add_argument("--browser", choices=["chrome", "firefox"], default="chrome", help="Navegador a usar para Selenium (default: chrome)")
    p.add_argument("--only-reports", dest="only_reports", action="store_true", default=True, help="Procesar sólo empresas con match en data/Reports (default)")
    p.add_argument("--all", dest="only_reports", action="store_false", help="Procesar todas las empresas (desactiva filtro por Reports)")
    p.add_argument("--reports-dir", default=os.path.join('data','Reports'), help="Directorio de Reports (default: data/Reports)")
    p.add_argument("--fuzzy-threshold", type=float, default=0.80, help="Umbral de similitud para match difuso (0-1, default: 0.80)")
    args = p.parse_args()

    enricher = CMFCompanyEnricher(input_path=args.input, output_dir=args.outdir, sleep_between=args.sleep, max_rows=args.max_rows)
    # allow switching browser (chrome|firefox)
    enricher.browser = args.browser or os.environ.get('BROWSER', 'chrome')
    # Filtrado por Reports
    enricher.only_reports = bool(args.only_reports)
    enricher.reports_dir = args.reports_dir
    enricher.fuzzy_threshold = float(args.fuzzy_threshold)
    # Ajustes desde CLI
    enricher.checkpoint_every = max(5, args.checkpoint_every)
    # Monkey-patch timeout via wrapper
    orig_cmf = enricher._cmf_identificacion
    def cmf_wrap(rut_sin: str, timeout: Optional[int] = None):
        return orig_cmf(rut_sin, timeout=args.cmf_timeout)
    enricher._cmf_identificacion = cmf_wrap  # type: ignore

    ok = enricher.enrich()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
