from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.score import ScoredCandidate
from matcher.scoring.ranker import band


def print_results(
    candidates: list[ScoredCandidate],
    gap_candidates: list[ScoredCandidate],
    config: ScoringConfig,
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

    if gap_candidates:
        print("\n=== Filtered Out (hard filter) ===")
        for c in gap_candidates:
            flags = "; ".join(c.supply_gap_flags) if c.supply_gap_flags else "hard filter"
            print(f"  {c.consultant_name} ({flags})")
