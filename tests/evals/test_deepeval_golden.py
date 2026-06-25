from __future__ import annotations

from pathlib import Path

import pytest
import yaml

GOLDEN_PATH = Path("evals/golden/roles.yaml")
_FIXTURE_WORKBOOK = Path("evals/fixtures/eval_data.xlsx")
_REAL_WORKBOOK = Path("data/demand-supply.xlsx")
WORKBOOK_PATH = _REAL_WORKBOOK if _REAL_WORKBOOK.exists() else _FIXTURE_WORKBOOK


def _entries() -> list[dict]:  # type: ignore[type-arg]
    if not GOLDEN_PATH.exists():
        return []
    return (yaml.safe_load(GOLDEN_PATH.read_text()) or {}).get("entries", [])


@pytest.fixture(scope="module")
def golden_entries() -> list[dict]:  # type: ignore[type-arg]
    entries = _entries()
    if not entries or not WORKBOOK_PATH.exists():
        pytest.skip("golden dataset or workbook not found")
    return entries


def test_eval_pass_rate(golden_entries: list[dict]) -> None:  # type: ignore[type-arg]
    pytest.importorskip("deepeval")

    from matcher.config import AppConfig, load_adjacency
    from matcher.pipeline.ingest import (
        ingest_consultants,
        ingest_consultants_from_workbook,
        ingest_feedback,
        ingest_roles,
    )
    from matcher.pipeline.match import match_role
    from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii
    from matcher.scoring.confidence import attach_confidence_levels
    from matcher.scoring.info_flags import attach_info_flags

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))

    workbook = WORKBOOK_PATH
    roles = ingest_roles(workbook)
    consultants = ingest_consultants_from_workbook(workbook)
    if workbook != config.data_dir / "demand-supply.xlsx":
        pass  # fixture workbook has no PDF profiles or feedback files
    else:
        consultants = ingest_consultants(config.data_dir / "profiles", consultants)
        consultants = ingest_feedback(config.data_dir / "project_feedback", consultants)
    consultants = canonicalise_locations(consultants)
    consultants = dedup_by_email(consultants)
    consultants = scrub_pii(consultants)

    passed = 0
    total = len(golden_entries)

    for entry in golden_entries:
        role = next((r for r in roles if r.id == entry["role_id"]), None)
        if role is None:
            continue

        ranked, _ = match_role(
            role, consultants, adjacency_map, config.weights, config.scoring_config, top_n=3
        )
        ranked = attach_confidence_levels(ranked, consultants, config.scoring_config)
        ranked = attach_info_flags(ranked, consultants, role, config.scoring_config)

        kind = entry.get("kind", "exact")
        expected_emails: list[str] = entry.get("expected_top_emails", [])

        if kind == "unfillable":
            if not ranked:
                passed += 1
        elif kind == "negative":
            top_emails = {c.consultant_email for c in ranked}
            if not any(e in top_emails for e in expected_emails):
                passed += 1
        else:
            if not expected_emails:
                passed += 1
            else:
                top_emails = {c.consultant_email for c in ranked}
                if any(e in top_emails for e in expected_emails):
                    passed += 1

    if total == 0:
        pytest.skip("no golden entries to evaluate")

    pass_rate = passed / total
    assert pass_rate >= 0.70, (
        f"Pass rate {pass_rate:.2f} below 0.70 — suite too easy or pipeline broken"
    )
    assert pass_rate <= 0.85, (
        f"Pass rate {pass_rate:.2f} above 0.85 — suite not discriminating, add negatives"
    )
