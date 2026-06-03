"""Dialog for creating and editing RX triggers."""
from __future__ import annotations

import uuid

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from kcom.models.trigger import RxTrigger
from kcom.ui.dialogs.base_dialog import CenteredDialog


class TriggerEditorDialog(CenteredDialog):
    """Simplified editor for an RxTrigger — Name, Pattern encoding, Pattern.

    The trigger always uses ``contains`` matching with boundary buffering and
    highlights the matching row in the terminal when it fires.  Enabled state
    is controlled by the per-row Start/Stop button in the trigger panel.

    Usage::

        dlg = TriggerEditorDialog(parent=self)
        dlg.set_trigger(existing_trigger)   # optional — omit when adding
        if dlg.exec() == QDialog.DialogCode.Accepted:
            trigger = dlg.get_trigger()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trigger Editor")
        self.setMinimumWidth(440)
        self._trigger_id: str | None = None
        self._build_ui()
        self._name_edit.textChanged.connect(self._update_ok_button)
        self._pattern_edit.textChanged.connect(self._update_ok_button)
        self._update_ok_button()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setSpacing(6)
        outer.addLayout(form)

        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Error Response")
        form.addRow("Name:", self._name_edit)

        self._penc_combo = QComboBox()
        self._penc_combo.addItems(["ASCII", "Hex"])
        self._penc_combo.setCurrentIndex(0)
        form.addRow("Pattern encoding:", self._penc_combo)

        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText("Pattern to match in received data")
        form.addRow("Pattern:", self._pattern_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _update_ok_button(self) -> None:
        name_ok = bool(self._name_edit.text().strip())
        pattern_ok = bool(self._pattern_edit.text().strip())
        self._ok_button.setEnabled(name_ok and pattern_ok)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    _PENC_MAP = {0: "ascii", 1: "hex"}
    _PENC_RMAP = {"ascii": 0, "hex": 1}

    def set_sequences(self, sequences: list) -> None:
        """No-op — kept for API compatibility with TriggerPanel."""

    def set_trigger(self, t: RxTrigger) -> None:
        """Populate fields from an existing RxTrigger."""
        self._trigger_id = t.id
        self._name_edit.setText(t.name)
        self._penc_combo.setCurrentIndex(self._PENC_RMAP.get(t.pattern_encoding, 0))
        self._pattern_edit.setText(t.pattern)
        self._update_ok_button()

    def get_trigger(self) -> RxTrigger:
        """Return the configured RxTrigger. Call after Accepted."""
        return RxTrigger(
            id=self._trigger_id or str(uuid.uuid4()),
            name=self._name_edit.text().strip(),
            enabled=True,
            match_type="contains",
            pattern=self._pattern_edit.text().strip(),
            pattern_encoding=self._PENC_MAP.get(self._penc_combo.currentIndex(), "ascii"),
            action="log",
            action_data="",
            description="",
        )
