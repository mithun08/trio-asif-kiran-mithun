from __future__ import annotations

from datetime import date

from matcher.config import AppConfig, ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role
from matcher.models.score import ScoredCandidate
from matcher.pipeline.gap import build_gap_report


def _role() -> Role:
    return Role(
        id="R1",
        title="Cobol Engineer",
        required_skills=[RequiredSkill(name="Cobol")],
        co_located=True,
        locations=["Tokyo"],
        start_date=date(2026, 7, 1),
    )


def _consultant(email: str, location: str = "London") -> Consultant:
    return Consultant(
        email=email,
        name=email,
        location=location,
        skills=[Skill(name="Python")],
        supply_state="beach",
    )


def _gap_sc(email: str, reason: str) -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email=email,
        consultant_name=email,
        total_score=0.0,
        rank=-1,
        supply_gap_flags=[reason],
    )


_CFG = ScoringConfig()
_W = ScoringWeights()
_APP_CFG = AppConfig(openrouter_api_key="")


def test_all_filtered_sets_flag_and_filter_reasons() -> None:
    consultants = [_consultant("a@x.com"), _consultant("b@x.com")]
    gap_sc = [
        _gap_sc("a@x.com", "location_mismatch"),
        _gap_sc("b@x.com", "location_mismatch"),
    ]
    report = build_gap_report(_role(), consultants, [], gap_sc, {}, _W, _CFG, _APP_CFG)
    assert report.all_filtered is True
    assert "location_mismatch" in report.filter_reasons


def test_all_filtered_runs_relaxed_match() -> None:
    consultants = [_consultant("a@x.com"), _consultant("b@x.com")]
    gap_sc = [
        _gap_sc("a@x.com", "location_mismatch"),
        _gap_sc("b@x.com", "location_mismatch"),
    ]
    report = build_gap_report(_role(), consultants, [], gap_sc, {}, _W, _CFG, _APP_CFG)
    assert len(report.relaxed_candidates) > 0


def test_bench_distribution_populated_on_all_filtered() -> None:
    consultants = [_consultant("a@x.com"), _consultant("b@x.com")]
    gap_sc = [_gap_sc("a@x.com", "location_mismatch")]
    report = build_gap_report(_role(), consultants, [], gap_sc, {}, _W, _CFG, _APP_CFG)
    assert len(report.bench_distribution) > 0


def test_no_all_filtered_when_ranked_candidates_exist() -> None:
    from matcher.models.score import DimensionScore

    ranked = [
        ScoredCandidate(
            consultant_email="a@x.com",
            consultant_name="A",
            total_score=80.0,
            rank=1,
            dimensions=[
                DimensionScore(name="skill_match", raw_score=90.0, weight=0.35, weighted_score=31.5)
            ],
        )
    ]
    report = build_gap_report(_role(), [], ranked, [], {}, _W, _CFG, _APP_CFG)
    assert report.all_filtered is False
