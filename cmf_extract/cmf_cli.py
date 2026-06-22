#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CMF Extract - Unified CLI v3.0
Entry point for the Chilean financial data processing platform.

Usage:
    python cmf_cli.py                   # Interactive mode
    python cmf_cli.py --all             # Process all companies (phases 1-4)
    python cmf_cli.py --all --phases 2  # Specific phase on all companies
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import os
import sys
import warnings
from pathlib import Path

# Ensure repo root is in path for legacy imports
_REPO_ROOT = Path(__file__).resolve().parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from cmf.config import CMFConfig
from cmf.companies import CompanyRegistry, Company
from cmf.pipeline import PipelineResult
from cmf.pipeline import sync as pipeline_sync
from cmf.pipeline import consolidation as pipeline_consolidation
from cmf.pipeline import excel_gen as pipeline_excel_gen
from cmf.pipeline import analysis as pipeline_analysis
from cmf.pipeline import to_sql as pipeline_to_sql
from cmf.pipeline import download as pipeline_download
from cmf.ui.theme import console, print_header, print_section
from cmf.ui.tables import show_company_table, show_results_summary
from cmf.ui.progress import run_with_progress
from cmf.ui.menus import (
    show_main_menu,
    select_companies,
    select_phases,
    confirm,
    show_config,
)


# ──────────────────────────────────────────────────────────────────────────
# Pipeline runner
# ──────────────────────────────────────────────────────────────────────────

_PHASE_NAMES = {
    1: "Fase 1 - Consolidacion XBRL",
    2: "Fase 2 - Generacion Excel",
    3: "Fase 3 - Analisis Financiero",
    4: "Fase 4 - Exportar a CSV (TO_SQL)",
}

_PHASE_RUNNERS = {
    1: pipeline_consolidation,
    2: pipeline_excel_gen,
    3: pipeline_analysis,
    4: pipeline_to_sql,
}


def _make_pipeline_callback(progress, task_id, phase_name: str = ""):
    """Adapt pipeline callback(message, current, total) to Rich progress."""

    def _cb(message: str, current: int = 0, total: int = 0) -> None:
        update_kw = {}
        if total > 0:
            update_kw["total"] = total
        if current > 0:
            update_kw["completed"] = current
        if message:
            # Extract company name from messages like "[1/10] 76036453-5_AGROSUPER_SA"
            desc = message
            if "] " in desc:
                desc = desc.split("] ", 1)[-1]
            # Strip verbose prefixes
            for prefix in ("Phase ", "Fase ", "  "):
                if desc.startswith(prefix):
                    desc = desc.lstrip()
            # Show short description; fall back to phase name
            desc = desc[:55] or phase_name
            update_kw["description"] = desc
        progress.update(task_id, **update_kw)

    return _cb


@contextlib.contextmanager
def _quiet_pipeline():
    """Suppress stdout print() noise from legacy scripts during progress bars.

    Redirects stdout to devnull and raises the logging level so that only
    warnings/errors come through.  stderr is left untouched so Rich progress
    bars (which render to stderr via the console singleton) display cleanly.
    """
    old_level = logging.root.level
    logging.root.setLevel(logging.WARNING)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with contextlib.redirect_stdout(io.StringIO()):
            try:
                yield
            finally:
                logging.root.setLevel(old_level)


def run_phases(
    config: CMFConfig,
    companies: list[Company],
    phases: list[int],
) -> dict[int, PipelineResult]:
    """Execute the requested phases for the selected companies."""
    config.apply_env()
    config.ensure_dirs()

    company_dirs = [c.xbrl_dir for c in companies if c.xbrl_dir]
    if not company_dirs:
        console.print("[error]Ninguna empresa seleccionada tiene directorio XBRL.[/error]")
        return {}

    results: dict[int, PipelineResult] = {}

    for phase_num in sorted(phases):
        phase_name = _PHASE_NAMES[phase_num]
        runner = _PHASE_RUNNERS[phase_num]

        print_section(phase_name)

        from cmf.ui.progress import create_pipeline_progress, create_progress_callback

        progress = create_pipeline_progress()
        with progress:
            task_id = progress.add_task(phase_name, total=len(company_dirs))
            cb = _make_pipeline_callback(progress, task_id, phase_name)
            with _quiet_pipeline():
                result = runner.run(config, company_dirs, progress_callback=cb)

        results[phase_num] = result
        show_results_summary(result, phase_name)

    # Final summary
    if len(phases) > 1:
        _show_final_summary(results)

    return results


