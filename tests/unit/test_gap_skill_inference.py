from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from matcher.config import AppConfig, ScoringConfig, ScoringWeights
from matcher.llm.skill_inference import infer_skills_for_role
from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.gap import build_gap_report


def _make_role(with_skills: bool = False) -> Role:
    skills = [RequiredSkill(name="Python")] if with_skills else []
    return Role(id="R1", title="Python Engineer", description="Python role", required_skills=skills)


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    return lm


def test_infer_skills_returns_skills_above_threshold() -> None:
    mock_result = MagicMock()
    mock_result.inferred_skills_json = (
        '[{"name": "Python", "confidence": 0.8}, {"name": "FastAPI", "confidence": 0.7}]'
    )

    with patch("matcher.llm.skill_inference.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.skill_inference.dspy.context"):
            skills, conf = infer_skills_for_role(_make_role(), _mock_lm(), min_confidence=0.5)

    assert len(skills) == 2
    assert skills[0].name == "Python"
    assert conf == pytest.approx(0.75)


def test_infer_skills_filters_below_threshold() -> None:
    mock_result = MagicMock()
    mock_result.inferred_skills_json = (
        '[{"name": "Python", "confidence": 0.8}, {"name": "Cobol", "confidence": 0.3}]'
    )

    with patch("matcher.llm.skill_inference.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.skill_inference.dspy.context"):
            skills, conf = infer_skills_for_role(_make_role(), _mock_lm(), min_confidence=0.5)

    assert len(skills) == 1
    assert skills[0].name == "Python"


def test_infer_skills_returns_empty_on_parse_failure() -> None:
    mock_result = MagicMock()
    mock_result.inferred_skills_json = "not json at all"

    with patch("matcher.llm.skill_inference.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.skill_inference.dspy.context"):
            skills, conf = infer_skills_for_role(_make_role(), _mock_lm())

    assert skills == []
    assert conf == 0.0


def test_infer_skills_average_confidence_correct() -> None:
    mock_result = MagicMock()
    mock_result.inferred_skills_json = (
        '[{"name": "Python", "confidence": 0.7}, {"name": "FastAPI", "confidence": 0.9}]'
    )

    with patch("matcher.llm.skill_inference.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.skill_inference.dspy.context"):
            skills, conf = infer_skills_for_role(_make_role(), _mock_lm(), min_confidence=0.5)

    assert conf == pytest.approx(0.8)


def test_no_required_skills_sets_flag_no_api_key() -> None:
    role = _make_role(with_skills=False)
    cfg = AppConfig(openrouter_api_key="")
    report = build_gap_report(role, [], [], [], {}, ScoringWeights(), ScoringConfig(), cfg)
    assert report.no_required_skills is True
    assert report.inferred_skills == []


def test_has_required_skills_no_flag() -> None:
    role = _make_role(with_skills=True)
    cfg = AppConfig(openrouter_api_key="")
    report = build_gap_report(role, [], [], [], {}, ScoringWeights(), ScoringConfig(), cfg)
    assert report.no_required_skills is False
