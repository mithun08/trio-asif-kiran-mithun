from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class BenchEntry(BaseModel):
    grade: str
    supply_state: Literal["beach", "rolling_off", "new_joiner"]
    count: int


class GapReport(BaseModel):
    all_filtered: bool = False
    filter_reasons: list[str] = Field(default_factory=list)
    no_required_skills: bool = False
    inferred_skills: list[str] = Field(default_factory=list)
    skill_inference_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    partial_matches: list[str] = Field(default_factory=list)
    bench_distribution: list[BenchEntry] = Field(default_factory=list)
    relaxed_candidates: list[str] = Field(default_factory=list)
