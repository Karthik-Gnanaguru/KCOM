"""Receive Triggers panel — per-row Start/Stop matching toggle.

Each trigger has its own button that enables or disables matching for that
rule (mirroring the per-row send button in the Send Sequences panel).
Action labels and text colors come from the application palette so the panel
stays readable on both the light and dark themes.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, pyqtSignal as Signal
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

from kcom.models.trigger import RxTrigger
from kcom.ui.dialogs.trigger_editor_dialog import TriggerEditorDialog


# Matches the Send Sequence button palette so the two panels feel consistent.
_START_STYLE = (
    "QPushButton { background: #238636; color: #ffffff; font-weight: 600; "
    "border: 1px solid #2ea043; border-radius: 6px; padding: 3px 10px; }"
    "QPushButton:hover { background: #2ea043; }"
)
_STOP_STYLE = (
    "QPushButton { background: #da3633; color: #ffffff; font-weight: 600; "
    "border: 1px solid #f85149; border-radius: 6px; padding: 3px 10px; }"
    "QPushButton:hover { background: #f85149; }"
)


class _TriggerRow(QWidget):
    """One trigger entry: dot · name · action chip · sub-line + Start/Stop."""

    toggle_clicked: Signal = Signal(str)   # trig_id

    def __init__(self, trig: RxTrigger,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._trig_id = trig.id
        self._enabled = trig.enabled

        outer = QHBoxLayout(self)
        outer.setContentsMargins(6, 4, 6, 4)
        outer.setSpacing(8)

        # Color dot — the user-chosen trigger color
        try:
            QColor(trig.color)
            dot_color = trig.color
        except Exception:
            dot_color = "#8b949e"
        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {dot_color}; font-size: 14px; background: transparent;"
        )
        outer.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignTop)

        # Stacked text: name + chip line, then match summary
        text_box = QVBoxLayout()
        text_box.setContentsMargins(0, 0, 0, 0)
        text_box.setSpacing(2)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)

        self._name_label = QLabel(trig.name or "(unnamed)")
        self._name_label.setStyleSheet(
            "font-weight: 600; background: transparent;"
        )
        self._name_label.setWordWrap(True)
        top_row.addWidget(self._name_label, stretch=1)
        text_box.addLayout(top_row)

        pattern_preview = trig.pattern[:56] + ("…" if len(trig.pattern) > 56 else "")
        encoding_tag = "hex" if trig.pattern_encoding == "hex" else "ascii"
        self._sub_label = QLabel(
            f"{encoding_tag} · \"{pattern_preview}\""
        )
        self._sub_label.setStyleSheet(
            "color: #7d8590; font-size: 10px; background: transparent;"
        )
        self._sub_label.setWordWrap(True)
        text_box.addWidget(self._sub_label)
        outer.addLayout(text_box, stretch=1)

        # Start / Stop matching button on the right
        self._btn = QPushButton()
        self._btn.setFixedWidth(80)
        self._btn.clicked.connect(self._on_clicked)
        outer.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignTop)

        self._apply_button_state()

    @property
    def trig_id(self) -> str:
        return self._trig_id

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _on_clicked(self) -> None:
        self.toggle_clicked.emit(self._trig_id)

    def set_enabled_state(self, enabled: bool) -> None:
        self._enabled = enabled
        self._apply_button_state()

    def _apply_button_state(self) -> None:
        if self._enabled:
            self._btn.setText("■ Stop")
            self._btn.setStyleSheet(_STOP_STYLE)
            self._btn.setToolTip("Stop matching this trigger")
            self._dot.setStyleSheet(self._dot.styleSheet())  # full opacity
        else:
            self._btn.setText("▶ Start")
            self._btn.setStyleSheet(_START_STYLE)
            self._btn.setToolTip("Start matching this trigger")


class TriggerPanel(QWidget):
    """Dock panel for managing RX triggers / auto-responses.

    Each row has its own Start/Stop button that enables or disables matching
    for that specific trigger. Matched packets are highlighted directly in
    the terminal — there's no fire-count counter in this panel.

    Signals
    -------
    triggers_changed(list[RxTrigger]):
        Emitted whenever the trigger list is modified.
    """

    triggers_changed: Signal = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._triggers: list[RxTrigger] = []
        self._rows: dict[str, _TriggerRow] = {}
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
        title = QLabel("Receive Triggers")
        title.setStyleSheet(
            "font-weight: bold; font-size: 12px; background: transparent;"
        )
        header_layout.addWidget(title)
        hint = QLabel("Double-click to edit · matched packet highlights in terminal")
        hint.setStyleSheet(
            "color: #7d8590; font-size: 10px; background: transparent;"
        )
        header_layout.addWidget(hint)
        header_layout.addStretch()
        layout.addLayout(header_layout)

        self._list = QListWidget()
        self._list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list.setAlternatingRowColors(True)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self._list, stretch=1)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(3)

        self._add_btn = QPushButton("＋ Add")
        self._add_btn.setToolTip("Add a new RX trigger")
        self._add_btn.clicked.connect(self._on_add)
        btn_layout.addWidget(self._add_btn)

        self._edit_btn = QPushButton("✎ Edit")
        self._edit_btn.setToolTip("Edit selected trigger")
        self._edit_btn.setEnabled(False)
        self._edit_btn.clicked.connect(self._on_edit)
        btn_layout.addWidget(self._edit_btn)

        self._dup_btn = QPushButton("⧉ Dup")
        self._dup_btn.setToolTip("Duplicate selected trigger")
        self._dup_btn.setEnabled(False)
        self._dup_btn.clicked.connect(self._on_duplicate)
        btn_layout.addWidget(self._dup_btn)

        self._del_btn = QPushButton("✕ Del")
        self._del_btn.setToolTip("Delete selected trigger")
        self._del_btn.setEnabled(False)
        self._del_btn.clicked.connect(self._on_delete)
        btn_layout.addWidget(self._del_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self._list.itemSelectionChanged.connect(self._on_selection_changed)

    # ------------------------------------------------------------------
    # List management
    # ------------------------------------------------------------------

    def _refresh_list(self) -> None:
        self._list.clear()
        self._rows.clear()
        for trig in self._triggers:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, trig.id)
            row = _TriggerRow(trig)
            row.toggle_clicked.connect(self._on_row_toggle)
            hint = row.sizeHint()
            item.setSizeHint(QSize(hint.width(), max(hint.height(), 60)))
            self._list.addItem(item)
            self._list.setItemWidget(item, row)
            self._rows[trig.id] = row
        self._on_selection_changed()

    def _selected_trigger(self) -> RxTrigger | None:
        items = self._list.selectedItems()
        if not items:
            return None
        trig_id = items[0].data(Qt.ItemDataRole.UserRole)
        return next((t for t in self._triggers if t.id == trig_id), None)

    def _index_of(self, trig_id: str) -> int:
        for i, t in enumerate(self._triggers):
            if t.id == trig_id:
                return i
        return -1

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _new_editor(self) -> TriggerEditorDialog:
        return TriggerEditorDialog(parent=self)

    def _on_add(self) -> None:
        dlg = self._new_editor()
        if dlg.exec() == TriggerEditorDialog.DialogCode.Accepted:
            self._triggers.append(dlg.get_trigger())
            self._refresh_list()
            self.triggers_changed.emit(list(self._triggers))

    def _on_edit(self) -> None:
        trig = self._selected_trigger()
        if trig is None:
            return
        dlg = self._new_editor()
        dlg.set_trigger(trig)
        if dlg.exec() == TriggerEditorDialog.DialogCode.Accepted:
            updated = dlg.get_trigger()
            idx = self._index_of(trig.id)
            if idx >= 0:
                self._triggers[idx] = updated
            self._refresh_list()
            self.triggers_changed.emit(list(self._triggers))

    def _on_duplicate(self) -> None:
        trig = self._selected_trigger()
        if trig is None:
            return
        import uuid as _uuid
        from dataclasses import replace as _replace
        copy = _replace(trig, id=str(_uuid.uuid4()), name=f"Copy of {trig.name}")
        self._triggers.append(copy)
        self._refresh_list()
        self.triggers_changed.emit(list(self._triggers))

    def _on_delete(self) -> None:
        trig = self._selected_trigger()
        if trig is None:
            return
        self._triggers = [t for t in self._triggers if t.id != trig.id]
        self._refresh_list()
        self.triggers_changed.emit(list(self._triggers))

    def _on_row_toggle(self, trig_id: str) -> None:
        """Per-row Start/Stop matching button."""
        idx = self._index_of(trig_id)
        if idx < 0:
            return
        new_state = not self._triggers[idx].enabled
        self._triggers[idx].enabled = new_state
        row = self._rows.get(trig_id)
        if row is not None:
            row.set_enabled_state(new_state)
        self.triggers_changed.emit(list(self._triggers))

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        self._on_edit()

    def _on_selection_changed(self) -> None:
        has_selection = bool(self._list.selectedItems())
        self._edit_btn.setEnabled(has_selection)
        self._dup_btn.setEnabled(has_selection)
        self._del_btn.setEnabled(has_selection)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_trigger_preset(self, data: bytes) -> None:
        """Open trigger editor pre-filled with *data* as a hex pattern."""
        import uuid as _uuid
        dlg = TriggerEditorDialog(parent=self)
        prefill = RxTrigger(
            id=str(_uuid.uuid4()),
            name="",
            enabled=True,
            match_type="contains",
            pattern_encoding="hex",
            pattern=" ".join(f"{b:02X}" for b in data),
            action="log",
            action_data="",
        )
        dlg.set_trigger(prefill)
        if dlg.exec() == TriggerEditorDialog.DialogCode.Accepted:
            self._triggers.append(dlg.get_trigger())
            self._refresh_list()
            self.triggers_changed.emit(list(self._triggers))

    def set_triggers(self, triggers: list[RxTrigger]) -> None:
        """Replace the current list with the given triggers."""
        self._triggers = list(triggers)
        self._refresh_list()

    def get_triggers(self) -> list[RxTrigger]:
        """Return a copy of the current trigger list."""
        return list(self._triggers)

    def set_sequences(self, sequences: list) -> None:
        """No-op — kept for API compatibility with MainWindow."""

    def set_theme(self, is_dark: bool) -> None:
        """Kept for API compatibility with MainWindow theme toggling."""
        # Row colors are palette-driven; no per-row update needed.
        return
