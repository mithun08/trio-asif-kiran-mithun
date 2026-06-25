from __future__ import annotations

from pathlib import Path

import pytest

from matcher.models.errors import BudgetExceededError
from matcher.observability import telemetry as _tel


def test_budget_raises_on_cost_exceeded() -> None:
    _tel.reset()
    _tel.record_llm_call("test", 1000, 2.00, False)
    with pytest.raises(BudgetExceededError):
        _tel.check_budget(max_cost_usd=1.50, max_tokens=0)


def test_budget_passes_when_zero_limit() -> None:
    _tel.reset()
    _tel.record_llm_call("test", 999999, 999.99, False)
    _tel.check_budget(max_cost_usd=0.0, max_tokens=0)


def test_budget_raises_on_token_exceeded() -> None:
    _tel.reset()
    _tel.record_llm_call("test", 100001, 0.01, False)
    with pytest.raises(BudgetExceededError):
        _tel.check_budget(max_cost_usd=0.0, max_tokens=100000)


def test_budget_exceeded_error_is_runtime_error() -> None:
    assert issubclass(BudgetExceededError, RuntimeError)


def test_config_has_budget_fields() -> None:
    from matcher.config import AppConfig

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.max_cost_usd_per_run == 0.0
    assert config.max_tokens_per_run == 0
