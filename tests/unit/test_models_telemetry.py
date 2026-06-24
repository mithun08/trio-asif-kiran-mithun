from __future__ import annotations

from matcher.models.output import RunOutput
from matcher.models.telemetry import RunTelemetry


def test_cache_hit_rate_zero_when_no_calls() -> None:
    rt = RunTelemetry()
    assert rt.cache_hit_rate == 0.0


def test_cache_hit_rate_computed_correctly() -> None:
    rt = RunTelemetry(llm_calls=4, cache_hits=2)
    assert rt.cache_hit_rate == 0.5


def test_cache_hit_rate_all_hits() -> None:
    rt = RunTelemetry(llm_calls=3, cache_hits=3)
    assert rt.cache_hit_rate == 1.0


def test_telemetry_in_run_output() -> None:
    rt = RunTelemetry(llm_calls=2, total_tokens=100, total_cost_usd=0.001)
    output = RunOutput(snapshot_id="abc", role_id="ROLE-01", run_telemetry=rt)
    assert output.run_telemetry is not None
    assert output.run_telemetry.llm_calls == 2


def test_telemetry_serialises_in_run_output() -> None:
    rt = RunTelemetry(llm_calls=1, total_tokens=50)
    output = RunOutput(snapshot_id="abc", role_id="ROLE-01", run_telemetry=rt)
    json_str = output.model_dump_json()
    assert "run_telemetry" in json_str
    assert "llm_calls" in json_str
