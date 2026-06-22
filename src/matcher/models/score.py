from __future__ import annotations

from pydantic import BaseModel, Field


class DimensionScore(BaseModel):
    name: str
    raw_score: float = Field(ge=0.0, le=100.0)
    weight: float = Field(ge=0.0, le=1.0)
    weighted_score: float = Field(ge=0.0, le=100.0)
    evidence: list[str] = Field(default_factory=list)


class ScoredCandidate(BaseModel):
    consultant_email: str
    consultant_name: str
    total_score: float = Field(ge=0.0, le=100.0)
    rank: int
    dimensions: list[DimensionScore] = Field(default_factory=list)
    explanation: str = ""
    supply_gap_flags: list[str] = Field(default_factory=list)
    data_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
