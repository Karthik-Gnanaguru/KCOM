"""Periodic sequence sender driven by a QTimer.

Sends a payload ``repeat_count`` times spaced ``interval_ms`` apart. A
``repeat_count`` of 0 means "repeat forever until stopped". The runner does not
know about ports or data — it only emits :pyattr:`tick` whenever a send should
happen, leaving the actual transmission to the owner.
"""

from __future__ import annotations

from PyQt6.QtCore import QObject, QTimer, pyqtSignal as Signal


class SequenceRunner(QObject):
    """Drives repeated sends with a configurable interval.

    Signals
    -------
    tick():
        Emitted once per scheduled send (including the immediate first send).
    progress(int, int):
        (sent_so_far, total). ``total == 0`` indicates infinite repeat.
    finished():
        Emitted when the configured count is reached or :meth:`stop` is called.
    """

    tick: Signal = Signal()
    progress: Signal = Signal(int, int)
    finished: Signal = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_timeout)
        self._sent = 0
        self._total = 0          # 0 == infinite
        self._interval_ms = 100
        self._running = False
        self._paused = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def sent(self) -> int:
        return self._sent

    def start(self, repeat_count: int, interval_ms: int) -> None:
        """Begin sending. Fires the first tick immediately, then on the timer.

        Args:
            repeat_count: Total sends; 0 (or negative) repeats until stopped.
            interval_ms:  Delay between sends in milliseconds.
        """
        self.stop()
        self._total = repeat_count if repeat_count > 0 else 0
        self._interval_ms = max(1, interval_ms)
        self._sent = 0
        self._running = True
        self._paused = False

        # First send happens straight away.
        self._fire()

        # A single send needs no timer.
        if self._total == 1:
            self.stop()
            return

        self._timer.start(self._interval_ms)

    def pause(self) -> None:
        """Suspend the timer without resetting state.  Call :meth:`resume` to continue."""
        if self._running and not self._paused and self._timer.isActive():
            self._timer.stop()
            self._paused = True

    def resume(self) -> None:
        """Resume a paused runner.  No-op if not paused."""
        if self._running and self._paused:
            self._paused = False
            self._timer.start(self._interval_ms)

    def _on_timeout(self) -> None:
        if not self._running:
            return
        # Stop if we've already hit the target (finite case).
        if self._total > 0 and self._sent >= self._total:
            self.stop()
            return
        self._fire()
        if self._total > 0 and self._sent >= self._total:
            self.stop()

    def _fire(self) -> None:
        self._sent += 1
        self.tick.emit()
        self.progress.emit(self._sent, self._total)

    def stop(self) -> None:
        """Stop sending and emit :pyattr:`finished` (if it was running)."""
        if self._timer.isActive():
            self._timer.stop()
        self._paused = False
        if self._running:
            self._running = False
            self.finished.emit()
