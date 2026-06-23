from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.llm.extract import (
    extract_adaptability,
    extract_feedback,
    extract_profile,
    extract_trend,
)
from matcher.models.consultant import Consultant


def extract_signals(consultants: list[Consultant], config: ScoringConfig) -> list[Consultant]:
    result: list[Consultant] = []

    for consultant in consultants:
        has_profile = bool(consultant.raw_profile_text.strip())
        has_feedback = bool(consultant.feedback_text)

        if not has_profile and not has_feedback:
            flagged = consultant.model_copy(
                update={"data_gaps": [*consultant.data_gaps, "no feedback"]}
            )
            result.append(flagged)
            continue

        if has_profile:
            consultant = extract_profile(consultant, config)

        for source in list(consultant.feedback_text.keys()):
            consultant = extract_feedback(consultant, source, config)

        combined_parts = [consultant.raw_profile_text] + list(consultant.feedback_text.values())
        combined_text = "\n".join(part for part in combined_parts if part.strip())

        if combined_text.strip():
            consultant = extract_adaptability(consultant, combined_text, config)
            consultant = extract_trend(consultant, combined_text, config)

        result.append(consultant)

    return result
