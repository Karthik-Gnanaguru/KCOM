"""TCP Server protocol handler."""

from __future__ import annotations

import time

from PyQt6.QtNetwork import QAbstractSocket, QHostAddress, QTcpServer, QTcpSocket

from kcom.models.port_config import PortConfig
from kcom.protocols.base_protocol import BaseProtocol


class TcpServerProtocol(BaseProtocol):
    """Listens on a local port; serves one TCP client at a time.

    ``connected`` is emitted when the server starts listening (not per-client).
    A connecting client is accepted automatically; a previous client is closed.
    """

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._server = QTcpServer(self)
        self._client: QTcpSocket | None = None
        self._server.newConnection.connect(self._on_new_connection)

    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        net = self._config.network
        host_str = (net.host or "").strip()
        if host_str and host_str not in ("0.0.0.0", ""):
            bind_addr = QHostAddress(host_str)
        else:
            bind_addr = QHostAddress(QHostAddress.SpecialAddress.AnyIPv4)

        if not self._server.listen(bind_addr, net.port):
            self.error_occurred.emit(
                "LISTEN_FAILED",
                f"TCP Server: cannot listen on port {net.port}: "
                f"{self._server.errorString()}",
            )
            return
        self.connected.emit()

    def disconnect(self) -> None:  # type: ignore[override]
        if self._client is not None:
            self._client.abort()
            self._client = None
        self._server.close()
        self.disconnected.emit()

    def send(self, data: bytes) -> None:
        if (
            self._client is not None
            and self._client.state() == QAbstractSocket.SocketState.ConnectedState
        ):
            self._client.write(data)

    def is_connected(self) -> bool:
        return self._server.isListening()

    def peer_info(self) -> str:
        if (
            self._client is not None
            and self._client.state() == QAbstractSocket.SocketState.ConnectedState
        ):
            return (
                f"{self._client.peerAddress().toString()}"
                f":{self._client.peerPort()}"
            )
        return f"listening :{self._config.network.port}"

    # ------------------------------------------------------------------

    def _on_new_connection(self) -> None:
        if self._client is not None:
            self._client.abort()
            self._client.deleteLater()

        self._client = self._server.nextPendingConnection()
        self._client.readyRead.connect(self._on_ready_read)
        self._client.disconnected.connect(self._on_client_disconnected)

    def _on_ready_read(self) -> None:
        if self._client is not None:
            data = bytes(self._client.readAll())
            if data:
                self.data_received.emit(data, time.time())

    def _on_client_disconnected(self) -> None:
        if self._client is not None:
            self._client.deleteLater()
            self._client = None
