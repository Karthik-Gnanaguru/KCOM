"""Named-pipe / Unix-domain-socket protocol handlers.

Uses ``QLocalSocket`` (client) and ``QLocalServer`` (server) from QtNetwork.
On Windows the *path* should be a Win32 named-pipe name such as
``\\\\\\\\.\\\pipe\\kcom``; on Linux/macOS it is a filesystem path to a Unix
domain socket (e.g. ``/tmp/kcom.sock``).
"""

from __future__ import annotations

import time

from PyQt6.QtCore import QTimer
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from kcom.models.port_config import PortConfig
from kcom.protocols.base_protocol import BaseProtocol

_RECONNECT_DELAY_MS = 3000


class NamedPipeClientProtocol(BaseProtocol):
    """Connects to a named-pipe / Unix socket server.

    Auto-reconnects after unexpected disconnection when ``config.auto_reconnect``
    is True (same behaviour as ``TcpClientProtocol``).
    """

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._user_disconnected = False

        self._socket = QLocalSocket(self)
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
        else:
            self.error_occurred.emit("NOT_CONNECTED", "Pipe is not connected")

    def is_connected(self) -> bool:
        return self._socket.state() == QLocalSocket.LocalSocketState.ConnectedState

    def peer_info(self) -> str:
        if self.is_connected():
            return self._config.named_pipe.path
        return ""

    # ------------------------------------------------------------------

    def _do_connect(self) -> None:
        self._socket.connectToServer(self._config.named_pipe.path)

    def _on_socket_connected(self) -> None:
        self.connected.emit()

    def _on_socket_disconnected(self) -> None:
        self.disconnected.emit()
        if not self._user_disconnected and self._config.auto_reconnect:
            self._reconnect_timer.start(_RECONNECT_DELAY_MS)

    def _on_socket_error(self, _err: QLocalSocket.LocalSocketError) -> None:
        self.error_occurred.emit(
            "CONNECT_ERROR", f"Pipe error: {self._socket.errorString()}"
        )
        if not self._user_disconnected and self._config.auto_reconnect:
            self._reconnect_timer.start(_RECONNECT_DELAY_MS)

    def _on_ready_read(self) -> None:
        data = bytes(self._socket.readAll())
        if data:
            self.data_received.emit(data, time.perf_counter())


class NamedPipeServerProtocol(BaseProtocol):
    """Listens for connections on a named-pipe / Unix socket.

    Accepts one client at a time; a new incoming connection replaces the
    previous one (same policy as ``TcpServerProtocol``).
    ``connected`` is emitted when the server starts listening.
    """

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._server = QLocalServer(self)
        self._client: QLocalSocket | None = None
        self._server.newConnection.connect(self._on_new_connection)

    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        path = self._config.named_pipe.path
        # Remove stale socket file on Unix
        QLocalServer.removeServer(path)
        if not self._server.listen(path):
            self.error_occurred.emit(
                "LISTEN_FAILED",
                f"Pipe Server: cannot listen on '{path}': {self._server.errorString()}",
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
            and self._client.state() == QLocalSocket.LocalSocketState.ConnectedState
        ):
            self._client.write(data)

    def is_connected(self) -> bool:
        return self._server.isListening()

    def peer_info(self) -> str:
        if self._client is not None and self._client.state() == QLocalSocket.LocalSocketState.ConnectedState:
            return f"(client) {self._config.named_pipe.path}"
        return f"listening {self._config.named_pipe.path}"

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
                self.data_received.emit(data, time.perf_counter())

    def _on_client_disconnected(self) -> None:
        if self._client is not None:
            self._client.deleteLater()
            self._client = None
