"""Diagnostics dialog — live snapshot of resources for triage.

Surfaces the information a senior engineer would want when investigating
"the app feels slow" / "is something leaking" reports:

* Per-session pipeline status — RX bytes, ring-buffer fill, dropped chunks
* Per-session log writer status — bytes written, queue depth, drops
* Terminal pending queue (RX coalescer backlog)
* Live thread count, Qt object count, process RSS (resident memory)

Refreshes every 500 ms while open.

Resource-leak audit checklist
-----------------------------
Every long-lived resource KCom creates is enumerated here. If a metric
keeps growing while no new connections are being opened, that is the
leak.
"""

from __future__ import annotations

import os
import sys
import threading

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


def _process_rss_mb() -> float | None:
    """Return CURRENT process resident set size in MB, or None if unavailable.

    NOTE: do not use ``resource.getrusage().ru_maxrss`` — that returns the
    PEAK RSS since process start and only ever increases, which makes it
    look like the app is leaking even when memory has been freed.
    """
    # Linux — /proc/self/status has live VmRSS.
    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/status", "r") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        # "VmRSS:   123456 kB"
                        return int(parts[1]) / 1024
        except Exception:
            pass
    # macOS — ps -o rss= is the easiest live source (ru_maxrss is peak).
    if sys.platform == "darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["ps", "-o", "rss=", "-p", str(os.getpid())],
                stderr=subprocess.DEVNULL, timeout=1,
            )
            return int(out.strip()) / 1024
        except Exception:
            pass
    # Windows fallback via ctypes / Windows API.
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb",                         wintypes.DWORD),
                    ("PageFaultCount",             wintypes.DWORD),
                    ("PeakWorkingSetSize",         ctypes.c_size_t),
                    ("WorkingSetSize",             ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage",    ctypes.c_size_t),
                    ("QuotaPagedPoolUsage",        ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage",     ctypes.c_size_t),
                    ("PagefileUsage",              ctypes.c_size_t),
                    ("PeakPagefileUsage",          ctypes.c_size_t),
                ]

            counters = _PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(_PROCESS_MEMORY_COUNTERS)
            handle = ctypes.windll.kernel32.GetCurrentProcess()
            ok = ctypes.windll.psapi.GetProcessMemoryInfo(
                handle, ctypes.byref(counters), counters.cb,
            )
            if ok:
                return counters.WorkingSetSize / 1024 / 1024
    except Exception:
        pass
    return None


class DiagnosticsDialog(QDialog):
    """Live snapshot of session, thread, and memory resources."""

    def __init__(self, main_window, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("KCom Diagnostics")
        self.resize(720, 480)
        self._mw = main_window
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(500)
        self._timer.timeout.connect(self._refresh)
        self._timer.start()
        self._refresh()

    # ── UI ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Process-level summary line
        self._summary = QLabel()
        self._summary.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._summary)

        # Per-session table
        layout.addWidget(QLabel("<b>Per-session resources</b>"))
        self._table = QTableWidget(0, 8)
        self._table.setHorizontalHeaderLabels([
            "Session", "Type", "RX bytes", "TX bytes",
            "Ring fill", "Drops", "Log writes", "Log Q drops",
        ])
        self._table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self._table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        layout.addWidget(self._table)

        # Terminal coalescer backlog summary
        self._terminal_summary = QLabel()
        layout.addWidget(self._terminal_summary)

        # Buttons
        btns = QHBoxLayout()
        self._copy_btn = QPushButton("Copy report")
        self._copy_btn.clicked.connect(self._on_copy)
        btns.addWidget(self._copy_btn)

        self._gc_btn = QPushButton("Force GC")
        self._gc_btn.setToolTip(
            "Run a full Python garbage collection cycle so memory growth "
            "from cyclic references is visible as a drop in resident memory."
        )
        self._gc_btn.clicked.connect(self._on_gc)
        btns.addWidget(self._gc_btn)

        btns.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        btns.addWidget(bb)
        layout.addLayout(btns)

    # ── Refresh ─────────────────────────────────────────────────────────

    def _refresh(self) -> None:
        # Process-level
        rss = _process_rss_mb()
        rss_txt = f"{rss:.1f} MB" if rss is not None else "n/a"
        thread_count = threading.active_count()
        pid = os.getpid()
        self._summary.setText(
            f"PID <b>{pid}</b>  ·  Threads <b>{thread_count}</b>  "
            f"·  Resident memory <b>{rss_txt}</b>"
        )

        # Per-session table
        sessions = self._mw._session_manager.all_sessions()
        self._table.setRowCount(len(sessions))
        for row, sess in enumerate(sessions):
            stats = sess.stats
            ring_fill = len(sess.pipeline._ring_buffer)
            ring_cap = sess.pipeline.RING_BUFFER_SIZE
            drops = sess.pipeline.dropped_count
            log_bytes = sess.log_manager.bytes_written
            log_drops = (
                sess.log_manager._writer.dropped_count
                if sess.log_manager._writer is not None else 0
            )
            ctype = sess.config.connection_type.value
            cells = [
                sess.config.display_name(),
                ctype,
                f"{stats.bytes_rx:,}",
                f"{stats.bytes_tx:,}",
                f"{ring_fill}/{ring_cap}",
                f"{drops}",
                f"{log_bytes:,}",
                f"{log_drops}",
            ]
            for col, txt in enumerate(cells):
                item = QTableWidgetItem(txt)
                self._table.setItem(row, col, item)

        # Terminal coalescer summary across all open tabs
        backlogs = []
        for tab in self._mw._port_tabs.values():
            n = len(tab.terminal._pending)
            if n > 0:
                backlogs.append(
                    f"{tab.title}={n}" if hasattr(tab, "title") else f"tab={n}"
                )
        if backlogs:
            self._terminal_summary.setText(
                f"<b>RX coalescer backlog:</b> {', '.join(backlogs)}"
            )
        else:
            self._terminal_summary.setText(
                "<b>RX coalescer backlog:</b> 0 (no pending chunks)"
            )

    # ── Copy report ─────────────────────────────────────────────────────

    def _on_copy(self) -> None:
        """Copy the current diagnostics snapshot to the clipboard."""
        from PyQt6.QtWidgets import QApplication
        rss = _process_rss_mb()
        rss_txt = f"{rss:.1f} MB" if rss is not None else "n/a"
        lines = [
            "── KCom Diagnostics ──────────────────────────────",
            f"  PID:     {os.getpid()}",
            f"  Threads: {threading.active_count()}",
            f"  Memory:  {rss_txt}",
            "",
            "Sessions:",
        ]
        for sess in self._mw._session_manager.all_sessions():
            s = sess.stats
            ring_fill = len(sess.pipeline._ring_buffer)
            ring_cap = sess.pipeline.RING_BUFFER_SIZE
            log_q_drops = (
                sess.log_manager._writer.dropped_count
                if sess.log_manager._writer is not None else 0
            )
            lines.append(
                f"  • {sess.config.display_name()} "
                f"[{sess.config.connection_type.value}] "
                f"RX={s.bytes_rx:,}  TX={s.bytes_tx:,}  "
                f"ring={ring_fill}/{ring_cap}  "
                f"ring_drops={sess.pipeline.dropped_count}  "
                f"log_bytes={sess.log_manager.bytes_written:,}  "
                f"log_q_drops={log_q_drops}"
            )
        QApplication.clipboard().setText("\n".join(lines))

    def _on_gc(self) -> None:
        """Force a Python GC cycle and refresh the snapshot immediately."""
        import gc
        gc.collect()
        self._refresh()

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
