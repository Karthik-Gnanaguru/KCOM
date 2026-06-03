"""Log manager — writes session data to files in a background writer thread.

Threading model
---------------
Each :class:`LogManager` owns a dedicated :class:`_LogWriterThread` that drains
a :class:`queue.Queue` of pre-formatted strings and writes them to disk.  The
UI thread only does string formatting + a non-blocking ``queue.put()``; it
never blocks on file I/O, even on Windows where small synchronous writes used
to freeze the GUI under high RX rates.

The writer thread flushes the file lazily (every ~250 ms) rather than after
every chunk.  Two synchronous flushes per chunk on the UI thread used to be
the dominant cause of the Windows hang reported by users.

Supported formats
-----------------
* ``text``  — ``[<wall-time>] [<dir>] <data-in-active-display-mode>``
* ``csv``   — ``timestamp,direction,<data-in-active-display-mode>``

The exact data column written depends on the *terminal display mode* in effect
when logging starts (or whenever the user switches mode mid-session):

* **ASCII** → ASCII column with ``\\r\\n`` collapsed and non-printable bytes
  rendered as ``\\xNN``.
* **HEX** → space-separated uppercase hex.
* **DEC** → space-separated decimal.
* **BIN** → space-separated 8-bit binary.
* **MIXED** → HEX + ``  |  `` + ASCII (matches the terminal's MIXED display).
"""

from __future__ import annotations

import os
import queue
import shutil
import threading
import time
from datetime import datetime
from typing import IO

from PyQt6.QtCore import QObject, pyqtSignal as Signal


# ─── Display-mode helpers ────────────────────────────────────────────────────
# Kept in sync with kcom/ui/terminal_table.py constants. We can't import from
# the UI layer here (core has zero UI imports), so the canonical string values
# are duplicated.

DISPLAY_ASCII = "ASCII"
DISPLAY_HEX   = "HEX"
DISPLAY_DEC   = "DEC"
DISPLAY_BIN   = "BIN"
DISPLAY_MIXED = "MIXED"

_VALID_DISPLAY_MODES = {
    DISPLAY_ASCII, DISPLAY_HEX, DISPLAY_DEC, DISPLAY_BIN, DISPLAY_MIXED,
}


def _ascii_render(data: bytes) -> str:
    """Render bytes as ASCII for the log; printable + escape sequences."""
    out: list[str] = []
    i = 0
    n = len(data)
    while i < n:
        b = data[i]
        if b == 0x0D:                              # \r — collapse \r\n
            if i + 1 < n and data[i + 1] == 0x0A:
                out.append("\n")
                i += 2
                continue
            out.append("\n")
        elif b == 0x0A:
            out.append("\n")
        elif b == 0x09:
            out.append("\t")
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\x{b:02x}")
        i += 1
    return "".join(out)


