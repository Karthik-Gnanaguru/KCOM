"""Tests for kcom/core/settings_store.py — SettingsStore."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QSettings
from kcom.core.settings_store import SettingsStore


@pytest.fixture(autouse=True)
def isolated_settings(qapp, monkeypatch):
    """Point QSettings to an in-memory (INI) scope per test to avoid cross-test pollution."""
    from PyQt6.QtCore import QSettings
    store = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                      "KComTest", "KComTest_tmp")
    store.clear()
    store.sync()

    original_init = SettingsStore.__init__

    def patched_init(self):
        from PyQt6.QtCore import QSettings
        self._s = QSettings(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                            "KComTest", "KComTest_tmp")
        self._migrate()

    monkeypatch.setattr(SettingsStore, "__init__", patched_init)
    yield
    store.clear()
    store.sync()


class TestTheme:
    def test_default_is_light(self):
        s = SettingsStore()
        assert s.get_theme() == "light"

    def test_set_dark(self):
        s = SettingsStore()
        s.set_theme("dark")
        assert s.get_theme() == "dark"

    def test_set_light(self):
        s = SettingsStore()
        s.set_theme("dark")
        s.set_theme("light")
        assert s.get_theme() == "light"

    def test_invalid_theme_ignored(self):
        s = SettingsStore()
        s.set_theme("blue")  # invalid — should be ignored
        assert s.get_theme() == "light"


class TestLogPath:
    def test_default_contains_filename(self):
        s = SettingsStore()
        assert "kcom-session.txt" in s.get_log_path()

    def test_set_path(self):
        s = SettingsStore()
        s.set_log_path("/tmp/my-log.txt")
        assert s.get_log_path() == "/tmp/my-log.txt"


class TestConnectionPresets:
    def test_empty_by_default(self):
        s = SettingsStore()
        assert s.get_connection_presets() == []

    def test_save_and_get(self):
        s = SettingsStore()
        s.save_connection_preset("Test", {"port": "COM1", "baud": 9600})
        presets = s.get_connection_presets()
        assert len(presets) == 1
        assert presets[0]["preset_name"] == "Test"
        assert presets[0]["port"] == "COM1"

    def test_duplicate_name_updates_in_place(self):
        s = SettingsStore()
        s.save_connection_preset("Dev", {"port": "COM1"})
        s.save_connection_preset("Dev", {"port": "COM2"})
        presets = s.get_connection_presets()
        assert len(presets) == 1
        assert presets[0]["port"] == "COM2"

    def test_delete_preset(self):
        s = SettingsStore()
        s.save_connection_preset("A", {"x": 1})
        s.save_connection_preset("B", {"x": 2})
        s.delete_connection_preset("A")
        names = [p["preset_name"] for p in s.get_connection_presets()]
        assert "A" not in names
        assert "B" in names

    def test_empty_name_ignored(self):
        s = SettingsStore()
        s.save_connection_preset("", {"x": 1})
        assert s.get_connection_presets() == []

    def test_multiple_presets(self):
        s = SettingsStore()
        for i in range(5):
            s.save_connection_preset(f"p{i}", {"index": i})
        assert len(s.get_connection_presets()) == 5


class TestLastConfig:
    def test_default_none(self):
        s = SettingsStore()
        assert s.get_last_config() is None

    def test_set_and_get(self):
        s = SettingsStore()
        cfg = {"port": "COM1", "baud": 115200}
        s.set_last_config(cfg)
        result = s.get_last_config()
        assert result == cfg

    def test_round_trip_nested(self):
        s = SettingsStore()
        cfg = {"serial": {"port": "COM3", "baud": 9600}, "type": "serial"}
        s.set_last_config(cfg)
        assert s.get_last_config() == cfg


class TestWindowGeometry:
    def test_default_none(self):
        s = SettingsStore()
        assert s.get_window_geometry() is None

    def test_set_and_get(self):
        s = SettingsStore()
        geom = bytes([1, 2, 3, 4, 5])
        s.set_window_geometry(geom)
        result = s.get_window_geometry()
        assert isinstance(result, bytes)
        assert result == geom


class TestProcessPriority:
    def test_default_normal(self):
        s = SettingsStore()
        assert s.get_process_priority() == "normal"

    def test_set_valid(self):
        s = SettingsStore()
        for p in ("normal", "above_normal", "high", "below_normal", "idle"):
            s.set_process_priority(p)
            assert s.get_process_priority() == p

    def test_invalid_ignored(self):
        s = SettingsStore()
        s.set_process_priority("ultra")
        assert s.get_process_priority() == "normal"


class TestRenderThrottle:
    def test_default_zero(self):
        s = SettingsStore()
        assert s.get_render_throttle_bps() == 0

    def test_set_value(self):
        s = SettingsStore()
        s.set_render_throttle_bps(1_000_000)
        assert s.get_render_throttle_bps() == 1_000_000

    def test_negative_clamped_to_zero(self):
        s = SettingsStore()
        s.set_render_throttle_bps(-100)
        assert s.get_render_throttle_bps() == 0


class TestRxBufferCap:
    def test_default_zero(self):
        s = SettingsStore()
        assert s.get_rx_buffer_cap() == 0

    def test_set_value(self):
        s = SettingsStore()
        s.set_rx_buffer_cap(50_000)
        assert s.get_rx_buffer_cap() == 50_000

    def test_negative_clamped(self):
        s = SettingsStore()
        s.set_rx_buffer_cap(-1)
        assert s.get_rx_buffer_cap() == 0


class TestAPISettings:
    def test_api_disabled_by_default(self):
        s = SettingsStore()
        assert s.get_api_enabled() is False

    def test_set_enabled(self):
        s = SettingsStore()
        s.set_api_enabled(True)
        assert s.get_api_enabled() is True

    def test_api_port_default(self):
        s = SettingsStore()
        assert s.get_api_port() == 8765

    def test_set_api_port(self):
        s = SettingsStore()
        s.set_api_port(9000)
        assert s.get_api_port() == 9000

    def test_api_port_clamped_low(self):
        s = SettingsStore()
        s.set_api_port(80)  # below 1024
        assert s.get_api_port() == 1024

    def test_api_port_clamped_high(self):
        s = SettingsStore()
        s.set_api_port(70000)
        assert s.get_api_port() == 65535


class TestVersioning:
    def test_settings_version_written(self):
        s = SettingsStore()
        assert s._s.value("settings_version", None) is not None

    def test_version_equals_current(self):
        s = SettingsStore()
        stored = int(s._s.value("settings_version", 0, type=int))
        assert stored == SettingsStore.SETTINGS_VERSION
