from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate
from matcher.scoring.dimensions import (
    score_adaptability,
    score_availability,
    score_feedback_quality,
    score_performance_trend,
    score_skill_match,
    score_supply_state,
)
from matcher.scoring.filters import apply_hard_filters
from matcher.scoring.ranker import rank_candidates


def match_role(
    role: Role,
    consultants: list[Consultant],
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
    top_n: int = 5,
) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    passing = apply_hard_filters(consultants, role)
    passing_emails = {c.email.casefold() for c in passing}
    filtered_out = [c for c in consultants if c.email.casefold() not in passing_emails]

    scored: list[ScoredCandidate] = []
    for consultant in passing:
        dims = [
            score_skill_match(consultant, role, adjacency_map, config),
            score_feedback_quality(consultant, config),
            score_availability(consultant, role, config),
            score_adaptability(consultant, config),
            score_supply_state(consultant, config),
            score_performance_trend(consultant, config),
        ]
        total_weighted = sum(d.weight * d.raw_score for d in dims)
        total_weight = sum(d.weight for d in dims)
        total = total_weighted / total_weight if total_weight > 0 else 0.0
        assert 0.0 <= total <= 100.0, f"total score {total} out of range for {consultant.email}"
        scored.append(
            ScoredCandidate(
                consultant_email=consultant.email,
                consultant_name=consultant.name,
                total_score=round(total, 2),
                rank=0,
                dimensions=dims,
                data_confidence=consultant.data_confidence,
            )
        )

    ranked = rank_candidates(scored, config)[:top_n]

    gap_candidates = [
        ScoredCandidate(
            consultant_email=c.email,
            consultant_name=c.name,
            total_score=0.0,
            rank=-1,
            supply_gap_flags=c.data_gaps,
        )
        for c in filtered_out
    ]

    return ranked, gap_candidates
