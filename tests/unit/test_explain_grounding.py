from __future__ import annotations

from matcher.llm.explain_module import _DIM_VOCAB, _build_why_not_higher_context
from matcher.models.score import DimensionScore, ScoredCandidate


def _sc(dims: list[tuple[str, float]]) -> ScoredCandidate:
    dimension_list = [
        DimensionScore(name=n, raw_score=s, weight=0.1, weighted_score=s * 0.1) for n, s in dims
    ]
    return ScoredCandidate(
        consultant_email="a@b.com",
        consultant_name="A",
        total_score=50.0,
        rank=1,
        dimensions=dimension_list,
    )


def test_grounding_check_returns_true_with_dim_name() -> None:
    text = "The skill_match score indicates strong Python alignment."
    assert _DIM_VOCAB.search(text) is not None


def test_grounding_check_returns_false_no_dim_name() -> None:
    text = "This candidate has great experience and communication skills."
    assert _DIM_VOCAB.search(text) is None


def test_build_why_not_higher_context_rank_1_returns_empty() -> None:
    candidate = _sc([("skill_match", 80.0), ("availability", 70.0)])
    assert _build_why_not_higher_context(candidate, None) == ""


def test_build_why_not_higher_context_shows_gap_dims() -> None:
    above = _sc([("skill_match", 95.0), ("availability", 80.0)])
    below = _sc([("skill_match", 60.0), ("availability", 80.0)])
    ctx = _build_why_not_higher_context(below, above)
    assert "skill_match" in ctx
    assert "95.0" in ctx
    assert "60.0" in ctx


def test_build_why_not_higher_context_no_gap_returns_empty() -> None:
    above = _sc([("skill_match", 60.0)])
    below = _sc([("skill_match", 80.0)])
    ctx = _build_why_not_higher_context(below, above)
    assert ctx == ""