def _show_final_summary(results: dict[int, PipelineResult]) -> None:
    """Print an overall summary across all phases."""
    print_section("Resumen Final")

    from rich.table import Table

    table = Table(
        show_header=True,
        header_style="table.header",
        border_style="muted",
        expand=True,
    )
    table.add_column("Fase", style="accent", min_width=35)
    table.add_column("Exitosos", justify="center", style="success", width=10)
    table.add_column("Errores", justify="center", width=10)
    table.add_column("Duracion", justify="right", style="info", width=12)

    total_success = 0
    total_errors = 0
    total_elapsed = 0.0

    for phase_num, result in sorted(results.items()):
        name = _PHASE_NAMES[phase_num]
        err_style = "error" if result.errors else "muted"
        elapsed_str = f"{result.elapsed:.1f}s"
        table.add_row(
            name,
            str(len(result.success)),
            f"[{err_style}]{len(result.errors)}[/{err_style}]",
            elapsed_str,
        )
        total_success += len(result.success)
        total_errors += len(result.errors)
        total_elapsed += result.elapsed

    table.add_section()
    table.add_row(
        "[bold]TOTAL[/bold]",
        f"[bold]{total_success}[/bold]",
        f"[bold]{total_errors}[/bold]",
        f"[bold]{total_elapsed:.1f}s[/bold]",
    )

    console.print(table)
    console.print()


# ──────────────────────────────────────────────────────────────────────────
# Menu handlers
# ──────────────────────────────────────────────────────────────────────────


def handle_download_xbrl(config: CMFConfig, registry: CompanyRegistry) -> None:
    """[1] Download XBRL from CMF."""
    print_section("Descargar XBRL desde CMF")

    from cmf.scraping.xbrl_downloader import SELENIUM_AVAILABLE

    if not SELENIUM_AVAILABLE:
        console.print(
            "[error]Selenium no esta instalado.[/error]\n"
            "[muted]Instala con: pip install selenium[/muted]"
        )
        return

    companies = select_companies(registry)
    if not companies:
        return

    from rich.prompt import Prompt

    mode = Prompt.ask(
        "[accent]Modo de descarga[/accent]",
        choices=["total", "annual", "quarterly"],
        default="total",
        console=console,
    )

    start_year = int(
        Prompt.ask("[accent]Ano inicio[/accent]", default="2024", console=console)
    )
    end_year = int(
        Prompt.ask("[accent]Ano fin[/accent]", default="2014", console=console)
    )
    max_browsers = int(
        Prompt.ask(
            "[accent]Browsers paralelos por empresa[/accent] (1=secuencial)",
            default="2",
            console=console,
        )
    )

    ruts = [c.rut_number for c in companies if c.rut_number]
    console.print(
        f"\n[info]Descargando {len(ruts)} empresa(s) | Modo: {mode} | "
        f"Anos: {start_year}-{end_year} | Browsers: {max_browsers}[/info]"
    )

    if not confirm("Continuar con la descarga?"):
        return

    from cmf.ui.progress import create_pipeline_progress

    progress = create_pipeline_progress()
    with progress:
        task_id = progress.add_task("Descargando XBRL", total=len(ruts))
        cb = _make_pipeline_callback(progress, task_id, "Descargando XBRL")
        with _quiet_pipeline():
            result = pipeline_download.run(
                config,
                ruts=ruts,
                mode=mode,
                start_year=start_year,
                end_year=end_year,
                progress_callback=cb,
                max_browsers=max_browsers,
            )

    show_results_summary(result, "Descarga XBRL")


def handle_check_availability(config: CMFConfig) -> None:
    """[2] Check XBRL availability on CMF."""
    print_section("Verificar disponibilidad XBRL")

    from cmf.scraping.xbrl_checker import SELENIUM_AVAILABLE

    if not SELENIUM_AVAILABLE:
        console.print(
            "[error]Selenium no esta instalado.[/error]\n"
            "[muted]Instala con: pip install selenium[/muted]"
        )
        return

    from cmf.scraping.xbrl_checker import CMFXBRLChecker
    from rich.prompt import Prompt

    workers = int(
        Prompt.ask(
            "[accent]Workers (navegadores simultaneos)[/accent]",
            default="4",
            console=console,
        )
    )

    checker = CMFXBRLChecker(config=config)
    console.print("[info]Verificando disponibilidad...[/info]\n")
    summary = checker.run_check(max_workers=workers)

    if summary and summary.get("total_new_periods", 0) > 0:
        from rich.table import Table

        table = Table(
            title="Periodos nuevos disponibles",
            title_style="success",
            border_style="muted",
            expand=True,
        )
        table.add_column("Empresa", style="accent")
        table.add_column("Ultimo local", style="muted")
        table.add_column("Nuevos", style="success")

        for name, detail in summary.get("details", {}).items():
            if detail.get("new_periods_available"):
                table.add_row(
                    name,
                    detail["latest_local_period"],
                    ", ".join(detail["new_periods_available"]),
                )

        console.print(table)
    else:
        console.print("[success]Tu coleccion XBRL esta actualizada.[/success]")
    console.print()


