from __future__ import annotations

import pytest
from pydantic import ValidationError

from matcher.config import AppConfig


def test_allowed_models_valid_combo_passes() -> None:
    config = AppConfig(
        openrouter_api_key="test",
        model_extraction="openai/gpt-4o-mini",
        model_explain="openai/gpt-4o-mini",
        model_skill_inference="openai/gpt-4o-mini",
        allowed_models=["openai/gpt-4o-mini", "openai/gpt-4o"],
    )
    assert "openai/gpt-4o-mini" in config.allowed_models


def test_allowed_models_extraction_outside_list_raises() -> None:
    with pytest.raises(ValidationError, match="model_extraction"):
        AppConfig(
            openrouter_api_key="test",
            model_extraction="openai/gpt-4o",
            model_explain="openai/gpt-4o-mini",
            model_skill_inference="openai/gpt-4o-mini",
            allowed_models=["openai/gpt-4o-mini"],
        )


def test_allowed_models_empty_skips_validation() -> None:
    config = AppConfig(
        openrouter_api_key="test",
        model_extraction="openai/gpt-4o",
        allowed_models=[],
    )
    assert config.model_extraction == "openai/gpt-4o"
