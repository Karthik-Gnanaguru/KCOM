"""Abstract base class for all communication protocol handlers."""

from __future__ import annotations

from abc import abstractmethod

from PyQt6.QtCore import QObject, pyqtSignal as Signal


class BaseProtocol(QObject):
    """Abstract base for serial, TCP, UDP protocol handlers.

    All implementations must:
    - Emit ``data_received`` with (bytes, float timestamp) from a worker thread.
    - Emit ``error_occurred`` with a human-readable message on errors.
    - Emit ``connected`` / ``disconnected`` at state transitions.
    - Never call Qt UI functions from non-main threads.
    """

    # Emitted from reader thread — connect with Qt.ConnectionType.QueuedConnection
    data_received: Signal = Signal(bytes, float)
    # (error_code, human_readable_message) — see protocol implementations for codes
    error_occurred: Signal = Signal(str, str)
    connected: Signal = Signal()
    disconnected: Signal = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

    @abstractmethod
    def connect(self) -> None:  # type: ignore[override]
        """Open the connection."""
        ...

    @abstractmethod
    def disconnect(self) -> None:  # type: ignore[override]
        """Close the connection."""
        ...

    @abstractmethod
    def send(self, data: bytes) -> None:
        """Send raw bytes."""
        ...

    @abstractmethod
    def is_connected(self) -> bool:
        """Return True if the connection is currently open."""
        ...

    def peer_info(self) -> str:
        """Return a human-readable remote endpoint string, or '' if unknown."""
        return ""

    def send_break(self) -> None:
        """Send a serial BREAK condition (no-op for non-serial protocols)."""
