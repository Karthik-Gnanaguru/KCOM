"""UDP Socket protocol handler."""

from __future__ import annotations

import time

from PyQt6.QtNetwork import QHostAddress, QUdpSocket

from kcom.models.port_config import PortConfig
from kcom.protocols.base_protocol import BaseProtocol


class UdpProtocol(BaseProtocol):
    """Binds a local port and exchanges datagrams with a configured remote.

    ``connected`` is emitted after the socket is successfully bound.
    Sending writes datagrams to ``config.network.host:port``.
    ``local_port=0`` lets the OS assign an ephemeral port.
    """

    def __init__(self, config: PortConfig) -> None:
        super().__init__()
        self._config = config
        self._socket = QUdpSocket(self)
        self._last_sender: tuple[str, int] | None = None
        self._bound = False
        self._socket.readyRead.connect(self._on_ready_read)

    # ------------------------------------------------------------------

    def connect(self) -> None:  # type: ignore[override]
        net = self._config.network
        bind_port = net.local_port or 0
        if not self._socket.bind(QHostAddress.SpecialAddress.AnyIPv4, bind_port):
            self.error_occurred.emit(
                "BIND_FAILED",
                f"UDP: cannot bind on port {bind_port}: {self._socket.errorString()}",
            )
            return
        self._bound = True
        self.connected.emit()

    def disconnect(self) -> None:  # type: ignore[override]
        self._socket.close()
        self._bound = False
        self._last_sender = None
        self.disconnected.emit()

    def send(self, data: bytes) -> None:
        if self._bound:
            net = self._config.network
            self._socket.writeDatagram(data, QHostAddress(net.host), net.port)

    def is_connected(self) -> bool:
        return self._bound

    def peer_info(self) -> str:
        if self._last_sender:
            return f"{self._last_sender[0]}:{self._last_sender[1]}"
        if self._bound:
            net = self._config.network
            return f"→ {net.host}:{net.port}"
        return ""

    # ------------------------------------------------------------------

    def _on_ready_read(self) -> None:
        """Drain every pending datagram in one pass and emit a single batch.

        Emitting once per datagram used to fire the whole downstream chain
        (terminal, log, triggers, scripts, API) for each one — at UDP rates
        that's a real cost. We now concatenate every datagram available in
        the socket's buffer and emit one ``data_received`` per readyRead.
        PortSession's RX coalescer further merges across calls.
        """
        chunks: list[bytes] = []
        while self._socket.hasPendingDatagrams():
            datagram = self._socket.receiveDatagram()
            data = bytes(datagram.data())
            if data:
                self._last_sender = (
                    datagram.senderAddress().toString(),
                    datagram.senderPort(),
                )
                chunks.append(data)
        if chunks:
            merged = b"".join(chunks) if len(chunks) > 1 else chunks[0]
            self.data_received.emit(merged, time.time())
