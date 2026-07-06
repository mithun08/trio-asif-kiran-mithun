from __future__ import annotations

from typing import Any

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.models.role import RequiredSkill, Role
from matcher.models.score import DimensionScore


def _best_credit(
    req: RequiredSkill,
    consultant: Consultant,
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
    *,
    apply_new_joiner_fallback: bool = True,
) -> float:
    req_name = req.name.casefold()

    for skill in consultant.skills:
        s_name = skill.name.casefold()
        if s_name == req_name:
            if req.required_proficiency is None or skill.proficiency >= req.required_proficiency:
                return config.c_exact
            return config.c_prof

    for skill in consultant.skills:
        s_name = skill.name.casefold()
        adjacents = adjacency_map.get(s_name, []) + adjacency_map.get(req_name, [])
        if req_name in adjacents or s_name in adjacents:
            return config.c_adjacent

    if index_client is not None and embedding_model is not None:
        req_vec = embedding_model.encode(req_name).tolist()
        results = index_client.search(
            collection_name="skill_embeddings",
            data=[req_vec],
            limit=1,
            filter=f'consultant_email == "{consultant.email}"',
            output_fields=["skill_name"],
        )
        if results and results[0]:
            hit = results[0][0]
            # Milvus's COSINE metric returns a distance (1 - cosine_similarity,
            # lower = more similar), not the similarity itself — convert before
            # comparing to the similarity threshold.
            distance = hit.get("distance", 0.0)
            similarity = 1.0 - distance
            if similarity >= config.skill_vector_similarity:
                return config.c_vector

    if apply_new_joiner_fallback and consultant.supply_state == "new_joiner":
        return config.c_newjoiner
    return 0.0


def has_domain_evidence(
    req: RequiredSkill,
    consultants: list[Consultant],
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
) -> bool:
    return any(
        _best_credit(
            req,
            consultant,
            adjacency_map,
            config,
            index_client,
            embedding_model,
            apply_new_joiner_fallback=False,
        )
        > 0
        for consultant in consultants
    )


def score_skill_match(
    consultant: Consultant,
    role: Role,
    adjacency_map: dict[str, list[str]],
    weights: ScoringWeights,
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
) -> DimensionScore:
    mandatory = [rs for rs in role.required_skills if rs.mandatory]
    optional = [rs for rs in role.required_skills if not rs.mandatory]

    if mandatory:
        credits = [
            _best_credit(rs, consultant, adjacency_map, config, index_client, embedding_model)
            for rs in mandatory
        ]
        required_mean = sum(credits) / len(credits)
    else:
        required_mean = 0.0

    bonus_count = sum(
        1
        for rs in optional
        if _best_credit(rs, consultant, adjacency_map, config, index_client, embedding_model) > 0
    )
    skill_bonus = min(config.nth_bonus_per * bonus_count, config.nth_bonus_cap)
    raw = min(100.0, required_mean + skill_bonus)

    evidence = [f"mandatory mean={required_mean:.1f}", f"bonus={skill_bonus:.1f}"]

    matched_excludes = [
        name
        for name in role.exclude_skills
        if _best_credit(
            RequiredSkill(name=name),
            consultant,
            adjacency_map,
            config,
            index_client,
            embedding_model,
        )
        > 0
    ]
    if matched_excludes:
        exclude_penalty = min(
            config.skill_exclude_penalty_per * len(matched_excludes),
            config.skill_exclude_penalty_cap,
        )
        raw = max(0.0, raw - exclude_penalty)
        evidence.append(f"excluded skills matched: {', '.join(matched_excludes)}")

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
    weight = weights.feedback_quality

    if not consultant.feedback_signals:
        return DimensionScore(
            name="feedback_quality",
            raw_score=config.neutral_baseline,
            weight=weight,
            weighted_score=round(config.neutral_baseline * weight, 4),
            evidence=["no feedback"],
        )

    sentiment_base_map = {
        "positive": config.feedback_sent_pos,
        "neutral": config.feedback_sent_neutral,
        "negative": config.feedback_sent_neg,
    }
    evidence: list[str] = []
    source_scores: dict[str, float] = {}

    for source in ["project", "client", "beach"]:
        signal = consultant.feedback_signals.get(source)
        if signal is None:
            source_scores[source] = config.neutral_baseline
            evidence.append(f"no {source} feedback")
            continue

        base_score = sentiment_base_map[signal.sentiment]
        is_client_keep = source == "client" and signal.client_keep_signal
        keep_bonus = config.feedback_kw_keep if is_client_keep else 0.0
        domain_bonus = config.feedback_kw_domain if signal.domain_depth else 0.0
        concern_penalty = config.feedback_kw_concern if signal.concerns else 0.0
        sub_score = max(0.0, min(100.0, base_score + keep_bonus + domain_bonus - concern_penalty))

        source_scores[source] = sub_score
        evidence.append(f"{source}: {signal.sentiment}")

    raw = (
        config.feedback_weight_project * source_scores["project"]
        + config.feedback_weight_client * source_scores["client"]
        + config.feedback_weight_beach * source_scores["beach"]
    )

    return DimensionScore(
        name="feedback_quality",
        raw_score=round(raw, 2),
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=evidence,
    )


def score_adaptability(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    weight = weights.adaptability

    if consultant.adaptability_signals is None:
        return DimensionScore(
            name="adaptability",
            raw_score=config.neutral_baseline,
            weight=weight,
            weighted_score=round(config.neutral_baseline * weight, 4),
            evidence=["no data"],
        )

    sig = consultant.adaptability_signals
    evidence: list[str] = []
    bonus = 0.0

    if sig.tech_transitions >= config.adapt_min_transitions:
        bonus += config.adapt_pts_transitions
        evidence.append(f"tech_transitions={sig.tech_transitions}")

    if sig.learning_speed_mentions:
        bonus += config.adapt_pts_learning
        evidence.append("learning_speed_mentioned")

    if sig.cross_domain >= config.adapt_min_crossdomain:
        bonus += config.adapt_pts_crossdomain
        evidence.append(f"cross_domain={sig.cross_domain}")

    if sig.upskilling:
        bonus += config.adapt_pts_upskill
        evidence.append("upskilling")

    raw = max(0.0, min(100.0, config.neutral_baseline + bonus))

    return DimensionScore(
        name="adaptability",
        raw_score=round(raw, 2),
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=evidence if evidence else ["no signals"],
    )


def score_performance_trend(
    consultant: Consultant, weights: ScoringWeights, config: ScoringConfig
) -> DimensionScore:
    trend_score_map = {
        "improving": config.trend_improving,
        "stable": config.trend_stable,
        "declining": config.trend_declining,
        "unknown": config.neutral_baseline,
    }
    raw = trend_score_map[consultant.performance_trend]
    weight = weights.performance_trend

    return DimensionScore(
        name="performance_trend",
        raw_score=raw,
        weight=weight,
        weighted_score=round(raw * weight, 4),
        evidence=[consultant.performance_trend],
    )
