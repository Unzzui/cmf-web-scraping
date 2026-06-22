"""Interactive menus for the CMF Extract CLI.

All functions in this module print exclusively through the shared
``console`` singleton and read input via Rich prompt helpers.  They
are intentionally free of side-effects beyond I/O so they can be
composed arbitrarily by the top-level CLI driver.
"""

from __future__ import annotations

from rich.columns import Columns
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from cmf.companies import Company, CompanyRegistry
from cmf.config import CMFConfig
from cmf.ui.tables import show_company_table
from cmf.ui.theme import console, print_section


# ---------------------------------------------------------------------------
# Menu constants
# ---------------------------------------------------------------------------

_MENU_SECTIONS: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "DESCARGA Y SINCRONIZACION",
        [
            ("1", "Descargar XBRL desde CMF"),
            ("2", "Verificar disponibilidad XBRL"),
            ("3", "Sincronizar desde repo scraping"),
            ("4", "Descargar datos bancarios"),
        ],
    ),
    (
        "PROCESAMIENTO",
        [
            ("5", "Pipeline completo (Fases 1-4)"),
            ("6", "Seleccionar fases especificas"),
            ("7", "Procesar empresa individual"),
        ],
    ),
    (
        "HERRAMIENTAS",
        [
            ("8", "Explorar empresas"),
            ("9", "Configuracion"),
        ],
    ),
]

_VALID_MAIN_CHOICES: frozenset[str] = frozenset(
    {str(i) for i in range(1, 10)} | {"q", "Q"}
)


# ---------------------------------------------------------------------------
# Main menu
# ---------------------------------------------------------------------------


def show_main_menu() -> str:
    """Render the main menu and return the validated user selection.

    Loops until the user enters a recognised option.

    Returns:
        A string in ``{"1" .. "9", "q"}``.
    """
    while True:
        _render_main_menu()
        raw = Prompt.ask(
            "[accent]Seleccione una opcion[/accent]",
            console=console,
        ).strip()

        if raw.lower() == "q":
            return "q"

        if raw in _VALID_MAIN_CHOICES:
            return raw

        console.print(
            f"  [error]Opcion invalida:[/error] [muted]{raw!r}[/muted]"
            "  — ingrese un numero del 1 al 9 o [bold]q[/bold] para salir.\n"
        )


def _render_main_menu() -> None:
    """Print the styled main menu to the console."""
    console.print()

    for section_title, items in _MENU_SECTIONS:
        section_text = Text(f"\n  {section_title}\n", style="section")
        console.print(section_text)

        for key, label in items:
            key_text = Text()
            key_text.append(f"    [{key}]", style="accent")
            key_text.append(f"  {label}", style="header")
            console.print(key_text)

    console.print()
    console.print(Text("    [q]  Salir", style="muted"))
    console.print()


# ---------------------------------------------------------------------------
# Company selection
# ---------------------------------------------------------------------------


