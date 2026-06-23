from __future__ import annotations

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.scoring.dimensions import score_performance_trend

_WEIGHTS = ScoringWeights()
_CONFIG = ScoringConfig()


def _consultant_with_trend(trend: str) -> Consultant:
    return Consultant(
        email="test@example.com",
        name="Test",
        performance_trend=trend,  # type: ignore[arg-type]
    )


def test_improving_scores_100() -> None:
    result = score_performance_trend(_consultant_with_trend("improving"), _WEIGHTS, _CONFIG)
    assert result.raw_score == 100.0


def test_stable_scores_70() -> None:
    result = score_performance_trend(_consultant_with_trend("stable"), _WEIGHTS, _CONFIG)
    assert result.raw_score == 70.0


def test_declining_scores_30() -> None:
    result = score_performance_trend(_consultant_with_trend("declining"), _WEIGHTS, _CONFIG)
    assert result.raw_score == 30.0


def test_unknown_scores_neutral_50() -> None:
    result = score_performance_trend(_consultant_with_trend("unknown"), _WEIGHTS, _CONFIG)
    assert result.raw_score == _CONFIG.neutral_baseline


def test_config_override_changes_improving_score() -> None:
    config = ScoringConfig(trend_improving=80.0)
    result = score_performance_trend(_consultant_with_trend("improving"), _WEIGHTS, config)
    assert result.raw_score == 80.0
