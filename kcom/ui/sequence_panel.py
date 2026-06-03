"""Send Sequences panel — per-row Send/Stop toggle buttons.

Each sequence in the list owns its own Send/Stop button (green ▶ when idle,
red ■ when transmitting). Multiple sequences can run concurrently — the
MainWindow keeps one SequenceRunner per active seq_id, and this panel just
reflects the running state via :py:meth:`set_row_running`.
"""
from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt, pyqtSignal as Signal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from kcom.models.sequence import TxSequence
from kcom.ui.dialogs.sequence_editor_dialog import SequenceEditorDialog


# Shared button styles — kept at module scope so both row + panel can reuse them.
_SEND_STYLE = (
    "QPushButton { background: #238636; color: #ffffff; font-weight: 600; "
    "border: 1px solid #2ea043; border-radius: 6px; padding: 3px 10px; }"
    "QPushButton:hover { background: #2ea043; }"
    "QPushButton:disabled { background: #21262d; color: #6e7681; border-color: #30363d; }"
)
_STOP_STYLE = (
    "QPushButton { background: #da3633; color: #ffffff; font-weight: 600; "
    "border: 1px solid #f85149; border-radius: 6px; padding: 3px 10px; }"
    "QPushButton:hover { background: #f85149; }"
)


class _SequenceRow(QWidget):
    """One row in the sequence list — color swatch + name/preview + Send/Stop."""

    send_clicked: Signal = Signal(str)   # seq_id
    stop_clicked: Signal = Signal(str)   # seq_id

    def __init__(self, seq: TxSequence, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._seq_id = seq.id
        self._running = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Name + preview stacked vertically. Both labels wrap so long names
        # and longer hex previews stay fully visible inside the panel.
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)

        self._name_label = QLabel(seq.name or "(unnamed)")
        self._name_label.setStyleSheet(
            "font-weight: 600; background: transparent;"
        )
        self._name_label.setWordWrap(True)
        text_box.addWidget(self._name_label)

        try:
            preview_text = seq.hex_preview(max_bytes=24)
        except Exception:
            preview_text = "[parse error]"
        self._preview_label = QLabel(preview_text)
        # Mid-grey reads on both themes (#1f2328 light bg, #1e1e2e dark bg).
        self._preview_label.setStyleSheet(
            "color: #7d8590; font-size: 10px; background: transparent;"
        )
        self._preview_label.setWordWrap(True)
        text_box.addWidget(self._preview_label)
        layout.addLayout(text_box, stretch=1)

        # Send / Stop button on the right
        self._btn = QPushButton("▶ Send")
        self._btn.setFixedWidth(80)
        self._btn.setStyleSheet(_SEND_STYLE)
        self._btn.setToolTip("Send this sequence")
        self._btn.clicked.connect(self._on_clicked)
        layout.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignTop)

    @property
    def seq_id(self) -> str:
        return self._seq_id

    @property
    def is_running(self) -> bool:
        return self._running

    def _on_clicked(self) -> None:
        if self._running:
            self.stop_clicked.emit(self._seq_id)
        else:
            self.send_clicked.emit(self._seq_id)

    def set_running(self, running: bool) -> None:
        self._running = running
        if running:
            self._btn.setText("■ Stop")
            self._btn.setStyleSheet(_STOP_STYLE)
            self._btn.setToolTip("Stop sending this sequence")
        else:
            self._btn.setText("▶ Send")
            self._btn.setStyleSheet(_SEND_STYLE)
            self._btn.setToolTip("Send this sequence")

    def set_button_enabled(self, enabled: bool) -> None:
        """Disable the Send button (e.g. when no port is connected).

        The Stop side of the toggle stays clickable so an in-flight sequence
        can always be stopped, even after its target port is closed.
        """
        if self._running:
            self._btn.setEnabled(True)
        else:
            self._btn.setEnabled(enabled)


