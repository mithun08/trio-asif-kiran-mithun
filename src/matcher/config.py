from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ScoringWeights(BaseModel):
    skill_match: float = 0.35
    feedback_quality: float = 0.25
    availability: float = 0.15
    adaptability: float = 0.15
    supply_state: float = 0.05
    performance_trend: float = 0.05

    @model_validator(mode="after")
    def _check_sum(self) -> ScoringWeights:
        total = sum(self.model_dump().values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"ScoringWeights must sum to 1.0, got {total:.6f}")
        return self


def _clamp(value: object, lo: float, hi: float, field: str) -> float:
    v = float(value)  # type: ignore[arg-type]
    if v < lo or v > hi:
        warnings.warn(f"ScoringConfig.{field}={v} out of range [{lo}, {hi}]; clamped", stacklevel=4)
        return max(lo, min(hi, v))
    return v


class ScoringConfig(BaseModel):
    band_strong: float = 75.0
    band_partial: float = 40.0
    c_exact: float = 100.0
    c_prof: float = 70.0
    c_adjacent: float = 60.0
    c_newjoiner: float = 40.0
    nth_bonus_per: float = 5.0
    nth_bonus_cap: float = 10.0
    avail_horizon_days: int = 30
    rolloff_buffer: int = 5
    new_joiner_buffer: int = 7
    rolloff_penalty_high: float = 0.0
    rolloff_penalty_medium: float = 0.10
    rolloff_penalty_low: float = 0.30
    supply_beach: float = 100.0
    supply_rolloff: float = 70.0
    supply_newjoiner: float = 40.0
    neutral_baseline: float = 50.0

    @field_validator("band_strong", "band_partial", mode="before")
    @classmethod
    def _clamp_band(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 100.0, info.field_name)

    @field_validator(
        "c_exact",
        "c_prof",
        "c_adjacent",
        "c_newjoiner",
        "nth_bonus_per",
        "nth_bonus_cap",
        mode="before",
    )
    @classmethod
    def _clamp_credit(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 100.0, info.field_name)

    @field_validator(
        "rolloff_penalty_high",
        "rolloff_penalty_medium",
        "rolloff_penalty_low",
        mode="before",
    )
    @classmethod
    def _clamp_penalty(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 1.0, info.field_name)

    @field_validator("neutral_baseline", mode="before")
    @classmethod
    def _clamp_neutral(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 100.0, info.field_name)


def load_adjacency(path: Path = Path("config/skill_adjacency.yaml")) -> dict[str, list[str]]:
    raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
    return {k.lower(): [s.lower() for s in v] for k, v in raw.get("adjacency", {}).items()}


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
    scoring_config: ScoringConfig = Field(default_factory=ScoringConfig)

    @classmethod
    def from_yaml(cls, path: Path = Path("config/default.yaml")) -> AppConfig:
        if not path.exists():
            return cls()
        raw: dict[str, Any] = yaml.safe_load(path.read_text()) or {}
        scoring = raw.get("scoring", {})
        weights_data = scoring.get("weights", {})
        config_data = scoring.get("config", {})
        models = raw.get("models", {})
        return cls(
            model_extraction=models.get("extraction", "openai/gpt-4o-mini"),
            model_explain=models.get("explanation", "openai/gpt-4o"),
            model_fallback=models.get("fallback", "anthropic/claude-3-haiku"),
            weights=ScoringWeights(**weights_data) if weights_data else ScoringWeights(),
            scoring_config=ScoringConfig(**config_data) if config_data else ScoringConfig(),
        )