def handle_sync(config: CMFConfig) -> None:
    """[3] Sync from scraping repo."""
    print_section("Sincronizar desde repo scraping")

    if not config.scraping_repo:
        console.print(
            "[warning]No se ha configurado la ruta del repo de scraping.[/warning]\n"
            "[muted]Configura CMF_SCRAPING_REPO o scraping_repo en CMFConfig.[/muted]\n"
            "[muted]Ejemplo: export CMF_SCRAPING_REPO=/ruta/a/cmf-web-scraping[/muted]"
        )
        from rich.prompt import Prompt

        path = Prompt.ask(
            "[accent]Ruta al repo cmf-web-scraping[/accent]",
            default="/home/unzzui/Documents/coding/cmf-web-scraping",
            console=console,
        )
        config.scraping_repo = Path(path)

    console.print(f"[info]Origen: {config.scraping_repo}[/info]")
    console.print(f"[info]Destino: {config.xbrl_base_dir}[/info]\n")

    if not confirm("Iniciar sincronizacion?"):
        return

    from cmf.ui.progress import create_pipeline_progress

    progress = create_pipeline_progress()
    with progress:
        task_id = progress.add_task("Sincronizando", total=100)
        cb = _make_pipeline_callback(progress, task_id)
        result = pipeline_sync.run(config, progress_callback=cb)

    show_results_summary(result, "Sincronizacion")


def handle_bank_data(config: CMFConfig) -> None:
    """[4] Download bank data."""
    print_section("Descargar datos bancarios")

    from cmf.scraping.bank_scraper import CMFBankScraper
    from rich.prompt import Prompt
    from rich.table import Table

    # Show available banks
    table = Table(
        title="Bancos disponibles",
        title_style="accent",
        border_style="muted",
    )
    table.add_column("Codigo", style="accent", width=8)
    table.add_column("Banco", style="header")

    for code, name in sorted(CMFBankScraper.BANK_CODES.items()):
        if code != "999":
            table.add_row(code, name)

    console.print(table)
    console.print()

    bank_input = Prompt.ask(
        "[accent]Codigos de banco[/accent] [muted](separados por coma, o 'all')[/muted]",
        default="all",
        console=console,
    )

    report_type = Prompt.ask(
        "[accent]Tipo de reporte[/accent]",
        choices=list(CMFBankScraper.REPORT_TYPES.keys()),
        default="MB1",
        console=console,
    )

    month = int(Prompt.ask("[accent]Mes[/accent]", default="12", console=console))
    year = int(Prompt.ask("[accent]Ano[/accent]", default="2024", console=console))

    output_dir = config.repo_root / "output" / "banks"
    scraper = CMFBankScraper(output_dir=str(output_dir))

    if bank_input.lower() == "all":
        results = scraper.download_all_banks(report_type, month, year)
    else:
        codes = [c.strip() for c in bank_input.split(",")]
        results = scraper.download_multiple_banks(codes, report_type, month, year)

    console.print(
        f"\n[success]Descargados {len(results)} archivos bancarios.[/success]\n"
    )


def handle_full_pipeline(config: CMFConfig, registry: CompanyRegistry) -> None:
    """[5] Full pipeline (phases 1-4)."""
    companies = select_companies(registry)
    if not companies:
        return

    console.print(
        f"\n[info]Pipeline completo para {len(companies)} empresa(s) - Fases 1 a 4[/info]"
    )
    if not confirm("Iniciar procesamiento?"):
        return

    run_phases(config, companies, [1, 2, 3, 4])


def handle_select_phases(config: CMFConfig, registry: CompanyRegistry) -> None:
    """[6] Select specific phases."""
    companies = select_companies(registry)
    if not companies:
        return

    phases = select_phases()
    if not phases:
        return

    phase_names = ", ".join(_PHASE_NAMES[p] for p in phases)
    console.print(
        f"\n[info]{len(companies)} empresa(s) | Fases: {phase_names}[/info]"
    )
    if not confirm("Iniciar procesamiento?"):
        return

    run_phases(config, companies, phases)


