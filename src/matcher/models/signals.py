from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class FeedbackSignal(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    client_keep_signal: bool = False
    domain_depth: bool = False
    evidence_spans: list[str] = Field(default_factory=list)


class AdaptabilitySignals(BaseModel):
    tech_transitions: int = 0
    learning_speed_mentions: bool = False
    cross_domain: int = 0
    upskilling: bool = False
    evidence_spans: list[str] = Field(default_factory=list)
