from __future__ import annotations

from pydantic import BaseModel, Field


class IngestionReport(BaseModel):
    profiles_parsed: int = 0
    profiles_low_confidence: list[str] = Field(default_factory=list)
    feedback_matched: int = 0
    feedback_unmatched: list[str] = Field(default_factory=list)
    supply_without_profile: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
