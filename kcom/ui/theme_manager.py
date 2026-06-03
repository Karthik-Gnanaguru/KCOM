"""Theme manager — loads, applies, and persists QSS stylesheets."""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtWidgets import QApplication

from kcom.core.settings_store import SettingsStore


class ThemeManager:
    """Loads QSS themes, applies them to the QApplication, and persists choice.

    The default theme is "light". When a :class:`SettingsStore` is supplied,
    applying or toggling a theme also writes it to settings so the choice
    survives restarts.
    """

    _THEMES_DIR = Path(__file__).parent.parent / "resources" / "themes"

    DEFAULT_THEME = "light"

    def __init__(self, app: QApplication, settings: SettingsStore | None = None) -> None:
        self._app = app
        self._settings = settings
        self._current_theme: str = self.DEFAULT_THEME

    @property
    def current(self) -> str:
        return self._current_theme

    def load_saved(self) -> str:
        """Read the saved theme (default light) and apply it."""
        theme = self.DEFAULT_THEME
        if self._settings is not None:
            theme = self._settings.get_theme()
        self.apply(theme)
        return self._current_theme

    def apply(self, theme: str) -> bool:
        """Load and apply a theme stylesheet, persisting it if possible.

        Args:
            theme: Theme name without extension, e.g. "dark" or "light".

        Returns:
            True if the theme was applied, False if the file was not found.
        """
        if theme not in ("light", "dark"):
            theme = self.DEFAULT_THEME

        qss_path = self._THEMES_DIR / f"{theme}.qss"
        if not qss_path.exists():
            print(f"[ThemeManager] Theme file not found: {qss_path}")
            return False

        try:
            qss = qss_path.read_text(encoding="utf-8")
        except OSError as e:
            print(f"[ThemeManager] Failed to read theme {theme!r}: {e}")
            return False

        self._app.setStyleSheet(qss)
        self._current_theme = theme
        if self._settings is not None:
            self._settings.set_theme(theme)
        return True

    def toggle(self) -> str:
        """Switch between dark and light themes (persisting via apply).

        Returns the name of the newly applied theme.
        """
        new_theme = "light" if self._current_theme == "dark" else "dark"
        self.apply(new_theme)
        return self._current_theme

    def available_themes(self) -> list[str]:
        """Return names of all available themes."""
        if not self._THEMES_DIR.exists():
            return []
        return sorted(p.stem for p in self._THEMES_DIR.glob("*.qss"))
