from __future__ import annotations

from matcher.config import AppConfig
from matcher.llm.client import make_lm
from matcher.llm.explain_module import generate_explanation
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate


def generate_explanations(
    candidates: list[ScoredCandidate],
    role: Role,
    consultants: list[Consultant],
    config: AppConfig,
) -> list[ScoredCandidate]:
    if not config.openrouter_api_key:
        return candidates

    explanation_lm = make_lm(config.model_explain, config)
    fallback_lm = make_lm(config.model_fallback, config)
    by_email = {c.email.casefold(): c for c in consultants}
    result: list[ScoredCandidate] = []

    for i, sc in enumerate(candidates):
        consultant = by_email.get(sc.consultant_email.casefold())
        if consultant is None:
            result.append(sc)
            continue
        ranked_above = candidates[i - 1] if i > 0 else None
        try:
            updated = generate_explanation(
                sc,
                ranked_above,
                role,
                consultant,
                explanation_lm,
                consultant.pii_token_map,
            )
        except Exception:
            updated = generate_explanation(
                sc,
                ranked_above,
                role,
                consultant,
                fallback_lm,
                consultant.pii_token_map,
            )
        result.append(updated)

    return result
