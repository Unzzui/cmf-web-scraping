#!/usr/bin/env python3
"""Estados y eventos del pipeline unificado."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Stage(str, Enum):
    """Etapas del flujo end-to-end."""
    DOWNLOAD = "download"
    CONSOLIDATE = "consolidate"
    UPLOAD = "upload"

    @property
    def label(self) -> str:
        return {
            Stage.DOWNLOAD: "Descargar",
            Stage.CONSOLIDATE: "Consolidar",
            Stage.UPLOAD: "Subir",
        }[self]


# Orden canónico de ejecución
STAGE_ORDER: list[Stage] = [Stage.DOWNLOAD, Stage.CONSOLIDATE, Stage.UPLOAD]


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"

    @property
    def badge(self) -> str:
        return {
            StageStatus.PENDING: "Pendiente",
            StageStatus.RUNNING: "En curso",
            StageStatus.DONE: "Listo",
            StageStatus.ERROR: "Error",
            StageStatus.SKIPPED: "Omitido",
        }[self]


@dataclass
class CompanyState:
    """Estado vivo de una empresa a través de todas las etapas."""
    rut: str                       # RUT sin guión (clave)
    rut_completo: str              # RUT-DV
    name: str
    stages: dict[Stage, StageStatus] = field(default_factory=dict)
    progress: float = 0.0          # 0..1 de la etapa en curso
    progress_text: str = ""        # "3/12"
    eta_seconds: Optional[float] = None
    detail: str = ""               # último mensaje legible
    error: str = ""
    disk_periods: int = 0          # períodos XBRL ya descargados en disco
    output_file: Optional[str] = None   # Excel de análisis producido
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    # --- Métricas de la etapa UPLOAD (para el resumen) ---
    upload_blob_ok: Optional[bool] = None      # 3A: blob + catálogo FinDataChile
    upload_datapoints: int = 0                  # 3B: financial_data upserts
    upload_ratios_ok: Optional[bool] = None     # 3B: recálculo de ratios
    upload_dcf_ok: Optional[bool] = None        # 3B: recálculo de DCF

    def __post_init__(self) -> None:
        if not self.stages:
            self.stages = {s: StageStatus.PENDING for s in STAGE_ORDER}

    @property
    def is_terminal(self) -> bool:
        """True si ya no hay nada más que hacer (todo done/skipped o algún error)."""
        vals = list(self.stages.values())
        if any(v == StageStatus.ERROR for v in vals):
            return True
        return all(v in (StageStatus.DONE, StageStatus.SKIPPED) for v in vals)

    @property
    def has_error(self) -> bool:
        return any(v == StageStatus.ERROR for v in self.stages.values()) or bool(self.error)

    @property
    def elapsed(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at if self.finished_at is not None else time.time()
        return max(0.0, end - self.started_at)


@dataclass
class PipelineEvent:
    """Mensaje emitido por el orquestador hacia la UI (vía cola thread-safe)."""
    kind: str                      # "stage" | "progress" | "log" | "started" | "finished" | "company_done"
    rut: Optional[str] = None
    stage: Optional[Stage] = None
    status: Optional[StageStatus] = None
    message: str = ""
    level: str = "INFO"            # INFO|SUCCESS|WARNING|ERROR
    current: int = 0
    total: int = 0
    eta_seconds: Optional[float] = None
    payload: dict[str, Any] = field(default_factory=dict)