def _hex_render(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def _dec_render(data: bytes) -> str:
    return " ".join(str(b) for b in data)


def _bin_render(data: bytes) -> str:
    return " ".join(f"{b:08b}" for b in data)


def _render_for_mode(data: bytes, display_mode: str) -> str:
    """Format ``data`` the same way the terminal currently displays it."""
    if display_mode == DISPLAY_HEX:
        return _hex_render(data)
    if display_mode == DISPLAY_DEC:
        return _dec_render(data)
    if display_mode == DISPLAY_BIN:
        return _bin_render(data)
    if display_mode == DISPLAY_MIXED:
        return f"{_hex_render(data)}  |  {_ascii_render(data)}"
    # default: ASCII
    return _ascii_render(data)


def _csv_escape(value: str) -> str:
    """Wrap value in quotes if it contains commas, newlines, or quotes."""
    if any(ch in value for ch in (",", "\n", "\r", '"')):
        return '"' + value.replace('"', '""') + '"'
    return value


# Deferred-format callable used by SessionLogger.feed — runs on the writer
# thread, never on the UI thread.
def _session_log_format(ts: str, port_name: str, direction: str, data: bytes) -> str:
    hex_part = " ".join(f"{b:02X}" for b in data)
    ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return (
        f"[{ts}] [{port_name:12s}] [{direction}] "
        f"{hex_part:<48}  |{ascii_part}|\n"
    )


# ─── Background writer thread ────────────────────────────────────────────────


class _LogWriterThread(threading.Thread):
    """Drains string chunks from a queue and writes them to ``file_handle``.

    The writer flushes lazily (default 250 ms) so high-volume RX doesn't
    hammer the disk with one syscall per chunk. A queue ``None`` sentinel
    tells the thread to finish.

    Robustness — the queue is **bounded** (default 100_000 entries). If the
    disk cannot keep up (slow USB stick, fragmented drive, antivirus
    scanning), older entries are silently dropped from the head rather than
    letting memory grow without bound. The :attr:`dropped_count` counter
    surfaces how many records were lost so the UI can warn the user.
    """

    _STOP = object()
    _MAX_QUEUE = 100_000

    def __init__(
        self,
        file_handle: IO,
        flush_interval_s: float = 0.25,
        max_queue: int = _MAX_QUEUE,
    ) -> None:
        super().__init__(daemon=True, name="kcom-log-writer")
        self._file = file_handle
        self._q: queue.Queue = queue.Queue()
        self._max_queue = max_queue
        self._flush_interval = flush_interval_s
        self._last_flush = time.monotonic()
        self._dropped_count = 0
        self._lock = threading.Lock()

    @property
    def dropped_count(self) -> int:
        return self._dropped_count

    def write(self, text: str) -> None:
        """Non-blocking enqueue; safe from any thread.

        If the queue is at capacity the oldest pending entry is dropped to
        make room for the new one. The dropped count is tracked but no
        exception is raised — the UI thread is never blocked or interrupted.
        """
        if self._q.qsize() >= self._max_queue:
            try:
                # Drop oldest — keep the most-recent data
                self._q.get_nowait()
                with self._lock:
                    self._dropped_count += 1
            except queue.Empty:
                pass
        self._q.put(text)

    def write_deferred(self, formatter, args: tuple) -> None:
        """Enqueue a ``(formatter, args)`` pair — formatter runs on this thread.

        Same drop-policy as :meth:`write`. Used by callers that would
        otherwise spend significant UI-thread time building a string —
        we hand off raw arguments and let the writer thread format.
        """
        if self._q.qsize() >= self._max_queue:
            try:
                self._q.get_nowait()
                with self._lock:
                    self._dropped_count += 1
            except queue.Empty:
                pass
        self._q.put((formatter, args))

    def stop(self, timeout: float = 2.0) -> None:
        self._q.put(self._STOP)
        self.join(timeout=timeout)

    def run(self) -> None:
        while True:
            try:
                item = self._q.get(timeout=self._flush_interval)
            except queue.Empty:
                self._maybe_flush(force=True)
                continue

            if item is self._STOP:
                break

            try:
                # Two shapes are accepted:
                #   * plain ``str`` — write as-is
                #   * ``(formatter, args)`` — call formatter(*args) on this
                #     thread to build the string (cheap formatting moves
                #     off the UI thread, where it would otherwise contend
                #     with the GUI event loop).
                if isinstance(item, tuple):
                    formatter, args = item
                    text = formatter(*args)
                else:
                    text = item
                self._file.write(text)
            except (OSError, ValueError):
                break
            except Exception:
                # A bad formatter must not kill the writer; drop and keep going.
                continue

            self._maybe_flush()

        # Final drain — write any pending items so we don't lose tail data
        try:
            while True:
                try:
                    item = self._q.get_nowait()
                except queue.Empty:
                    break
                if item is self._STOP:
                    continue
                try:
                    if isinstance(item, tuple):
                        formatter, args = item
                        text = formatter(*args)
                    else:
                        text = item
                    self._file.write(text)
                except Exception:
                    continue
            self._file.flush()
        except (OSError, ValueError):
            pass

    def _maybe_flush(self, force: bool = False) -> None:
        now = time.monotonic()
        if force or (now - self._last_flush) >= self._flush_interval:
            try:
                self._file.flush()
            except (OSError, ValueError):
                pass
            self._last_flush = now


# ─── LogManager ──────────────────────────────────────────────────────────────


class LogManager(QObject):
    """Per-session log writer.

    Writes are formatted on the calling thread (cheap string-build) and then
    handed off to a background :class:`_LogWriterThread` via a queue. The UI
    thread never blocks on file I/O.

    File format columns are chosen by the *terminal display mode* (call
    :meth:`set_display_mode`) and the *output format* (``text`` or ``csv``)
    selected when :meth:`start_logging` is called.
    """

    logging_started: Signal = Signal(str)   # file path
    logging_stopped: Signal = Signal(str)   # file path
    error_occurred:  Signal = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._file: IO | None = None
        self._writer: _LogWriterThread | None = None
        self._path: str = ""
        self._mode: str = "text"                       # "text" | "csv"
        self._display_mode: str = DISPLAY_ASCII        # ASCII/HEX/DEC/BIN/MIXED
        self._bytes_written: int = 0
        # Filter DSL (same as the terminal toolbar). Empty string = log
        # everything. When set, only records that ``matches_filter`` returns
        # True for are written — exactly mirrors the on-screen view.
        self._filter_text: str = ""

    def __del__(self) -> None:
        """RAII safety net — if the owner forgot to call :meth:`stop_logging`,
        ensure the writer thread and file handle don't leak."""
        try:
            if self._writer is not None or self._file is not None:
                self.stop_logging()
        except Exception:
            pass

    # ── Properties ──────────────────────────────────────────────────────

    @property
    def is_logging(self) -> bool:
        return self._file is not None

    @property
    def log_path(self) -> str:
        return self._path

    @property
    def bytes_written(self) -> int:
        return self._bytes_written

    @property
    def display_mode(self) -> str:
        return self._display_mode

    # ── Configuration ───────────────────────────────────────────────────

    def set_display_mode(self, mode: str) -> None:
        """Update the column rendering used for subsequent writes.

        Called by the UI when the user switches terminal mode (ASCII / HEX /
        DEC / BIN / MIXED) — log output then matches what is on-screen.
        """
        if mode not in _VALID_DISPLAY_MODES:
            return
        self._display_mode = mode

    def set_filter(self, filter_text: str) -> None:
        """Apply the terminal's filter DSL to subsequent log writes.

        While a non-empty filter is active, only records that the on-screen
        terminal would *show* are written to the file — matching the user's
        "log what's visible" expectation. Set to ``""`` to log everything
        again. Records already written stay in the file.
        """
        self._filter_text = filter_text or ""

    # ── Public API ──────────────────────────────────────────────────────

    def start_logging(
        self,
        path: str,
        mode: str = "text",
        display_mode: str | None = None,
    ) -> None:
        """Open a log file and start the writer thread.

        Args:
            path:          Destination file path.
            mode:          ``"text"`` (default) or ``"csv"``.
            display_mode:  Terminal display mode active when logging starts —
                           ``"ASCII"`` / ``"HEX"`` / ``"DEC"`` / ``"BIN"`` /
                           ``"MIXED"``. Falls back to the previously-set mode.
        """
        if self._file is not None:
            self.stop_logging()

        mode = mode if mode in ("text", "csv") else "text"
        if display_mode is not None:
            self.set_display_mode(display_mode)

        self._mode = mode
        self._path = path
        self._bytes_written = 0

        try:
            # Larger Python-level buffer (64 KB) so a slow disk doesn't
            # block the writer thread on every small chunk either.
            self._file = open(
                path, "w", encoding="utf-8", newline="", buffering=64 * 1024
            )
        except OSError as e:
            self._file = None
            self.error_occurred.emit(f"Cannot open log file: {e}")
            return

        # CSV gets a column header so the file is importable into Excel /
        # pandas as-is. Text logs contain only data — no comment banner.
        if mode == "csv":
            self._file.write(self._csv_header() + "\n")

        # Start the background writer AFTER headers are written
        self._writer = _LogWriterThread(self._file)
        self._writer.start()
        self.logging_started.emit(path)

    def stop_logging(self) -> None:
        """Drain the writer thread and close the file."""
        if self._writer is not None:
            self._writer.stop()
            self._writer = None
        if self._file is not None:
            try:
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            finally:
                path = self._path
                self._file = None
                self.logging_stopped.emit(path)

    def feed(self, data: bytes, direction: str, timestamp: float) -> None:
        """Format a chunk on the caller's thread and enqueue for the writer.

        ``timestamp`` is accepted for API compatibility but the wall-clock
        time used in the log is read fresh here, so log lines reflect the
        moment of arrival rather than the perf_counter time.

        If a terminal filter is active (set via :meth:`set_filter`), records
        that the on-screen view would hide are *also* skipped here — the
        log file then contains exactly what the user can see.
        """
        if self._writer is None or not data:
            return
        if self._filter_text:
            # Lazy import — keeps the core layer's import cycle simple.
            from kcom.core.filter import matches_filter
            if not matches_filter(data, direction, self._filter_text):
                return
        try:
            line = self._format_record(data, direction)
            self._writer.write(line)
            self._bytes_written += len(data)
        except Exception as e:  # never let log formatting kill the UI
            self.error_occurred.emit(f"Log format error: {e}")

    def annotate(self, text: str) -> None:
        """Write a user annotation marker to the active log file."""
        if self._writer is None or not text:
            return
        ts = datetime.now().isoformat(timespec="milliseconds")
        if self._mode == "csv":
            line = (
                f"{_csv_escape(ts)},ANNOTATION,{_csv_escape(text)}\n"
            )
        else:
            line = f"[{ts}] [ANNOTATION] {text}\n"
        self._writer.write(line)

    # ── Internals ───────────────────────────────────────────────────────

    def _csv_header(self) -> str:
        col = self._display_mode.lower()
        return f"timestamp,direction,{col}"

    def _format_record(self, data: bytes, direction: str) -> str:
        wall_time = datetime.now().isoformat(timespec="milliseconds")
        payload = _render_for_mode(data, self._display_mode)
        if self._mode == "csv":
            return (
                f"{_csv_escape(wall_time)},{direction},"
                f"{_csv_escape(payload)}\n"
            )
        return f"[{wall_time}] [{direction}] {payload}\n"


# ─── SessionLogger ───────────────────────────────────────────────────────────


class SessionLogger:
    """Global session log written to ``~/kcom-session.txt`` by default.

    Same threading model as :class:`LogManager`: pre-format on the caller's
    thread, queue to a background writer. Each new session truncates the file.
    """

    DEFAULT_FILENAME = "kcom-session.txt"

    def __init__(self, path: str | None = None) -> None:
        self._path = path or os.path.join(
            os.path.expanduser("~"), self.DEFAULT_FILENAME
        )
        self._file: IO | None = None
        self._writer: _LogWriterThread | None = None

    def __del__(self) -> None:
        """RAII safety net — make sure the writer thread + file are released
        if the SessionLogger is garbage-collected without an explicit close."""
        try:
            if self._writer is not None or self._file is not None:
                self.close()
        except Exception:
            pass

    def start_session(self, port_name: str) -> None:
        """Open (truncating) the log file and write a session header."""
        self.close()
        try:
            self._file = open(
                self._path, "w", encoding="utf-8",
                newline="", buffering=64 * 1024,
            )
            ts = datetime.now().isoformat(timespec="milliseconds")
            self._file.write(f"{'=' * 72}\n")
            self._file.write(f"# KCom session started  {ts}\n")
            self._file.write(f"# Connection: {port_name}\n")
            self._file.write(f"{'=' * 72}\n")
            self._writer = _LogWriterThread(self._file)
            self._writer.start()
        except OSError:
            self._file = None
            self._writer = None

    def set_path(self, path: str) -> None:
        """Change the target log path; reopen (truncating) if currently open."""
        was_open = self._file is not None
        if was_open:
            self.close()
        self._path = path
        if was_open:
            self.start_session("(relocated)")

    def feed(self, port_name: str, data: bytes, direction: str) -> None:
        """Write a data chunk to the session log.

        Formatting (per-byte hex + ASCII string building) is deferred onto
        the writer thread so the caller pays only the cost of an enqueue.
        At flood rates (8 KB merged chunks at 60+ Hz) this saves the UI
        thread ~500 KB/s of string churn.
        """
        if self._writer is None or not data:
            return
        ts = datetime.now().isoformat(timespec="milliseconds")
        # Defer formatting: enqueue a callable that the writer thread runs.
        self._writer.write_deferred(
            _session_log_format, (ts, port_name, direction, data)
        )

    def log_event(self, port_name: str, event: str) -> None:
        """Log a connect/disconnect/error event."""
        if self._writer is None:
            return
        ts = datetime.now().isoformat(timespec="milliseconds")
        self._writer.write(
            f"[{ts}] [{port_name:12s}] [{event}]\n"
        )

    def export(self, dest_path: str) -> bool:
        """Copy the current session log to ``dest_path``.

        Stops the writer briefly to guarantee a complete copy, then resumes.
        Returns True on success.
        """
        was_running = self._writer is not None
        port_name = "(export)"
        if was_running:
            self.close()
        try:
            shutil.copyfile(self._path, dest_path)
            ok = True
        except OSError:
            ok = False
        if was_running:
            # Reopen — but in append mode so previous content is preserved
            try:
                self._file = open(
                    self._path, "a", encoding="utf-8",
                    newline="", buffering=64 * 1024,
                )
                self._writer = _LogWriterThread(self._file)
                self._writer.start()
            except OSError:
                self._file = None
                self._writer = None
        return ok

    def close(self) -> None:
        if self._writer is not None:
            self._writer.stop()
            self._writer = None
        if self._file is not None:
            try:
                ts = datetime.now().isoformat(timespec="milliseconds")
                self._file.write(f"# KCom session ended    {ts}\n")
                self._file.flush()
                self._file.close()
            except OSError:
                pass
            self._file = None

    @property
    def path(self) -> str:
        return self._path
