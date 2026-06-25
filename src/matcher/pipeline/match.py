from __future__ import annotations

from typing import Any

from matcher.config import ScoringConfig, ScoringWeights
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
    weights: ScoringWeights,
    config: ScoringConfig,
    top_n: int = 5,
    *,
    skip_skill_dim: bool = False,
    disable_availability_filter: bool = False,
    disable_location_filter: bool = False,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
) -> tuple[list[ScoredCandidate], list[ScoredCandidate]]:
    passing, rejected = apply_hard_filters(
        consultants,
        role,
        disable_availability_filter=disable_availability_filter,
        disable_location_filter=disable_location_filter,
    )

    scored: list[ScoredCandidate] = []
    for consultant in passing:
        dims = []
        if not skip_skill_dim:
            dims.append(
                score_skill_match(
                    consultant, role, adjacency_map, weights, config, index_client, embedding_model
                )
            )
        dims += [
            score_feedback_quality(consultant, weights, config),
            score_availability(consultant, role, weights, config),
            score_adaptability(consultant, weights, config),
            score_supply_state(consultant, weights, config),
            score_performance_trend(consultant, weights, config),
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
            supply_gap_flags=[reason],
        )
        for c, reason in rejected
    ]

    return ranked, gap_candidates
