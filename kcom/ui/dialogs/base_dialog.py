"""Base dialog that always centers itself over the main application window."""

from __future__ import annotations

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QShowEvent
from PyQt6.QtWidgets import QApplication, QDialog, QWidget


class CenteredDialog(QDialog):
    """A QDialog that auto-sizes to its content and centers on the parent window."""

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        # adjustSize() before show so the initial geometry is correct.
        self.adjustSize()
        # Defer the actual move to after the event loop processes the show event.
        # On X11/Wayland, calling move() synchronously inside showEvent is ignored
        # by the window manager because the window hasn't been mapped yet.
        QTimer.singleShot(0, self._center_on_parent)

    def _center_on_parent(self) -> None:
        # Walk up to the true top-level window (handles docked / embedded parents).
        ref: QWidget | None = None
        candidate = self.parent()
        while isinstance(candidate, QWidget):
            if candidate.isWindow():
                ref = candidate
                break
            candidate = candidate.parent()
        # Fall back to whichever top-level window is currently active.
        if ref is None or not ref.isVisible():
            active = QApplication.activeWindow()
            if active is not None and active is not self:
                ref = active
        if ref is None:
            return
        # Re-confirm size (layout may have finished after the timer fired).
        self.adjustSize()
        geo = self.frameGeometry()
        geo.moveCenter(ref.frameGeometry().center())
        self.move(geo.topLeft())
