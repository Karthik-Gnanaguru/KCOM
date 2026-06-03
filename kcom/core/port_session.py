"""PortSession — wraps one active communication connection."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto

from PyQt6.QtCore import QObject, QTimer, pyqtSignal as Signal

from kcom.core.data_pipeline import DataPipeline
from kcom.core.log_manager import LogManager
from kcom.core.trigger_engine import TriggerEngine
from kcom.models.port_config import ConnectionType, PortConfig
from kcom.protocols.base_protocol import BaseProtocol


# ── RX coalescing tuning ───────────────────────────────────────────────────
# Bursty serial sources (e.g. 1000 packets/sec from a microcontroller) used to
# punish KCom: every chunk fired the whole downstream chain — log, terminal
# row, trigger eval, API push, script callback. That's typically 100+ μs of
# UI-thread work per chunk, which saturates the main thread at 1 kHz.
#
# The coalescer merges consecutive RX chunks within a short window into a
# single emit. Trigger continuity is preserved by ``TriggerEngine``'s own
# tail-buffer, so split-frame matches still fire exactly once.
_RX_COALESCE_WINDOW_MS = 8       # max time to hold bytes before flushing
_RX_COALESCE_BYTES_CAP = 8 * 1024  # max bytes to hold before forced flush


class ConnectionStatus(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class SessionStats:
    bytes_rx: int = 0
    bytes_tx: int = 0
    connect_time: float = field(default_factory=time.perf_counter)
    error_count: int = 0


class PortSession(QObject):
    """Owns one connection lifecycle: protocol + pipeline + logging."""

    data_received: Signal = Signal(bytes, float)     # forwarded from protocol
    status_changed: Signal = Signal(str, str)         # (session_id, status_name)
    error_occurred: Signal = Signal(str, str)         # (session_id, error_msg)
    stats_updated: Signal = Signal(str)               # session_id
    overflow_warning: Signal = Signal(str, int)       # (session_id, chunks_dropped)

    def __init__(self, config: PortConfig, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._session_id = str(uuid.uuid4())
        self._config = config
        self._status = ConnectionStatus.DISCONNECTED
        self._stats = SessionStats()
        self._protocol: BaseProtocol | None = None

        # Sub-systems
        self._pipeline = DataPipeline(self._session_id, parent=self)
        self._log_manager = LogManager(parent=self)
        self._trigger_engine = TriggerEngine(parent=self)

        # RX coalescing buffer (see _RX_COALESCE_* above).
        # Used by _on_data_received to merge bursty chunks into a single
        # emit before the downstream chain runs.
        self._rx_buffer: list[bytes] = []
        self._rx_buffer_size: int = 0
        self._rx_first_ts: float = 0.0
        self._rx_timer = QTimer(self)
        self._rx_timer.setSingleShot(True)
        self._rx_timer.timeout.connect(self._flush_rx_buffer)

        # Connect log manager to our data stream
        self.data_received.connect(
            lambda data, ts: self._log_manager.feed(data, "RX", ts)
        )
        self._pipeline.overflow_warning.connect(self._on_overflow_warning)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def config(self) -> PortConfig:
        return self._config

    @property
    def status(self) -> ConnectionStatus:
        return self._status

    @property
    def stats(self) -> SessionStats:
        return self._stats

    @property
    def pipeline(self) -> DataPipeline:
        return self._pipeline

    @property
    def log_manager(self) -> LogManager:
        return self._log_manager

    @property
    def trigger_engine(self) -> TriggerEngine:
        return self._trigger_engine

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        """Create the protocol handler and open the connection."""
        self._set_status(ConnectionStatus.CONNECTING)
        self._protocol = self._create_protocol()

        self._protocol.data_received.connect(self._on_data_received)
        self._protocol.error_occurred.connect(self._on_protocol_error)
        self._protocol.connected.connect(self._on_connected)
        self._protocol.disconnected.connect(self._on_disconnected)

        self._protocol.connect()  # type: ignore[call-arg]

    def disconnect(self) -> None:  # type: ignore[override]
        """Close the connection and clean up all owned resources.

        RAII contract — calling ``disconnect()`` guarantees that:

        * the underlying protocol handler is closed (sockets / serial port released),
        * the background log writer thread is stopped and its file flushed/closed,
        * any in-flight sequence runner state is left to the caller (sequences
          have their own lifecycle managed by :class:`SequenceRunner`).

        It is safe to call ``disconnect()`` more than once — subsequent calls
        are no-ops.
        """
        if self._protocol is not None:
            try:
                self._protocol.disconnect()  # type: ignore[call-arg]
            except Exception:
                pass
        # Flush any buffered RX bytes so the tail of the stream isn't lost
        try:
            if self._rx_timer.isActive():
                self._rx_timer.stop()
            self._flush_rx_buffer()
        except Exception:
            pass
        if self._log_manager.is_logging:
            try:
                self._log_manager.stop_logging()
            except Exception:
                pass

    def send(self, data: bytes) -> None:
        """Send bytes. Updates TX stats."""
        if self._protocol is None or not self._protocol.is_connected():
            self.error_occurred.emit(self._session_id, "[NOT_CONNECTED] Not connected")
            return
        self._protocol.send(data)
        self._stats.bytes_tx += len(data)
        self._log_manager.feed(data, "TX", time.perf_counter())
        self.stats_updated.emit(self._session_id)

    def is_connected(self) -> bool:
        return self._status == ConnectionStatus.CONNECTED

    def peer_info(self) -> str:
        return self._protocol.peer_info() if self._protocol is not None else ""

    def send_break(self) -> None:
        """Send a serial BREAK (no-op for non-serial connections)."""
        if self._protocol is not None:
            self._protocol.send_break()

    def annotate(self, text: str) -> None:
        """Write an annotation marker to the active per-session log."""
        self._log_manager.annotate(text)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _create_protocol(self) -> BaseProtocol:
        """Factory: instantiate the right protocol from the config."""
        ct = self._config.connection_type
        if ct == ConnectionType.SERIAL:
            from kcom.protocols.serial_port import SerialProtocol
            return SerialProtocol(self._config)
        elif ct == ConnectionType.TCP_CLIENT:
            from kcom.protocols.tcp_client import TcpClientProtocol
            return TcpClientProtocol(self._config)
        elif ct == ConnectionType.TCP_SERVER:
            from kcom.protocols.tcp_server import TcpServerProtocol
            return TcpServerProtocol(self._config)
        elif ct == ConnectionType.UDP:
            from kcom.protocols.udp_socket import UdpProtocol
            return UdpProtocol(self._config)
        elif ct == ConnectionType.USB_HID:
            from kcom.protocols.usb_hid import HIDProtocol
            return HIDProtocol(self._config)
        elif ct == ConnectionType.NAMED_PIPE_CLIENT:
            from kcom.protocols.named_pipe import NamedPipeClientProtocol
            return NamedPipeClientProtocol(self._config)
        elif ct == ConnectionType.NAMED_PIPE_SERVER:
            from kcom.protocols.named_pipe import NamedPipeServerProtocol
            return NamedPipeServerProtocol(self._config)
        else:
            raise ValueError(f"Unsupported connection type: {ct}")

    def _set_status(self, status: ConnectionStatus) -> None:
        self._status = status
        self.status_changed.emit(self._session_id, status.value)

    def _on_data_received(self, data: bytes, timestamp: float) -> None:
        """Slot from the protocol — accumulate into the RX coalescer.

        Bytes are dropped into the coalescer buffer and a single timer-driven
        flush fans the merged chunk out to the rest of the system (terminal,
        log, triggers, scripts, API). This collapses the per-chunk fan-out
        cost to roughly one fan-out per :data:`_RX_COALESCE_WINDOW_MS`, which
        is the key to surviving a 1 kHz packet flood without UI freeze.
        """
        if not data:
            return
        # Stats are real-time even when coalescing — the user gets accurate
        # byte counters in the status bar.
        self._stats.bytes_rx += len(data)

        if not self._rx_buffer:
            self._rx_first_ts = timestamp
        self._rx_buffer.append(data)
        self._rx_buffer_size += len(data)

        # Force-flush when the byte cap is reached so the table doesn't grow
        # one giant row per second on very fast links.
        if self._rx_buffer_size >= _RX_COALESCE_BYTES_CAP:
            self._flush_rx_buffer()
            return

        if not self._rx_timer.isActive():
            self._rx_timer.start(_RX_COALESCE_WINDOW_MS)

    def _flush_rx_buffer(self) -> None:
        """Concatenate buffered chunks and fan them out as a single emit."""
        if not self._rx_buffer:
            return
        # Use the timestamp of the first chunk in the window — it's the
        # most accurate reflection of when the burst actually started.
        ts = self._rx_first_ts
        merged = b"".join(self._rx_buffer)
        self._rx_buffer.clear()
        self._rx_buffer_size = 0

        self.data_received.emit(merged, ts)
        self._pipeline.feed(merged, ts)
        self._trigger_engine.feed(merged)
        self.stats_updated.emit(self._session_id)

    def _on_connected(self) -> None:
        self._stats.connect_time = time.perf_counter()
        self._set_status(ConnectionStatus.CONNECTED)

    def _on_disconnected(self) -> None:
        self._set_status(ConnectionStatus.DISCONNECTED)

    def _on_protocol_error(self, code: str, msg: str) -> None:
        self._stats.error_count += 1
        self._set_status(ConnectionStatus.ERROR)
        formatted = f"[{code}] {msg}" if code else msg
        self.error_occurred.emit(self._session_id, formatted)

    def _on_overflow_warning(self, _session_id: str, dropped: int) -> None:
        self.overflow_warning.emit(self._session_id, dropped)
