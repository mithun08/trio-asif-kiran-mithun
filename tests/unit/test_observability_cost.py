from __future__ import annotations

import warnings

import pytest

from matcher.observability import telemetry as _tel
from matcher.observability.cost_table import _load_table, _warned_models, cost_for


@pytest.fixture(autouse=True)
def reset_telemetry() -> None:
    _tel.reset()
    _warned_models.clear()
    _load_table.cache_clear()


def test_cost_for_known_model() -> None:
    cost = cost_for("openai/gpt-4o-mini", 1_000_000, 0)
    assert abs(cost - 0.15) < 1e-6


def test_cost_for_completion_tokens() -> None:
    cost = cost_for("openai/gpt-4o-mini", 0, 1_000_000)
    assert abs(cost - 0.60) < 1e-6


def test_cost_for_unknown_model_returns_zero() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cost = cost_for("unknown/model", 100, 50)
    assert cost == 0.0
    assert any("unknown/model" in str(warning.message) for warning in w)


def test_cost_for_unknown_model_warns_once() -> None:
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        cost_for("once/model", 100, 50)
        cost_for("once/model", 200, 100)
    assert sum(1 for warning in w if "once/model" in str(warning.message)) == 1


def test_record_llm_call_increments_counters() -> None:
    _tel.record_llm_call("extract", 80, 0.001, False)
    assert _tel.current_telemetry.llm_calls == 1
    assert _tel.current_telemetry.total_tokens == 80
    assert abs(_tel.current_telemetry.total_cost_usd - 0.001) < 1e-9


def test_record_llm_call_increments_cache_hits() -> None:
    _tel.record_llm_call("extract", 80, 0.001, True)
    assert _tel.current_telemetry.cache_hits == 1


def test_reset_clears_telemetry() -> None:
    _tel.record_llm_call("extract", 80, 0.001, False)
    _tel.reset()
    assert _tel.current_telemetry.llm_calls == 0
    assert _tel.current_telemetry.total_cost_usd == 0.0


class _FakeLm:
    def __init__(self, history: list[dict]) -> None:
        self.history = history
        self.model = "openai/gpt-4o-mini"


def test_tap_lm_history_reads_dict_history_entries() -> None:
    lm = _FakeLm([{"usage": {"prompt_tokens": 100, "completion_tokens": 20}, "cost": 0.01}])
    _tel.tap_lm_history(lm, "extract")
    assert _tel.current_telemetry.llm_calls == 1
    assert _tel.current_telemetry.total_tokens == 120
    assert _tel.current_telemetry.cache_hits == 0


def test_tap_lm_history_prefers_dspy_cost_field() -> None:
    lm = _FakeLm([{"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}, "cost": 0.5}])
    _tel.tap_lm_history(lm, "extract")
    assert abs(_tel.current_telemetry.total_cost_usd - 0.5) < 1e-9


def test_tap_lm_history_falls_back_to_cost_table_when_cost_missing() -> None:
    lm = _FakeLm([{"usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0}}])
    _tel.tap_lm_history(lm, "extract")
    assert abs(_tel.current_telemetry.total_cost_usd - 0.15) < 1e-6


def test_tap_lm_history_detects_cache_hit() -> None:
    lm = _FakeLm([{"usage": {}, "cost": None}])
    _tel.tap_lm_history(lm, "extract")
    assert _tel.current_telemetry.cache_hits == 1
    assert _tel.current_telemetry.total_tokens == 0


def test_tap_lm_history_detects_cache_hit_with_stale_nonzero_cost() -> None:
    # dspy/clients/cache.py:_prepare_cached_response clears `usage` on a cache
    # hit but leaves `cost` at the original call's stale, non-None value —
    # empty usage alone must be enough to flag the hit, and cost must be
    # forced to 0 rather than re-reporting the stale charge.
    lm = _FakeLm([{"usage": {}, "cost": 0.5}])
    _tel.tap_lm_history(lm, "extract")
    assert _tel.current_telemetry.cache_hits == 1
    assert _tel.current_telemetry.total_tokens == 0
    assert _tel.current_telemetry.total_cost_usd == 0.0


def test_tap_lm_history_empty_history_is_noop() -> None:
    lm = _FakeLm([])
    _tel.tap_lm_history(lm, "extract")
    assert _tel.current_telemetry.llm_calls == 0
