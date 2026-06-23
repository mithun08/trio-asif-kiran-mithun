from __future__ import annotations

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.models.role import RequiredSkill, Role
from matcher.models.score import DimensionScore


def _best_credit(
    req: RequiredSkill,
    consultant: Consultant,
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
) -> float:
    req_name = req.name.casefold()
    for skill in consultant.skills:
        s_name = skill.name.casefold()
        if s_name == req_name:
            if req.required_proficiency is None or skill.proficiency >= req.required_proficiency:
                return config.c_exact
            return config.c_prof
        adjacents = adjacency_map.get(s_name, []) + adjacency_map.get(req_name, [])
        if req_name in adjacents or s_name in adjacents:
            return config.c_adjacent
    if consultant.supply_state == "new_joiner":
        return config.c_newjoiner
    return 0.0


def score_skill_match(
    consultant: Consultant,
    role: Role,
    adjacency_map: dict[str, list[str]],
    weights: ScoringWeights,
    config: ScoringConfig,
) -> DimensionScore:
    mandatory = [rs for rs in role.required_skills if rs.mandatory]
    optional = [rs for rs in role.required_skills if not rs.mandatory]

    if mandatory:
        credits = [_best_credit(rs, consultant, adjacency_map, config) for rs in mandatory]
        required_mean = sum(credits) / len(credits)
    else:
        required_mean = 0.0

    bonus_count = sum(
        1 for rs in optional if _best_credit(rs, consultant, adjacency_map, config) > 0
    )
    skill_bonus = min(config.nth_bonus_per * bonus_count, config.nth_bonus_cap)
    raw = min(100.0, required_mean + skill_bonus)

    evidence = [f"mandatory mean={required_mean:.1f}", f"bonus={skill_bonus:.1f}"]
    weight = weights.skill_match
    return DimensionScore(
        name="skill_match",
        raw_score=round(raw, 2),
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=evidence,
    )


def score_availability(
    consultant: Consultant,
    role: Role,
    weights: ScoringWeights,
    config: ScoringConfig,
) -> DimensionScore:
    if role.start_date is None:
        weight = weights.availability
        return DimensionScore(
            name="availability",
            raw_score=config.neutral_baseline,
            weight=weight,
            weighted_score=round(config.neutral_baseline * weight, 4),
            evidence=["no start date"],
        )

    available_date = consultant.available_from if consultant.available_from else role.start_date
    days_late = max(0, (available_date - role.start_date).days)
    k = 100.0 / config.avail_horizon_days
    base_avail = max(0.0, min(100.0, 100.0 - k * days_late))
    penalty = getattr(config, f"rolloff_penalty_{consultant.rolloff_confidence}")
    raw = round(base_avail * (1.0 - penalty), 2)

    evidence = [f"days_late={days_late}", f"base={base_avail:.1f}", f"penalty={penalty}"]
    weight = weights.availability
    return DimensionScore(
        name="availability",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=evidence,
    )


def score_supply_state(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    score_map = {
        "beach": config.supply_beach,
        "rolling_off": config.supply_rolloff,
        "new_joiner": config.supply_newjoiner,
    }
    raw = score_map[consultant.supply_state]
    weight = weights.supply_state
    return DimensionScore(
        name="supply_state",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=[consultant.supply_state],
    )


def score_feedback_quality(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    raw = config.neutral_baseline
    weight = weights.feedback_quality
    return DimensionScore(
        name="feedback_quality",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=["no data"],
    )


def score_adaptability(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    raw = config.neutral_baseline
    weight = weights.adaptability
    return DimensionScore(
        name="adaptability",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=["no data"],
    )


def score_performance_trend(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    raw = config.neutral_baseline
    weight = weights.performance_trend
    return DimensionScore(
        name="performance_trend",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=["no data"],
    )
