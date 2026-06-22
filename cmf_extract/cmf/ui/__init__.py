"""Rich-based UI layer for CMF Extract CLI.

Public surface
--------------

**theme**
    ``console``         – Module-level Console singleton (use for all output).
    ``print_header``    – Renders the main CLI banner.
    ``print_section``   – Renders a section separator rule.

**tables**
    ``show_company_table``    – Paginated company listing.
    ``show_results_summary``  – Pipeline phase result panel.

**progress**
    ``create_pipeline_progress``  – Configured Progress instance factory.
    ``create_progress_callback``  – Callback adaptor for pipeline stages.
    ``run_with_progress``         – Context manager combining both.

**menus**
    ``show_main_menu``    – Interactive main menu, returns user's choice.
    ``select_companies``  – Interactive company picker.
    ``select_phases``     – Interactive phase picker.
    ``confirm``           – Yes/no Rich prompt wrapper.
    ``show_config``       – Render active CMFConfig in a table.
"""

from cmf.ui.menus import (
    confirm,
    select_companies,
    select_phases,
    show_config,
    show_main_menu,
)
from cmf.ui.progress import (
    create_pipeline_progress,
    create_progress_callback,
    run_with_progress,
)
from cmf.ui.tables import show_company_table, show_results_summary
from cmf.ui.theme import console, print_header, print_section

__all__ = [
    # theme
    "console",
    "print_header",
    "print_section",
    # tables
    "show_company_table",
    "show_results_summary",
    # progress
    "create_pipeline_progress",
    "create_progress_callback",
    "run_with_progress",
    # menus
    "show_main_menu",
    "select_companies",
    "select_phases",
    "confirm",
    "show_config",
]
