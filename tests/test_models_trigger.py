"""Tests for kcom/models/trigger.py — RxTrigger."""
from __future__ import annotations

import pytest
from kcom.models.trigger import RxTrigger


class TestRxTrigger:
    def test_defaults(self):
        t = RxTrigger()
        assert t.enabled is True
        assert t.match_type == "contains"
        assert t.pattern_encoding == "ascii"
        assert t.action == "log"

    def test_get_pattern_bytes_ascii(self):
        t = RxTrigger(pattern="OK", pattern_encoding="ascii")
        assert t.get_pattern_bytes() == b"OK"

    def test_get_pattern_bytes_hex(self):
        t = RxTrigger(pattern="41 42 43", pattern_encoding="hex")
        assert t.get_pattern_bytes() == b"ABC"

    def test_get_pattern_bytes_hex_odd(self):
        t = RxTrigger(pattern="F", pattern_encoding="hex")
        assert t.get_pattern_bytes() == b"\x0F"

    def test_get_pattern_bytes_empty(self):
        t = RxTrigger(pattern="", pattern_encoding="ascii")
        assert t.get_pattern_bytes() == b""

    def test_round_trip(self):
        t = RxTrigger(
            name="On Error",
            enabled=False,
            match_type="starts_with",
            pattern="ERROR",
            pattern_encoding="ascii",
            action="notify",
            action_data="seq-123",
            color="#FF0000",
            description="Detect errors",
        )
        t2 = RxTrigger.from_dict(t.to_dict())
        assert t2.name == t.name
        assert t2.enabled == t.enabled
        assert t2.match_type == t.match_type
        assert t2.pattern == t.pattern
        assert t2.action == t.action
        assert t2.action_data == t.action_data

    def test_from_dict_defaults(self):
        t = RxTrigger.from_dict({})
        assert t.enabled is True
        assert t.match_type == "contains"

    def test_id_generated_if_missing(self):
        t = RxTrigger.from_dict({})
        assert len(t.id) == 36  # UUID format

    def test_id_preserved_in_round_trip(self):
        t = RxTrigger(name="test")
        t2 = RxTrigger.from_dict(t.to_dict())
        assert t2.id == t.id
