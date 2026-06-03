"""Tests for kcom/core/data_pipeline.py — DataPipeline."""
from __future__ import annotations

import time
import pytest
from kcom.core.data_pipeline import DataPipeline
from kcom.utils.encoding import DisplayMode


@pytest.fixture()
def pipeline(qapp):
    return DataPipeline(session_id="test-session")


class TestFeedBasics:
    def test_empty_data_ignored(self, pipeline):
        # No exception; ring buffer untouched.
        pipeline.feed(b"", 0.0)
        assert len(pipeline._ring_buffer) == 0

    def test_buffer_grows(self, pipeline):
        for i in range(5):
            pipeline.feed(bytes([i]), float(i))
        assert len(pipeline._ring_buffer) == 5

    def test_timestamp_stored_in_buffer(self, pipeline):
        pipeline.feed(b"x", 42.0)
        chunk, ts = pipeline._ring_buffer[0]
        assert chunk == b"x"
        assert ts == 42.0


class TestDisplayMode:
    def test_set_display_mode(self, pipeline):
        pipeline.set_display_mode(DisplayMode.HEX)
        assert pipeline.display_mode == DisplayMode.HEX

    def test_mode_property_setter(self, pipeline):
        pipeline.display_mode = DisplayMode.MIXED
        assert pipeline.display_mode == DisplayMode.MIXED


class TestOverflow:
    def test_dropped_count_initial_zero(self, pipeline):
        assert pipeline.dropped_count == 0

    def test_hwm_warning_fires_at_90_percent(self, qapp):
        """Overflow warning with 0 drops fires when buffer reaches exactly HWM."""
        p = DataPipeline("hwm-session")
        warnings = []
        p.overflow_warning.connect(lambda sid, n: warnings.append((sid, n)))
        hwm = DataPipeline.HIGH_WATER_MARK
        # Need hwm+1 feeds: the warning check runs on the (hwm+1)th call
        # when len(buf)==hwm before appending.
        for i in range(hwm + 1):
            p.feed(bytes([i % 256]), float(i))
        assert len(warnings) >= 1
        # The first warning is the HWM early warning (dropped=0)
        assert warnings[0][0] == "hwm-session"
        assert warnings[0][1] == 0  # no drops yet

    def test_hwm_warning_rearmed_below_half(self, qapp):
        """HWM warning re-arms after buffer is manually cleared and _hwm_warned reset."""
        p = DataPipeline("rearm-session")
        warnings = []
        p.overflow_warning.connect(lambda sid, n: warnings.append((sid, n)))
        hwm = DataPipeline.HIGH_WATER_MARK
        # Trigger first HWM warning (needs hwm+1 feeds)
        for i in range(hwm + 1):
            p.feed(bytes([i % 256]), float(i))
        count_after_fill = len(warnings)
        assert count_after_fill >= 1
        # Simulate the buffer draining below HWM//2 and the flag re-arming
        p._ring_buffer.clear()
        p._hwm_warned = False
        # Fill to HWM again — should emit a second warning
        for i in range(hwm + 1):
            p.feed(bytes([i % 256]), float(i))
        assert len(warnings) > count_after_fill

    def test_overflow_increments_dropped_count(self, qapp):
        p = DataPipeline("drop-session")
        cap = DataPipeline.RING_BUFFER_SIZE
        # Fill to capacity
        for i in range(cap):
            p.feed(b"\x00", 0.0)
        # One more push → drop
        p.feed(b"\x01", 1.0)
        assert p.dropped_count == 1

    def test_overflow_warning_emitted_on_drop(self, qapp):
        p = DataPipeline("warn-session")
        warnings = []
        p.overflow_warning.connect(lambda sid, n: warnings.append((sid, n)))
        cap = DataPipeline.RING_BUFFER_SIZE
        for i in range(cap + 1):
            p.feed(b"\x00", float(i))
        # At least one overflow_warning with n > 0 must have been emitted
        drop_warns = [w for w in warnings if w[1] > 0]
        assert len(drop_warns) >= 1
        assert drop_warns[0][0] == "warn-session"

    def test_session_id_in_warning(self, qapp):
        sid = "my-unique-session"
        p = DataPipeline(sid)
        warnings = []
        p.overflow_warning.connect(lambda s, n: warnings.append(s))
        for i in range(DataPipeline.RING_BUFFER_SIZE + 1):
            p.feed(b"\x00", 0.0)
        assert sid in warnings
