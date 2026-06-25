from __future__ import annotations

import statistics
import time
from pathlib import Path

import pytest


@pytest.mark.skip(reason="requires real data — run with DSM_EVAL_WORKBOOK set")
def test_match_p95_latency_under_threshold() -> None:
    from matcher.config import AppConfig, load_adjacency
    from matcher.pipeline.ingest import (
        ingest_consultants_from_workbook,
        ingest_roles,
    )
    from matcher.pipeline.match import match_role
    from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))
    workbook = config.data_dir / "demand-supply.xlsx"

    roles = ingest_roles(workbook)
    consultants = ingest_consultants_from_workbook(workbook)
    consultants = canonicalise_locations(consultants)
    consultants = dedup_by_email(consultants)
    consultants = scrub_pii(consultants)

    latencies: list[float] = []
    for role in roles[:10]:
        t0 = time.perf_counter()
        match_role(role, consultants, adjacency_map, config.weights, config.scoring_config)
        latencies.append((time.perf_counter() - t0) * 1000)

    p95 = statistics.quantiles(latencies, n=20)[18]
    assert p95 < 500, f"p95 latency {p95:.0f}ms exceeds 500ms threshold"
