from __future__ import annotations

from matcher.models.score import ScoredCandidate


def rank_candidates(candidates: list[ScoredCandidate]) -> list[ScoredCandidate]:
    """Sort by total_score descending, apply tiebreak rules, assign rank field."""
    raise NotImplementedError
