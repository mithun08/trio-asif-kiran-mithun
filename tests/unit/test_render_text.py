from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.models.gap import GapReport
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.render.text import print_results


def _sc(**kwargs: object) -> ScoredCandidate:
    defaults: dict[str, object] = {
        "consultant_email": "a@b.com",
        "consultant_name": "Alice",
        "total_score": 75.0,
        "rank": 1,
        "dimensions": [
            DimensionScore(name="skill_match", raw_score=80.0, weight=0.35, weighted_score=28.0)
        ],
    }
    defaults.update(kwargs)
    return ScoredCandidate(**defaults)  # type: ignore[arg-type]


def test_print_results_shows_confidence_level(capsys: pytest.CaptureFixture[str]) -> None:
    sc = _sc(confidence_level="High")
    print_results([sc], [], ScoringConfig())
    out = capsys.readouterr().out
    assert "High" in out


def test_print_results_shows_info_flags(capsys: pytest.CaptureFixture[str]) -> None:
    sc = _sc(info_flags=["long_bench", "sector_match"])
    print_results([sc], [], ScoringConfig())
    out = capsys.readouterr().out
    assert "long_bench" in out
    assert "sector_match" in out


def test_print_results_shows_explanation(capsys: pytest.CaptureFixture[str]) -> None:
    sc = _sc(explanation="The skill_match score is strong.")
    print_results([sc], [], ScoringConfig())
    out = capsys.readouterr().out
    assert "skill_match score is strong" in out


def test_print_results_shows_why_not_higher(capsys: pytest.CaptureFixture[str]) -> None:
    sc = _sc(why_not_higher="skill_match gap vs rank 1.")
    print_results([sc], [], ScoringConfig())
    out = capsys.readouterr().out
    assert "why not higher" in out
    assert "skill_match gap" in out


def test_print_results_gap_report_all_filtered(capsys: pytest.CaptureFixture[str]) -> None:
    gap = GapReport(
        all_filtered=True,
        filter_reasons=["location_mismatch"],
        relaxed_candidates=["x@y.com"],
    )
    print_results([], [], ScoringConfig(), gap_report=gap)
    out = capsys.readouterr().out
    assert "All Filtered" in out
    assert "location_mismatch" in out
    assert "x@y.com" in out


def test_print_results_gap_report_inferred_skills(capsys: pytest.CaptureFixture[str]) -> None:
    gap = GapReport(no_required_skills=True, inferred_skills=["Python", "FastAPI"])
    print_results([], [], ScoringConfig(), gap_report=gap)
    out = capsys.readouterr().out
    assert "No Required Skills" in out
    assert "Python" in out


def test_print_results_no_gap_report_no_crash(capsys: pytest.CaptureFixture[str]) -> None:
    print_results([], [], ScoringConfig(), gap_report=None)
    out = capsys.readouterr().out
    assert out == ""
