"""Dialog for creating and editing TX sequences."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from kcom.models.sequence import TxSequence


from kcom.ui.dialogs.base_dialog import CenteredDialog


class SequenceEditorDialog(CenteredDialog):
    """Full editor for a TxSequence.

    Usage::

        dlg = SequenceEditorDialog(parent=self)
        dlg.set_sequence(existing_seq)   # optional — populate fields
        if dlg.exec() == QDialog.DialogCode.Accepted:
            seq = dlg.get_sequence()
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sequence Editor")
        self.setMinimumWidth(520)
        self._sequence_id: str | None = None
        self._build_ui()
        self._connect_signals()
        self._update_preview()
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

        # Name
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Read Register 0x01")
        form.addRow("Name:", self._name_edit)

        # Description
        self._desc_edit = QLineEdit()
        self._desc_edit.setPlaceholderText("Optional description")
        form.addRow("Description:", self._desc_edit)

        # Encoding
        self._encoding_combo = QComboBox()
        self._encoding_combo.addItems(["Hex", "ASCII", "Dec", "Bin"])
        self._encoding_combo.setCurrentIndex(0)
        form.addRow("Encoding:", self._encoding_combo)

        # Data
        self._data_edit = QPlainTextEdit()
        self._data_edit.setPlaceholderText(
            "Hex: 01 03 00 00 00 02\n"
            "ASCII: Hello\\r\\n\n"
            "Dec: 1 3 0 0 0 2\n"
            "Bin: 00000001 00000011"
        )
        self._data_edit.setMinimumHeight(80)
        form.addRow("Data:", self._data_edit)

        # Terminator
        self._term_combo = QComboBox()
        self._term_combo.addItems(["None", "CR  (\\r)", "LF  (\\n)", "CR+LF (\\r\\n)"])
        self._term_combo.setCurrentIndex(0)
        form.addRow("Terminator:", self._term_combo)

        # Checksum
        self._cs_combo = QComboBox()
        self._cs_combo.addItems(["None", "XOR", "Sum8", "CRC-8", "CRC-16 Modbus", "CRC-32"])
        self._cs_combo.setCurrentIndex(0)
        form.addRow("Checksum:", self._cs_combo)

        # Checksum start offset
        self._cs_start_spin = QSpinBox()
        self._cs_start_spin.setRange(0, 4096)
        self._cs_start_spin.setValue(0)
        self._cs_start_spin.setToolTip("Byte offset to start checksum calculation (0 = from start)")
        form.addRow("Checksum start:", self._cs_start_spin)

        # Repeat count
        self._repeat_spin = QSpinBox()
        self._repeat_spin.setRange(0, 1_000_000)
        self._repeat_spin.setValue(0)  # default: continuous (until stopped)
        self._repeat_spin.setSpecialValueText("∞ (continuous)")
        self._repeat_spin.setToolTip(
            "Number of times to send. 0 = repeat continuously until you press Stop."
        )
        form.addRow("Repeat count:", self._repeat_spin)

        # Repeat interval
        self._interval_spin = QSpinBox()
        self._interval_spin.setRange(0, 3_600_000)
        self._interval_spin.setSuffix(" ms")
        self._interval_spin.setValue(1000)  # default: 1 second between sends
        self._interval_spin.setToolTip("Delay between repeated sends (default 1000 ms)")
        form.addRow("Repeat interval:", self._interval_spin)

        # Delay before
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(0, 60000)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.setValue(0)
        self._delay_spin.setToolTip("Delay before the first send")
        form.addRow("Delay before:", self._delay_spin)

        # Preview section
        preview_label = QLabel("Bytes to send:")
        preview_label.setStyleSheet("font-weight: bold; margin-top: 6px;")
        outer.addWidget(preview_label)

        self._preview_edit = QLineEdit()
        self._preview_edit.setReadOnly(True)
        self._preview_edit.setPlaceholderText("(preview will appear here)")
        self._preview_edit.setStyleSheet(
            "font-family: monospace; background: #1e1e2e; color: #a6e3a1; "
            "border: 1px solid #45475a; border-radius: 4px; padding: 4px;"
        )
        outer.addWidget(self._preview_edit)

        # OK / Cancel
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        self._ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        outer.addWidget(buttons)

    # ------------------------------------------------------------------
    # Signal connections
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._name_edit.textChanged.connect(self._update_ok_button)
        self._data_edit.textChanged.connect(self._update_preview)
        self._encoding_combo.currentIndexChanged.connect(self._update_preview)
        self._term_combo.currentIndexChanged.connect(self._update_preview)
        self._cs_combo.currentIndexChanged.connect(self._update_preview)
        self._cs_start_spin.valueChanged.connect(self._update_preview)

    # ------------------------------------------------------------------
    # Preview and validation
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        seq = self._build_sequence_from_fields()
        try:
            raw = seq.get_bytes()
            if not raw:
                self._preview_edit.setText("(empty)")
                self._preview_edit.setStyleSheet(
                    "font-family: monospace; background: #1e1e2e; color: #6c7086; "
                    "border: 1px solid #45475a; border-radius: 4px; padding: 4px;"
                )
                return
            hex_str = " ".join(f"{b:02X}" for b in raw[:32])
            if len(raw) > 32:
                hex_str += f"  … ({len(raw)} bytes total)"
            else:
                hex_str += f"  ({len(raw)} byte{'s' if len(raw) != 1 else ''})"
            self._preview_edit.setText(hex_str)
            self._preview_edit.setStyleSheet(
                "font-family: monospace; background: #1e1e2e; color: #a6e3a1; "
                "border: 1px solid #45475a; border-radius: 4px; padding: 4px;"
            )
        except Exception as exc:
            self._preview_edit.setText(f"[parse error: {exc}]")
            self._preview_edit.setStyleSheet(
                "font-family: monospace; background: #1e1e2e; color: #f38ba8; "
                "border: 1px solid #f38ba8; border-radius: 4px; padding: 4px;"
            )

    def _update_ok_button(self) -> None:
        self._ok_button.setEnabled(bool(self._name_edit.text().strip()))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    _ENCODING_MAP = {0: "hex", 1: "ascii", 2: "dec", 3: "bin"}
    _ENCODING_RMAP = {"hex": 0, "ascii": 1, "dec": 2, "bin": 3}
    _TERM_MAP = {0: "none", 1: "cr", 2: "lf", 3: "crlf"}
    _TERM_RMAP = {"none": 0, "cr": 1, "lf": 2, "crlf": 3}
    _CS_MAP = {0: "none", 1: "xor", 2: "sum8", 3: "crc8", 4: "crc16_modbus", 5: "crc32"}
    _CS_RMAP = {"none": 0, "xor": 1, "sum8": 2, "crc8": 3, "crc16_modbus": 4, "crc32": 5}

    def _build_sequence_from_fields(self) -> TxSequence:
        seq = TxSequence(
            id=self._sequence_id or "",
            name=self._name_edit.text().strip(),
            data_str=self._data_edit.toPlainText(),
            encoding=self._ENCODING_MAP.get(self._encoding_combo.currentIndex(), "hex"),
            terminator=self._TERM_MAP.get(self._term_combo.currentIndex(), "none"),
            checksum=self._CS_MAP.get(self._cs_combo.currentIndex(), "none"),
            checksum_start=self._cs_start_spin.value(),
            repeat_count=self._repeat_spin.value(),
            repeat_interval_ms=self._interval_spin.value(),
            delay_before_ms=self._delay_spin.value(),
            description=self._desc_edit.text().strip(),
        )
        return seq

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_sequence(self, seq: TxSequence) -> None:
        """Populate all fields from an existing TxSequence."""
        self._sequence_id = seq.id
        self._name_edit.setText(seq.name)
        self._desc_edit.setText(seq.description)
        self._data_edit.setPlainText(seq.data_str)
        self._encoding_combo.setCurrentIndex(self._ENCODING_RMAP.get(seq.encoding, 0))
        self._term_combo.setCurrentIndex(self._TERM_RMAP.get(seq.terminator, 0))
        self._cs_combo.setCurrentIndex(self._CS_RMAP.get(seq.checksum, 0))
        self._cs_start_spin.setValue(seq.checksum_start)
        self._repeat_spin.setValue(seq.repeat_count)
        self._interval_spin.setValue(seq.repeat_interval_ms)
        self._delay_spin.setValue(seq.delay_before_ms)
        self._update_preview()
        self._update_ok_button()

    def get_sequence(self) -> TxSequence:
        """Return the configured TxSequence. Call after Accepted."""
        seq = self._build_sequence_from_fields()
        if self._sequence_id:
            seq.id = self._sequence_id
        return seq
