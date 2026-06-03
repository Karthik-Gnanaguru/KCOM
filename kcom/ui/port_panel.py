"""Port panel — left dock widget listing all open port sessions."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer, pyqtSignal as Signal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kcom.core.port_session import ConnectionStatus


class PortPanel(QWidget):
    """Shows all open sessions with status and stats.

    Emits ``port_selected(session_id)`` when an item is clicked.
    Emits ``new_connection_requested()`` when the + button is clicked.
    Emits ``close_port_requested(session_id)`` when Close is clicked.
    """

    port_selected: Signal = Signal(str)
    new_connection_requested: Signal = Signal()
    close_port_requested: Signal = Signal(str)

    # Status → (icon_char, colour)
    _STATUS_STYLE: dict[str, tuple[str, str]] = {
        # Colors picked to be readable on BOTH the light (#f6f8fa) and dark
        # (#1e1e2e) panel backgrounds.
        ConnectionStatus.CONNECTED.value: ("●", "#1f883d"),
        ConnectionStatus.CONNECTING.value: ("◌", "#bf8700"),
        ConnectionStatus.DISCONNECTED.value: ("○", "#7d8590"),
        ConnectionStatus.ERROR.value: ("✕", "#cf222e"),
    }

    def __init__(self, session_manager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._session_manager = session_manager
        # session_id → QListWidgetItem
        self._items: dict[str, QListWidgetItem] = {}

        self._build_ui()
        self._connect_signals()

        # Refresh stats periodically
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_stats)
        self._timer.start(500)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Title label
        title = QLabel("Ports")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        layout.addWidget(title)

        # Session list
        self._list = QListWidget()
        self._list.setAlternatingRowColors(False)
        self._list.setSpacing(1)
        layout.addWidget(self._list, stretch=1)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(4)

        self._new_btn = QPushButton("+ New")
        self._new_btn.setToolTip("Open new connection")
        btn_layout.addWidget(self._new_btn)

        self._close_btn = QPushButton("Close")
        self._close_btn.setToolTip("Close selected connection")
        self._close_btn.setEnabled(False)
        btn_layout.addWidget(self._close_btn)

        layout.addLayout(btn_layout)

    def _connect_signals(self) -> None:
        self._list.currentRowChanged.connect(self._on_selection_changed)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._new_btn.clicked.connect(self.new_connection_requested)
        self._close_btn.clicked.connect(self._on_close_clicked)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_session(self, session) -> None:
        """Add a new session item to the list."""
        text = self._format_item_text(session)
        item = QListWidgetItem(text)
        item.setData(Qt.ItemDataRole.UserRole, session.session_id)
        self._list.addItem(item)
        self._items[session.session_id] = item

    def remove_session(self, session_id: str) -> None:
        """Remove a session item from the list."""
        item = self._items.pop(session_id, None)
        if item is not None:
            row = self._list.row(item)
            self._list.takeItem(row)

    def update_session_status(self, session_id: str, status: str) -> None:
        """Update the status display for a session."""
        session = self._session_manager.get_session(session_id)
        if session is None:
            return
        item = self._items.get(session_id)
        if item is None:
            return
        item.setText(self._format_item_text(session))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _format_item_text(self, session) -> str:
        status_val = session.status.value
        icon, _colour = self._STATUS_STYLE.get(status_val, ("?", "#cdd6f4"))
        name = session.config.display_name()
        rx = session.stats.bytes_rx
        tx = session.stats.bytes_tx
        return f"{icon} {name}\n   RX: {rx}  TX: {tx}"

    def _refresh_stats(self) -> None:
        for session_id, item in self._items.items():
            session = self._session_manager.get_session(session_id)
            if session is not None:
                item.setText(self._format_item_text(session))

    def _on_selection_changed(self, row: int) -> None:
        self._close_btn.setEnabled(row >= 0)
        if row >= 0:
            item = self._list.item(row)
            if item:
                session_id = item.data(Qt.ItemDataRole.UserRole)
                self.port_selected.emit(session_id)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        session_id = item.data(Qt.ItemDataRole.UserRole)
        self.port_selected.emit(session_id)

    def _on_close_clicked(self) -> None:
        item = self._list.currentItem()
        if item:
            session_id = item.data(Qt.ItemDataRole.UserRole)
            self.close_port_requested.emit(session_id)
