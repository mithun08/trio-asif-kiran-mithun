from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SkillCriterion(BaseModel):
    name: str
    polarity: Literal["require", "prefer", "exclude"]
    min_proficiency: int | None = None


class QuerySpec(BaseModel):
    title: str
    skills: list[SkillCriterion] = Field(default_factory=list)
    include_locations: list[str] = Field(default_factory=list)
    exclude_locations: list[str] = Field(default_factory=list)
    exclude_supply_states: list[Literal["beach", "rolling_off", "new_joiner"]] = Field(
        default_factory=list
    )
    relative_start_phrase: str = ""
