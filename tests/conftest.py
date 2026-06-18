from __future__ import annotations

import pytest

from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role


@pytest.fixture
def sample_role() -> Role:
    return Role(
        id="role-001",
        title="Senior Python Engineer",
        required_skills=[
            RequiredSkill(name="python", mandatory=True, min_years=3.0),
            RequiredSkill(name="aws", mandatory=False),
        ],
        locations=["London"],
        required_availability_days=14,
    )


@pytest.fixture
def sample_consultant() -> Consultant:
    return Consultant(
        email="jane.doe@example.com",
        name="Jane Doe",
        grade="Senior",
        location="London",
        skills=[
            Skill(name="python", years_experience=5.0, proficiency=4),
            Skill(name="aws", years_experience=2.0, proficiency=3),
        ],
    )
