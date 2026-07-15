"""Parser de números en formato español (punto de miles, coma decimal)."""


def parse_spanish_number(raw: str | None) -> float | None:
    """Convierte un número con formato español a float.

    '59878091792,00' -> 59878091792.0
    '40.844,79'      -> 40844.79
    ''/None/'N/A'    -> None
    """
    if raw is None:
        return None
    s = raw.strip()
    if s == "":
        return None
    s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None
