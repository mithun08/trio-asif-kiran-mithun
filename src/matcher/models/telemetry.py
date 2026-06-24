from __future__ import annotations

from pydantic import BaseModel, Field, computed_field


class RunTelemetry(BaseModel):
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0

    @computed_field
    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.llm_calls if self.llm_calls else 0.0
