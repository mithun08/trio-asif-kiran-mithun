from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class RequiredSkill(BaseModel):
    name: str
    mandatory: bool = True
    min_years: float | None = None
    required_proficiency: int | None = None


class Role(BaseModel):
    id: str
    title: str
    description: str = ""
    required_skills: list[RequiredSkill] = Field(default_factory=list)
    locations: list[str] = Field(default_factory=list)
    required_availability_days: int = 0
    co_located: bool = False
    start_date: date | None = None
    sector: str = ""
    exclude_skills: list[str] = Field(default_factory=list)
    exclude_locations: list[str] = Field(default_factory=list)
    exclude_supply_states: list[Literal["beach", "rolling_off", "new_joiner"]] = Field(
        default_factory=list
    )
