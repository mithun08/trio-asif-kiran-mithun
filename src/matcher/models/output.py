from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from matcher.models.gap import GapReport
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate


class DataQualityReport(BaseModel):
    total_consultants_ingested: int = 0
    unmatched_records: list[str] = Field(default_factory=list)
    low_confidence_profiles: list[str] = Field(default_factory=list)


class RunOutput(BaseModel):
    snapshot_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    role_id: str
    candidates: list[ScoredCandidate] = Field(default_factory=list)
    data_quality: DataQualityReport = Field(default_factory=DataQualityReport)
    config_version: str = "0.1.0"
    llm_tokens_used: int = 0
    llm_cost_usd: float = 0.0
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    gap_report: GapReport = Field(default_factory=GapReport)
    role_snapshot: Role | None = None
