from __future__ import annotations

from typing import Literal

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.models.score import ScoredCandidate

ConfidenceLevel = Literal["High", "Medium", "Low"]


def _compute_confidence(consultant: Consultant, config: ScoringConfig) -> ConfidenceLevel:
    if consultant.supply_state == "new_joiner":
        return "Low"
    if consultant.data_confidence < 0.5:
        return "Low"
    project_keys = [k for k in consultant.feedback_signals if "project" in k]
    non_project_keys = [k for k in consultant.feedback_signals if "project" not in k]
    verified_skills = sum(1 for s in consultant.skills if s.proficiency >= 3)
    if (
        len(project_keys) >= config.confidence_high_min_projects
        and len(non_project_keys) >= 1
        and verified_skills >= 1
    ):
        return "High"
    if len(consultant.feedback_signals) >= config.confidence_medium_min_sources:
        return "Medium"
    return "Low"


def attach_confidence_levels(
    candidates: list[ScoredCandidate],
    consultants: list[Consultant],
    config: ScoringConfig,
) -> list[ScoredCandidate]:
    by_email = {c.email.casefold(): c for c in consultants}
    result = []
    for sc in candidates:
        consultant = by_email.get(sc.consultant_email.casefold())
        if consultant is None:
            result.append(sc)
            continue
        level = _compute_confidence(consultant, config)
        result.append(sc.model_copy(update={"confidence_level": level}))
    return result
