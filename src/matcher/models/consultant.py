from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


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
