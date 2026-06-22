from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Tuple


def _load_json() -> Dict:
    base = Path(__file__).resolve().parent
    path = base / "cuentas.json"
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_mappings() -> Tuple[Dict[str, Dict[str, str]], Dict[str, Dict[str, str]]]:
    """
    Returns:
      (es_to_en, en_to_es) where keys are groups: 'balance', 'estado_resultados', 'flujo_caja'
    """
    data = _load_json()
    groups = {"balance", "estado_resultados", "flujo_caja"}
    es_to_en = {}
    en_to_es = {}
    for g in groups:
        mapping = data.get(g, {})
        es_to_en[g] = mapping
        rev: Dict[str, str] = {}
        for es, en in mapping.items():
            # Allow both original and lower-cased keys when matching
            rev[en] = es
            rev[en.lower()] = es
        en_to_es[g] = rev
    return es_to_en, en_to_es


def guess_is_english(concepts: list[str]) -> bool:
    """Heurística para detectar si la lista de conceptos está en inglés."""
    es_to_en, _ = load_mappings()
    english_vocab = set()
    for gmap in es_to_en.values():
        english_vocab.update(gmap.values())
    english_vocab_lc = {s.lower() for s in english_vocab}
    sample = concepts[: min(50, len(concepts))]
    hits = sum(1 for c in sample if str(c).strip().lower() in english_vocab_lc)
    return hits >= max(3, int(0.1 * max(1, len(sample))))


