"""
Shared utility functions for the processor package.
=====================================================

Most utility functions in BulkProcessor are deeply embedded closures that
rely on local variables (formula_builder, label_norm, etc.), so they remain
inside their respective methods.  This module contains standalone helpers
that can be reused across mixin files.
"""

import re


def quarter_from_month(m: int) -> str | None:
    """Map month number to quarter label (Q1..Q4) or None."""
    try:
        mi = int(m)
    except Exception:
        return None
    return {3: 'Q1', 6: 'Q2', 9: 'Q3', 12: 'Q4'}.get(mi)


def normalize_label(raw: str) -> str | None:
    """Normalize a raw header string to a period label (YYYY or YYYYQn).

    Accepts formats like 'YYYY', 'YYYY-MM', 'YYYY-MM-DD', 'YYYYQn'.
    Returns None if the string cannot be parsed.
    """
    s = str(raw).strip().split("\n", 1)[0]
    # YYYYQn
    if re.match(r"^\d{4}Q[1-4]$", s):
        return s
    # YYYY-MM or YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})", s)
    if m:
        y = m.group(1)
        q = quarter_from_month(m.group(2))
        return f"{y}{q}" if q else y
    # YYYY
    if re.match(r"^\d{4}$", s):
        return s
    return None
