from __future__ import annotations

import json

from matcher.models.gap import GapReport
from matcher.models.output import RunOutput
from matcher.models.role import Role
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.render.json import render_json


def _make_output() -> RunOutput:
    role = Role(id="R1", title="Dev", sector="FinTech")
    sc = ScoredCandidate(
        consultant_email="a@b.com",
        consultant_name="A",
        total_score=75.0,
        rank=1,
        confidence_level="High",
        info_flags=["sector_match"],
        dimensions=[
            DimensionScore(name="skill_match", raw_score=80.0, weight=0.35, weighted_score=28.0)
        ],
    )
    gap = GapReport(no_required_skills=False, inferred_skills=[])
    return RunOutput(
        snapshot_id="abc123",
        role_id="R1",
        candidates=[sc],
        gap_report=gap,
        role_snapshot=role,
    )


def test_render_json_returns_valid_json() -> None:
    output = _make_output()
    raw = render_json(output)
    parsed = json.loads(raw)
    assert isinstance(parsed, dict)


def test_render_json_contains_role_id() -> None:
    output = _make_output()
    raw = render_json(output)
    parsed = json.loads(raw)
    assert parsed["role_id"] == "R1"


def test_render_json_candidates_serialised() -> None:
    output = _make_output()
    raw = render_json(output)
    parsed = json.loads(raw)
    assert len(parsed["candidates"]) == 1
    assert parsed["candidates"][0]["consultant_email"] == "a@b.com"


def test_render_json_gap_report_serialised() -> None:
    output = _make_output()
    raw = render_json(output)
    parsed = json.loads(raw)
    assert "gap_report" in parsed
    assert "no_required_skills" in parsed["gap_report"]


def test_render_json_confidence_level_per_candidate() -> None:
    output = _make_output()
    raw = render_json(output)
    parsed = json.loads(raw)
    assert parsed["candidates"][0]["confidence_level"] == "High"


def test_render_json_round_trips() -> None:
    output = _make_output()
    raw = render_json(output)
    restored = RunOutput.model_validate_json(raw)
    assert restored.role_id == output.role_id
    assert restored.candidates[0].confidence_level == "High"
