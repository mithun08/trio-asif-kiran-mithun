from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from matcher.models.signals import AdaptabilitySignals, FeedbackSignal


class Skill(BaseModel):
    name: str
    years_experience: float = 0.0
    proficiency: int = Field(default=3, ge=1, le=5)


class Consultant(BaseModel):
    email: str
    name: str
    grade: str = ""
    location: str = ""
    available_from: date | None = None
    skills: list[Skill] = Field(default_factory=list)
    raw_profile_text: str = ""
    data_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    data_gaps: list[str] = Field(default_factory=list)
    supply_state: Literal["beach", "rolling_off", "new_joiner"] = "beach"
    rolloff_confidence: Literal["high", "medium", "low"] = "high"
    feedback_text: dict[str, str] = Field(default_factory=dict)
    feedback_signals: dict[str, FeedbackSignal] = Field(default_factory=dict)
    adaptability_signals: AdaptabilitySignals | None = None
    performance_trend: Literal["improving", "stable", "declining", "unknown"] = "unknown"
    pii_token_map: dict[str, str] = Field(default_factory=dict)
    days_on_beach: int = 0
