"""Keyboard shortcut reference dialog — auto-generated from the QAction registry."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QKeySequence
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from kcom.ui.dialogs.base_dialog import CenteredDialog


class HotkeysDialog(CenteredDialog):
    """Read-only table of all registered keyboard shortcuts.

    Collects every ``QAction`` that has both a non-empty text and a non-empty
    shortcut from the given parent widget (typically ``MainWindow``).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumSize(560, 520)
        self.setModal(True)
        self._build_ui(parent)

    # ------------------------------------------------------------------

    def _build_ui(self, owner: QWidget | None) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        hint = QLabel(
            "All keyboard shortcuts registered in KCom.  "
            "Type in the search box to filter."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7d8590; font-size: 10px;")
        layout.addWidget(hint)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search shortcuts or actions…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._table = QTableWidget(0, 3)
        self._table.setObjectName("shortcutsTable")
        self._table.setHorizontalHeaderLabels(["Shortcut", "Action", "Menu"])
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        layout.addWidget(self._table)

        # Manual shortcuts not on QActions (terminal, find bar, etc.)
        self._static_rows: list[tuple[str, str, str]] = [
            ("Ctrl+F",          "Find / Search in terminal",        "Terminal"),
            ("Esc",             "Close find bar",                   "Terminal"),
            ("F3 / Enter",      "Find next match",                  "Terminal"),
            ("Shift+F3",        "Find previous match",              "Terminal"),
            ("Ctrl+C",          "Copy selection",                   "Terminal"),
            ("F5",              "Run script",                       "Script Panel"),
            ("Ctrl+Shift+S",    "Show / hide Script Panel",         "View"),
            ("Ctrl+Shift+T",    "New Tap Connection",               "Ports"),
            ("F1",              "Show context help",                "Help"),
        ]

        self._all_rows: list[tuple[str, str, str]] = []
        self._populate(owner)
        self._render()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _populate(self, owner: QWidget | None) -> None:
        from PyQt6.QtGui import QAction
        seen: set[str] = set()

        # Collect from QAction children of owner
        if owner is not None:
            for action in owner.findChildren(QAction):
                text = action.text().replace("&", "").strip()
                shortcut = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
                if not shortcut or not text:
                    continue
                key = (shortcut, text)
                if key in seen:
                    continue
                seen.add(key)
                # Try to find which menu the action belongs to
                menu_name = ""
                for obj in action.associatedObjects():
                    from PyQt6.QtWidgets import QMenu
                    if isinstance(obj, QMenu):
                        menu_name = obj.title().replace("&", "")
                        break
                self._all_rows.append((shortcut, text, menu_name))

        # Add static rows that aren't in QActions
        for row in self._static_rows:
            key = (row[0], row[1])
            if key not in seen:
                self._all_rows.append(row)

        # Sort: shortcuts first, then by shortcut text
        self._all_rows.sort(key=lambda r: (r[0].lower(), r[1].lower()))

    def _render(self, filter_text: str = "") -> None:
        fl = filter_text.lower()
        rows = [
            r for r in self._all_rows
            if not fl or fl in r[0].lower() or fl in r[1].lower() or fl in r[2].lower()
        ]
        self._table.setRowCount(len(rows))
        for i, (shortcut, text, menu) in enumerate(rows):
            sc_item = QTableWidgetItem(shortcut)
            sc_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            sc_item.setFont(_mono_font())
            self._table.setItem(i, 0, sc_item)
            self._table.setItem(i, 1, QTableWidgetItem(text))
            self._table.setItem(i, 2, QTableWidgetItem(menu))

    def _filter(self, text: str) -> None:
        self._render(text)


def _mono_font():
    from PyQt6.QtGui import QFont
    f = QFont("Consolas")
    f.setPointSize(9)
    return f
