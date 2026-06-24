from __future__ import annotations

from unittest.mock import MagicMock, patch

from matcher.llm.explain_module import generate_explanation
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import DimensionScore, ScoredCandidate


def _make_sc() -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email="a@b.com",
        consultant_name="<PERSON_0>",
        total_score=70.0,
        rank=2,
        dimensions=[
            DimensionScore(name="skill_match", raw_score=80.0, weight=0.35, weighted_score=28.0)
        ],
    )


def _make_above() -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email="b@c.com",
        consultant_name="B",
        total_score=85.0,
        rank=1,
        dimensions=[
            DimensionScore(name="skill_match", raw_score=95.0, weight=0.35, weighted_score=33.25)
        ],
    )


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    return lm


def test_explanation_rehydrates_pii_tokens() -> None:
    token_map = {"<PERSON_0>": "Aarav Krishnan"}
    mock_result = MagicMock()
    mock_result.explanation = "<PERSON_0> showed strong skill_match."
    mock_result.why_not_higher = ""

    with patch("matcher.llm.explain_module.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.explain_module.dspy.context"):
            updated = generate_explanation(
                _make_sc(),
                _make_above(),
                Role(id="R1", title="Dev"),
                Consultant(email="a@b.com", name="A"),
                _mock_lm(),
                token_map,
            )

    assert "Aarav Krishnan" in updated.explanation
    assert "<PERSON_0>" not in updated.explanation


def test_empty_token_map_is_noop() -> None:
    mock_result = MagicMock()
    mock_result.explanation = "Strong skill_match performance noted."
    mock_result.why_not_higher = ""

    with patch("matcher.llm.explain_module.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.explain_module.dspy.context"):
            updated = generate_explanation(
                _make_sc(),
                _make_above(),
                Role(id="R1", title="Dev"),
                Consultant(email="a@b.com", name="A"),
                _mock_lm(),
                {},
            )

    assert updated.explanation == "Strong skill_match performance noted."


def test_ungrounded_explanation_cleared() -> None:
    mock_result = MagicMock()
    mock_result.explanation = "This candidate is a great fit and very experienced."
    mock_result.why_not_higher = ""

    with patch("matcher.llm.explain_module.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.explain_module.dspy.context"):
            updated = generate_explanation(
                _make_sc(),
                _make_above(),
                Role(id="R1", title="Dev"),
                Consultant(email="a@b.com", name="A"),
                _mock_lm(),
                {},
            )

    assert updated.explanation == ""
