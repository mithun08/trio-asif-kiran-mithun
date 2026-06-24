from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.models.signals import FeedbackSignal
from matcher.scoring.info_flags import attach_info_flags, compute_info_flags


def _role(**kwargs: object) -> Role:
    defaults: dict[str, object] = {"id": "R1", "title": "Developer"}
    defaults.update(kwargs)
    return Role(**defaults)  # type: ignore[arg-type]


def _consultant(**kwargs: object) -> Consultant:
    defaults: dict[str, object] = {"email": "x@y.com", "name": "X"}
    defaults.update(kwargs)
    return Consultant(**defaults)  # type: ignore[arg-type]


def _sc(skill_raw: float = 80.0) -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email="x@y.com",
        consultant_name="X",
        total_score=skill_raw,
        rank=1,
        dimensions=[
            DimensionScore(
                name="skill_match",
                raw_score=skill_raw,
                weight=0.35,
                weighted_score=skill_raw * 0.35,
            )
        ],
    )


def test_long_bench_flag_exceeds_threshold() -> None:
    cfg = ScoringConfig(beach_long_days=60)
    c = _consultant(days_on_beach=90)
    flags = compute_info_flags(_sc(), c, _role(), cfg)
    assert "long_bench" in flags


def test_no_long_bench_flag_below_threshold() -> None:
    cfg = ScoringConfig(beach_long_days=60)
    c = _consultant(days_on_beach=30)
    flags = compute_info_flags(_sc(), c, _role(), cfg)
    assert "long_bench" not in flags


def test_sector_match_from_raw_profile_text() -> None:
    c = _consultant(raw_profile_text="experience in Financial Services sector")
    role = _role(sector="Financial Services")
    flags = compute_info_flags(_sc(), c, role, ScoringConfig())
    assert "sector_match" in flags


def test_sector_match_from_feedback_strengths() -> None:
    sig = FeedbackSignal(sentiment="positive", strengths=["deep fintech knowledge"])
    c = _consultant(feedback_signals={"client": sig})
    role = _role(sector="fintech")
    flags = compute_info_flags(_sc(), c, role, ScoringConfig())
    assert "sector_match" in flags


def test_no_sector_match_when_role_sector_empty() -> None:
    c = _consultant(raw_profile_text="anything")
    role = _role(sector="")
    flags = compute_info_flags(_sc(), c, role, ScoringConfig())
    assert "sector_match" not in flags


def test_grade_mismatch_senior_role_wrong_grade() -> None:
    c = _consultant(grade="Analyst")
    role = _role(title="Senior Developer")
    flags = compute_info_flags(_sc(), c, role, ScoringConfig())
    assert "grade_mismatch" in flags


def test_no_grade_mismatch_for_non_senior_role() -> None:
    c = _consultant(grade="Analyst")
    role = _role(title="Developer")
    flags = compute_info_flags(_sc(), c, role, ScoringConfig())
    assert "grade_mismatch" not in flags


def test_skill_gap_flag_when_skill_band_not_strong() -> None:
    flags = compute_info_flags(_sc(skill_raw=50.0), _consultant(), _role(), ScoringConfig())
    assert "skill_gap" in flags


def test_no_skill_gap_when_strong() -> None:
    flags = compute_info_flags(_sc(skill_raw=90.0), _consultant(), _role(), ScoringConfig())
    assert "skill_gap" not in flags


def test_attach_info_flags_integration() -> None:
    c = _consultant(email="x@y.com", days_on_beach=90)
    role = _role()
    result = attach_info_flags([_sc()], [c], role, ScoringConfig())
    assert result[0].info_flags  # at least long_bench
    assert "long_bench" in result[0].info_flags
