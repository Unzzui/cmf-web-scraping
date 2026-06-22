"""Pipeline wrappers for CMF Extract processing stages.

Each sub-module exposes a single ``run()`` function that accepts a
:class:`~cmf.config.CMFConfig` and an optional *progress_callback*, executes
one discrete stage of the pipeline, and returns a :class:`PipelineResult`.

Stages
------
sync            Synchronise XBRL source files from the scraping repo.
consolidation   Phase 1 - XBRL -> consolidated facts CSV (via Arelle).
excel_gen       Phase 2 - Facts CSV -> primary Excel workbook.
analysis        Phase 3 - Primary Excel -> financial analysis workbook + start sheet.
to_sql          Phase 4 - Export analysis workbooks to CSV for database import.
download        Download raw XBRL files from CMF website.
polish          (deprecated) Merged into Phase 3 analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PipelineResult:
    """Outcome of a single pipeline stage.

    Attributes
    ----------
    success:
        Names (or identifiers) of items that were processed without error.
    errors:
        Mapping of item name -> error message for items that failed.
    elapsed:
        Wall-clock seconds taken by the stage.
    """

    success: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)
    elapsed: float = 0.0

    @property
    def ok(self) -> bool:
        """True when there are no errors."""
        return not self.errors

    @property
    def total(self) -> int:
        """Total items attempted (succeeded + errored)."""
        return len(self.success) + len(self.errors)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"PipelineResult(success={len(self.success)}, "
            f"errors={len(self.errors)}, elapsed={self.elapsed:.1f}s)"
        )


__all__ = ["PipelineResult"]
