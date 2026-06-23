from __future__ import annotations

import dspy

from matcher.config import AppConfig


def configure_lm(config: AppConfig) -> None:
    if not config.openrouter_api_key:
        raise RuntimeError(
            "DSM_OPENROUTER_API_KEY is not set. Use --no-llm for offline runs."
        )

    lm = dspy.LM(
        model=config.model_extraction,
        api_key=config.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=3,
    )
    dspy.configure(lm=lm)
