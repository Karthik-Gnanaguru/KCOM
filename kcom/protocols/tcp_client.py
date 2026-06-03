"""TCP Client protocol handler."""

from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QAbstractSocket, QTcpSocket

from kcom.models.port_config import PortConfig
from kcom.protocols.base_protocol import BaseProtocol

_RECONNECT_DELAY_MS = 3000


class TcpClientProtocol(BaseProtocol):
    """Connects to a remote host:port; auto-reconnects on unexpected drop."""

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._user_disconnected = False

        self._socket = QTcpSocket(self)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_connect)

        self._socket.readyRead.connect(self._on_ready_read)
        self._socket.connected.connect(self._on_socket_connected)
        self._socket.disconnected.connect(self._on_socket_disconnected)
        self._socket.errorOccurred.connect(self._on_socket_error)

    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        self._user_disconnected = False
        self._do_connect()

    def disconnect(self) -> None:  # type: ignore[override]
        self._user_disconnected = True
        self._reconnect_timer.stop()
        self._socket.abort()

    def send(self, data: bytes) -> None:
        if self.is_connected():
            self._socket.write(data)

    def is_connected(self) -> bool:
        return self._socket.state() == QAbstractSocket.SocketState.ConnectedState

    def peer_info(self) -> str:
        if self.is_connected():
            return f"{self._socket.peerAddress().toString()}:{self._socket.peerPort()}"
        return ""

    # ------------------------------------------------------------------

    def _do_connect(self) -> None:
        net = self._config.network
        self._socket.connectToHost(net.host, net.port)

    def _on_socket_connected(self) -> None:
        self.connected.emit()

    def _on_socket_disconnected(self) -> None:
        self.disconnected.emit()
        if not self._user_disconnected and self._config.auto_reconnect:
            self._reconnect_timer.start(_RECONNECT_DELAY_MS)

    def _on_socket_error(self, _err: QAbstractSocket.SocketError) -> None:
        self.error_occurred.emit("NETWORK_ERROR", f"TCP error: {self._socket.errorString()}")
        if not self._user_disconnected and self._config.auto_reconnect:
            self._reconnect_timer.start(_RECONNECT_DELAY_MS)

    def _on_ready_read(self) -> None:
        data = bytes(self._socket.readAll())
        if data:
            self.data_received.emit(data, time.time())
