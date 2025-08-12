#!/usr/bin/env python3
"""
Console dashboard (static-like) for XBRL downloads that updates in place.
Uses rich if available, otherwise falls back to ANSI redraws.
"""

from __future__ import annotations

import threading
import time
from typing import Dict, List, Any
import logging
from logging import StreamHandler, FileHandler


try:
    from rich.live import Live
    from rich.table import Table
    from rich.console import Console, Group
    _HAS_RICH = True
except Exception:
    _HAS_RICH = False


class ConsoleXBRLDashboard:
    def __init__(self, companies: List[Dict[str, Any]], *, mute_stdout_logs: bool = True,
                 log_to_file: bool = True, log_file_path: str = "./data/debug/xbrl_run.log"):
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._order: List[str] = []  # stable order of RUTs
        self._status: Dict[str, Dict[str, Any]] = {}
        for company in companies:
            rut = str(company.get('rut_sin_guion') or company.get('rut') or '')
            empresa = company.get('razon_social', '')
            self._order.append(rut)
            self._status[rut] = {
                'empresa': empresa,
                'rut': rut,
                'estado': 'En cola',
                'worker': '-',
                'archivos': '-',
                'progreso': '-',
                'periodo': '-',
                'percent': '-',
                'bar': '',
            }

        self._console = Console() if _HAS_RICH else None
        # Logging control
        self._saved_handlers: List[logging.Handler] | None = None
        self._file_handler: FileHandler | None = None
        self._mute_stdout_logs = mute_stdout_logs
        self._log_to_file = log_to_file
        self._log_file_path = log_file_path
        self._start_ts: float | None = None

    def start(self):
        if self._thread is not None:
            return
        self._start_ts = time.time()
        self._mute_logging()
        self._thread = threading.Thread(target=self._run, name="ConsoleXBRLDashboard", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._restore_logging()

    def update(self, rut: str, estado: str | None = None, worker: int | str | None = None,
               archivos: int | None = None, progreso: str | None = None,
               periodo: str | None = None, eta_seconds: float | int | None = None,
               current: int | None = None, total: int | None = None):
        key = str(rut)
        with self._lock:
            row = self._status.get(key)
            if not row:
                return
            if estado is not None:
                row['estado'] = estado
            if worker is not None:
                row['worker'] = str(worker)
            if archivos is not None:
                row['archivos'] = str(archivos)
            if progreso is not None:
                row['progreso'] = str(progreso)
            if periodo is not None:
                row['periodo'] = str(periodo)
            # Percent and bar from current/total
            if current is not None and total:
                try:
                    pct = max(0, min(100, int(round((float(current) / float(total)) * 100))))
                    row['percent'] = f"{pct}%"
                    # build 10-slot bar
                    slots = 10
                    filled = max(0, min(slots, int(round((pct / 100) * slots))))
                    row['bar'] = '█' * filled + '░' * (slots - filled)
                except Exception:
                    row['percent'] = '-'
                    row['bar'] = ''
            if eta_seconds is not None:
                try:
                    minutes = int(max(0, float(eta_seconds)) // 60)
                    row['eta'] = f"{minutes}m"
                except Exception:
                    row['eta'] = '-'

    # Internal
    def _run(self):
        if _HAS_RICH:
            self._run_rich()
        else:
            self._run_fallback()

    # Logging suppression while dashboard is active
    def _mute_logging(self):
        if not self._mute_stdout_logs:
            return
        try:
            root = logging.getLogger()
            self._saved_handlers = list(root.handlers)
            # keep only non-stream handlers
            kept: List[logging.Handler] = []
            for h in root.handlers:
                if isinstance(h, StreamHandler):
                    continue
                kept.append(h)
            root.handlers = kept
            if self._log_to_file:
                fh = FileHandler(self._log_file_path, mode='a', encoding='utf-8')
                fh.setLevel(logging.INFO)
                formatter = logging.Formatter('%(asctime)s | %(levelname)s | [WORKER %(thread)d] | %(message)s')
                fh.setFormatter(formatter)
                root.addHandler(fh)
                self._file_handler = fh
        except Exception:
            # If anything fails, don't break the app
            self._saved_handlers = None
            self._file_handler = None

    def _restore_logging(self):
        try:
            root = logging.getLogger()
            if self._file_handler is not None:
                try:
                    root.removeHandler(self._file_handler)
                except Exception:
                    pass
                try:
                    self._file_handler.close()
                except Exception:
                    pass
                self._file_handler = None
            if self._saved_handlers is not None:
                root.handlers = self._saved_handlers
                self._saved_handlers = None
        except Exception:
            pass

    def _render_table(self):
        table = Table(title="Estado Descarga XBRL", expand=True)
        table.add_column("Empresa", justify="left", no_wrap=True)
        table.add_column("RUT", justify="center")
        table.add_column("Estado", justify="center")
        table.add_column("Worker", justify="center")
        table.add_column("Archivos", justify="center")
        table.add_column("Progreso", justify="center")
        table.add_column("%", justify="center")
        table.add_column("Barra", justify="center")
        table.add_column("Periodo", justify="center")
        table.add_column("ETA", justify="center")
        with self._lock:
            for rut in self._order:
                row = self._status.get(rut, {})
                table.add_row(
                    str(row.get('empresa', '')),
                    str(row.get('rut', rut)),
                    str(row.get('estado', '-')),
                    str(row.get('worker', '-')),
                    str(row.get('archivos', '-')),
                    str(row.get('progreso', '-')),
                    str(row.get('percent', '-')),
                    str(row.get('bar', '')),
                    str(row.get('periodo', '-')),
                    str(row.get('eta', '-')),
                )
        if not _HAS_RICH:
            return table

        # Build summary table
        comp, err, prog, pend, total, elapsed = self._summary_stats()
        summary = Table(title="Resumen", expand=True)
        summary.add_column("Completadas", justify="center")
        summary.add_column("Errores", justify="center")
        summary.add_column("En progreso", justify="center")
        summary.add_column("Pendientes", justify="center")
        summary.add_column("Total", justify="center")
        summary.add_column("Transcurrido", justify="center")
        summary.add_row(str(comp), str(err), str(prog), str(pend), str(total), elapsed)

        return Group(table, summary)

    def _summary_stats(self):
        completed = errors = in_progress = pending = 0
        with self._lock:
            total = len(self._order)
            for rut in self._order:
                estado = str(self._status.get(rut, {}).get('estado', '')).lower()
                if 'complet' in estado:
                    completed += 1
                elif 'error' in estado:
                    errors += 1
                elif 'progreso' in estado:
                    in_progress += 1
                else:
                    pending += 1
        elapsed = '-'
        if self._start_ts:
            sec = int(max(0, time.time() - self._start_ts))
            elapsed = f"{sec//60:02d}:{sec%60:02d}"
        return completed, errors, in_progress, pending, total, elapsed

    def _run_rich(self):
        assert self._console is not None
        refresh_hz = 6.0
        with Live(self._render_table(), console=self._console, refresh_per_second=refresh_hz, transient=False) as live:
            while not self._stop_event.is_set():
                live.update(self._render_table())
                time.sleep(1.0 / refresh_hz)

    def _run_fallback(self):
        # Simple ANSI full redraw
        while not self._stop_event.is_set():
            # Clear screen and move cursor home
            print("\x1b[2J\x1b[H", end="")
            print("Estado Descarga XBRL (fallback)")
            print("=" * 80)
            header = f"{'Empresa':<40} {'RUT':<12} {'Estado':<14} {'Worker':<8} {'Archivos':<8} {'Prog':<7} {'%':<4} {'Barra':<12} {'Periodo':<8} {'ETA':<6}"
            print(header)
            print("-" * 80)
            with self._lock:
                for rut in self._order:
                    row = self._status.get(rut, {})
                    empresa = str(row.get('empresa', ''))[:38]
                    rutv = str(row.get('rut', rut))
                    estado = str(row.get('estado', '-'))
                    worker = str(row.get('worker', '-'))
                    archivos = str(row.get('archivos', '-'))
                    prog = str(row.get('progreso', '-'))
                    periodo = str(row.get('periodo', '-'))
                    percent = str(row.get('percent', '-'))
                    bar = str(row.get('bar', ''))
                    eta = str(row.get('eta', '-'))
                    print(f"{empresa:<40} {rutv:<12} {estado:<14} {worker:<8} {archivos:<8} {prog:<7} {percent:<4} {bar:<12} {periodo:<8} {eta:<6}")
            # Summary footer
            comp, err, progcnt, pend, total, elapsed = self._summary_stats()
            print("\nResumen: ", end="")
            print(f"Completadas: {comp} | Errores: {err} | En progreso: {progcnt} | Pendientes: {pend} | Total: {total} | Transcurrido: {elapsed}")
            time.sleep(0.2)


