from __future__ import annotations

import asyncio
from typing import Any

from matcher.config import AppConfig, ScoringConfig
from matcher.llm.extract import (
    extract_adaptability,
    extract_feedback,
    extract_profile,
    extract_trend,
)
from matcher.models.consultant import Consultant


def extract_signals(
    consultants: list[Consultant],
    config: ScoringConfig,
    app_config: AppConfig | None = None,
    primary_lm: Any | None = None,
    fallback_lm: Any | None = None,
) -> list[Consultant]:
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
            consultant = extract_profile(consultant, config, primary_lm, fallback_lm)

        for source in list(consultant.feedback_text.keys()):
            consultant = extract_feedback(consultant, source, config, primary_lm, fallback_lm)

        combined_parts = [consultant.raw_profile_text] + list(consultant.feedback_text.values())
        combined_text = "\n".join(part for part in combined_parts if part.strip())

        if combined_text.strip():
            consultant = extract_adaptability(
                consultant, combined_text, config, primary_lm, fallback_lm
            )
            consultant = extract_trend(consultant, combined_text, config, primary_lm, fallback_lm)

        result.append(consultant)

        if app_config is not None:
            from matcher.observability.telemetry import check_budget
            check_budget(app_config.max_cost_usd_per_run, app_config.max_tokens_per_run)

    return result


async def _extract_one(
    consultant: Consultant,
    config: ScoringConfig,
    semaphore: asyncio.Semaphore,
    primary_lm: Any | None,
    fallback_lm: Any | None,
) -> Consultant:
    async with semaphore:
        loop = asyncio.get_running_loop()

        has_profile = bool(consultant.raw_profile_text.strip())
        has_feedback = bool(consultant.feedback_text)

        if not has_profile and not has_feedback:
            return consultant.model_copy(
                update={"data_gaps": [*consultant.data_gaps, "no feedback"]}
            )

        if has_profile:
            consultant = await loop.run_in_executor(
                None, extract_profile, consultant, config, primary_lm, fallback_lm
            )

        for source in list(consultant.feedback_text.keys()):
            consultant = await loop.run_in_executor(
                None, extract_feedback, consultant, source, config, primary_lm, fallback_lm
            )

        combined_parts = [consultant.raw_profile_text] + list(consultant.feedback_text.values())
        combined_text = "\n".join(part for part in combined_parts if part.strip())

        if combined_text.strip():
            consultant = await loop.run_in_executor(
                None,
                extract_adaptability,
                consultant, combined_text, config, primary_lm, fallback_lm,
            )
            consultant = await loop.run_in_executor(
                None,
                extract_trend,
                consultant, combined_text, config, primary_lm, fallback_lm,
            )

        return consultant


async def extract_signals_async(
    consultants: list[Consultant],
    config: ScoringConfig,
    max_workers: int = 5,
    primary_lm: Any | None = None,
    fallback_lm: Any | None = None,
) -> list[Consultant]:
    semaphore = asyncio.Semaphore(max_workers)
    tasks = [_extract_one(c, config, semaphore, primary_lm, fallback_lm) for c in consultants]
    return list(await asyncio.gather(*tasks))
