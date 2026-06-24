from __future__ import annotations

import dspy

from matcher.config import AppConfig, ScoringConfig, ScoringWeights
from matcher.llm.skill_inference import infer_skills_for_role
from matcher.models.consultant import Consultant
from matcher.models.gap import BenchEntry, GapReport
from matcher.models.role import Role
from matcher.models.score import ScoredCandidate
from matcher.pipeline.match import match_role
from matcher.scoring.ranker import band


def _bench_distribution(consultants: list[Consultant]) -> list[BenchEntry]:
    counts: dict[tuple[str, str], int] = {}
    for c in consultants:
        key = (c.grade, c.supply_state)
        counts[key] = counts.get(key, 0) + 1
    return [
        BenchEntry(grade=g, supply_state=s, count=n)  # type: ignore[arg-type]
        for (g, s), n in sorted(counts.items())
    ]


def build_gap_report(
    role: Role,
    all_consultants: list[Consultant],
    ranked: list[ScoredCandidate],
    gap_candidates: list[ScoredCandidate],
    adjacency_map: dict[str, list[str]],
    weights: ScoringWeights,
    config: ScoringConfig,
    app_config: AppConfig,
) -> GapReport:
    report = GapReport()

    if not ranked and gap_candidates:
        reasons = list({f for gc in gap_candidates for f in gc.supply_gap_flags})
        relaxed, _ = match_role(
            role,
            all_consultants,
            adjacency_map,
            weights,
            config,
            top_n=config.gap_top_n,
            disable_availability_filter=True,
            disable_location_filter=True,
        )
        report = report.model_copy(
            update={
                "all_filtered": True,
                "filter_reasons": reasons,
                "bench_distribution": _bench_distribution(all_consultants),
                "relaxed_candidates": [rc.consultant_email for rc in relaxed],
            }
        )

    if not role.required_skills:
        inferred_names: list[str] = []
        infer_conf = 0.0
        if app_config.openrouter_api_key:
            inference_lm = dspy.LM(
                model=app_config.model_skill_inference,
                api_key=app_config.openrouter_api_key,
                api_base="https://openrouter.ai/api/v1",
                temperature=0,
                max_retries=3,
            )
            inferred_skills, infer_conf = infer_skills_for_role(
                role, inference_lm, config.skill_infer_min
            )
            inferred_names = [s.name for s in inferred_skills]
        report = report.model_copy(
            update={
                "no_required_skills": True,
                "inferred_skills": inferred_names,
                "skill_inference_confidence": infer_conf,
            }
        )

    if ranked:
        top_skill = next((d for d in ranked[0].dimensions if d.name == "skill_match"), None)
        if top_skill is not None and band(top_skill.raw_score, config) != "Strong":
            partials = [
                sc.consultant_email
                for sc in ranked
                if any(
                    d.name == "skill_match" and band(d.raw_score, config) != "Strong"
                    for d in sc.dimensions
                )
            ]
            report = report.model_copy(update={"partial_matches": partials})

    return report
