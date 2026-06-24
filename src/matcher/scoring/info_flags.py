from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate
from matcher.scoring.ranker import band

_SENIOR_GRADES = {"senior consultant", "lead consultant", "director"}


def compute_info_flags(
    sc: ScoredCandidate,
    consultant: Consultant,
    role: Role,
    config: ScoringConfig,
) -> list[str]:
    flags: list[str] = []

    if consultant.days_on_beach >= config.beach_long_days:
        flags.append("long_bench")

    if role.sector:
        sector_lower = role.sector.casefold()
        if sector_lower in consultant.raw_profile_text.casefold():
            flags.append("sector_match")
        else:
            for sig in consultant.feedback_signals.values():
                if any(sector_lower in s.casefold() for s in sig.strengths + sig.concerns):
                    flags.append("sector_match")
                    break

    if "senior" in role.title.casefold() and consultant.grade.casefold() not in _SENIOR_GRADES:
        flags.append("grade_mismatch")

    skill_dim = next((d for d in sc.dimensions if d.name == "skill_match"), None)
    if skill_dim is not None and band(skill_dim.raw_score, config) != "Strong":
        flags.append("skill_gap")

    return flags


def attach_info_flags(
    candidates: list[ScoredCandidate],
    consultants: list[Consultant],
    role: Role,
    config: ScoringConfig,
) -> list[ScoredCandidate]:
    by_email = {c.email.casefold(): c for c in consultants}
    result = []
    for sc in candidates:
        consultant = by_email.get(sc.consultant_email.casefold())
        if consultant is None:
            result.append(sc)
            continue
        flags = compute_info_flags(sc, consultant, role, config)
        result.append(sc.model_copy(update={"info_flags": flags}))
    return result
