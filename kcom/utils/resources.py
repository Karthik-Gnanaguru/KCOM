"""Helpers for locating bundled resource files (icons, themes)."""

from __future__ import annotations

import os

# kcom/utils/resources.py  ->  kcom/
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_RESOURCES = os.path.join(_PKG_ROOT, "resources")
# Project root (one level above the package)
_PROJECT_ROOT = os.path.dirname(_PKG_ROOT)


def resource_path(*parts: str) -> str:
    """Return an absolute path inside the kcom/resources directory."""
    return os.path.join(_RESOURCES, *parts)


def logo_path() -> str:
    """Return the path to the KCom logo, checking package then project root."""
    candidates = [
        os.path.join(_RESOURCES, "icons", "kcom_logo.png"),
        os.path.join(_PROJECT_ROOT, "kcom_logo.png"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return candidates[0]


def theme_path(theme: str) -> str:
    """Return the path to a theme QSS file (e.g. 'dark' -> dark.qss)."""
    return os.path.join(_RESOURCES, "themes", f"{theme}.qss")