def handle_single_company(config: CMFConfig, registry: CompanyRegistry) -> None:
    """[7] Process single company."""
    companies = select_companies(registry)
    if not companies:
        return

    # For single company mode, take just the first if multiple selected
    company = companies[0]
    console.print(
        f"\n[info]Procesando: {company.display_name}[/info]\n"
        f"[info]Pipeline completo (Fases 1-4)[/info]"
    )
    if not confirm("Iniciar procesamiento?"):
        return

    run_phases(config, [company], [1, 2, 3, 4])


def handle_browse_companies(registry: CompanyRegistry) -> None:
    """[8] Browse companies."""
    print_section("Explorar empresas")

    companies = registry.companies_with_xbrl
    console.print(
        f"[info]{len(companies)} empresa(s) con datos XBRL en disco[/info]\n"
        f"[muted]{len(registry)} empresa(s) en total en el registro CSV[/muted]\n"
    )

    page = 0
    page_size = 20
    from rich.prompt import Prompt
    import math

    while True:
        show_company_table(companies, page=page, page_size=page_size)
        choice = Prompt.ask(
            "[muted]n=siguiente, p=anterior, b <texto>=buscar, q=volver[/muted]",
            default="q",
            console=console,
        ).strip().lower()

        if choice == "q":
            break
        elif choice == "n":
            total_pages = max(1, math.ceil(len(companies) / page_size))
            page = min(page + 1, total_pages - 1)
        elif choice == "p":
            page = max(0, page - 1)
        elif choice.startswith("b "):
            query = choice[2:].strip()
            results = registry.search(query)
            if results:
                console.print(
                    f"\n[info]{len(results)} resultado(s) para '{query}':[/info]\n"
                )
                show_company_table(results, page=0, page_size=page_size)
                Prompt.ask("[muted]Enter para volver[/muted]", default="", console=console)
            else:
                console.print(f"[warning]Sin resultados para '{query}'[/warning]\n")


# ──────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CMF Extract - Plataforma de datos financieros chilenos",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Procesar todas las empresas (modo no-interactivo)",
    )
    parser.add_argument(
        "--phases",
        type=str,
        default="1-4",
        help="Fases a ejecutar (ej: '1-4', '2,3', '1'). Default: 1-4",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Modo debug",
    )
    return parser.parse_args()


def _parse_phases_arg(phases_str: str) -> list[int]:
    """Parse a phase range string like '1-4' or '2,3' into a list of ints."""
    result = set()
    for part in phases_str.replace(";", ",").split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return sorted(n for n in result if 1 <= n <= 4)


def interactive_loop(config: CMFConfig, registry: CompanyRegistry) -> int:
    """Main interactive menu loop."""
    while True:
        print_header()
        choice = show_main_menu()

        if choice == "q":
            console.print("\n[muted]Hasta luego![/muted]\n")
            return 0

        try:
            if choice == "1":
                handle_download_xbrl(config, registry)
            elif choice == "2":
                handle_check_availability(config)
            elif choice == "3":
                handle_sync(config)
            elif choice == "4":
                handle_bank_data(config)
            elif choice == "5":
                handle_full_pipeline(config, registry)
            elif choice == "6":
                handle_select_phases(config, registry)
            elif choice == "7":
                handle_single_company(config, registry)
            elif choice == "8":
                handle_browse_companies(registry)
            elif choice == "9":
                show_config(config)
        except KeyboardInterrupt:
            console.print("\n[warning]Operacion interrumpida.[/warning]\n")
        except Exception as e:
            console.print(f"\n[error]Error: {e}[/error]\n")
            if config.debug:
                console.print_exception()

        # Pause before redrawing menu
        from rich.prompt import Prompt
        Prompt.ask(
            "\n[muted]Presione Enter para continuar...[/muted]",
            default="",
            console=console,
        )


def main() -> int:
    args = parse_args()
    config = CMFConfig(debug=args.debug)
    registry = CompanyRegistry(config)

    if args.all:
        # Non-interactive mode
        phases = _parse_phases_arg(args.phases)
        if not phases:
            console.print("[error]No se especificaron fases validas.[/error]")
            return 1

        print_header()
        companies = registry.companies_with_xbrl
        console.print(
            f"[info]Modo batch: {len(companies)} empresa(s) | "
            f"Fases: {phases}[/info]\n"
        )

        results = run_phases(config, companies, phases)
        return 0 if all(r.ok for r in results.values()) else 1

    return interactive_loop(config, registry)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        console.print("\n[warning]Interrumpido por el usuario.[/warning]")
        raise SystemExit(1)
