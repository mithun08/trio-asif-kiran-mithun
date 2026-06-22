from __future__ import annotations

from datetime import date

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.match import match_role

_CFG = ScoringConfig()
_ADJ: dict[str, list[str]] = {}


def _role(co_located: bool = True) -> Role:
    return Role(
        id="R1",
        title="Test",
        start_date=date(2026, 7, 1),
        co_located=co_located,
        locations=["Bengaluru"],
        required_skills=[RequiredSkill(name="Python")],
    )


def _consultant(email: str, location: str = "Bengaluru", supply_state: str = "beach") -> Consultant:
    return Consultant(
        email=email,
        name=email,
        location=location,
        supply_state=supply_state,  # type: ignore[arg-type]
        skills=[Skill(name="Python", proficiency=3)],
    )


def test_filtered_consultant_absent_from_ranked() -> None:
    local = _consultant("local@x.com", location="Bengaluru")
    non_local = _consultant("nonlocal@x.com", location="Mumbai")
    ranked, _ = match_role(_role(co_located=True), [local, non_local], _ADJ, _CFG)
    ranked_emails = {c.consultant_email for c in ranked}
    assert "nonlocal@x.com" not in ranked_emails


def test_filtered_consultant_present_in_gap_list() -> None:
    local = _consultant("local@x.com", location="Bengaluru")
    non_local = _consultant("nonlocal@x.com", location="Mumbai")
    _, gaps = match_role(_role(co_located=True), [local, non_local], _ADJ, _CFG)
    gap_emails = {c.consultant_email for c in gaps}
    assert "nonlocal@x.com" in gap_emails


def test_all_dimension_scores_in_range() -> None:
    consultants = [_consultant("a@x.com"), _consultant("b@x.com")]
    ranked, _ = match_role(_role(co_located=False), consultants, _ADJ, _CFG)
    for candidate in ranked:
        for dim in candidate.dimensions:
            assert 0.0 <= dim.raw_score <= 100.0, f"{dim.name} score {dim.raw_score} out of range"


def test_gap_candidates_have_rank_minus_one() -> None:
    local = _consultant("local@x.com", location="Bengaluru")
    non_local = _consultant("nonlocal@x.com", location="Mumbai")
    _, gaps = match_role(_role(co_located=True), [local, non_local], _ADJ, _CFG)
    assert all(c.rank == -1 for c in gaps)


def test_gap_candidates_total_score_is_zero() -> None:
    local = _consultant("local@x.com", location="Bengaluru")
    non_local = _consultant("nonlocal@x.com", location="Mumbai")
    _, gaps = match_role(_role(co_located=True), [local, non_local], _ADJ, _CFG)
    assert all(c.total_score == 0.0 for c in gaps)


def test_top_n_limits_ranked_output() -> None:
    consultants = [_consultant(f"c{i}@x.com") for i in range(10)]
    ranked, _ = match_role(_role(co_located=False), consultants, _ADJ, _CFG, top_n=3)
    assert len(ranked) <= 3
