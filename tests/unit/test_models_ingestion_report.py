from __future__ import annotations

from matcher.models.ingestion_report import IngestionReport


def test_default_counts_are_zero() -> None:
    report = IngestionReport()
    assert report.profiles_parsed == 0
    assert report.feedback_matched == 0
    assert report.profiles_low_confidence == []
    assert report.feedback_unmatched == []
    assert report.supply_without_profile == []
    assert report.warnings == []


def test_round_trip_json() -> None:
    report = IngestionReport(
        profiles_parsed=5,
        profiles_low_confidence=["a@b.com"],
        feedback_matched=3,
        feedback_unmatched=["orphan.md"],
        supply_without_profile=["c@d.com"],
        warnings=["stale date"],
    )
    serialised = report.model_dump_json()
    restored = IngestionReport.model_validate_json(serialised)
    assert restored.profiles_parsed == 5
    assert restored.profiles_low_confidence == ["a@b.com"]
    assert restored.feedback_matched == 3
    assert restored.feedback_unmatched == ["orphan.md"]
    assert restored.supply_without_profile == ["c@d.com"]
    assert restored.warnings == ["stale date"]
