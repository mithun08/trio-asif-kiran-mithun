from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.gap import GapReport
from matcher.models.score import ScoredCandidate
from matcher.scoring.ranker import band


def print_results(
    candidates: list[ScoredCandidate],
    gap_candidates: list[ScoredCandidate],
    config: ScoringConfig,
    gap_report: GapReport | None = None,
) -> None:
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
