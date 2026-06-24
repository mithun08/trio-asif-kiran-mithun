from __future__ import annotations

import pytest
from pydantic import ValidationError

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate


def test_role_sector_defaults_empty() -> None:
    role = Role(id="R1", title="Dev")
    assert role.sector == ""


def test_role_sector_set() -> None:
    role = Role(id="R1", title="Dev", sector="FinTech")
    assert role.sector == "FinTech"


def test_consultant_days_on_beach_defaults_zero() -> None:
    c = Consultant(email="x@y.com", name="X")
    assert c.days_on_beach == 0


def test_consultant_days_on_beach_set() -> None:
    c = Consultant(email="x@y.com", name="X", days_on_beach=45)
    assert c.days_on_beach == 45


def test_scored_candidate_confidence_defaults_medium() -> None:
    sc = ScoredCandidate(consultant_email="a@b.com", consultant_name="A", total_score=50.0, rank=1)
    assert sc.confidence_level == "Medium"


def test_scored_candidate_info_flags_defaults_empty() -> None:
    sc = ScoredCandidate(consultant_email="a@b.com", consultant_name="A", total_score=50.0, rank=1)
    assert sc.info_flags == []


def test_scored_candidate_why_not_higher_defaults_empty() -> None:
    sc = ScoredCandidate(consultant_email="a@b.com", consultant_name="A", total_score=50.0, rank=1)
    assert sc.why_not_higher == ""


def test_scored_candidate_confidence_literal_rejected() -> None:
    with pytest.raises(ValidationError):
        ScoredCandidate(
            consultant_email="a@b.com",
            consultant_name="A",
            total_score=50.0,
            rank=1,
            confidence_level="Bad",  # type: ignore[arg-type]
        )
