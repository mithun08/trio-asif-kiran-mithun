from __future__ import annotations

import time

import pytest

from matcher.models.telemetry import RunTelemetry
from matcher.observability.timing import stage_timer


def test_stage_timer_populates_telemetry() -> None:
    tel = RunTelemetry()
    with stage_timer("test_stage", tel):
        time.sleep(0.01)
    assert "test_stage" in tel.stage_timings_ms
    assert tel.stage_timings_ms["test_stage"] >= 0.0


def test_stage_timer_elapsed_reasonable() -> None:
    tel = RunTelemetry()
    with stage_timer("quick_stage", tel):
        pass
    assert tel.stage_timings_ms["quick_stage"] >= 0.0
    assert tel.stage_timings_ms["quick_stage"] < 5000.0


def test_stage_timer_multiple_stages() -> None:
    tel = RunTelemetry()
    with stage_timer("stage_a", tel):
        pass
    with stage_timer("stage_b", tel):
        pass
    assert "stage_a" in tel.stage_timings_ms
    assert "stage_b" in tel.stage_timings_ms


def test_stage_timer_calls_log_stage_timing(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, float]] = []

    def _mock_log(stage: str, elapsed_ms: float) -> None:
        calls.append((stage, elapsed_ms))

    monkeypatch.setattr("matcher.observability.timing.log_stage_timing", _mock_log)

    tel = RunTelemetry()
    with stage_timer("logged_stage", tel):
        pass

    assert len(calls) == 1
    assert calls[0][0] == "logged_stage"


def test_stage_timer_without_telemetry_does_not_raise() -> None:
    with stage_timer("no_tel"):
        pass
