"""Pipeline stage: synchronise XBRL files from the scraping repository.

This is a non-interactive wrapper around the logic originally contained in
``sync_xbrl_data.py``.  All decisions (copy new files, overwrite changed files)
are made automatically without prompting the user.

Public interface
----------------
::

    from cmf.pipeline.sync import run
    result = run(config, progress_callback=my_cb)

The *progress_callback* signature is::

    callback(message: str, current: int = 0, total: int = 0) -> None
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Callable, Set, Tuple

from cmf.config import CMFConfig
from cmf.pipeline import PipelineResult

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, int, int], None]

_NOOP: ProgressCallback = lambda msg, cur=0, tot=0: None  # noqa: E731


# ---------------------------------------------------------------------------
# Core filesystem helpers (reused from sync_xbrl_data.py)
# ---------------------------------------------------------------------------

def scan_directory(path: Path) -> Tuple[Set[str], Set[str], Set[str]]:
    """Recursively scan *path* and return relative paths.

    Returns
    -------
    files:
        Relative paths of all files found.
    main_directories:
        Names of first-level subdirectories.
    all_subdirectories:
        Relative paths of all subdirectories (any depth).
    """
    files: Set[str] = set()
    main_directories: Set[str] = set()
    all_subdirectories: Set[str] = set()

    for root, dirs, filenames in os.walk(path):
        root_path = Path(root)

        if root_path == path:
            for d in dirs:
                main_directories.add(d)

        for d in dirs:
            dir_path = root_path / d
            all_subdirectories.add(str(dir_path.relative_to(path)))

        for filename in filenames:
            rel = root_path.relative_to(path) / filename
            files.add(str(rel))

    return files, main_directories, all_subdirectories


def compare_files(source_file: Path, dest_file: Path) -> bool:
    """Return True when *source_file* and *dest_file* have identical content."""
    if not dest_file.exists():
        return False
    try:
        src_stat = source_file.stat()
        dst_stat = dest_file.stat()
        if src_stat.st_size != dst_stat.st_size:
            return False
        with open(source_file, "rb") as f1, open(dest_file, "rb") as f2:
            return f1.read() == f2.read()
    except OSError:
        return False


def copy_file_with_backup(
    source_file: Path,
    dest_file: Path,
    backup_dir: Path,
) -> None:
    """Copy *source_file* to *dest_file*, preserving a backup of any existing file.

    Parameters
    ----------
    source_file:
        File to copy from.
    dest_file:
        Destination path.
    backup_dir:
        Directory where the pre-existing destination file is saved before
        being overwritten.
    """
    backup_dir.mkdir(parents=True, exist_ok=True)

    if dest_file.exists():
        backup_path = backup_dir / dest_file.name
        shutil.copy2(dest_file, backup_path)

    dest_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, dest_file)


# ---------------------------------------------------------------------------
# Main pipeline entry point
# ---------------------------------------------------------------------------

def run(
    config: CMFConfig,
    progress_callback: ProgressCallback | None = None,
) -> PipelineResult:
    """Synchronise XBRL files from the scraping repository to the working tree.

    Source path is derived from ``config.scraping_repo`` when set, otherwise
    the function returns an error immediately.

    Destination path is ``config.xbrl_base_dir``.

    Only *new* and *changed* files are copied; files that already exist at the
    destination with identical content are skipped.  No files are deleted from
    the destination.

    Parameters
    ----------
    config:
        Populated :class:`~cmf.config.CMFConfig` instance.
    progress_callback:
        Optional callable invoked with ``(message, current, total)`` throughout
        the operation.

    Returns
    -------
    PipelineResult
        ``success`` contains the relative paths of files that were
        new-or-updated.  ``errors`` maps relative paths to error messages.
    """
    cb = progress_callback or _NOOP
    start = time.time()
    success: list[str] = []
    errors: dict[str, str] = {}

    # Resolve source path
    if config.scraping_repo is not None:
        source_path = config.scraping_repo / "data" / "XBRL" / "Total"
    else:
        return PipelineResult(
            success=[],
            errors={"config": "scraping_repo is not configured in CMFConfig"},
            elapsed=time.time() - start,
        )

    dest_path = config.xbrl_base_dir

    # Basic validation
    if not source_path.exists():
        return PipelineResult(
            success=[],
            errors={"source": f"Source path does not exist: {source_path}"},
            elapsed=time.time() - start,
        )

    if not dest_path.exists():
        try:
            dest_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return PipelineResult(
                success=[],
                errors={"dest": f"Cannot create destination directory: {exc}"},
                elapsed=time.time() - start,
            )

    cb(f"Scanning source: {source_path}", 0, 0)
    source_files, source_main_dirs, source_subdirs = scan_directory(source_path)

    cb(f"Scanning destination: {dest_path}", 0, 0)
    dest_files, _dest_main_dirs, _dest_subdirs = scan_directory(dest_path)

    new_files = source_files - dest_files
    common_files = source_files & dest_files

    # Identify changed files among common ones
    changed_files: list[str] = []
    cb("Comparing common files...", 0, len(common_files))
    for idx, rel in enumerate(sorted(common_files), 1):
        src = source_path / rel
        dst = dest_path / rel
        if not compare_files(src, dst):
            changed_files.append(rel)
        if idx % 50 == 0:
            cb(f"Compared {idx}/{len(common_files)} files", idx, len(common_files))

    files_to_copy = sorted(new_files) + sorted(changed_files)
    total_to_copy = len(files_to_copy)

    if total_to_copy == 0:
        cb("All files are already up to date.", 0, 0)
        return PipelineResult(success=[], errors={}, elapsed=time.time() - start)

    # Ensure new company directories exist first
    new_main_dirs = source_main_dirs - _dest_main_dirs
    for main_dir in sorted(new_main_dirs):
        target = dest_path / main_dir
        try:
            target.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors[main_dir] = f"Cannot create directory: {exc}"

    backup_dir = dest_path.parent / "backup_sync"

    cb(f"Copying {total_to_copy} file(s)...", 0, total_to_copy)
    for idx, rel in enumerate(files_to_copy, 1):
        src = source_path / rel
        dst = dest_path / rel
        action = "new" if rel in new_files else "updated"
        cb(f"[{action}] {rel}", idx, total_to_copy)
        try:
            copy_file_with_backup(src, dst, backup_dir)
            success.append(rel)
        except OSError as exc:
            errors[rel] = str(exc)

    cb(
        f"Sync complete: {len(success)} copied, {len(errors)} errors.",
        total_to_copy,
        total_to_copy,
    )
    return PipelineResult(success=success, errors=errors, elapsed=time.time() - start)
