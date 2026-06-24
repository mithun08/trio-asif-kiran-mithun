from __future__ import annotations

from unittest.mock import MagicMock, patch

from matcher.config import AppConfig
from matcher.llm.explain_module import generate_explanation
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.pipeline.explain import generate_explanations


def _make_sc(email: str = "a@b.com", rank: int = 1) -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email=email,
        consultant_name="A",
        total_score=70.0,
        rank=rank,
        dimensions=[
            DimensionScore(name="skill_match", raw_score=80.0, weight=0.35, weighted_score=28.0)
        ],
    )


def _make_consultant(email: str = "a@b.com") -> Consultant:
    return Consultant(email=email, name="A", pii_token_map={})


def _make_role() -> Role:
    return Role(id="R1", title="Senior Dev")


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    return lm


def test_why_not_higher_empty_for_rank_1() -> None:
    mock_result = MagicMock()
    mock_result.explanation = "The skill_match score is strong."
    mock_result.why_not_higher = "Some gap text."

    with patch("matcher.llm.explain_module.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.explain_module.dspy.context"):
            updated = generate_explanation(
                _make_sc(rank=1),
                None,
                _make_role(),
                _make_consultant(),
                _mock_lm(),
                {},
            )

    assert updated.why_not_higher == ""


def test_why_not_higher_nonempty_when_ranked_above() -> None:
    mock_result = MagicMock()
    mock_result.explanation = "The skill_match score is strong."
    mock_result.why_not_higher = "skill_match gap vs rank 1."

    above = _make_sc(rank=1)

    with patch("matcher.llm.explain_module.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = mock_result
        with patch("matcher.llm.explain_module.dspy.context"):
            updated = generate_explanation(
                _make_sc(rank=2),
                above,
                _make_role(),
                _make_consultant(),
                _mock_lm(),
                {},
            )

    assert updated.why_not_higher == "skill_match gap vs rank 1."


def test_generate_explanations_skips_on_no_api_key() -> None:
    config = AppConfig(openrouter_api_key="")
    sc = _make_sc()
    result = generate_explanations([sc], _make_role(), [_make_consultant()], config)
    assert result == [sc]
