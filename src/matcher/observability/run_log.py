from __future__ import annotations

import logging
from pathlib import Path

import structlog

logger = structlog.get_logger()

_sink_configured = False

_NOISY_LOGGERS = (
    "docling",
    "dspy",
    "sentence_transformers",
    "pymilvus",
    "urllib3",
    "httpx",
    "httpcore",
)


def _suppress_noisy_loggers() -> None:
    logging.getLogger().setLevel(logging.WARNING)
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)


def configure_log_sink(path: Path) -> None:
    global _sink_configured
    if _sink_configured:
        return
    _suppress_noisy_loggers()
    path.parent.mkdir(parents=True, exist_ok=True)
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.WriteLoggerFactory(file=path.open("a", encoding="utf-8")),
    )
    _sink_configured = True


def _reset_log_sink() -> None:
    global _sink_configured
    _sink_configured = False


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
