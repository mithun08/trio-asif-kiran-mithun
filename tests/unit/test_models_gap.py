from __future__ import annotations

import pytest
from pydantic import ValidationError

from matcher.models.gap import BenchEntry, GapReport
from matcher.models.output import RunOutput


def test_gap_report_defaults() -> None:
    r = GapReport()
    assert r.all_filtered is False
    assert r.filter_reasons == []
    assert r.no_required_skills is False
    assert r.inferred_skills == []
    assert r.skill_inference_confidence == 0.0
    assert r.partial_matches == []
    assert r.bench_distribution == []
    assert r.relaxed_candidates == []


def test_gap_report_all_filtered_true() -> None:
    r = GapReport(all_filtered=True, filter_reasons=["availability: too late"])
    assert r.all_filtered is True
    assert "availability: too late" in r.filter_reasons


def test_gap_report_no_required_skills() -> None:
    r = GapReport(no_required_skills=True, inferred_skills=["Python", "FastAPI"])
    assert r.no_required_skills is True
    assert r.inferred_skills == ["Python", "FastAPI"]


def test_gap_report_skill_inference_confidence_too_high_raises() -> None:
    with pytest.raises(ValidationError):
        GapReport(skill_inference_confidence=1.5)


def test_gap_report_round_trips_json() -> None:
    r = GapReport(
        all_filtered=True,
        filter_reasons=["location_mismatch"],
        bench_distribution=[BenchEntry(grade="Senior", supply_state="beach", count=2)],
    )
    dumped = r.model_dump_json()
    restored = GapReport.model_validate_json(dumped)
    assert restored.all_filtered is True
    assert restored.bench_distribution[0].grade == "Senior"


def test_run_output_has_gap_report() -> None:
    out = RunOutput(snapshot_id="abc", role_id="R1")
    assert isinstance(out.gap_report, GapReport)


def test_run_output_role_snapshot_none_by_default() -> None:
    out = RunOutput(snapshot_id="abc", role_id="R1")
    assert out.role_snapshot is None


def test_bench_entry_supply_state_literal() -> None:
    be = BenchEntry(grade="Senior", supply_state="beach", count=3)
    assert be.supply_state == "beach"


def test_bench_entry_bad_supply_state_raises() -> None:
    with pytest.raises(ValidationError):
        BenchEntry(grade="Senior", supply_state="unknown", count=1)  # type: ignore[arg-type]
