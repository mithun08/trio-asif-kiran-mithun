from __future__ import annotations

import dspy

from matcher.config import AppConfig


def make_lm(model: str, config: AppConfig) -> dspy.LM:
    return dspy.LM(
        model=model,
        api_key=config.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=2,
        extra_headers={"X-Title": "demand-supply-matcher"},
        extra_body={"provider": {"data_collection": config.provider.data_collection}},
    )


def configure_lm(config: AppConfig) -> dspy.LM:
    if not config.openrouter_api_key:
        raise RuntimeError("DSM_OPENROUTER_API_KEY is not set. Use --no-llm for offline runs.")

    dspy.configure_cache(
        restrict_pickle=True,
        disk_cache_dir=str(config.cache_dir / "dspy"),
    )

    lm = dspy.LM(
        model=config.model_extraction,
        api_key=config.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=3,
        extra_headers={"X-Title": "demand-supply-matcher"},
        extra_body={"provider": {"data_collection": config.provider.data_collection}},
    )
    dspy.configure(lm=lm)
    return lm
