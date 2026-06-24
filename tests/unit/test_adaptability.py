from __future__ import annotations

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.models.signals import AdaptabilitySignals
from matcher.scoring.dimensions import score_adaptability

_WEIGHTS = ScoringWeights()
_CONFIG = ScoringConfig()


def _consultant_with_signals(signals: AdaptabilitySignals | None) -> Consultant:
    return Consultant(
        email="test@example.com",
        name="Test",
        adaptability_signals=signals,
    )


def test_full_signals_scores_95() -> None:
    signals = AdaptabilitySignals(
        tech_transitions=3,
        learning_speed_mentions=True,
        cross_domain=2,
        upskilling=True,
    )
    consultant = _consultant_with_signals(signals)
    result = score_adaptability(consultant, _WEIGHTS, _CONFIG)

    expected = 50.0 + 15.0 + 10.0 + 10.0 + 10.0
    assert abs(result.raw_score - expected) < 0.01


def test_no_signals_returns_neutral_50() -> None:
    consultant = _consultant_with_signals(None)
    result = score_adaptability(consultant, _WEIGHTS, _CONFIG)

    assert result.raw_score == _CONFIG.neutral_baseline
    assert "no data" in result.evidence


def test_transitions_below_minimum_no_bonus() -> None:
    signals = AdaptabilitySignals(tech_transitions=1)
    consultant = _consultant_with_signals(signals)
    result = score_adaptability(consultant, _WEIGHTS, _CONFIG)

    assert result.raw_score == _CONFIG.neutral_baseline


def test_score_capped_at_100() -> None:
    config = ScoringConfig(
        adapt_pts_transitions=40.0,
        adapt_pts_learning=40.0,
        adapt_pts_crossdomain=40.0,
        adapt_pts_upskill=40.0,
    )
    signals = AdaptabilitySignals(
        tech_transitions=5,
        learning_speed_mentions=True,
        cross_domain=5,
        upskilling=True,
    )
    consultant = _consultant_with_signals(signals)
    result = score_adaptability(consultant, _WEIGHTS, config)

    assert result.raw_score == 100.0
