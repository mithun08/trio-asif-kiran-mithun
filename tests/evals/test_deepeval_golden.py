# Eval pass rate thresholds:
#   Minimum 0.70 — below this means the pipeline is broken or the golden set is misconfigured.
#   Maximum 0.85 — above this means the golden set is not discriminating enough; add negatives
#                  or unfillable entries to keep the suite challenging.
# These thresholds are calibrated against the synthetic fixture set in evals/fixtures/.
# When adding new golden entries, keep the pass rate in the [0.70, 0.85] window.
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

GOLDEN_PATH = Path("evals/golden/roles.yaml")
WORKBOOK_PATH = Path("evals/fixtures/eval_data.xlsx")


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
    from matcher.pipeline.ingest import ingest_consultants_from_workbook, ingest_roles
    from matcher.pipeline.match import match_role
    from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii
    from matcher.scoring.confidence import attach_confidence_levels
    from matcher.scoring.info_flags import attach_info_flags

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))

    roles = ingest_roles(WORKBOOK_PATH)
    consultants = ingest_consultants_from_workbook(WORKBOOK_PATH)
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
        elif kind == "gap":
            if ranked and all("skill_gap" in c.info_flags for c in ranked):
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


def test_relevance_gate_rejects_implausible_query(golden_entries: list[dict]) -> None:  # type: ignore[type-arg]
    # The pass-rate loop above only exercises match_role, never the query-relevance
    # gate (pipeline/relevance.py) that's supposed to catch out-of-domain requests
    # before ranking (see docs/what-the-demo-taught-us.html). This closes that gap
    # against the real fixture vocabulary/consultants, not synthetic unit fixtures.
    from matcher.config import AppConfig, load_adjacency
    from matcher.models.role import RequiredSkill, Role
    from matcher.pipeline.ingest import ingest_consultants_from_workbook, ingest_roles
    from matcher.pipeline.relevance import check_skill_evidence

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))
    roles = ingest_roles(WORKBOOK_PATH)
    consultants = ingest_consultants_from_workbook(WORKBOOK_PATH)

    nonsense_role = Role(
        id="EVAL-NONSENSE",
        title="Query",
        required_skills=[RequiredSkill(name="Underwater Basket Weaving")],
    )
    verdict = check_skill_evidence(
        nonsense_role, consultants, roles, adjacency_map, config.scoring_config, lm=None
    )
    assert verdict is not None
    assert verdict.in_domain is False

    # Sanity check the other side of the gate: a real-but-unsupplied skill (COBOL,
    # EVAL-04) must NOT be rejected here — it's a supply gap, not an out-of-domain
    # query, and should fall through to normal ranking flagged skill_gap instead.
    unsupplied_role = next(r for r in roles if r.id == "EVAL-04")
    verdict = check_skill_evidence(
        unsupplied_role, consultants, roles, adjacency_map, config.scoring_config, lm=None
    )
    assert verdict is None or verdict.in_domain is True
