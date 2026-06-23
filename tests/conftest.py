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


@pytest.fixture
def synthetic_feedback_text() -> dict[str, str]:
    return {
        "project": "Alice worked on payments. Contact alice@client.example.com or +91-9876543210.",
        "client": "Please keep Alice Smith on the project permanently.",
        "beach": "Upskilling with cloud certifications.",
    }


@pytest.fixture
def consultant_with_pii_in_text() -> Consultant:
    return Consultant(
        email="alice.smith@paritypartners.example",
        name="Alice Smith",
        grade="Senior",
        location="London",
        raw_profile_text=(
            "Profile for Alice Smith. Email: alice.smith@paritypartners.example. "
            "Phone: +91-9876543210. Works at Meridian Pay."
        ),
        feedback_text={
            "client": (
                "Meridian Pay: Alice Smith is exceptional."
                " Keep alice.smith@paritypartners.example."
            ),
        },
    )


@pytest.fixture
def mock_dspy_lm(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    captured: list[str] = []

    class MockPrediction:
        sentiment = "positive"
        strengths = '["strong technical skills"]'
        concerns = "[]"
        client_keep_signal = "false"
        domain_depth = "false"
        evidence_spans = "[]"
        trend = "stable"
        tech_transitions = "1"
        learning_speed_mentions = "false"
        cross_domain = "1"
        upskilling = "false"
        skills_json = "[]"
        location = ""
        grade = ""

    def _capture_and_return(self: object, **kwargs: object) -> MockPrediction:
        for value in kwargs.values():
            if isinstance(value, str):
                captured.append(value)
        return MockPrediction()

    monkeypatch.setattr("dspy.Predict.__call__", _capture_and_return)
    return captured
