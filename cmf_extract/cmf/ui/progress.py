"""Rich Progress helpers for CMF pipeline stages.

Usage pattern::

    progress = create_pipeline_progress()
    with progress:
        task = progress.add_task("Consolidacion XBRL", total=len(companies))
        callback = create_progress_callback(progress, task)
        result = run_phase(config, progress_callback=callback)

Or via the convenience context manager::

    with run_with_progress("Fase 1 - Consolidacion", total=40) as (prog, cb):
        result = run_phase(config, progress_callback=cb)
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable, Generator

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)

from cmf.ui.theme import console


# ---------------------------------------------------------------------------
# Progress factory
# ---------------------------------------------------------------------------


def create_pipeline_progress() -> Progress:
    """Return a :class:`rich.progress.Progress` configured for pipeline ops.

    Column layout:

    * Spinner   – Animated indicator that the stage is alive.
    * Task name – Description text supplied when the task is added.
    * Bar       – Proportional fill bar.
    * ``n/N``   – Discrete count (e.g. "12/40").
    * ``%``     – Percentage complete.
    * Elapsed   – Wall-clock time since the task started.

    Returns:
        A fully constructed but *not yet started* Progress instance that
        shares the module-level ``console`` singleton.
    """
    return Progress(
        SpinnerColumn(style="accent"),
        TextColumn("[bold]{task.description}[/bold]", style="header"),
        BarColumn(
            bar_width=None,
            style="muted",
            complete_style="success",
            finished_style="success",
        ),
        MofNCompleteColumn(),
        TextColumn("[muted]{task.percentage:>5.1f}%[/muted]"),
        TimeElapsedColumn(),
        console=console,
        expand=True,
        transient=False,
    )


# ---------------------------------------------------------------------------
# Callback factory
# ---------------------------------------------------------------------------


def create_progress_callback(
    progress: Progress,
    task_id: TaskID,
) -> Callable[[int, int, str], None]:
    """Return a callback that advances *task_id* inside *progress*.

    The returned callable has the signature::

        callback(completed: int, total: int, description: str = "") -> None

    It can be passed directly to pipeline stage ``run()`` functions as their
    ``progress_callback`` keyword argument.

    Args:
        progress:   The active :class:`Progress` instance.
        task_id:    The task whose state should be updated on each call.

    Returns:
        A zero-import callable suitable for use as a progress hook.
    """

    def _callback(completed: int, total: int, description: str = "") -> None:
        update_kwargs: dict = {"completed": completed, "total": total}
        if description:
            update_kwargs["description"] = description
        progress.update(task_id, **update_kwargs)

    return _callback


# ---------------------------------------------------------------------------
# Convenience context manager
# ---------------------------------------------------------------------------


@contextmanager
def run_with_progress(
    description: str,
    total: int = 100,
) -> Generator[tuple[Progress, Callable[[int, int, str], None]], None, None]:
    """Context manager that starts a progress bar and yields ``(progress, callback)``.

    Ensures the Progress instance is properly started and stopped even if an
    exception is raised inside the block.

    Args:
        description:  The task label shown in the progress bar.
        total:        Expected number of steps (units of work).

    Yields:
        A ``(Progress, callback)`` tuple.  Pass *callback* to the pipeline
        stage so it can report incremental progress.

    Example::

        with run_with_progress("Consolidacion XBRL", total=40) as (prog, cb):
            result = consolidation.run(config, progress_callback=cb)
    """
    progress = create_pipeline_progress()
    with progress:
        task_id = progress.add_task(description, total=total)
        callback = create_progress_callback(progress, task_id)
        yield progress, callback
