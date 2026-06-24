from __future__ import annotations

import warnings
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

_COST_TABLE_PATH = Path("config/cost_table.yaml")
_warned_models: set[str] = set()


@lru_cache(maxsize=1)
def _load_table() -> dict[str, dict[str, float]]:
    if not _COST_TABLE_PATH.exists():
        return {}
    raw: dict[str, Any] = yaml.safe_load(_COST_TABLE_PATH.read_text()) or {}
    result: dict[str, dict[str, float]] = raw.get("models", {})
    return result


def cost_for(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    table = _load_table()
    if model not in table:
        if model not in _warned_models:
            warnings.warn(f"No cost entry for model {model!r}; returning 0.0", stacklevel=2)
            _warned_models.add(model)
        return 0.0
    entry = table[model]
    return (
        prompt_tokens * entry.get("prompt", 0.0) + completion_tokens * entry.get("completion", 0.0)
    ) / 1_000_000
