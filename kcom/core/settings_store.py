"""Centralized persistence wrapper over QSettings."""

from __future__ import annotations

import json
import os

from PyQt6.QtCore import QSettings


class SettingsStore:
    """Thin wrapper over ``QSettings("KCom", "KCom")`` for app persistence.

    Lists/dicts are stored as JSON strings so they round-trip identically
    across platforms regardless of the QSettings backend.

    Schema versioning: ``settings_version`` key is written/read so future
    releases can apply forward migrations when the stored version is older.
    """

    DEFAULT_THEME = "light"
    DEFAULT_LOG_FILENAME = "kcom-session.txt"

    #: Increment when stored keys change shape and a migration is needed.
    SETTINGS_VERSION = 2

    # Migration callables: keyed by the *source* version they handle.
    # Each callable receives ``QSettings`` and upgrades it one step.
    _MIGRATIONS: dict[int, object] = {
        # v1 → v2: render_throttle_bps was absent; default 0 is fine.
        1: lambda s: s.setValue("render_throttle_bps", s.value("render_throttle_bps", 0, type=int)),
    }

    def __init__(self) -> None:
        self._s = QSettings("KCom", "KCom")
        self._migrate()

    # ------------------------------------------------------------------
    # Schema migration
    # ------------------------------------------------------------------

    def _migrate(self) -> None:
        """Run any pending migrations up to SETTINGS_VERSION."""
        stored = self._s.value("settings_version", 1, type=int)
        version = stored
        while version < self.SETTINGS_VERSION:
            fn = self._MIGRATIONS.get(version)
            if fn:
                fn(self._s)
            version += 1
        if version != stored:
            self._s.setValue("settings_version", version)
            self._s.sync()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def get_theme(self) -> str:
        value = self._s.value("theme", self.DEFAULT_THEME, type=str)
        value = (value or "").lower()
        return value if value in ("light", "dark") else self.DEFAULT_THEME

    def set_theme(self, theme: str) -> None:
        if theme in ("light", "dark"):
            self._s.setValue("theme", theme)
            self._s.sync()

    # ------------------------------------------------------------------
    # Log path
    # ------------------------------------------------------------------

    def _default_log_path(self) -> str:
        return os.path.join(os.path.expanduser("~"), self.DEFAULT_LOG_FILENAME)

    def get_log_path(self) -> str:
        return self._s.value("log_path", self._default_log_path(), type=str) or self._default_log_path()

    def set_log_path(self, path: str) -> None:
        self._s.setValue("log_path", path)
        self._s.sync()

    # ------------------------------------------------------------------
    # Connection presets
    # ------------------------------------------------------------------

    def get_connection_presets(self) -> list[dict]:
        raw = self._s.value("connection_presets", "", type=str)
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except (ValueError, TypeError):
            pass
        return []

    def _write_presets(self, presets: list[dict]) -> None:
        self._s.setValue("connection_presets", json.dumps(presets))
        self._s.sync()

    def save_connection_preset(self, name: str, config_dict: dict) -> None:
        name = (name or "").strip()
        if not name:
            return
        entry = dict(config_dict)
        entry["preset_name"] = name
        presets = self.get_connection_presets()
        for i, p in enumerate(presets):
            if p.get("preset_name") == name:
                presets[i] = entry
                break
        else:
            presets.append(entry)
        self._write_presets(presets)

    def delete_connection_preset(self, name: str) -> None:
        name = (name or "").strip()
        presets = [p for p in self.get_connection_presets() if p.get("preset_name") != name]
        self._write_presets(presets)

    # ------------------------------------------------------------------
    # Last-used config
    # ------------------------------------------------------------------

    def get_last_config(self) -> dict | None:
        raw = self._s.value("last_config", "", type=str)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except (ValueError, TypeError):
            return None

    def set_last_config(self, config_dict: dict) -> None:
        self._s.setValue("last_config", json.dumps(config_dict))
        self._s.sync()

    # ------------------------------------------------------------------
    # Window geometry
    # ------------------------------------------------------------------

    def get_window_geometry(self) -> bytes | None:
        value = self._s.value("window_geometry", None)
        if value is None:
            return None
        try:
            if isinstance(value, (bytes, bytearray)):
                return bytes(value)
            data = bytes(value)
            return data if data else None
        except (TypeError, ValueError):
            return None

    def set_window_geometry(self, geom: bytes) -> None:
        self._s.setValue("window_geometry", bytes(geom))
        self._s.sync()

    # ------------------------------------------------------------------
    # Terminal style
    # ------------------------------------------------------------------

    def get_terminal_style(self):
        """Return a :class:`~kcom.models.terminal_style.TerminalStyle`
        built from persisted user overrides."""
        from kcom.models.terminal_style import TerminalStyle
        raw = self._s.value("terminal_style", "", type=str)
        if not raw:
            return TerminalStyle()
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return TerminalStyle.from_dict(data)
        except (ValueError, TypeError):
            pass
        return TerminalStyle()

    def set_terminal_style(self, style) -> None:
        """Persist a :class:`~kcom.models.terminal_style.TerminalStyle`."""
        self._s.setValue("terminal_style", json.dumps(style.to_dict()))
        self._s.sync()

    # ------------------------------------------------------------------
    # Advanced / Expert settings
    # ------------------------------------------------------------------

    # Valid priority names map to platform process-priority calls in main.py.
    _VALID_PRIORITIES = ("normal", "above_normal", "high", "below_normal", "idle")

    def get_process_priority(self) -> str:
        v = self._s.value("process_priority", "normal", type=str)
        return v if v in self._VALID_PRIORITIES else "normal"

    def set_process_priority(self, priority: str) -> None:
        if priority in self._VALID_PRIORITIES:
            self._s.setValue("process_priority", priority)
            self._s.sync()

    def get_render_throttle_bps(self) -> int:
        """Max bytes/s before terminal rendering is skipped; 0 = no limit."""
        return self._s.value("render_throttle_bps", 0, type=int)

    def set_render_throttle_bps(self, n: int) -> None:
        self._s.setValue("render_throttle_bps", max(0, n))
        self._s.sync()

    def get_rx_buffer_cap(self) -> int:
        """Override for DataPipeline.RING_BUFFER_SIZE; 0 = use built-in default."""
        return self._s.value("rx_buffer_cap", 0, type=int)

    def set_rx_buffer_cap(self, n: int) -> None:
        self._s.setValue("rx_buffer_cap", max(0, n))
        self._s.sync()

    # ------------------------------------------------------------------
    # HTTP/JSON API server
    # ------------------------------------------------------------------

    def get_api_enabled(self) -> bool:
        return self._s.value("api_enabled", False, type=bool)

    def set_api_enabled(self, enabled: bool) -> None:
        self._s.setValue("api_enabled", enabled)
        self._s.sync()

    def get_api_port(self) -> int:
        return self._s.value("api_port", 8765, type=int)

    def set_api_port(self, port: int) -> None:
        self._s.setValue("api_port", max(1024, min(65535, port)))
        self._s.sync()

    # ------------------------------------------------------------------
    # Mixed terminal display layers
    # ------------------------------------------------------------------

    _VALID_MIXED_LAYERS = frozenset(("hex", "ascii", "dec", "bin"))
    _DEFAULT_MIXED_LAYERS = ["hex", "ascii"]

    def get_mixed_layers(self) -> list[str]:
        """Return the ordered list of sub-formats shown in MIXED display mode.

        Valid values: ``"hex"``, ``"ascii"``, ``"dec"``, ``"bin"``.
        Defaults to ``["hex", "ascii"]`` when not set.
        """
        raw = self._s.value("mixed_layers", "", type=str)
        if not raw:
            return list(self._DEFAULT_MIXED_LAYERS)
        try:
            layers = json.loads(raw)
            if isinstance(layers, list):
                valid = [l for l in layers if l in self._VALID_MIXED_LAYERS]
                return valid if valid else list(self._DEFAULT_MIXED_LAYERS)
        except (ValueError, TypeError):
            pass
        return list(self._DEFAULT_MIXED_LAYERS)

    def set_mixed_layers(self, layers: list[str]) -> None:
        """Persist the ordered list of sub-formats for MIXED display mode."""
        valid = [l for l in layers if l in self._VALID_MIXED_LAYERS]
        self._s.setValue("mixed_layers", json.dumps(valid))
        self._s.sync()