def select_companies(registry: CompanyRegistry) -> list[Company]:
    """Interactively select one or more companies from *registry*.

    Selection modes:

    * ``t`` / ``todo``   – All companies that have XBRL data on disk.
    * ``b`` / ``buscar`` – Full-text search by name or RUT substring.
    * A comma-separated list of row numbers (ranges accepted, e.g. ``1,3,5-8``).
    * ``n`` followed by page navigation for manual browsing.

    Args:
        registry: The populated :class:`~cmf.companies.CompanyRegistry`.

    Returns:
        A (possibly empty) list of selected :class:`~cmf.companies.Company`
        instances.  Returns an empty list if the user cancels.
    """
    companies = registry.companies_with_xbrl
    if not companies:
        console.print("[warning]No se encontraron empresas con datos XBRL en disco.[/warning]")
        return []

    print_section("Seleccion de Empresas")
    console.print(f"  [info]{len(companies)} empresa(s) con datos XBRL disponibles.[/info]\n")

    _show_selection_help()

    page = 0
    page_size = 15

    while True:
        show_company_table(companies, page=page, page_size=page_size)

        raw = Prompt.ask(
            "[accent]Seleccion[/accent] [muted](t/todo, b/buscar, a/agregar, numeros, n/p, Enter=cancelar)[/muted]",
            default="",
            console=console,
        ).strip()

        if not raw:
            console.print("[muted]Seleccion cancelada.[/muted]")
            return []

        lower = raw.lower()

        # All companies
        if lower in ("t", "todo", "todos"):
            console.print(f"[success]Seleccionadas todas las empresas ({len(companies)}).[/success]")
            return list(companies)

        # Text search (only companies with XBRL)
        if lower.startswith("b") or lower.startswith("buscar"):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            if not query:
                query = Prompt.ask(
                    "[accent]Termino de busqueda[/accent]",
                    console=console,
                ).strip()
            if not query:
                continue
            results = [c for c in registry.search(query) if c.xbrl_dir is not None]
            if not results:
                console.print(f"[warning]Sin resultados para:[/warning] [muted]{query!r}[/muted]\n")
                continue
            console.print(f"\n  [info]{len(results)} resultado(s) para[/info] [accent]{query!r}[/accent]\n")
            show_company_table(results, page=0, page_size=page_size)
            sub = Prompt.ask(
                "[accent]Numeros de empresa[/accent] [muted](1-based sobre esta lista, Enter=cancelar)[/muted]",
                default="",
                console=console,
            ).strip()
            if not sub:
                continue
            selected = _parse_number_selection(sub, results)
            if selected:
                _echo_selection(selected)
                return selected
            continue

        # Add company from full CSV catalog (including those without XBRL)
        if lower.startswith("a") and (lower == "a" or lower.startswith("agregar") or lower.startswith("a ")):
            query = raw.split(None, 1)[1].strip() if " " in raw else ""
            if not query:
                query = Prompt.ask(
                    "[accent]Buscar empresa en catalogo CMF[/accent]",
                    console=console,
                ).strip()
            if not query:
                continue
            results = registry.search(query)
            if not results:
                console.print(f"[warning]Sin resultados en catalogo CMF para:[/warning] [muted]{query!r}[/muted]\n")
                continue
            console.print(f"\n  [info]{len(results)} resultado(s) en catalogo CMF para[/info] [accent]{query!r}[/accent]\n")
            show_company_table(results, page=0, page_size=page_size)
            sub = Prompt.ask(
                "[accent]Numeros de empresa[/accent] [muted](1-based sobre esta lista, Enter=cancelar)[/muted]",
                default="",
                console=console,
            ).strip()
            if not sub:
                continue
            selected = _parse_number_selection(sub, results)
            if selected:
                _echo_selection(selected)
                return selected
            continue

        # Pagination
        if lower in ("n", "next", "siguiente"):
            import math
            total_pages = max(1, math.ceil(len(companies) / page_size))
            page = min(page + 1, total_pages - 1)
            continue

        if lower in ("p", "prev", "anterior"):
            page = max(0, page - 1)
            continue

        # Number selection (e.g. "1,3,5-8")
        selected = _parse_number_selection(raw, companies)
        if selected is not None:
            if not selected:
                console.print("[warning]Ninguna empresa valida en la seleccion.[/warning]\n")
                continue
            _echo_selection(selected)
            return selected

        console.print(
            "[error]Entrada no reconocida.[/error] "
            "[muted]Use t/todo, b/buscar, numeros (ej. 1,3,5-8), n/p para paginar.[/muted]\n"
        )


def _show_selection_help() -> None:
    """Print a compact help hint for the selection prompt."""
    help_table = Table.grid(padding=(0, 2))
    help_table.add_column(style="accent", no_wrap=True)
    help_table.add_column(style="muted")

    help_table.add_row("t / todo", "Seleccionar todas las empresas")
    help_table.add_row("b <texto>", "Buscar por nombre o RUT")
    help_table.add_row("a <texto>", "Agregar empresa del catalogo CMF (sin XBRL)")
    help_table.add_row("1,3,5-8", "Numeros de fila (rangos aceptados)")
    help_table.add_row("n / p", "Siguiente / pagina anterior")
    help_table.add_row("Enter", "Cancelar seleccion")

    console.print(
        Panel(help_table, title="[muted]Ayuda[/muted]", border_style="muted", padding=(0, 2))
    )
    console.print()


def _parse_number_selection(raw: str, companies: list[Company]) -> list[Company] | None:
    """Parse a number/range string against *companies*.

    Returns:
        A list of matched companies, or ``None`` if the input cannot be
        interpreted as a number selection at all (so the caller can
        try other modes).
    """
    tokens = [t.strip() for t in raw.replace(";", ",").split(",")]
    indices: set[int] = set()
    valid = True

    for token in tokens:
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            try:
                lo, hi = int(parts[0]), int(parts[1])
                indices.update(range(lo, hi + 1))
            except ValueError:
                valid = False
                break
        else:
            try:
                indices.add(int(token))
            except ValueError:
                valid = False
                break

    if not valid:
        return None

    result: list[Company] = []
    for idx in sorted(indices):
        real_idx = idx - 1  # 1-based input
        if 0 <= real_idx < len(companies):
            result.append(companies[real_idx])
        else:
            console.print(f"  [warning]Numero fuera de rango ignorado:[/warning] [muted]{idx}[/muted]")

    return result


def _echo_selection(companies: list[Company]) -> None:
    """Print a brief confirmation of which companies were selected."""
    console.print(f"\n[success]Seleccionadas {len(companies)} empresa(s):[/success]")
    for c in companies[:10]:
        console.print(f"  [muted]-[/muted] [accent]{c.rut}[/accent]  {c.short_name}")
    if len(companies) > 10:
        console.print(f"  [muted]... y {len(companies) - 10} mas.[/muted]")
    console.print()


