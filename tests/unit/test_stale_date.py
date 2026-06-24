from __future__ import annotations

from datetime import date

from matcher.models.role import Role
from matcher.pipeline import stale_date
from matcher.pipeline.free_text_role import parse


def _role(start: date | None = None) -> Role:
    return Role(id="R-01", title="Test Role", start_date=start)


def test_past_date_returns_warning() -> None:
    role = _role(start=date(2020, 1, 1))
    warnings = stale_date.check(role, date(2026, 6, 24))
    assert len(warnings) == 1
    assert "in the past" in warnings[0]
    assert "R-01" in warnings[0]


def test_future_date_returns_empty() -> None:
    role = _role(start=date(2027, 1, 1))
    warnings = stale_date.check(role, date(2026, 6, 24))
    assert warnings == []


def test_none_start_date_returns_empty() -> None:
    role = _role(start=None)
    warnings = stale_date.check(role, date(2026, 6, 24))
    assert warnings == []


def test_free_text_parse_iso_date() -> None:
    role, ambiguities = parse(
        "Need a Python dev in Bengaluru 2026-09-01",
        known_locations={"Bengaluru"},
        known_skills={"Python"},
    )
    assert role.start_date == date(2026, 9, 1)
    assert not any("start_date" in a for a in ambiguities)


def test_free_text_parse_next_month_ambiguity() -> None:
    _, ambiguities = parse(
        "Need someone for the auth stuff next month",
        known_locations=set(),
        known_skills=set(),
    )
    assert any("next month" in a for a in ambiguities)


def test_free_text_parse_location_matched() -> None:
    role, _ = parse(
        "Senior Python engineer in Bengaluru starting 2026-09-01",
        known_locations={"Bengaluru"},
        known_skills={"Python"},
    )
    assert "Bengaluru" in role.locations


def test_free_text_parse_skill_matched() -> None:
    role, _ = parse(
        "Senior Python engineer in Bengaluru starting 2026-09-01",
        known_locations={"Bengaluru"},
        known_skills={"Python"},
    )
    skill_names = [s.name for s in role.required_skills]
    assert "Python" in skill_names


def test_free_text_parse_no_skills_adds_ambiguity() -> None:
    _, ambiguities = parse(
        "Need someone next year",
        known_locations=set(),
        known_skills=set(),
    )
    assert any("skills" in a for a in ambiguities)
