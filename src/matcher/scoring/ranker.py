from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.score import ScoredCandidate


def _dim_raw(candidate: ScoredCandidate, name: str) -> float:
    return next((d.raw_score for d in candidate.dimensions if d.name == name), 0.0)


def _sort_key(c: ScoredCandidate) -> tuple[float, float, float, float]:
    return (
        c.total_score,
        _dim_raw(c, "availability"),
        c.data_confidence,
        _dim_raw(c, "supply_state"),
    )


def band(score: float, config: ScoringConfig) -> str:
    if score >= config.band_strong:
        return "Strong"
    return "Partial" if score >= config.band_partial else "Gap"


def rank_candidates(
    candidates: list[ScoredCandidate], config: ScoringConfig
) -> list[ScoredCandidate]:
    ordered = sorted(candidates, key=_sort_key, reverse=True)
    result: list[ScoredCandidate] = []
    for i, c in enumerate(ordered):
        if i > 0 and _sort_key(ordered[i]) == _sort_key(ordered[i - 1]):
            rank = result[i - 1].rank
        else:
            rank = i + 1
        result.append(c.model_copy(update={"rank": rank}))
    return result
