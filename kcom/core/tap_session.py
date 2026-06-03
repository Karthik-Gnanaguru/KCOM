"""TapSession — passively monitors (and optionally bridges) two ports.

Two ``PortSession`` instances (A and B) share a single combined terminal.
Each incoming packet is tagged with its originating channel ("A" or "B") and
emitted via ``data_received``.  When a forward mode is active, data arriving
on one port is automatically re-sent on the other.
"""

from __future__ import annotations

import uuid

from PyQt6.QtCore import QObject, pyqtSignal as Signal

from kcom.core.port_session import PortSession
from kcom.models.port_config import TapConfig


class TapSession(QObject):
    """Owns two PortSessions and a combined data stream.

    Signals
    -------
    data_received(data, timestamp, channel)
        Raw bytes from one port.  ``channel`` is ``"A"`` or ``"B"``.
    status_changed(session_id, status_text)
        One of the inner sessions changed state; ``status_text`` is prefixed
        with ``"A:"`` or ``"B:"``.
    error_occurred(session_id, message)
        Error from one of the inner sessions; message prefixed with ``"[A]"``
        or ``"[B]"``.
    stats_updated(session_id)
        Forwarded whenever either inner session updates its stats.
    """

    data_received: Signal = Signal(bytes, float, str)   # (data, ts, channel)
    status_changed: Signal = Signal(str, str)            # (session_id, status)
    error_occurred: Signal = Signal(str, str)            # (session_id, msg)
    stats_updated:  Signal = Signal(str)                 # session_id

    _FORWARD_MODES = frozenset(("off", "a_to_b", "b_to_a", "both"))

    def __init__(self, config: TapConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session_id = str(uuid.uuid4())
        self._config = config
        self._forward_mode = config.forward_mode if config.forward_mode in self._FORWARD_MODES else "off"

        self._session_a = PortSession(config.port_a, parent=self)
        self._session_b = PortSession(config.port_b, parent=self)

        # Wire inner sessions
        self._session_a.data_received.connect(self._on_a_received)
        self._session_b.data_received.connect(self._on_b_received)

        self._session_a.status_changed.connect(
            lambda _sid, s: self.status_changed.emit(self._session_id, f"A:{s}")
        )
        self._session_b.status_changed.connect(
            lambda _sid, s: self.status_changed.emit(self._session_id, f"B:{s}")
        )
        self._session_a.error_occurred.connect(
            lambda _sid, msg: self.error_occurred.emit(self._session_id, f"[A] {msg}")
        )
        self._session_b.error_occurred.connect(
            lambda _sid, msg: self.error_occurred.emit(self._session_id, f"[B] {msg}")
        )
        self._session_a.stats_updated.connect(
            lambda _sid: self.stats_updated.emit(self._session_id)
        )
        self._session_b.stats_updated.connect(
            lambda _sid: self.stats_updated.emit(self._session_id)
        )

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def config(self) -> TapConfig:
        return self._config

    @property
    def session_a(self) -> PortSession:
        return self._session_a

    @property
    def session_b(self) -> PortSession:
        return self._session_b

    @property
    def forward_mode(self) -> str:
        return self._forward_mode

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open both underlying port connections."""
        self._session_a.connect()  # type: ignore[call-arg]
        self._session_b.connect()  # type: ignore[call-arg]

    def disconnect(self) -> None:
        """Close both underlying port connections."""
        self._session_a.disconnect()  # type: ignore[call-arg]
        self._session_b.disconnect()  # type: ignore[call-arg]

    def is_connected(self) -> bool:
        return self._session_a.is_connected() or self._session_b.is_connected()

    def set_forward_mode(self, mode: str) -> None:
        """Change forwarding at runtime.

        ``mode`` must be one of ``"off"``, ``"a_to_b"``, ``"b_to_a"``, ``"both"``.
        """
        if mode in self._FORWARD_MODES:
            self._forward_mode = mode

    # ------------------------------------------------------------------
    # Internal RX handlers
    # ------------------------------------------------------------------

    def _on_a_received(self, data: bytes, ts: float) -> None:
        self.data_received.emit(data, ts, "A")
        if self._forward_mode in ("a_to_b", "both") and self._session_b.is_connected():
            self._session_b.send(data)

    def _on_b_received(self, data: bytes, ts: float) -> None:
        self.data_received.emit(data, ts, "B")
        if self._forward_mode in ("b_to_a", "both") and self._session_a.is_connected():
            self._session_a.send(data)