# ---------------------------------------------------------------------------
# Phase selection
# ---------------------------------------------------------------------------

_PHASES: dict[int, str] = {
    1: "Consolidacion XBRL (Arelle → CSV)",
    2: "Generacion Excel primario (CSV → Excel)",
    3: "Analisis financiero + hoja inicio (Excel → Analisis)",
    4: "Exportar a CSV para BD (TO_SQL)",
}


def select_phases() -> list[int]:
    """Let the user pick which pipeline phases to run.

    Returns:
        A sorted list of phase numbers (subset of ``{1, 2, 3, 4}``).
        Returns all phases if the user selects ``t``/``todo``.
        Returns an empty list on cancellation.
    """
    print_section("Seleccion de Fases")

    phase_table = Table.grid(padding=(0, 2))
    phase_table.add_column(style="accent", no_wrap=True, width=4)
    phase_table.add_column(style="header")

    for num, label in _PHASES.items():
        phase_table.add_row(f"[{num}]", label)

    console.print(
        Panel(
            phase_table,
            title="[section]Fases disponibles[/section]",
            border_style="section",
            padding=(1, 2),
        )
    )
    console.print()

    raw = Prompt.ask(
        "[accent]Fases a ejecutar[/accent] "
        "[muted](t/todo, o numeros: 1,3-4, Enter=cancelar)[/muted]",
        default="",
        console=console,
    ).strip()

    if not raw:
        console.print("[muted]Seleccion cancelada.[/muted]")
        return []

    if raw.lower() in ("t", "todo", "todos"):
        console.print("[success]Ejecutando todas las fases (1-4).[/success]\n")
        return list(_PHASES.keys())

    phases_list = list(_PHASES.keys())
    selected_companies = _parse_number_selection(raw, [None] * len(phases_list))  # type: ignore[arg-type]

    # Re-implement for integer parsing without Company objects
    tokens = [t.strip() for t in raw.replace(";", ",").split(",")]
    selected: set[int] = set()

    for token in tokens:
        if not token:
            continue
        if "-" in token:
            parts = token.split("-", 1)
            try:
                lo, hi = int(parts[0]), int(parts[1])
                selected.update(range(lo, hi + 1))
            except ValueError:
                console.print(f"  [warning]Token ignorado:[/warning] [muted]{token!r}[/muted]")
        else:
            try:
                selected.add(int(token))
            except ValueError:
                console.print(f"  [warning]Token ignorado:[/warning] [muted]{token!r}[/muted]")

    valid = sorted(n for n in selected if n in _PHASES)
    invalid = sorted(n for n in selected if n not in _PHASES)

    if invalid:
        console.print(f"  [warning]Fases ignoradas (no existen):[/warning] [muted]{invalid}[/muted]")

    if not valid:
        console.print("[warning]No se seleccionaron fases validas.[/warning]\n")
        return []

    console.print(f"[success]Fases seleccionadas:[/success] [accent]{valid}[/accent]\n")
    return valid


# ---------------------------------------------------------------------------
# Confirm wrapper
# ---------------------------------------------------------------------------


def confirm(message: str, default: bool = False) -> bool:
    """Display a Rich yes/no confirmation prompt.

    Args:
        message: The question to ask the user.
        default: The pre-selected answer when the user presses Enter.

    Returns:
        ``True`` if the user confirmed, ``False`` otherwise.
    """
    return Confirm.ask(message, default=default, console=console)


# ---------------------------------------------------------------------------
# Config display
# ---------------------------------------------------------------------------


def show_config(config: CMFConfig) -> None:
    """Render the current :class:`~cmf.config.CMFConfig` in a Rich table.

    Args:
        config: The active configuration instance.
    """
    print_section("Configuracion actual")

    table = Table(
        show_header=True,
        header_style="table.header",
        border_style="muted",
        expand=True,
    )
    table.add_column("Parametro", style="accent", no_wrap=True, min_width=24)
    table.add_column("Valor", min_width=40)

    def _row(label: str, value: object, style: str = "") -> None:
        val_text = Text(str(value), style=style)
        table.add_row(label, val_text)

    _row("repo_root", config.repo_root)
    _row("arelle_dir", config.arelle_dir)
    _row("xbrl_base_dir", config.xbrl_base_dir)
    _row("products_dir", config.products_dir)
    _row("product_v1_dir", config.product_v1_dir)
    _row("companies_csv", config.companies_csv)
    _row(
        "scraping_repo",
        config.scraping_repo if config.scraping_repo else "(no configurado)",
        style="" if config.scraping_repo else "muted",
    )
    _row("workers", config.workers, style="info")
    _row("langs", ", ".join(config.langs), style="info")
    _row("debug", str(config.debug), style="warning" if config.debug else "")
    _row("combined", str(config.combined), style="info")
    _row("keep_all_dates", str(config.keep_all_dates), style="info")
    _row("combined_ttm_last_n", config.combined_ttm_last_n, style="info")

    console.print(table)
    console.print()
