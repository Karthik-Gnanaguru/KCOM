"""Tests for kcom/models/project.py — ProjectData."""
from __future__ import annotations

import pytest
from kcom.models.project import ProjectData
from kcom.models.port_config import PortConfig, SerialConfig, TapConfig
from kcom.models.sequence import TxSequence
from kcom.models.trigger import RxTrigger


class TestProjectData:
    def test_defaults(self):
        p = ProjectData()
        assert p.version == "1.1"   # fresh saves now stamp the current schema version
        assert p.name == "Untitled"
        assert p.notes == ""
        assert p.port_configs == []
        assert p.sequences == []
        assert p.triggers == []
        assert p.tap_configs == []

    def test_created_is_set(self):
        p = ProjectData()
        assert p.created  # non-empty ISO string

    def test_round_trip_empty(self):
        p = ProjectData()
        p2 = ProjectData.from_dict(p.to_dict())
        assert p2.name == p.name
        assert p2.version == p.version

    def test_round_trip_with_port_config(self):
        pc = PortConfig(serial=SerialConfig(port="/dev/ttyUSB0", baud_rate=9600))
        p = ProjectData(name="Test", port_configs=[pc])
        p2 = ProjectData.from_dict(p.to_dict())
        assert len(p2.port_configs) == 1
        assert p2.port_configs[0].serial.port == "/dev/ttyUSB0"

    def test_round_trip_with_sequence(self):
        seq = TxSequence(name="Ping", data_str="01 02", encoding="hex")
        p = ProjectData(sequences=[seq])
        p2 = ProjectData.from_dict(p.to_dict())
        assert len(p2.sequences) == 1
        assert p2.sequences[0].name == "Ping"

    def test_round_trip_with_trigger(self):
        trig = RxTrigger(name="On Error", pattern="ERROR")
        p = ProjectData(triggers=[trig])
        p2 = ProjectData.from_dict(p.to_dict())
        assert len(p2.triggers) == 1
        assert p2.triggers[0].name == "On Error"

    def test_round_trip_with_tap_config(self):
        tap = TapConfig(forward_mode="both", name="Bridge")
        p = ProjectData(tap_configs=[tap])
        p2 = ProjectData.from_dict(p.to_dict())
        assert len(p2.tap_configs) == 1
        assert p2.tap_configs[0].forward_mode == "both"

    def test_from_dict_empty(self):
        p = ProjectData.from_dict({})
        assert p.name == "Untitled"
        assert p.port_configs == []
        assert p.tap_configs == []

    def test_to_dict_lists(self):
        d = ProjectData().to_dict()
        assert isinstance(d["port_configs"], list)
        assert isinstance(d["sequences"], list)
        assert isinstance(d["triggers"], list)
        assert isinstance(d["tap_configs"], list)

    def test_notes_preserved(self):
        p = ProjectData(notes="My test project")
        p2 = ProjectData.from_dict(p.to_dict())
        assert p2.notes == "My test project"
