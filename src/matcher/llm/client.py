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

    # No dspy.configure(lm=...) here: it permanently binds whichever thread calls
    # it first as the sole "owner" thread for the rest of the process (Streamlit
    # spawns a new thread per script rerun, so a second caller crashes with
    # "dspy.settings can only be changed by the thread that initially configured
    # it"). Every predictor call in this codebase already threads its lm through
    # dspy.context(lm=...), so no global default is needed.
    return dspy.LM(
        model=config.model_extraction,
        api_key=config.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=3,
        extra_headers={"X-Title": "demand-supply-matcher"},
        extra_body={"provider": {"data_collection": config.provider.data_collection}},
    )
