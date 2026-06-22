"""Rich theme, console singleton, and shared banner/section helpers.

All UI output in CMF Extract flows through the ``console`` singleton
exported from this module.  Importing from elsewhere in the package
guarantees a consistent style and avoids multiple Console instances
fighting over stderr/stdout.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.style import Style
from rich.text import Text
from rich.theme import Theme


# ---------------------------------------------------------------------------
# Theme definition
# ---------------------------------------------------------------------------

cmf_theme = Theme(
    {
        # Brand / identity
        "brand": Style(color="steel_blue1", bold=True),
        "accent": Style(color="dodger_blue2", bold=True),
        # Structural chrome
        "header": Style(color="grey100", bold=True),
        "section": Style(color="dodger_blue2", bold=True),
        "muted": Style(color="grey62"),
        # Semantic states
        "success": Style(color="green3", bold=True),
        "warning": Style(color="dark_orange", bold=True),
        "error": Style(color="red3", bold=True),
        "info": Style(color="sky_blue2"),
        # Table chrome
        "table.header": Style(color="steel_blue1", bold=True),
        "table.row.odd": Style(color="grey93"),
        "table.row.even": Style(color="grey74"),
    }
)

# ---------------------------------------------------------------------------
# Module-level console singleton
# ---------------------------------------------------------------------------

console = Console(theme=cmf_theme, highlight=False, stderr=True)


# ---------------------------------------------------------------------------
# Banner and section helpers
# ---------------------------------------------------------------------------

_BANNER_LINES: list[str] = [
    "CMF Extract  v3.0",
    "Plataforma de datos financieros chilenos",
    "Comision para el Mercado Financiero",
]


def print_header() -> None:
    """Print the main CLI banner as a Rich Panel.

    Example output::

        +----------------------------------------------------------+
        |           CMF Extract  v3.0                              |
        |   Plataforma de datos financieros chilenos               |
        |   Comision para el Mercado Financiero                    |
        +----------------------------------------------------------+
    """
    title = Text()
    title.append("CMF Extract", style="brand")
    title.append("  v3.0", style="muted")

    subtitle = Text()
    subtitle.append("Plataforma de datos financieros chilenos\n", style="info")
    subtitle.append("Comision para el Mercado Financiero", style="muted")

    console.print(
        Panel(
            subtitle,
            title=title,
            border_style="accent",
            padding=(1, 4),
            expand=True,
        )
    )
    console.print()


def print_section(title: str) -> None:
    """Print a visual section separator with *title*.

    Args:
        title: The section label displayed on the rule.

    Example::

        print_section("Procesamiento")
        # ─────────────── Procesamiento ───────────────
    """
    console.print()
    console.print(Rule(f"[section]{title}[/section]", style="section"))
    console.print()
