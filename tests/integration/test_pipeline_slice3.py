from __future__ import annotations

import json

from matcher.config import AppConfig, ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant, Skill
from matcher.models.gap import GapReport
from matcher.models.output import DataQualityReport, RunOutput
from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.gap import build_gap_report
from matcher.pipeline.match import match_role
from matcher.render.json import render_json
from matcher.scoring.confidence import attach_confidence_levels
from matcher.scoring.info_flags import attach_info_flags


def _role() -> Role:
    return Role(
        id="R1",
        title="Senior Python Engineer",
        sector="FinTech",
        required_skills=[RequiredSkill(name="Python", mandatory=True)],
        locations=["London"],
    )


def _consultants() -> list[Consultant]:
    return [
        Consultant(
            email="alice@x.com",
            name="Alice",
            grade="Senior Consultant",
            location="London",
            supply_state="beach",
            days_on_beach=80,
            skills=[Skill(name="Python", proficiency=4, years_experience=5.0)],
            raw_profile_text="Alice has FinTech experience",
        ),
        Consultant(
            email="bob@x.com",
            name="Bob",
            grade="Analyst",
            location="London",
            supply_state="rolling_off",
            skills=[Skill(name="Python", proficiency=2, years_experience=1.0)],
        ),
    ]


_CFG = ScoringConfig()
_W = ScoringWeights()
_APP_CFG = AppConfig(openrouter_api_key="")
_ADJ: dict[str, list[str]] = {}


def test_ranked_candidates_have_confidence_level() -> None:
    role = _role()
    consultants = _consultants()
    ranked, gaps = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    for sc in ranked:
        assert sc.confidence_level in {"High", "Medium", "Low"}


def test_ranked_candidates_have_info_flags_list() -> None:
    role = _role()
    consultants = _consultants()
    ranked, gaps = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    ranked = attach_info_flags(ranked, consultants, role, _CFG)
    for sc in ranked:
        assert isinstance(sc.info_flags, list)


def test_long_bench_flag_set_for_alice() -> None:
    role = _role()
    consultants = _consultants()
    ranked, _ = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    ranked = attach_info_flags(ranked, consultants, role, _CFG)
    alice = next(sc for sc in ranked if sc.consultant_email == "alice@x.com")
    assert "long_bench" in alice.info_flags


def test_sector_match_flag_set_for_alice() -> None:
    role = _role()
    consultants = _consultants()
    ranked, _ = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    ranked = attach_info_flags(ranked, consultants, role, _CFG)
    alice = next(sc for sc in ranked if sc.consultant_email == "alice@x.com")
    assert "sector_match" in alice.info_flags


def test_gap_report_constructed() -> None:
    role = _role()
    consultants = _consultants()
    ranked, gaps = match_role(role, consultants, _ADJ, _W, _CFG)
    gap_report = build_gap_report(role, consultants, ranked, gaps, _ADJ, _W, _CFG, _APP_CFG)
    assert isinstance(gap_report, GapReport)


def test_run_output_assembles_correctly() -> None:
    role = _role()
    consultants = _consultants()
    ranked, gaps = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    ranked = attach_info_flags(ranked, consultants, role, _CFG)
    gap_report = build_gap_report(role, consultants, ranked, gaps, _ADJ, _W, _CFG, _APP_CFG)
    output = RunOutput(
        snapshot_id="test123",
        role_id="R1",
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
        data_quality=DataQualityReport(total_consultants_ingested=len(consultants)),
    )
    assert output.snapshot_id == "test123"
    assert output.role_snapshot is not None
    assert isinstance(output.gap_report, GapReport)


def test_json_renderer_produces_valid_json() -> None:
    role = _role()
    consultants = _consultants()
    ranked, gaps = match_role(role, consultants, _ADJ, _W, _CFG)
    ranked = attach_confidence_levels(ranked, consultants, _CFG)
    ranked = attach_info_flags(ranked, consultants, role, _CFG)
    gap_report = build_gap_report(role, consultants, ranked, gaps, _ADJ, _W, _CFG, _APP_CFG)
    output = RunOutput(
        snapshot_id="test123",
        role_id="R1",
        candidates=ranked,
        gap_report=gap_report,
        role_snapshot=role,
    )
    raw = render_json(output)
    parsed = json.loads(raw)
    assert parsed["role_id"] == "R1"
    assert "candidates" in parsed
    assert "gap_report" in parsed
