from __future__ import annotations

import structlog

logger = structlog.get_logger()


def log_run_start(snapshot_id: str, config_version: str) -> None:
    logger.info("run_start", snapshot_id=snapshot_id, config_version=config_version)


def log_stage_timing(stage: str, elapsed_ms: float) -> None:
    logger.info("stage_timing", stage=stage, elapsed_ms=elapsed_ms)


def log_llm_usage(task: str, tokens: int, cost_usd: float, cache_hit: bool) -> None:
    logger.info("llm_usage", task=task, tokens=tokens, cost_usd=cost_usd, cache_hit=cache_hit)


def log_data_quality(unmatched: list[str], low_confidence: list[str]) -> None:
    logger.info(
        "data_quality",
        unmatched_count=len(unmatched),
        low_confidence_count=len(low_confidence),
    )
