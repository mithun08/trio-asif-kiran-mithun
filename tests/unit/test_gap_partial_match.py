from __future__ import annotations

from matcher.config import AppConfig, ScoringConfig, ScoringWeights
from matcher.models.role import RequiredSkill, Role
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.pipeline.gap import build_gap_report


def _role() -> Role:
    return Role(
        id="R1",
        title="Developer",
        required_skills=[RequiredSkill(name="Python"), RequiredSkill(name="Rust")],
    )


def _sc(email: str, skill_raw: float) -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email=email,
        consultant_name=email,
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


_CFG = ScoringConfig()
_W = ScoringWeights()
_APP = AppConfig(openrouter_api_key="")


def test_partial_match_when_skill_band_not_strong() -> None:
    ranked = [_sc("a@x.com", 50.0)]
    report = build_gap_report(_role(), [], ranked, [], {}, _W, _CFG, _APP)
    assert "a@x.com" in report.partial_matches


def test_no_partial_matches_when_strong() -> None:
    ranked = [_sc("a@x.com", 90.0)]
    report = build_gap_report(_role(), [], ranked, [], {}, _W, _CFG, _APP)
    assert report.partial_matches == []


def test_partial_matches_not_set_when_no_ranked_candidates() -> None:
    report = build_gap_report(_role(), [], [], [], {}, _W, _CFG, _APP)
    assert report.partial_matches == []


def test_multiple_partial_candidates_all_listed() -> None:
    ranked = [_sc("a@x.com", 50.0), _sc("b@x.com", 55.0)]
    report = build_gap_report(_role(), [], ranked, [], {}, _W, _CFG, _APP)
    assert "a@x.com" in report.partial_matches
    assert "b@x.com" in report.partial_matches
