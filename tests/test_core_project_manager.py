"""Tests for kcom/core/project_manager.py — ProjectManager."""
from __future__ import annotations

import json
import os
import zipfile
import tempfile
import pytest

from kcom.core.project_manager import ProjectManager, _migrate_project_dict
from kcom.models.project import ProjectData
from kcom.models.port_config import PortConfig, SerialConfig
from kcom.models.sequence import TxSequence
from kcom.models.trigger import RxTrigger


@pytest.fixture()
def manager(qapp):
    return ProjectManager()


@pytest.fixture()
def tmp_json(tmp_path):
    return str(tmp_path / "test.kcom")


@pytest.fixture()
def tmp_zip(tmp_path):
    return str(tmp_path / "test.kproj")


class TestSaveLoad:
    def test_save_creates_file(self, manager, tmp_json):
        p = ProjectData(name="Save Test")
        assert manager.save(tmp_json, p)
        assert os.path.exists(tmp_json)

    def test_save_returns_true_on_success(self, manager, tmp_json):
        assert manager.save(tmp_json, ProjectData()) is True

    def test_load_round_trip_json(self, manager, tmp_json):
        p = ProjectData(name="Round Trip", notes="Some notes")
        manager.save(tmp_json, p)
        p2 = manager.load(tmp_json)
        assert p2 is not None
        assert p2.name == "Round Trip"
        assert p2.notes == "Some notes"

    def test_load_preserves_sequences(self, manager, tmp_json):
        seq = TxSequence(name="Ping", data_str="01 02", encoding="hex")
        p = ProjectData(sequences=[seq])
        manager.save(tmp_json, p)
        p2 = manager.load(tmp_json)
        assert len(p2.sequences) == 1
        assert p2.sequences[0].name == "Ping"

    def test_load_preserves_port_configs(self, manager, tmp_json):
        pc = PortConfig(serial=SerialConfig(port="/dev/ttyUSB0"))
        p = ProjectData(port_configs=[pc])
        manager.save(tmp_json, p)
        p2 = manager.load(tmp_json)
        assert p2.port_configs[0].serial.port == "/dev/ttyUSB0"

    def test_load_preserves_triggers(self, manager, tmp_json):
        trig = RxTrigger(name="OnError", pattern="ERR")
        p = ProjectData(triggers=[trig])
        manager.save(tmp_json, p)
        p2 = manager.load(tmp_json)
        assert p2.triggers[0].name == "OnError"

    def test_save_emits_signal(self, manager, tmp_json):
        saved = []
        manager.project_saved.connect(lambda path: saved.append(path))
        manager.save(tmp_json, ProjectData())
        assert tmp_json in saved

    def test_load_emits_signal(self, manager, tmp_json):
        manager.save(tmp_json, ProjectData())
        loaded = []
        manager.project_loaded.connect(lambda path: loaded.append(path))
        manager.load(tmp_json)
        assert tmp_json in loaded

    def test_load_nonexistent_returns_none(self, manager):
        errors = []
        manager.error_occurred.connect(lambda msg: errors.append(msg))
        result = manager.load("/no/such/file.kcom")
        assert result is None
        assert len(errors) == 1


class TestZIPFormat:
    def test_save_kproj_is_zip(self, manager, tmp_zip):
        manager.save(tmp_zip, ProjectData())
        assert zipfile.is_zipfile(tmp_zip)

    def test_kproj_contains_manifest(self, manager, tmp_zip):
        manager.save(tmp_zip, ProjectData())
        with zipfile.ZipFile(tmp_zip) as zf:
            assert "manifest.json" in zf.namelist()

    def test_load_kproj_round_trip(self, manager, tmp_zip):
        p = ProjectData(name="ZIP Test")
        manager.save(tmp_zip, p)
        p2 = manager.load(tmp_zip)
        assert p2.name == "ZIP Test"

    def test_load_kproj_missing_manifest(self, manager, tmp_zip):
        with zipfile.ZipFile(tmp_zip, "w") as zf:
            zf.writestr("other.json", "{}")
        errors = []
        manager.error_occurred.connect(lambda m: errors.append(m))
        result = manager.load(tmp_zip)
        assert result is None
        assert len(errors) == 1


class TestRecentProjects:
    def test_save_adds_to_recent(self, manager, tmp_json):
        manager.save(tmp_json, ProjectData())
        assert tmp_json in manager.recent_projects

    def test_load_adds_to_recent(self, manager, tmp_json):
        manager.save(tmp_json, ProjectData())
        manager.clear_recent()
        manager.load(tmp_json)
        assert tmp_json in manager.recent_projects

    def test_recent_max_10(self, manager, tmp_path):
        for i in range(12):
            path = str(tmp_path / f"p{i}.kcom")
            manager.save(path, ProjectData())
        assert len(manager.recent_projects) <= 10

    def test_recent_deduplicates(self, manager, tmp_json):
        manager.save(tmp_json, ProjectData())
        manager.save(tmp_json, ProjectData())
        assert manager.recent_projects.count(tmp_json) == 1

    def test_recent_newest_first(self, manager, tmp_path):
        paths = [str(tmp_path / f"p{i}.kcom") for i in range(3)]
        for p in paths:
            manager.save(p, ProjectData())
        assert manager.recent_projects[0] == paths[-1]

    def test_clear_recent(self, manager, tmp_json):
        manager.save(tmp_json, ProjectData())
        manager.clear_recent()
        assert manager.recent_projects == []


class TestMigration:
    def test_no_migration_needed(self):
        d = {"version": "1.1", "tap_configs": [{"port_a": {}, "port_b": {}, "forward_mode": "off", "name": ""}]}
        result = _migrate_project_dict(d)
        assert result["version"] == "1.1"

    def test_v1_gets_tap_configs(self):
        d = {"version": "1.0", "name": "old"}
        result = _migrate_project_dict(d)
        assert "tap_configs" in result
        assert isinstance(result["tap_configs"], list)

    def test_version_bumped(self):
        d = {"version": "1.0"}
        result = _migrate_project_dict(d)
        assert result["version"] == "1.1"

    def test_existing_tap_configs_preserved(self):
        tap = {"port_a": {}, "port_b": {}, "forward_mode": "both", "name": "T"}
        d = {"version": "1.0", "tap_configs": [tap]}
        result = _migrate_project_dict(d)
        assert result["tap_configs"] == [tap]


class TestSaveError:
    def test_save_invalid_path_returns_false(self, manager):
        errors = []
        manager.error_occurred.connect(lambda m: errors.append(m))
        result = manager.save("/this/path/does/not/exist.kcom", ProjectData())
        assert result is False
        assert len(errors) == 1
