from __future__ import annotations

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.models.signals import FeedbackSignal
from matcher.scoring.dimensions import score_feedback_quality

_WEIGHTS = ScoringWeights()
_CONFIG = ScoringConfig()


def _consultant_with_signals(**signals: FeedbackSignal) -> Consultant:
    return Consultant(
        email="test@example.com",
        name="Test",
        feedback_signals=dict(signals),
    )


def test_no_feedback_signals_returns_neutral() -> None:
    consultant = Consultant(email="test@example.com", name="Test")
    result = score_feedback_quality(consultant, _WEIGHTS, _CONFIG)

    assert result.raw_score == _CONFIG.neutral_baseline
    assert "no feedback" in result.evidence


def test_client_positive_with_keep_signal_sub_score_90() -> None:
    signal = FeedbackSignal(sentiment="positive", client_keep_signal=True)
    consultant = _consultant_with_signals(client=signal)
    result = score_feedback_quality(consultant, _WEIGHTS, _CONFIG)

    client_sub = 80.0 + 10.0
    project_sub = _CONFIG.neutral_baseline
    beach_sub = _CONFIG.neutral_baseline
    expected = (
        _CONFIG.feedback_weight_project * project_sub
        + _CONFIG.feedback_weight_client * client_sub
        + _CONFIG.feedback_weight_beach * beach_sub
    )
    assert abs(result.raw_score - round(expected, 2)) < 0.01


def test_project_positive_with_domain_depth_sub_score_85() -> None:
    signal = FeedbackSignal(sentiment="positive", domain_depth=True)
    consultant = _consultant_with_signals(project=signal)
    result = score_feedback_quality(consultant, _WEIGHTS, _CONFIG)

    project_sub = 80.0 + 5.0
    client_sub = _CONFIG.neutral_baseline
    beach_sub = _CONFIG.neutral_baseline
    expected = (
        _CONFIG.feedback_weight_project * project_sub
        + _CONFIG.feedback_weight_client * client_sub
        + _CONFIG.feedback_weight_beach * beach_sub
    )
    assert abs(result.raw_score - round(expected, 2)) < 0.01


def test_aarav_composite_matches_scoring_spec() -> None:
    project_signal = FeedbackSignal(sentiment="positive", domain_depth=True)
    client_signal = FeedbackSignal(sentiment="positive", client_keep_signal=True)
    consultant = _consultant_with_signals(project=project_signal, client=client_signal)

    result = score_feedback_quality(consultant, _WEIGHTS, _CONFIG)

    project_sub = 85.0
    client_sub = 90.0
    beach_sub = _CONFIG.neutral_baseline
    expected = 0.5 * project_sub + 0.3 * client_sub + 0.2 * beach_sub
    assert abs(result.raw_score - round(expected, 2)) < 0.1


def test_missing_source_uses_neutral_with_evidence_tag() -> None:
    signal = FeedbackSignal(sentiment="positive")
    consultant = _consultant_with_signals(project=signal)
    result = score_feedback_quality(consultant, _WEIGHTS, _CONFIG)

    assert any("no client feedback" in e for e in result.evidence)
    assert any("no beach feedback" in e for e in result.evidence)


def test_config_change_alters_score() -> None:
    signal = FeedbackSignal(sentiment="positive")
    consultant = _consultant_with_signals(project=signal, client=signal, beach=signal)

    config_a = ScoringConfig(feedback_sent_pos=80.0)
    config_b = ScoringConfig(feedback_sent_pos=90.0)

    score_a = score_feedback_quality(consultant, _WEIGHTS, config_a).raw_score
    score_b = score_feedback_quality(consultant, _WEIGHTS, config_b).raw_score

    assert score_b > score_a
