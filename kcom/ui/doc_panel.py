"""Project documentation / pinouts panel."""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal as Signal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class DocPanel(QWidget):
    """Collapsible documentation area with a lock/edit toggle.

    Signals
    -------
    changed(str):
        Emitted whenever the document text changes (while editable).
    """

    changed: Signal = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locked = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        header = QLabel("Project Documentation & Pinouts")
        header.setObjectName("sectionHeader")
        header_row.addWidget(header)
        header_row.addStretch()

        self._lock_btn = QPushButton("🔒 Locked")
        self._lock_btn.setObjectName("lockBtn")
        self._lock_btn.clicked.connect(self._toggle_lock)
        header_row.addWidget(self._lock_btn)

        root.addLayout(header_row)

        self._doc_area = QTextEdit()
        self._doc_area.setObjectName("docArea")
        self._doc_area.setReadOnly(True)
        self._doc_area.setPlaceholderText(
            "Click Edit to add project documentation, pinouts, notes…"
        )
        self._doc_area.textChanged.connect(self._on_text_changed)
        root.addWidget(self._doc_area, stretch=1)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def text(self) -> str:
        return self._doc_area.toPlainText()

    def set_text(self, s: str) -> None:
        self._doc_area.setPlainText(s or "")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _toggle_lock(self) -> None:
        self._locked = not self._locked
        self._doc_area.setReadOnly(self._locked)
        if self._locked:
            self._lock_btn.setText("🔒 Locked")
        else:
            self._lock_btn.setText("🔓 Edit")
            self._doc_area.setFocus()

    def _on_text_changed(self) -> None:
        if not self._locked:
            self.changed.emit(self._doc_area.toPlainText())
