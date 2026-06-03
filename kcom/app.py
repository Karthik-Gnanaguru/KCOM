"""KComApp — QApplication subclass with splash screen and theme management."""

from __future__ import annotations

import sys

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QSplashScreen

from kcom.core.settings_store import SettingsStore
from kcom.ui.theme_manager import ThemeManager
from kcom.utils.resources import logo_path


class KComApp(QApplication):
    """Application root object.

    Responsibilities:
    - Set up application metadata (name, version, organization)
    - Create and manage the ThemeManager
    - Show a splash screen during startup
    """

    APP_NAME = "KCom"
    APP_VERSION = "1.0.0"
    ORG_NAME = "KCom"

    def __init__(self) -> None:
        super().__init__(sys.argv)
        self.setApplicationName(self.APP_NAME)
        self.setApplicationVersion(self.APP_VERSION)
        self.setOrganizationName(self.ORG_NAME)

        # Application-wide icon (taskbar, window, dialogs)
        self._app_icon = QIcon(logo_path())
        self.setWindowIcon(self._app_icon)

        # High-DPI is always enabled in Qt6 — no attribute needed

        # Persistence + theme manager (default light, restored from settings)
        self.settings = SettingsStore()
        self.theme_manager = ThemeManager(self, self.settings)
        self.theme_manager.load_saved()

        self._splash: QSplashScreen | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_splash(self) -> QSplashScreen:
        """Show a dark splash screen with KCom branding.

        Returns the splash instance so the caller can call finish() on it.
        """
        pixmap = self._make_splash_pixmap()
        splash = QSplashScreen(pixmap)
        splash.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint)
        splash.show()
        self.processEvents()
        self._splash = splash
        return splash

    def hide_splash(self) -> None:
        if self._splash is not None:
            self._splash.close()
            self._splash = None

    def apply_theme(self, theme_name: str) -> None:
        """Apply a named theme."""
        self.theme_manager.apply(theme_name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _make_splash_pixmap(self) -> QPixmap:
        """Draw a branded splash screen pixmap featuring the KCom logo."""
        w, h = 520, 320
        pixmap = QPixmap(w, h)
        pixmap.fill(QColor("#11111b"))

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Accent border
        painter.setPen(QColor("#89b4fa"))
        painter.drawRect(2, 2, w - 5, h - 5)

        # Logo, centred near the top
        logo = QPixmap(logo_path())
        if not logo.isNull():
            logo = logo.scaled(
                150, 150,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap((w - logo.width()) // 2, 28, logo)

        # Title under the logo
        title_font = QFont("Segoe UI", 30, QFont.Weight.Bold)
        painter.setFont(title_font)
        painter.setPen(QColor("#89b4fa"))
        painter.drawText(
            0, 180, w, 48,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
            "KCom",
        )

        # Subtitle
        sub_font = QFont("Segoe UI", 12)
        painter.setFont(sub_font)
        painter.setPen(QColor("#bac2de"))
        painter.drawText(
            0, 228, w, 28,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Serial & Network Communication Studio"
        )

        # Version
        ver_font = QFont("Segoe UI", 10)
        painter.setFont(ver_font)
        painter.setPen(QColor("#6c7086"))
        painter.drawText(
            0, h - 50, w, 24,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"v{self.APP_VERSION}"
        )

        # Loading text
        painter.setPen(QColor("#a6e3a1"))
        painter.drawText(
            0, h - 28, w, 22,
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "Loading…"
        )

        painter.end()
        return pixmap