class SequencePanel(QWidget):
    """Dock panel for managing and sending TX sequences.

    Signals
    -------
    send_requested(TxSequence):
        Emitted when the user clicks a row's Send button.
    stop_requested(str):
        Emitted (with seq_id) when the user clicks a row's Stop button.
    sequences_changed(list[TxSequence]):
        Emitted whenever the sequence list is modified.
    """

    send_requested: Signal = Signal(object)
    stop_requested: Signal = Signal(str)
    sequences_changed: Signal = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._sequences: list[TxSequence] = []
        self._rows: dict[str, _SequenceRow] = {}     # seq_id → row widget
        self._running_ids: set[str] = set()           # which seq_ids are mid-send
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        title = QLabel("Send Sequences")
        title.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(title)
        hint = QLabel("Double-click to edit · each row sends independently")
        hint.setStyleSheet("color: #6c7086; font-size: 10px;")
        header_layout.addWidget(hint)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Sequence list — single-select (per-row buttons drive sending now)
        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setAlternatingRowColors(True)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._list.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._list, stretch=1)

        # Add / Edit / Dup / Del toolbar (no global Send — it's per row now)
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(3)

        self._add_btn = QPushButton("＋ Add")
        self._add_btn.setToolTip("Add a new TX sequence")
        self._add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(self._add_btn)

        self._edit_btn = QPushButton("✎ Edit")
        self._edit_btn.setToolTip("Edit selected sequence")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._dup_btn = QPushButton("⧉ Dup")
        self._dup_btn.setToolTip("Duplicate selected sequence")
        self._dup_btn.setEnabled(False)
        self._dup_btn.clicked.connect(self._on_duplicate)
        btn_layout.addWidget(self._dup_btn)

        self._del_btn = QPushButton("✕ Del")
        self._del_btn.setToolTip("Delete selected sequence")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._del_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        previously_running = set(self._running_ids)
        self._list.clear()
        self._rows.clear()
        for seq in self._sequences:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, seq.id)
            row = _SequenceRow(seq)
            row.send_clicked.connect(self._on_row_send)
            row.stop_clicked.connect(self._on_row_stop)
            if seq.id in previously_running:
                row.set_running(True)
            # Reserve enough height for two wrapped lines of name + preview.
            hint = row.sizeHint()
            from PyQt6.QtCore import QSize
            item.setSizeHint(QSize(hint.width(), max(hint.height(), 56)))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._rows[seq.id] = row
        # Drop running ids that no longer exist (deleted sequences)
        self._running_ids = {sid for sid in previously_running if sid in self._rows}
        self._on_selection_changed()

    def _selected_sequence(self) -> TxSequence | None:
        items = self._list.selectedItems()
        if not items:
            return None
        seq_id = items[0].data(Qt.ItemDataRole.UserRole)
        return next((s for s in self._sequences if s.id == seq_id), None)

    def _index_of(self, seq_id: str) -> int:
        for i, s in enumerate(self._sequences):
            if s.id == seq_id:
                return i
        return -1

    # ------------------------------------------------------------------
    # Row button handlers
    # ------------------------------------------------------------------

    def _on_row_send(self, seq_id: str) -> None:
        seq = next((s for s in self._sequences if s.id == seq_id), None)
        if seq is None:
            return
        self.send_requested.emit(seq)

    def _on_row_stop(self, seq_id: str) -> None:
        self.stop_requested.emit(seq_id)

    # ------------------------------------------------------------------
    # Toolbar handlers
    # ------------------------------------------------------------------

    def _on_add(self) -> None:
        dlg = SequenceEditorDialog(parent=self)
        if dlg.exec() == SequenceEditorDialog.DialogCode.Accepted:
            seq = dlg.get_sequence()
            seq.id = str(uuid.uuid4())
            self._sequences.append(seq)
            self._refresh_list()
            self.sequences_changed.emit(list(self._sequences))

    def _on_edit(self) -> None:
        seq = self._selected_sequence()
        if seq is None:
            return
        # Don't allow edits while a sequence is mid-send — confusing state.
        if seq.id in self._running_ids:
            return
        dlg = SequenceEditorDialog(parent=self)
        dlg.set_sequence(seq)
        if dlg.exec() == SequenceEditorDialog.DialogCode.Accepted:
            updated = dlg.get_sequence()
            idx = self._index_of(seq.id)
            if idx >= 0:
                self._sequences[idx] = updated
            self._refresh_list()
            self.sequences_changed.emit(list(self._sequences))

    def _on_duplicate(self) -> None:
        seq = self._selected_sequence()
        if seq is None:
            return
        from dataclasses import replace
        copy = replace(seq, id=str(uuid.uuid4()), name=f"Copy of {seq.name}")
        self._sequences.append(copy)
        self._refresh_list()
        self.sequences_changed.emit(list(self._sequences))

    def _on_delete(self) -> None:
        seq = self._selected_sequence()
        if seq is None:
            return
        if seq.id in self._running_ids:
            return  # don't delete a sequence that's currently transmitting
        self._sequences = [s for s in self._sequences if s.id != seq.id]
        self._refresh_list()
        self.sequences_changed.emit(list(self._sequences))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_edit()

    def _on_selection_changed(self) -> None:
        seq = self._selected_sequence()
        has_selection = seq is not None
        is_running = bool(seq and seq.id in self._running_ids)
        self._edit_btn.setEnabled(has_selection and not is_running)
        self._dup_btn.setEnabled(has_selection)
        self._del_btn.setEnabled(has_selection and not is_running)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_row_running(self, seq_id: str, running: bool) -> None:
        """Toggle a single row's Send/Stop button state."""
        row = self._rows.get(seq_id)
        if row is None:
            return
        row.set_running(running)
        if running:
            self._running_ids.add(seq_id)
        else:
            self._running_ids.discard(seq_id)
        self._on_selection_changed()

    def add_sequence_preset(self, data: bytes) -> None:
        """Open sequence editor pre-filled with *data* as a hex string."""
        dlg = SequenceEditorDialog(parent=self)
        hex_str = " ".join(f"{b:02X}" for b in data)
        pre = TxSequence(name="", data_str=hex_str)
        dlg.set_sequence(pre)
        if dlg.exec() == SequenceEditorDialog.DialogCode.Accepted:
            seq = dlg.get_sequence()
            self._sequences.append(seq)
            self._refresh_list()
            self.sequences_changed.emit(list(self._sequences))

    def set_sequences(self, seqs: list[TxSequence]) -> None:
        """Replace the current list with the given sequences."""
        self._sequences = list(seqs)
        self._refresh_list()

    def get_sequences(self) -> list[TxSequence]:
        """Return a copy of the current sequence list."""
        return list(self._sequences)

    def running_sequence_ids(self) -> set[str]:
        """seq_ids of sequences currently in periodic-send mode."""
        return set(self._running_ids)
