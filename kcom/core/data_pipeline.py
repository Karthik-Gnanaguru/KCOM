"""Data pipeline: receives raw bytes and emits formatted display text."""

from __future__ import annotations

import collections
import time as _time

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from kcom.utils.encoding import DisplayMode, format_bytes


class DataPipeline(QObject):
    """Processes incoming raw bytes and prepares them for display.

    Flow::

        SerialReaderThread
            ↓ data_received(bytes, float)
        DataPipeline.feed()
            ↓ display_data(str, float)
        TerminalWidget

    The ring buffer keeps the last RING_BUFFER_SIZE chunks for potential
    re-rendering when the display mode changes.  When the buffer is full,
    the oldest chunk is silently dropped and ``overflow_warning`` is emitted
    (throttled to at most once per second).
    """

    #: Emits (formatted_text, timestamp) — connect to TerminalWidget in main thread
    display_data: Signal = Signal(str, float)

    #: Emitted (session_id, total_chunks_dropped) when the ring buffer overflows.
    #: Throttled: fired at most once per second while dropping is occurring.
    overflow_warning: Signal = Signal(str, int)

    RING_BUFFER_SIZE = 100_000
    # Warn once when 90 % full to give early notice before drops start.
    HIGH_WATER_MARK = int(RING_BUFFER_SIZE * 0.9)

    def __init__(self, session_id: str, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session_id = session_id
        self._ring_buffer: collections.deque[tuple[bytes, float]] = collections.deque(
            maxlen=self.RING_BUFFER_SIZE
        )
        self._display_mode = DisplayMode.ASCII
        self._dropped_count: int = 0
        self._last_overflow_emit: float = 0.0
        self._hwm_warned: bool = False

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def display_mode(self) -> DisplayMode:
        return self._display_mode

    @display_mode.setter
    def display_mode(self, mode: DisplayMode) -> None:
        self._display_mode = mode

    @property
    def dropped_count(self) -> int:
        """Total ring-buffer chunks dropped since this pipeline was created."""
        return self._dropped_count

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def feed(self, data: bytes, timestamp: float) -> None:
        """Main entry point — called from main thread via queued signal.

        Stores data in the ring buffer and tracks overflow. The
        ``display_data`` signal is intentionally NOT emitted: the
        ``TerminalTable`` widget does its own formatting and consuming
        this signal too would be duplicate work. Removing the
        ``format_bytes`` call here saves ~50–100 μs per chunk on the
        UI thread, which is the difference between smooth and choppy
        at 1000 chunks/sec.
        """
        if not data:
            return

        buf = self._ring_buffer
        n = len(buf)

        if n >= buf.maxlen:  # type: ignore[operator]
            # Oldest chunk will be silently evicted by the deque.
            self._dropped_count += 1
            now = _time.perf_counter()
            if now - self._last_overflow_emit >= 1.0:
                self._last_overflow_emit = now
                self.overflow_warning.emit(self._session_id, self._dropped_count)
        elif n >= self.HIGH_WATER_MARK and not self._hwm_warned:
            # High-water mark warning (not yet dropping).
            self._hwm_warned = True
            self.overflow_warning.emit(self._session_id, 0)
        elif n < self.HIGH_WATER_MARK // 2:
            self._hwm_warned = False

        buf.append((data, timestamp))

    def set_display_mode(self, mode: DisplayMode) -> None:
        """Change display mode. Future data will use the new format."""
        self._display_mode = mode
