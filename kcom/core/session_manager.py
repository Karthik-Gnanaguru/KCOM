"""Session manager — central registry for all open port sessions."""

from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from kcom.core.port_session import PortSession
from kcom.models.port_config import PortConfig


class SessionManager(QObject):
    """Manages the lifecycle of all active PortSession instances.

    This is the single point of truth for open connections. The MainWindow
    connects to its signals to keep the UI in sync.
    """

    session_opened: Signal = Signal(str)        # session_id
    session_closed: Signal = Signal(str)        # session_id
    session_error: Signal = Signal(str, str)    # (session_id, error_msg)
    session_status_changed: Signal = Signal(str, str)  # (session_id, status)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._sessions: dict[str, PortSession] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def open_session(self, config: PortConfig) -> str:
        """Create a new session, connect it, and return its session_id."""
        session = PortSession(config, parent=self)

        session.error_occurred.connect(self._on_session_error)
        session.status_changed.connect(self._on_status_changed)

        self._sessions[session.session_id] = session
        session.connect()  # type: ignore[call-arg]

        self.session_opened.emit(session.session_id)
        return session.session_id

    def close_session(self, session_id: str) -> None:
        """Disconnect and remove a session."""
        session = self._sessions.get(session_id)
        if session is None:
            return
        session.disconnect()  # type: ignore[call-arg]
        del self._sessions[session_id]
        self.session_closed.emit(session_id)

    def get_session(self, session_id: str) -> PortSession | None:
        return self._sessions.get(session_id)

    def all_sessions(self) -> list[PortSession]:
        return list(self._sessions.values())

    def close_all(self) -> None:
        """Close all sessions (called on app exit)."""
        for session_id in list(self._sessions.keys()):
            self.close_session(session_id)

    # ------------------------------------------------------------------
    # Private slots
    # ------------------------------------------------------------------

    def _on_session_error(self, session_id: str, msg: str) -> None:
        self.session_error.emit(session_id, msg)

    def _on_status_changed(self, session_id: str, status: str) -> None:
        self.session_status_changed.emit(session_id, status)
