from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant, Skill
from matcher.models.score import ScoredCandidate
from matcher.models.signals import FeedbackSignal
from matcher.scoring.confidence import _compute_confidence, attach_confidence_levels


def _cfg(**kwargs: object) -> ScoringConfig:
    return ScoringConfig(**kwargs)  # type: ignore[arg-type]


def _consultant(**kwargs: object) -> Consultant:
    defaults: dict[str, object] = {"email": "x@y.com", "name": "X"}
    defaults.update(kwargs)
    return Consultant(**defaults)  # type: ignore[arg-type]


def _signal(sentiment: str = "positive") -> FeedbackSignal:
    return FeedbackSignal(sentiment=sentiment)  # type: ignore[arg-type]


def test_new_joiner_is_low() -> None:
    c = _consultant(supply_state="new_joiner")
    assert _compute_confidence(c, ScoringConfig()) == "Low"


def test_low_data_confidence_is_low() -> None:
    c = _consultant(data_confidence=0.3)
    assert _compute_confidence(c, ScoringConfig()) == "Low"


def test_no_feedback_is_low() -> None:
    c = _consultant()
    assert _compute_confidence(c, ScoringConfig()) == "Low"


def test_one_source_is_medium() -> None:
    c = _consultant(feedback_signals={"client": _signal()})
    assert _compute_confidence(c, ScoringConfig()) == "Medium"


def test_high_requires_project_plus_non_project_plus_skills() -> None:
    cfg = ScoringConfig(confidence_high_min_projects=1)
    c = _consultant(
        feedback_signals={
            "project": _signal(),
            "client": _signal(),
        },
        skills=[Skill(name="Python", proficiency=4)],
    )
    assert _compute_confidence(c, cfg) == "High"


def test_high_not_reached_without_verified_skills() -> None:
    cfg = ScoringConfig(confidence_high_min_projects=1)
    c = _consultant(
        feedback_signals={
            "project": _signal(),
            "client": _signal(),
        },
        skills=[Skill(name="Python", proficiency=1)],
    )
    assert _compute_confidence(c, cfg) == "Medium"


def test_threshold_change_alters_result() -> None:
    cfg_strict = ScoringConfig(confidence_high_min_projects=3)
    c = _consultant(
        feedback_signals={
            "project": _signal(),
            "client": _signal(),
        },
        skills=[Skill(name="Python", proficiency=4)],
    )
    assert _compute_confidence(c, cfg_strict) != "High"


def test_attach_confidence_levels_unknown_email_unchanged() -> None:
    sc = ScoredCandidate(
        consultant_email="unknown@x.com",
        consultant_name="Unknown",
        total_score=50.0,
        rank=1,
    )
    result = attach_confidence_levels([sc], [], ScoringConfig())
    assert result[0].confidence_level == "Medium"


def test_attach_confidence_levels_sets_correct_level() -> None:
    c = _consultant(email="a@b.com", feedback_signals={"client": _signal()})
    sc = ScoredCandidate(
        consultant_email="a@b.com",
        consultant_name="A",
        total_score=60.0,
        rank=1,
    )
    result = attach_confidence_levels([sc], [c], ScoringConfig())
    assert result[0].confidence_level == "Medium"
