from __future__ import annotations

import json
import re

import dspy

from matcher.llm.modules import CandidateExplanation
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate
from matcher.privacy.scrubber import rehydrate_text

_DIM_VOCAB = re.compile(
    r"\b(skill_match|feedback_quality|availability|adaptability|supply_state|performance_trend)\b"
)


def _build_why_not_higher_context(candidate: ScoredCandidate, above: ScoredCandidate | None) -> str:
    if above is None:
        return ""
    above_dims = {d.name: d.raw_score for d in above.dimensions}
    parts = [
        f"{d.name}: {d.raw_score:.1f} vs {above_dims[d.name]:.1f}"
        for d in candidate.dimensions
        if d.name in above_dims and above_dims[d.name] > d.raw_score
    ]
    return "; ".join(parts)


def generate_explanation(
    candidate: ScoredCandidate,
    ranked_above: ScoredCandidate | None,
    role: Role,
    consultant: Consultant,
    explanation_lm: dspy.LM,
    token_map: dict[str, str],
) -> ScoredCandidate:
    why_ctx = _build_why_not_higher_context(candidate, ranked_above)
    dims_json = json.dumps([d.model_dump() for d in candidate.dimensions])

    with dspy.context(lm=explanation_lm):
        result = dspy.Predict(CandidateExplanation)(
            role_title=role.title,
            candidate_name=candidate.consultant_name,
            dimension_scores_json=dims_json,
            why_not_higher_context=why_ctx,
        )

    raw_exp: str = getattr(result, "explanation", "")
    raw_why: str = getattr(result, "why_not_higher", "")

    if not _DIM_VOCAB.search(raw_exp):
        raw_exp = ""

    explanation = rehydrate_text(raw_exp, token_map)
    why_not_higher = "" if ranked_above is None else rehydrate_text(raw_why, token_map)

    return candidate.model_copy(
        update={"explanation": explanation, "why_not_higher": why_not_higher}
    )
