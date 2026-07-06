from __future__ import annotations

from typing import Any

import dspy
from pydantic import BaseModel

from matcher.config import ScoringConfig
from matcher.llm.modules import QueryRelevanceCheck, SkillDomainPlausibility
from matcher.models.consultant import Consultant
from matcher.models.role import RequiredSkill, Role
from matcher.observability.telemetry import tap_lm_history
from matcher.scoring.dimensions import has_domain_evidence


class RelevanceVerdict(BaseModel):
    in_domain: bool
    reason: str = ""


def check_domain_plausibility(
    query_text: str, role: Role, lm: Any = None
) -> RelevanceVerdict | None:
    """Tier 2: LLM classifier for queries with no parsed skill to check deterministically.

    Only needs the parsed title and an LM — no ingestion/extraction/index required, so
    this can run immediately after parsing, before any ambiguity-confirmation prompt.
    Returns None when there's nothing to judge (skills were parsed) or no LM is available.
    """
    if role.required_skills or lm is None:
        return None

    with dspy.context(lm=lm):
        result = dspy.Predict(QueryRelevanceCheck)(query_text=query_text, parsed_title=role.title)
    tap_lm_history(lm, "relevance_check")

    in_domain = str(getattr(result, "in_domain", "true")).strip().casefold() == "true"
    reason = str(getattr(result, "reason", "")).strip()
    return RelevanceVerdict(in_domain=in_domain, reason=reason)


def _skill_name_in_vocab(name: str, vocab: set[str], adjacency_map: dict[str, list[str]]) -> bool:
    req_name = name.casefold()
    vocab_cf = {v.casefold() for v in vocab}
    if req_name in vocab_cf:
        return True
    req_adjacents = adjacency_map.get(req_name, [])
    return any(v in req_adjacents or req_name in adjacency_map.get(v, []) for v in vocab_cf)


def _judge_skill_plausibility(skill_name: str, query_text: str, lm: Any) -> RelevanceVerdict:
    with dspy.context(lm=lm):
        result = dspy.ChainOfThought(SkillDomainPlausibility)(
            skill_name=skill_name, query_context=query_text
        )
    tap_lm_history(lm, "skill_plausibility")

    plausible = str(getattr(result, "plausible", "false")).strip().casefold() == "true"
    reason = str(getattr(result, "reason", "")).strip()
    return RelevanceVerdict(in_domain=plausible, reason=reason)


def check_skill_evidence(
    role: Role,
    consultants: list[Consultant],
    all_roles: list[Role],
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
    lm: Any = None,
    query_text: str = "",
) -> RelevanceVerdict | None:
    """Tier 1: is at least one parsed skill in-domain, by any of three checks?

    1a. Does any current consultant have real skill evidence (exact/adjacent/vector)?
    1b. Does the skill literally appear in this business's own role vocabulary (exact/
        adjacency), even with zero current supply? A real-but-unsupplied skill (e.g.
        "leadership") is a supply gap, not an out-of-domain query — free, no LLM call.
    1c. LLM escalation (only when 1a AND 1b both find nothing, and only then): could
        this plausibly be a skill the business would need, even if never-before-seen
        (e.g. "Rust")? Catches what a fixed vocabulary structurally can't, at the cost
        of one LLM call only in this rare double-miss case.

    Requires consultants with LLM-extracted skills and the vector index to be ready, so
    this must run after extraction/index-load, not right after parsing. Returns None when
    there are no parsed skills to check (that case is handled by check_domain_plausibility).
    """
    if not role.required_skills:
        return None

    role_vocab = {s.name for r in all_roles for s in r.required_skills}

    still_missing: list[RequiredSkill] = []
    for rs in role.required_skills:
        has_evidence = has_domain_evidence(
            rs, consultants, adjacency_map, config, index_client, embedding_model
        )
        if has_evidence or _skill_name_in_vocab(rs.name, role_vocab, adjacency_map):
            continue
        still_missing.append(rs)

    if len(still_missing) < len(role.required_skills):
        return RelevanceVerdict(in_domain=True)

    if lm is not None:
        reasons: list[str] = []
        for rs in still_missing:
            verdict = _judge_skill_plausibility(rs.name, query_text, lm)
            if verdict.in_domain:
                return RelevanceVerdict(in_domain=True)
            reasons.append(f"{rs.name} ({verdict.reason})" if verdict.reason else rs.name)
        reason = f"not a plausible skill: {'; '.join(reasons)}"
        return RelevanceVerdict(in_domain=False, reason=reason)

    names = ", ".join(rs.name for rs in still_missing)
    return RelevanceVerdict(
        in_domain=False,
        reason=f"no consultant in the pool has any skill evidence for: {names}",
    )
