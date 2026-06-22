"""Rich table helpers for company listings and pipeline result summaries."""

from __future__ import annotations

import math

from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cmf.companies import Company
from cmf.pipeline import PipelineResult
from cmf.ui.theme import console


# ---------------------------------------------------------------------------
# Company table
# ---------------------------------------------------------------------------


def show_company_table(
    companies: list[Company],
    page: int = 0,
    page_size: int = 15,
) -> None:
    """Render a paginated Rich table of *companies*.

    Columns displayed:

    * ``#``        – 1-based sequential index across the full list.
    * ``RUT``      – Company tax identifier.
    * ``Nombre``   – Truncated company name.
    * ``XBRL``     – Checkmark when XBRL data exists on disk.
    * ``Periodos XBRL`` – Available reporting periods (Q1/Q2/Q3/Annual).

    Args:
        companies:  The complete list of companies to paginate over.
        page:       Zero-based page index.
        page_size:  How many rows to show per page (default 15).
    """
    if not companies:
        console.print("[muted]Sin empresas para mostrar.[/muted]")
        return

    total_pages = max(1, math.ceil(len(companies) / page_size))
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    end = min(start + page_size, len(companies))
    page_items = companies[start:end]

    table = Table(
        show_header=True,
        header_style="table.header",
        border_style="muted",
        row_styles=["table.row.odd", "table.row.even"],
        expand=True,
    )

    table.add_column("#", style="muted", justify="right", no_wrap=True, width=5)
    table.add_column("RUT", style="accent", no_wrap=True, min_width=13)
    table.add_column("Nombre", min_width=30)
    table.add_column("XBRL", justify="center", no_wrap=True, width=6)
    table.add_column("Periodos XBRL", min_width=20)

    for i, company in enumerate(page_items, start=start + 1):
        has_xbrl = company.xbrl_dir is not None
        xbrl_icon = Text("si", style="success") if has_xbrl else Text("--", style="muted")

        periods_text: str
        if company.periods_available:
            periods_text = "  ".join(company.periods_available.keys())
        elif has_xbrl:
            periods_text = "en disco"
        else:
            periods_text = "-"

        name_display = company.name[:52] + "..." if len(company.name) > 55 else company.name

        table.add_row(
            str(i),
            company.rut,
            name_display,
            xbrl_icon,
            periods_text,
        )

    console.print(table)

    # Pagination footer
    page_info = Text()
    page_info.append(f"Pagina {page + 1} de {total_pages}", style="muted")
    page_info.append(f"  |  Mostrando {start + 1}-{end} de {len(companies)} empresas", style="muted")
    console.print(page_info)
    console.print()


# ---------------------------------------------------------------------------
# Pipeline result summary
# ---------------------------------------------------------------------------


def show_results_summary(result: PipelineResult, phase_name: str) -> None:
    """Render a summary panel for a completed pipeline phase.

    Shows success count, error count, and elapsed time.  When errors are
    present, they are expanded into a secondary table beneath the panel.

    Args:
        result:     The :class:`~cmf.pipeline.PipelineResult` to display.
        phase_name: Human-readable phase label (e.g. ``"Consolidacion XBRL"``).
    """
    status_style = "success" if result.ok else "warning"
    status_label = "COMPLETADO" if result.ok else "COMPLETADO CON ERRORES"

    # Build summary content
    summary = Text()
    summary.append(f"Estado:    ", style="muted")
    summary.append(f"{status_label}\n", style=status_style)

    summary.append("Exitosos:  ", style="muted")
    summary.append(f"{len(result.success)}", style="success")
    summary.append(" empresa(s)\n")

    summary.append("Errores:   ", style="muted")
    error_style = "error" if result.errors else "muted"
    summary.append(f"{len(result.errors)}", style=error_style)
    summary.append(" empresa(s)\n")

    summary.append("Duracion:  ", style="muted")
    summary.append(_format_elapsed(result.elapsed), style="info")

    panel_title = Text()
    panel_title.append(phase_name, style="header")

    console.print(
        Panel(
            summary,
            title=panel_title,
            border_style=status_style,
            padding=(1, 2),
        )
    )

    # Error detail table
    if result.errors:
        console.print()
        _show_error_table(result.errors)


def _show_error_table(errors: dict[str, str]) -> None:
    """Render a compact table of failed items with their error messages.

    Args:
        errors: Mapping of company/item name to error description.
    """
    table = Table(
        title="Detalle de errores",
        title_style="error",
        show_header=True,
        header_style="table.header",
        border_style="error",
        expand=True,
    )
    table.add_column("Empresa / Item", style="accent", min_width=30)
    table.add_column("Error", style="error", min_width=40)

    for item, msg in errors.items():
        # Truncate very long error messages for readability
        short_msg = msg[:120] + "..." if len(msg) > 123 else msg
        table.add_row(item, short_msg)

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _format_elapsed(seconds: float) -> str:
    """Human-readable duration from *seconds*.

    Examples::

        _format_elapsed(45.3)    -> "45.3s"
        _format_elapsed(90.0)    -> "1m 30s"
        _format_elapsed(3720.0)  -> "1h 2m"
    """
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m"
