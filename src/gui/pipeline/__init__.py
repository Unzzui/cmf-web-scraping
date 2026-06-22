"""Capa de orquestación del pipeline unificado CMF.

Este paquete une las tres etapas del flujo en un solo proceso desatendido:

    Descargar (CMF)  ->  Consolidar a Excel (CMF_EXTRACT)  ->  Subir a FinDataChile

Componentes
-----------
settings              Configuración persistida + auto-detección de entorno.
models                Estados y eventos del pipeline.
cmf_extract_bridge    Cliente que ejecuta CMF_EXTRACT en su propio intérprete
                      (subprocess) y traduce su salida JSONL en eventos.
findatachile_uploader Subida automática a la API admin de FinDataChile.
orchestrator          Motor con workers por empresa y pipelining por etapa.
"""

from .models import Stage, StageStatus, CompanyState, PipelineEvent  # noqa: F401
from .settings import PipelineSettings  # noqa: F401

__all__ = [
    "Stage",
    "StageStatus",
    "CompanyState",
    "PipelineEvent",
    "PipelineSettings",
]
