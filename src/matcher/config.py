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
    feedback_weight_project: float = 0.5
    feedback_weight_client: float = 0.3
    feedback_weight_beach: float = 0.2
    feedback_sent_pos: float = 80.0
    feedback_sent_neutral: float = 50.0
    feedback_sent_neg: float = 20.0
    feedback_kw_keep: float = 10.0
    feedback_kw_domain: float = 5.0
    feedback_kw_concern: float = 10.0
    adapt_pts_transitions: float = 15.0
    adapt_pts_learning: float = 10.0
    adapt_pts_crossdomain: float = 10.0
    adapt_pts_upskill: float = 10.0
    adapt_min_transitions: int = 2
    adapt_min_crossdomain: int = 2
    trend_improving: float = 100.0
    trend_stable: float = 70.0
    trend_declining: float = 30.0
    extract_min_spans: int = 1
    confidence_high_min_projects: int = 2
    confidence_medium_min_sources: int = 1
    beach_long_days: int = 60
    skill_infer_min: float = 0.5
    gap_top_n: int = 3

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
        "feedback_weight_project",
        "feedback_weight_client",
        "feedback_weight_beach",
        mode="before",
    )
    @classmethod
    def _clamp_penalty(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 1.0, info.field_name)

    @field_validator("neutral_baseline", mode="before")
    @classmethod
    def _clamp_neutral(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 100.0, info.field_name)

    @field_validator(
        "feedback_sent_pos",
        "feedback_sent_neutral",
        "feedback_sent_neg",
        "feedback_kw_keep",
        "feedback_kw_domain",
        "feedback_kw_concern",
        "adapt_pts_transitions",
        "adapt_pts_learning",
        "adapt_pts_crossdomain",
        "adapt_pts_upskill",
        "trend_improving",
        "trend_stable",
        "trend_declining",
        mode="before",
    )
    @classmethod
    def _clamp_credit_ext(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 100.0, info.field_name)

    @model_validator(mode="after")
    def _check_feedback_weights(self) -> ScoringConfig:
        total = (
            self.feedback_weight_project + self.feedback_weight_client + self.feedback_weight_beach
        )
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"feedback_weight_* must sum to 1.0, got {total:.6f}")
        return self

    @field_validator(
        "confidence_high_min_projects", "confidence_medium_min_sources", "gap_top_n", mode="before"
    )
    @classmethod
    def _clamp_int_positive(cls, v: object, info: Any) -> int:
        vi: int = int(v)  # type: ignore[call-overload]
        if vi < 1:
            warnings.warn(
                f"ScoringConfig.{info.field_name}={vi} must be ≥ 1; clamped to 1", stacklevel=4
            )
            return 1
        return vi

    @field_validator("beach_long_days", mode="before")
    @classmethod
    def _clamp_beach_days(cls, v: object, info: Any) -> int:
        vi: int = int(v)  # type: ignore[call-overload]
        if vi < 30 or vi > 365:
            warnings.warn(
                f"ScoringConfig.{info.field_name}={vi} out of range [30, 365]; clamped",
                stacklevel=4,
            )
            return max(30, min(365, vi))
        return vi

    @field_validator("skill_infer_min", mode="before")
    @classmethod
    def _clamp_skill_infer(cls, v: object, info: Any) -> float:
        return _clamp(v, 0.0, 1.0, info.field_name)


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
    model_skill_inference: str = "openai/gpt-4o-mini"
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
            model_skill_inference=models.get("skill_inference", "openai/gpt-4o-mini"),
            model_fallback=models.get("fallback", "anthropic/claude-3-haiku"),
            weights=ScoringWeights(**weights_data) if weights_data else ScoringWeights(),
            scoring_config=ScoringConfig(**config_data) if config_data else ScoringConfig(),
        )
