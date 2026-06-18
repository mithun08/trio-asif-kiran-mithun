from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringWeights(BaseModel):
    skill_match: float = 0.35
    feedback_quality: float = 0.25
    availability: float = 0.15
    adaptability: float = 0.15
    supply_state: float = 0.05
    performance_trend: float = 0.05


class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DSM_",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
    )

    openrouter_api_key: str = Field(default="", description="OpenRouter API key")
    model_extraction: str = "openai/gpt-4o-mini"
    model_explain: str = "openai/gpt-4o"
    model_fallback: str = "anthropic/claude-3-haiku"

    data_dir: Path = Path("data/")
    cache_dir: Path = Path(".cache/")

    weights: ScoringWeights = Field(default_factory=ScoringWeights)

    @classmethod
    def from_yaml(cls, path: Path = Path("config/default.yaml")) -> AppConfig:
        if not path.exists():
            return cls()
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        scoring = raw.get("scoring", {})
        weights_data = scoring.get("weights", {})
        models = raw.get("models", {})
        return cls(
            model_extraction=models.get("extraction", "openai/gpt-4o-mini"),
            model_explain=models.get("explanation", "openai/gpt-4o"),
            model_fallback=models.get("fallback", "anthropic/claude-3-haiku"),
            weights=ScoringWeights(**weights_data) if weights_data else ScoringWeights(),
        )
