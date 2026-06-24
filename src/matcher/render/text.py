from __future__ import annotations

import sys

from matcher.config import ScoringConfig
from matcher.models.gap import GapReport
from matcher.models.ingestion_report import IngestionReport
from matcher.models.score import ScoredCandidate
from matcher.models.telemetry import RunTelemetry
from matcher.scoring.ranker import band


def print_results(
    candidates: list[ScoredCandidate],
    gap_candidates: list[ScoredCandidate],
    config: ScoringConfig,
    gap_report: GapReport | None = None,
    ingestion_report: IngestionReport | None = None,
    run_telemetry: RunTelemetry | None = None,
) -> None:
    if ingestion_report is not None:
        print("=== Ingestion Report ===")
        print(f"  profiles parsed: {ingestion_report.profiles_parsed}")
        if ingestion_report.profiles_low_confidence:
            print(f"  low confidence: {len(ingestion_report.profiles_low_confidence)}")
        if ingestion_report.feedback_unmatched:
            print(f"  unmatched feedback: {', '.join(ingestion_report.feedback_unmatched)}")
        if ingestion_report.supply_without_profile:
            print(f"  supply without profile: {len(ingestion_report.supply_without_profile)}")
        for w in ingestion_report.warnings:
            print(f"  warning: {w}", file=sys.stderr)

    if candidates:
        print("=== Ranked Candidates ===")
    for c in candidates:
        bands = [band(d.raw_score, config) for d in c.dimensions]
        strong_count = bands.count("Strong")
        gap_dims = [d.name for d, b in zip(c.dimensions, bands) if b == "Gap"]
        gap_str = f"  gaps: {', '.join(gap_dims)}" if gap_dims else ""
        n_dims = len(c.dimensions)
        print(f"#{c.rank}  {c.consultant_name}  [{strong_count} of {n_dims} strong]{gap_str}")
        flags_str = ", ".join(c.info_flags) if c.info_flags else "none"
        print(f"   confidence: {c.confidence_level}  flags: {flags_str}")
        if c.explanation:
            print(f"   {c.explanation}")
        if c.why_not_higher:
            print(f"   why not higher: {c.why_not_higher}")

    if gap_candidates:
        print("\n=== Filtered Out (hard filter) ===")
        for c in gap_candidates:
            flags = "; ".join(c.supply_gap_flags) if c.supply_gap_flags else "hard filter"
            print(f"  {c.consultant_name} ({flags})")

    if gap_report is not None:
        if gap_report.all_filtered:
            print("\n=== Gap Report: All Filtered ===")
            print(f"  reasons: {', '.join(gap_report.filter_reasons)}")
            if gap_report.relaxed_candidates:
                print(f"  relaxed candidates: {', '.join(gap_report.relaxed_candidates)}")
        if gap_report.no_required_skills:
            print("\n=== Gap Report: No Required Skills ===")
            if gap_report.inferred_skills:
                print(f"  inferred: {', '.join(gap_report.inferred_skills)}")
        if gap_report.partial_matches:
            print("\n=== Gap Report: Partial Matches ===")
            print(f"  {', '.join(gap_report.partial_matches)}")

    if run_telemetry is not None:
        total_s = sum(run_telemetry.stage_timings_ms.values()) / 1000.0
        rate_pct = int(run_telemetry.cache_hit_rate * 100)
        print(
            f"\n  telemetry: {total_s:.1f}s total, "
            f"{run_telemetry.llm_calls} LLM calls, "
            f"${run_telemetry.total_cost_usd:.4f}, "
            f"cache {rate_pct}%"
        )
