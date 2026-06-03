"""Tests for kcom/core/trigger_engine.py — TriggerEngine."""
from __future__ import annotations

import pytest
from kcom.core.trigger_engine import TriggerEngine
from kcom.models.trigger import RxTrigger


@pytest.fixture()
def engine(qapp):
    return TriggerEngine()


def _trig(match_type="contains", pattern="OK", encoding="ascii", enabled=True):
    return RxTrigger(
        match_type=match_type,
        pattern=pattern,
        pattern_encoding=encoding,
        enabled=enabled,
        action="log",
    )


class TestSetTriggers:
    def test_set_and_get(self, engine):
        t = _trig(pattern="HELLO")
        engine.set_triggers([t])
        assert len(engine.triggers) == 1

    def test_replaces_list(self, engine):
        engine.set_triggers([_trig("contains", "A"), _trig("contains", "B")])
        engine.set_triggers([_trig("contains", "C")])
        assert len(engine.triggers) == 1

    def test_clear(self, engine):
        engine.set_triggers([_trig()])
        engine.clear()
        assert engine.triggers == []


class TestContainsMatch:
    def test_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "OK")])
        engine.feed(b"received OK response")
        assert len(fired) == 1

    def test_no_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "ERROR")])
        engine.feed(b"everything is fine")
        assert len(fired) == 0

    def test_disabled_not_fired(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "OK", enabled=False)])
        engine.feed(b"OK")
        assert len(fired) == 0

    def test_empty_pattern_skipped(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "")])
        engine.feed(b"anything")
        assert len(fired) == 0


class TestStartsWithMatch:
    def test_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("starts_with", "START")])
        engine.feed(b"START: data follows")
        assert len(fired) == 1

    def test_no_match_middle(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("starts_with", "START")])
        engine.feed(b"data START: end")
        assert len(fired) == 0


class TestEndsWithMatch:
    def test_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        # Use hex encoding so strip() doesn't eat \r\n
        engine.set_triggers([_trig("ends_with", "0D 0A", "hex")])
        engine.feed(b"response\r\n")
        assert len(fired) == 1

    def test_no_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("ends_with", "0D 0A", "hex")])
        engine.feed(b"no newline")
        assert len(fired) == 0


class TestExactMatch:
    def test_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("exact", "ACK")])
        engine.feed(b"ACK")
        assert len(fired) == 1

    def test_no_match_longer(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("exact", "ACK")])
        engine.feed(b"ACK!")
        assert len(fired) == 0

    def test_no_match_shorter(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("exact", "ACK")])
        engine.feed(b"AC")
        assert len(fired) == 0


class TestRegexMatch:
    def test_simple_pattern(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("regex", r"\d+")])
        engine.feed(b"status 42")
        assert len(fired) == 1

    def test_no_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("regex", r"\d+")])
        engine.feed(b"no digits here")
        assert len(fired) == 0

    def test_anchored_start(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("regex", r"^ERR")])
        engine.feed(b"ERR: something")
        assert len(fired) == 1

    def test_anchored_start_no_match_middle(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("regex", r"^ERR")])
        engine.feed(b"data ERR: something")
        assert len(fired) == 0


class TestHexPattern:
    def test_hex_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "01 02", "hex")])
        engine.feed(b"\x01\x02")
        assert len(fired) == 1

    def test_hex_no_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "01 02", "hex")])
        engine.feed(b"\x01\x03")
        assert len(fired) == 0


class TestCrossBoundaryMatch:
    def test_contains_across_chunks(self, engine):
        """Pattern split across two feed() calls must still fire."""
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "HELLO")])
        engine.feed(b"say HEL")
        assert len(fired) == 0
        engine.feed(b"LO world")
        assert len(fired) == 1

    def test_regex_across_chunks(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("regex", r"DONE")])
        engine.feed(b"DO")
        engine.feed(b"NE")
        assert len(fired) == 1

    def test_starts_with_not_folded(self, engine):
        """starts_with only checks new chunk, not tail."""
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("starts_with", "HELLO")])
        engine.feed(b"HEL")   # partial, no match
        engine.feed(b"LO")    # LO does not start with HELLO
        assert len(fired) == 0

    def test_contains_fires_once_per_match(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "X")])
        engine.feed(b"X")
        engine.feed(b"X")
        assert len(fired) == 2  # each chunk independently matches


class TestMultipleTriggers:
    def test_multiple_triggers_all_checked(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t.name))
        engine.set_triggers([
            RxTrigger(name="T1", match_type="contains", pattern="OK"),
            RxTrigger(name="T2", match_type="contains", pattern="ERROR"),
        ])
        engine.feed(b"OK and ERROR in one chunk")
        assert "T1" in fired
        assert "T2" in fired


class TestEmptyFeed:
    def test_empty_data_skipped(self, engine):
        fired = []
        engine.trigger_fired.connect(lambda t, b: fired.append(t))
        engine.set_triggers([_trig("contains", "X")])
        engine.feed(b"")
        assert fired == []

    def test_no_triggers_no_error(self, engine):
        engine.feed(b"data")  # should not raise
