from __future__ import annotations

import json
import re
from typing import Any, Literal

import dspy

from matcher.config import ScoringConfig
from matcher.llm.modules import (
    AdaptabilitySignalExtraction,
    FeedbackSignalExtraction,
    PerformanceTrendExtraction,
    ProfileExtraction,
)
from matcher.models.consultant import Consultant, Skill
from matcher.models.signals import AdaptabilitySignals, FeedbackSignal
from matcher.observability.telemetry import tap_lm_history as _tap_lm_history

_LmType = Any


def _run_predict(
    predictor: Any,
    lm: _LmType,
    fallback_lm: _LmType,
    **kwargs: Any,
) -> Any:
    try:
        with dspy.context(lm=lm):
            result = predictor(**kwargs)
        _tap_lm_history(lm, "extract")
        return result
    except Exception:
        effective = fallback_lm if fallback_lm is not None else lm
        with dspy.context(lm=effective):
            result = predictor(**kwargs)
        _tap_lm_history(effective, "extract")
        return result


_PROFICIENCY_MAP: dict[str, int] = {
    "expert": 5,
    "working": 3,
    "experienced": 3,
    "proficient": 3,
    "beginner": 1,
    "learning": 1,
}

_VALID_SENTIMENTS = ("positive", "neutral", "negative")
_VALID_TRENDS = ("improving", "stable", "declining", "unknown")


def _parse_json_list(raw: str) -> list[Any]:
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return parsed
        return []
    except (json.JSONDecodeError, TypeError):
        return []


def _parse_bool_string(raw: str) -> bool:
    return raw.strip().lower() in ("true", "yes", "1")


def _parse_int_string(raw: str, default: int = 0) -> int:
    try:
        return int(raw.strip())
    except (ValueError, AttributeError):
        return default


def _parse_years(raw: Any, default: float = 0.0) -> float:
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"\d+(?:\.\d+)?", str(raw))
    return float(match.group()) if match else default


def _check_grounding(spans: list[str], source_text: str) -> tuple[list[str], bool]:
    grounded = [s for s in spans if s and s in source_text]
    any_dropped = len(grounded) < len(spans)
    return grounded, any_dropped


def _apply_evidence_floor(
    consultant: Consultant,
    grounded_spans: list[str],
    config: ScoringConfig,
    flag_name: str,
) -> Consultant:
    if len(grounded_spans) >= config.extract_min_spans:
        return consultant

    new_confidence = consultant.data_confidence * 0.7
    new_gaps = [*consultant.data_gaps, flag_name]
    return consultant.model_copy(update={"data_confidence": new_confidence, "data_gaps": new_gaps})


def extract_profile(
    consultant: Consultant,
    config: ScoringConfig,
    lm: _LmType = None,
    fallback_lm: _LmType = None,
) -> Consultant:
    predictor = dspy.Predict(ProfileExtraction)
    if lm is not None:
        result = _run_predict(predictor, lm, fallback_lm, raw_text=consultant.raw_profile_text)
    else:
        result = predictor(raw_text=consultant.raw_profile_text)
        _tap_lm_history(getattr(dspy.settings, "lm", None), "extract")

    skills_json_raw: str = getattr(result, "skills_json", "[]")
    skills_data = _parse_json_list(skills_json_raw)

    if not skills_data and skills_json_raw.strip() not in ("[]", ""):
        if lm is not None:
            result_retry = _run_predict(
                predictor, lm, fallback_lm, raw_text=consultant.raw_profile_text
            )
        else:
            result_retry = predictor(raw_text=consultant.raw_profile_text)
            _tap_lm_history(getattr(dspy.settings, "lm", None), "extract")
        skills_data = _parse_json_list(getattr(result_retry, "skills_json", "[]"))

        if not skills_data:
            new_gaps = [*consultant.data_gaps, "profile_extraction_parse_failed"]
            return consultant.model_copy(update={"data_gaps": new_gaps})

    evidence_spans_raw: str = getattr(result, "evidence_spans", "[]")
    spans = _parse_json_list(evidence_spans_raw)
    grounded_spans, any_dropped = _check_grounding(
        [s for s in spans if isinstance(s, str)],
        consultant.raw_profile_text,
    )

    data_gaps = list(consultant.data_gaps)
    if any_dropped:
        data_gaps.append("ungrounded_profile")

    updated = consultant.model_copy(update={"data_gaps": data_gaps})
    updated = _apply_evidence_floor(updated, grounded_spans, config, "low_evidence_profile")

    pdf_location: str = getattr(result, "location", "").strip()
    pdf_grade: str = getattr(result, "grade", "").strip()

    current_gaps = list(updated.data_gaps)
    if pdf_location and pdf_location.casefold() != consultant.location.casefold():
        current_gaps.append("location_mismatch_with_profile")
    if pdf_grade and pdf_grade.casefold() != consultant.grade.casefold():
        current_gaps.append("grade_mismatch_with_profile")

    merged_skills = _merge_skills(consultant.skills, skills_data)
    return updated.model_copy(update={"skills": merged_skills, "data_gaps": current_gaps})


def _merge_skills(existing: list[Skill], extracted: list[dict[str, Any]]) -> list[Skill]:
    existing_by_name = {s.name.casefold(): s for s in existing}

    for item in extracted:
        if not isinstance(item, dict):
            continue

        skill_name = str(item.get("name", "")).strip()
        if not skill_name:
            continue

        prof_raw = item.get("proficiency", "")
        if isinstance(prof_raw, str):
            proficiency = _PROFICIENCY_MAP.get(prof_raw.casefold(), 3)
        elif isinstance(prof_raw, int):
            proficiency = max(1, min(5, prof_raw))
        else:
            proficiency = 3

        years = _parse_years(item.get("years_experience", 0.0))
        key = skill_name.casefold()

        if key in existing_by_name:
            updated_skill = existing_by_name[key].model_copy(update={"proficiency": proficiency})
            existing_by_name[key] = updated_skill
        else:
            existing_by_name[key] = Skill(
                name=skill_name,
                years_experience=years,
                proficiency=proficiency,
            )

    return list(existing_by_name.values())


