#!/usr/bin/env python3
"""Configuración persistida y auto-detección de entorno para el pipeline unificado.

No asumimos rutas: el usuario corre los proyectos con pyenv / intérpretes
distintos y Arelle puede estar en cualquier lado. Por eso todo es configurable,
con valores por defecto auto-detectados y una verificación explícita.
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


def _scraping_repo_root() -> Path:
    """Raíz del repo cmf-web-scraping (sube desde src/gui/pipeline/)."""
    return Path(__file__).resolve().parents[3]


def _detect_cmf_extract_repo(scraping_root: Path) -> Path:
    """Ubicar CMF_EXTRACT. Prioriza la copia VENDORIZADA dentro de este repo
    (cmf_extract/) para no depender de repos externos ni rutas absolutas."""
    candidates = [
        scraping_root / "cmf_extract",          # vendorizado in-repo (preferido)
        scraping_root.parent / "CMF_EXTRACT",
        Path.home() / "Proyectos" / "CMF_EXTRACT",
        Path.home() / "Documents" / "coding" / "CMF_EXTRACT",
        Path.home() / "CMF_EXTRACT",
    ]
    for c in candidates:
        if (c / "cmf" / "pipeline").is_dir():
            return c
    return candidates[0]


def _python_candidates(repo: Path) -> list[str]:
    """Intérpretes candidatos para ejecutar CMF_EXTRACT, en orden de prioridad.

    IMPORTANTE: nunca el venv de esta GUI (cmf-web-scraping/.venv): ese no tiene
    las dependencias de CMF_EXTRACT (Arelle, etc.). CMF_EXTRACT corre con el
    Python del sistema (pyenv 'system' -> /usr/bin/python) en este equipo.
    """
    scraping_venv = os.path.abspath(_scraping_repo_root() / ".venv")
    cands: list[str] = []

    def add(p: str | None) -> None:
        if not p:
            return
        # NO resolver symlinks: el python de un venv es un symlink al intérprete
        # base; resolverlo rompería el aislamiento (usaría el site-packages base
        # en vez del del venv). Usamos ruta absoluta sin dereferenciar.
        rp = os.path.abspath(p)
        # Excluir cualquier intérprete dentro del venv de la GUI
        if rp.startswith(scraping_venv):
            return
        if rp not in cands:
            cands.append(rp)

    # 1. venv propio del repo CMF_EXTRACT, si existe
    for venv in (repo / ".venv" / "bin" / "python", repo / "venv" / "bin" / "python"):
        if venv.exists():
            add(str(venv))
    # 2. Python del sistema (lo que usa pyenv 'system')
    for p in ("/usr/bin/python3", "/usr/bin/python"):
        if Path(p).exists():
            add(p)
    # 3. shims de pyenv
    add(str(Path.home() / ".pyenv" / "shims" / "python3"))
    # 4. PATH (último recurso; ya excluimos el venv de la GUI)
    add(shutil.which("python3"))
    add(shutil.which("python"))
    return cands or ["python3"]


def _detect_python_interpreter(repo: Path) -> str:
    """Mejor candidato barato (sin lanzar subprocesos)."""
    return _python_candidates(repo)[0]


def probe_cmf_extract_python(repo: Path) -> tuple[str, str]:
    """Probar candidatos ejecutándolos y devolver el primero que importe
    ``cmf.pipeline``. Devuelve (intérprete, detalle). Más lento (subprocess)."""
    import subprocess
    repo = Path(repo)
    if not (repo / "cmf" / "pipeline").is_dir():
        return "", f"No es un repo CMF_EXTRACT válido: {repo}"
    last = ""
    for cand in _python_candidates(repo):
        try:
            res = subprocess.run(
                [cand, "-c", "import cmf.pipeline; print('ok')"],
                cwd=str(repo), capture_output=True, text=True, timeout=40,
                env={**os.environ, "PYTHONPATH": str(repo)},
            )
            if res.returncode == 0 and "ok" in res.stdout:
                return cand, f"OK ({cand})"
            last = (res.stderr.strip().splitlines() or ["fallo"])[-1]
        except Exception as e:  # pragma: no cover
            last = str(e)
    return "", f"Ningún intérprete pudo importar cmf.pipeline. Último error: {last}"


def _detect_arelle_dir(scraping_root: Path) -> str:
    """Ubicar Arelle. Prioriza la copia in-repo (tools/Arelle) para portabilidad."""
    env = os.getenv("CMF_ARELLE_DIR")
    if env:
        return env
    for c in (
        scraping_root / "tools" / "Arelle",     # in-repo (preferido)
        Path.home() / "Documents" / "Arelle",
        Path.home() / "Arelle",
        Path.home() / "arelle",
    ):
        if (c / "arelleCmdLine.py").exists():
            return str(c)
    return str(scraping_root / "tools" / "Arelle")


@dataclass
class PipelineSettings:
    """Ajustes del pipeline. Se serializa a JSON."""

    # --- Rutas de los repos / entorno ---
    scraping_repo: str = ""
    cmf_extract_repo: str = ""
    cmf_extract_python: str = ""
    arelle_dir: str = ""

    # --- Carpetas de datos ---
    # Carpeta de XBRL que produce la descarga y que consume CMF_EXTRACT.
    # Apuntamos CMF_EXTRACT directo aquí para no duplicar GB de XBRL.
    xbrl_base_dir: str = ""
    products_dir: str = ""        # Excel intermedios de CMF_EXTRACT
    product_v1_dir: str = ""      # Excel de análisis final (lo que se sube)
    companies_csv: str = ""

    # --- FinDataChile ---
    # Desactivado por ahora: la publicación a FinDataChile se hará aparte
    # (ese producto se ajustará para el usuario real). El uploader queda
    # implementado y listo para activarse cuando corresponda.
    fdc_enabled: bool = False
    fdc_base_url: str = "http://localhost:3000"
    fdc_username: str = ""
    fdc_password: str = ""

    # --- Rendimiento / concurrencia ---
    download_workers: int = 3       # navegadores selenium en paralelo
    consolidate_workers: int = 0    # subprocess Arelle en paralelo (0 = auto)
    upload_workers: int = 2
    arelle_workers: int = 0         # CMF_WORKERS interno (0 = auto = nº CPUs)
    langs: list[str] = field(default_factory=lambda: ["es"])

    # --- Comportamiento ---
    skip_existing: bool = True      # no re-descargar ni re-consolidar lo ya hecho
    debug: bool = False

    # ------------------------------------------------------------------ #
    @classmethod
    def _config_path(cls) -> Path:
        return _scraping_repo_root() / "config" / "pipeline_settings.json"

    @classmethod
    def with_defaults(cls) -> "PipelineSettings":
        """Construir settings con auto-detección de todo lo que falte."""
        scraping = _scraping_repo_root()
        cmf = _detect_cmf_extract_repo(scraping)
        cpu = os.cpu_count() or 4
        return cls(
            scraping_repo=str(scraping),
            cmf_extract_repo=str(cmf),
            cmf_extract_python=_detect_python_interpreter(cmf),
            arelle_dir=_detect_arelle_dir(scraping),
            xbrl_base_dir=str(scraping / "data" / "XBRL" / "Total"),
            products_dir=str(cmf / "Products"),
            product_v1_dir=str(cmf / "Product_v1" / "Total"),
            companies_csv=str(scraping / "data" / "RUT_Chilean_Companies" / "RUT_Chilean_Companies.csv"),
            consolidate_workers=max(1, cpu // 2),
            arelle_workers=cpu,
        )

    @classmethod
    def load(cls) -> "PipelineSettings":
        """Cargar de disco fusionando con los defaults (rellena claves nuevas)."""
        defaults = cls.with_defaults()
        path = cls._config_path()
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                merged = {**asdict(defaults), **{k: v for k, v in data.items() if v not in (None, "")}}
                # Mantener flags booleanos aunque sean False explícito
                for k in ("fdc_enabled", "skip_existing", "debug"):
                    if k in data:
                        merged[k] = data[k]
                # Portabilidad: si una ruta persistida NO existe (p. ej. settings
                # traídos de otro PC con rutas absolutas distintas), caer al
                # default in-repo, que sí es válido en esta máquina.
                merged = cls._heal_paths(merged, asdict(defaults))
                return cls(**{k: merged[k] for k in asdict(defaults)})
            except Exception:
                # Config corrupta: caer a defaults sin romper la app
                return defaults
        return defaults

    # Rutas que deben existir; si no, se sanan al default in-repo.
    _HEAL_FILE = {"cmf_extract_python", "companies_csv"}
    _HEAL_DIR_REQUIRED = {"cmf_extract_repo"}  # debe contener cmf/pipeline

    @staticmethod
    def _heal_paths(merged: dict, defaults: dict) -> dict:
        def ok_repo(p: str) -> bool:
            return bool(p) and (Path(p) / "cmf" / "pipeline").is_dir()

        def ok_arelle(p: str) -> bool:
            return bool(p) and (Path(p) / "arelleCmdLine.py").exists()

        def ok_path(p: str) -> bool:
            return bool(p) and Path(p).exists()

        if not ok_repo(merged.get("cmf_extract_repo", "")):
            merged["cmf_extract_repo"] = defaults["cmf_extract_repo"]
        if not ok_arelle(merged.get("arelle_dir", "")):
            merged["arelle_dir"] = defaults["arelle_dir"]
        for k in ("cmf_extract_python", "companies_csv"):
            if not ok_path(merged.get(k, "")):
                merged[k] = defaults[k]
        # Carpetas de salida: si la persistida no está bajo el repo actual,
        # preferir el default in-repo (evita escribir en rutas de otro PC).
        scraping = str(_scraping_repo_root())
        for k in ("xbrl_base_dir", "products_dir", "product_v1_dir"):
            val = merged.get(k, "")
            if not val or not str(Path(val)).startswith(scraping):
                # Mantener sólo si ya existe y es válida; si no, usar default.
                if not ok_path(val):
                    merged[k] = defaults[k]
        return merged

    def save(self) -> Path:
        path = self._config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    # ------------------------------------------------------------------ #
    def effective_arelle_workers(self) -> int:
        return self.arelle_workers if self.arelle_workers > 0 else (os.cpu_count() or 4)

    def effective_consolidate_workers(self) -> int:
        return self.consolidate_workers if self.consolidate_workers > 0 else max(1, (os.cpu_count() or 4) // 2)

    def runner_path(self) -> Path:
        """Ruta al script runner que ejecuta CMF_EXTRACT vía subprocess."""
        return Path(__file__).resolve().parent / "cmf_extract_runner.py"

    # ------------------------------------------------------------------ #
    def verify(self) -> list[dict[str, Any]]:
        """Chequeos de entorno. Devuelve lista de {name, ok, detail}.

        No lanza excepciones: cada item reporta su estado para mostrarlo en la UI.
        """
        checks: list[dict[str, Any]] = []

        def add(name: str, ok: bool, detail: str) -> None:
            checks.append({"name": name, "ok": ok, "detail": detail})

        # 1. Repo CMF_EXTRACT
        cmf = Path(self.cmf_extract_repo)
        add("Repo CMF_EXTRACT", (cmf / "cmf" / "pipeline").is_dir(),
            str(cmf) if cmf.exists() else f"No existe: {cmf}")

        # 2. Intérprete + import de cmf.pipeline
        py = self.cmf_extract_python
        ok_py = bool(py) and (Path(py).exists() or shutil.which(py) is not None)
        add("Intérprete Python CMF_EXTRACT", ok_py, py or "(no definido)")
        if ok_py and cmf.is_dir():
            import subprocess
            try:
                res = subprocess.run(
                    [py, "-c", "import cmf.pipeline; print('ok')"],
                    cwd=str(cmf), capture_output=True, text=True, timeout=30,
                    env={**os.environ, "PYTHONPATH": str(cmf)},
                )
                ok = res.returncode == 0 and "ok" in res.stdout
                add("Import cmf.pipeline", ok,
                    "OK" if ok else (res.stderr.strip().splitlines()[-1] if res.stderr.strip() else "fallo"))
            except Exception as e:  # pragma: no cover
                add("Import cmf.pipeline", False, str(e))

        # 3. Arelle
        ar = Path(self.arelle_dir)
        has_arelle = ar.is_dir() and (
            (ar / "arelleCmdLine.py").exists() or (ar / "arelle").is_dir()
        )
        add("Directorio Arelle", has_arelle,
            str(ar) if has_arelle else f"No encontrado (consolidación fallará): {ar}")

        # 4. Carpeta XBRL base
        xb = Path(self.xbrl_base_dir)
        add("Carpeta XBRL base", xb.is_dir() or xb.parent.is_dir(),
            str(xb) + ("" if xb.is_dir() else " (se creará al descargar)"))

        # 5. FinDataChile (solo si está habilitado)
        if self.fdc_enabled:
            has_creds = bool(self.fdc_username and self.fdc_password and self.fdc_base_url)
            add("Credenciales FinDataChile", has_creds,
                self.fdc_base_url if has_creds else "Falta usuario/contraseña/URL")
        return checks
