"""Tests for kcom/core/sequence_runner.py — SequenceRunner."""
from __future__ import annotations

import pytest
from PyQt6.QtCore import QCoreApplication
from kcom.core.sequence_runner import SequenceRunner


@pytest.fixture()
def runner(qapp):
    r = SequenceRunner()
    yield r
    if r.is_running:
        r.stop()


def pump(ms=50):
    """Process pending Qt events for up to ms milliseconds."""
    import time
    deadline = time.monotonic() + ms / 1000
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()


class TestInitialState:
    def test_not_running(self, runner):
        assert not runner.is_running

    def test_not_paused(self, runner):
        assert not runner.is_paused

    def test_sent_zero(self, runner):
        assert runner.sent == 0


class TestSingleSend:
    def test_tick_fires_once(self, runner):
        ticks = []
        runner.tick.connect(lambda: ticks.append(1))
        finished = []
        runner.finished.connect(lambda: finished.append(1))
        runner.start(repeat_count=1, interval_ms=100)
        assert len(ticks) == 1
        assert len(finished) == 1
        assert not runner.is_running

    def test_progress_emitted(self, runner):
        progress = []
        runner.progress.connect(lambda sent, total: progress.append((sent, total)))
        runner.start(repeat_count=1, interval_ms=100)
        assert progress == [(1, 1)]


class TestMultipleSends:
    def test_finite_repeat(self, runner):
        ticks = []
        finished = []
        runner.tick.connect(lambda: ticks.append(1))
        runner.finished.connect(lambda: finished.append(1))
        runner.start(repeat_count=3, interval_ms=10)
        # First tick fires immediately; others on timer
        pump(ms=100)
        assert len(ticks) == 3
        assert len(finished) == 1
        assert not runner.is_running

    def test_sent_count_matches(self, runner):
        runner.start(repeat_count=3, interval_ms=10)
        pump(ms=100)
        assert runner.sent == 3

    def test_progress_signals(self, runner):
        progress = []
        runner.progress.connect(lambda s, t: progress.append((s, t)))
        runner.start(repeat_count=3, interval_ms=10)
        pump(ms=100)
        assert (1, 3) in progress
        assert (3, 3) in progress


class TestInfiniteRepeat:
    def test_zero_is_infinite(self, runner):
        ticks = []
        runner.tick.connect(lambda: ticks.append(1))
        runner.start(repeat_count=0, interval_ms=10)
        pump(ms=100)
        # Should have fired many times without finishing
        assert len(ticks) >= 3
        assert runner.is_running

    def test_stop_ends_infinite(self, runner):
        finished = []
        runner.finished.connect(lambda: finished.append(1))
        runner.start(repeat_count=0, interval_ms=10)
        pump(ms=30)
        runner.stop()
        assert len(finished) == 1
        assert not runner.is_running


class TestStopBehavior:
    def test_stop_emits_finished(self, runner):
        finished = []
        runner.finished.connect(lambda: finished.append(1))
        runner.start(repeat_count=0, interval_ms=50)
        runner.stop()
        assert len(finished) == 1

    def test_stop_when_not_running_no_error(self, runner):
        runner.stop()  # should not raise

    def test_stop_idempotent(self, runner):
        finished = []
        runner.finished.connect(lambda: finished.append(1))
        runner.start(repeat_count=5, interval_ms=50)
        runner.stop()
        runner.stop()
        assert len(finished) == 1  # only one finished signal


class TestPauseResume:
    def test_pause_stops_timer(self, runner):
        ticks = []
        runner.tick.connect(lambda: ticks.append(1))
        runner.start(repeat_count=0, interval_ms=10)
        pump(ms=30)
        before = len(ticks)
        runner.pause()
        assert runner.is_paused
        pump(ms=50)
        assert len(ticks) == before  # no new ticks while paused

    def test_resume_continues(self, runner):
        ticks = []
        runner.tick.connect(lambda: ticks.append(1))
        runner.start(repeat_count=0, interval_ms=10)
        pump(ms=20)
        runner.pause()
        before = len(ticks)
        runner.resume()
        assert not runner.is_paused
        pump(ms=50)
        assert len(ticks) > before

    def test_resume_when_not_paused_noop(self, runner):
        runner.start(repeat_count=0, interval_ms=50)
        runner.resume()  # should not raise
        assert not runner.is_paused


class TestRestart:
    def test_start_resets_count(self, runner):
        runner.start(repeat_count=2, interval_ms=10)
        pump(ms=50)
        runner.start(repeat_count=2, interval_ms=10)
        pump(ms=50)
        assert runner.sent == 2  # fresh start resets counter