def extract_feedback(
    consultant: Consultant,
    source: str,
    config: ScoringConfig,
    lm: _LmType = None,
    fallback_lm: _LmType = None,
) -> Consultant:
    feedback_text = consultant.feedback_text.get(source, "")
    if not feedback_text:
        return consultant

    predictor = dspy.Predict(FeedbackSignalExtraction)
    if lm is not None:
        result = _run_predict(predictor, lm, fallback_lm, feedback_text=feedback_text)
    else:
        result = predictor(feedback_text=feedback_text)
        _tap_lm_history(getattr(dspy.settings, "lm", None), "extract")

    sentiment_raw: str = getattr(result, "sentiment", "neutral").strip().lower()
    sentiment: Literal["positive", "neutral", "negative"] = (
        sentiment_raw if sentiment_raw in _VALID_SENTIMENTS else "neutral"  # type: ignore[assignment]
    )

    strengths_raw: str = getattr(result, "strengths", "[]")
    concerns_raw: str = getattr(result, "concerns", "[]")
    client_keep_raw: str = getattr(result, "client_keep_signal", "false")
    domain_depth_raw: str = getattr(result, "domain_depth", "false")
    evidence_raw: str = getattr(result, "evidence_spans", "[]")

    strengths: list[str] = [s for s in _parse_json_list(strengths_raw) if isinstance(s, str)]
    concerns: list[str] = [s for s in _parse_json_list(concerns_raw) if isinstance(s, str)]
    client_keep = _parse_bool_string(client_keep_raw)
    domain_depth = _parse_bool_string(domain_depth_raw)

    spans = [s for s in _parse_json_list(evidence_raw) if isinstance(s, str)]
    grounded_spans, any_dropped = _check_grounding(spans, feedback_text)

    data_gaps = list(consultant.data_gaps)
    if any_dropped:
        data_gaps.append(f"ungrounded_feedback_{source}")

    signal = FeedbackSignal(
        sentiment=sentiment,
        strengths=strengths,
        concerns=concerns,
        client_keep_signal=client_keep,
        domain_depth=domain_depth,
        evidence_spans=grounded_spans,
    )

    updated_signals = {**consultant.feedback_signals, source: signal}
    updated = consultant.model_copy(
        update={"feedback_signals": updated_signals, "data_gaps": data_gaps}
    )
    return _apply_evidence_floor(updated, grounded_spans, config, f"low_evidence_{source}")


def extract_adaptability(
    consultant: Consultant,
    combined_text: str,
    config: ScoringConfig,
    lm: _LmType = None,
    fallback_lm: _LmType = None,
) -> Consultant:
    predictor = dspy.Predict(AdaptabilitySignalExtraction)
    if lm is not None:
        result = _run_predict(predictor, lm, fallback_lm, combined_text=combined_text)
    else:
        result = predictor(combined_text=combined_text)
        _tap_lm_history(getattr(dspy.settings, "lm", None), "extract")

    tech_transitions = _parse_int_string(getattr(result, "tech_transitions", "0"))
    cross_domain = _parse_int_string(getattr(result, "cross_domain", "0"))
    learning_raw: str = getattr(result, "learning_speed_mentions", "false")
    upskilling_raw: str = getattr(result, "upskilling", "false")
    evidence_raw: str = getattr(result, "evidence_spans", "[]")

    spans = [s for s in _parse_json_list(evidence_raw) if isinstance(s, str)]
    grounded_spans, any_dropped = _check_grounding(spans, combined_text)

    data_gaps = list(consultant.data_gaps)
    if any_dropped:
        data_gaps.append("ungrounded_adaptability")

    signals = AdaptabilitySignals(
        tech_transitions=tech_transitions,
        learning_speed_mentions=_parse_bool_string(learning_raw),
        cross_domain=cross_domain,
        upskilling=_parse_bool_string(upskilling_raw),
        evidence_spans=grounded_spans,
    )

    updated = consultant.model_copy(
        update={"adaptability_signals": signals, "data_gaps": data_gaps}
    )
    return _apply_evidence_floor(updated, grounded_spans, config, "low_evidence_adaptability")


def extract_trend(
    consultant: Consultant,
    combined_text: str,
    config: ScoringConfig,
    lm: _LmType = None,
    fallback_lm: _LmType = None,
) -> Consultant:
    predictor = dspy.Predict(PerformanceTrendExtraction)
    if lm is not None:
        result = _run_predict(predictor, lm, fallback_lm, combined_text=combined_text)
    else:
        result = predictor(combined_text=combined_text)
        _tap_lm_history(getattr(dspy.settings, "lm", None), "extract")

    trend_raw: str = getattr(result, "trend", "unknown").strip().lower()
    trend: Literal["improving", "stable", "declining", "unknown"] = (
        trend_raw if trend_raw in _VALID_TRENDS else "unknown"  # type: ignore[assignment]
    )

    evidence_raw: str = getattr(result, "evidence_spans", "[]")
    spans = [s for s in _parse_json_list(evidence_raw) if isinstance(s, str)]
    grounded_spans, any_dropped = _check_grounding(spans, combined_text)

    data_gaps = list(consultant.data_gaps)
    if any_dropped:
        data_gaps.append("ungrounded_trend")

    updated = consultant.model_copy(update={"performance_trend": trend, "data_gaps": data_gaps})
    return _apply_evidence_floor(updated, grounded_spans, config, "low_evidence_trend")
