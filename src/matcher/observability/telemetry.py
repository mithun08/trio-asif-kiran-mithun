from __future__ import annotations

from typing import Any

from matcher.models.telemetry import RunTelemetry

current_telemetry: RunTelemetry = RunTelemetry()


def reset() -> None:
    global current_telemetry
    current_telemetry = RunTelemetry()


def record_llm_call(task: str, tokens: int, cost_usd: float, cache_hit: bool) -> None:
    current_telemetry.llm_calls += 1
    current_telemetry.total_tokens += tokens
    current_telemetry.total_cost_usd += cost_usd
    if cache_hit:
        current_telemetry.cache_hits += 1


def tap_lm_history(lm: object, task: str) -> None:
    from matcher.observability.cost_table import cost_for

    history = getattr(lm, "history", None)
    if not history:
        return
    last = history[-1]
    if not isinstance(last, dict):
        return

    usage: dict[str, Any] = last.get("usage") or {}
    pt = int(usage.get("prompt_tokens", 0) or 0)
    ct = int(usage.get("completion_tokens", 0) or 0)
    model = str(last.get("model") or getattr(lm, "model", "") or "")

    # DSPy's cache layer (dspy/clients/cache.py:_prepare_cached_response) clears
    # `usage` to {} on a cache hit but leaves `cost` at the original call's stale
    # value (it's copied from the cached response's _hidden_params, never zeroed).
    # Empty usage is therefore the only reliable cache-hit signal; a real call
    # always returns non-empty usage. Force cost to 0 on a hit — no charge was
    # actually incurred on replay, regardless of what the stale field says.
    cache_hit = pt == 0 and ct == 0
    if cache_hit:
        cost = 0.0
    else:
        dspy_cost = last.get("cost")
        cost = float(dspy_cost) if dspy_cost is not None else cost_for(model, pt, ct)

    record_llm_call(task, pt + ct, cost, cache_hit)


def snapshot() -> RunTelemetry:
    return current_telemetry.model_copy()


def check_budget(max_cost_usd: float, max_tokens: int) -> None:
    from matcher.models.errors import BudgetExceededError

    if max_cost_usd > 0 and current_telemetry.total_cost_usd > max_cost_usd:
        raise BudgetExceededError(
            f"Run cost ${current_telemetry.total_cost_usd:.4f} exceeds budget ${max_cost_usd:.4f}"
        )
    if max_tokens > 0 and current_telemetry.total_tokens > max_tokens:
        raise BudgetExceededError(
            f"Run used {current_telemetry.total_tokens} tokens, exceeds budget {max_tokens}"
        )
