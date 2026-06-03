"""F1 context-sensitive help browser dock widget."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from kcom.resources.help_content import CONTEXT_MAP, TOPIC_HTML, TOPIC_TITLES


class HelpBrowser(QDockWidget):
    """Dockable help viewer.

    Left pane: topic list.  Right pane: HTML content rendered by QTextBrowser.
    Call :meth:`show_context_help` to jump to the topic that matches the
    currently focused widget.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Help", parent)
        self.setObjectName("helpBrowser")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
            | Qt.DockWidgetArea.BottomDockWidgetArea
        )
        self._build_ui()
        # Show overview by default
        self._show_topic(TOPIC_TITLES[0])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_context_help(self, focused_widget: QWidget | None = None) -> None:
        """Show the topic most relevant to *focused_widget*, then reveal dock."""
        topic = self._resolve_topic(focused_widget)
        self._show_topic(topic)
        self.show()
        self.raise_()

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        container = QWidget()
        root = QVBoxLayout(container)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: topic list
        self._topic_list = QListWidget()
        self._topic_list.setMaximumWidth(160)
        self._topic_list.setMinimumWidth(120)
        for title in TOPIC_TITLES:
            item = QListWidgetItem(title)
            item.setData(Qt.ItemDataRole.UserRole, title)
            self._topic_list.addItem(item)
        self._topic_list.currentItemChanged.connect(self._on_topic_selected)
        splitter.addWidget(self._topic_list)

        # Right: HTML content
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(4)

        self._title_label = QLabel()
        self._title_label.setStyleSheet(
            "font-size: 13px; font-weight: bold; color: #8250df; padding: 4px;"
        )
        right_layout.addWidget(self._title_label)

        self._browser = QTextBrowser()
        self._browser.setOpenExternalLinks(True)
        self._browser.setStyleSheet(
            "background: transparent; border: none;"
        )
        right_layout.addWidget(self._browser)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter)
        self.setWidget(container)

    def _show_topic(self, title: str) -> None:
        html = TOPIC_HTML.get(title, f"<p>Topic not found: {title}</p>")
        self._browser.setHtml(html)
        self._title_label.setText(title)
        # Sync list selection without triggering re-load
        for i in range(self._topic_list.count()):
            item = self._topic_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == title:
                self._topic_list.blockSignals(True)
                self._topic_list.setCurrentItem(item)
                self._topic_list.blockSignals(False)
                break

    def _on_topic_selected(self, current: QListWidgetItem | None, _prev) -> None:
        if current is not None:
            self._show_topic(current.data(Qt.ItemDataRole.UserRole))

    @staticmethod
    def _resolve_topic(widget: QWidget | None) -> str:
        """Walk up the widget hierarchy looking for a CONTEXT_MAP hit."""
        w = widget
        while w is not None:
            class_name = type(w).__name__
            obj_name = w.objectName() or ""
            for key in (class_name, obj_name):
                if key in CONTEXT_MAP:
                    return CONTEXT_MAP[key]
            w = w.parent() if hasattr(w, "parent") else None  # type: ignore[assignment]
        return TOPIC_TITLES[0]
