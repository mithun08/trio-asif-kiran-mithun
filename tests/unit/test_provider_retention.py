from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from matcher.config import AppConfig
from matcher.llm.client import configure_lm


@pytest.fixture
def config_with_key() -> AppConfig:
    return AppConfig(openrouter_api_key="test-key-123")


def test_configure_lm_sends_x_title_header(config_with_key: AppConfig) -> None:
    captured_kwargs: dict[str, Any] = {}

    class MockLM:
        history: list[Any] = []

        def __init__(self, model: str, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    with patch("matcher.llm.client.dspy.LM", MockLM):
        with patch("matcher.llm.client.dspy.configure"):
            configure_lm(config_with_key)

    assert "extra_headers" in captured_kwargs
    assert captured_kwargs["extra_headers"]["X-Title"] == "demand-supply-matcher"


def test_configure_lm_sends_data_collection_deny(config_with_key: AppConfig) -> None:
    captured_kwargs: dict[str, Any] = {}

    class MockLM:
        history: list[Any] = []

        def __init__(self, model: str, **kwargs: Any) -> None:
            captured_kwargs.update(kwargs)

    with patch("matcher.llm.client.dspy.LM", MockLM):
        with patch("matcher.llm.client.dspy.configure"):
            configure_lm(config_with_key)

    assert "extra_body" in captured_kwargs
    assert captured_kwargs["extra_body"] == {"provider": {"data_collection": "deny"}}


def test_configure_lm_no_key_raises_runtime_error() -> None:
    config = AppConfig(openrouter_api_key="")
    with pytest.raises(RuntimeError, match="DSM_OPENROUTER_API_KEY"):
        configure_lm(config)
