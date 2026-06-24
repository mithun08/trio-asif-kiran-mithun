from __future__ import annotations

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


def snapshot() -> RunTelemetry:
    return current_telemetry.model_copy()
