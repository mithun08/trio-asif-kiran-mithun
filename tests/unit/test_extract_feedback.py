from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.llm.extract import extract_feedback
from matcher.models.consultant import Consultant


def _consultant_with_feedback(source: str, text: str) -> Consultant:
    return Consultant(
        email="test@example.com",
        name="Test User",
        feedback_text={source: text},
    )


def test_extract_feedback_maps_positive_sentiment(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        sentiment = "positive"
        strengths = '["strong technical skills"]'
        concerns = "[]"
        client_keep_signal = "false"
        domain_depth = "false"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    consultant = _consultant_with_feedback("project", "Great technical work.")
    result = extract_feedback(consultant, "project", ScoringConfig())

    assert "project" in result.feedback_signals
    signal = result.feedback_signals["project"]
    assert signal.sentiment == "positive"
    assert signal.strengths == ["strong technical skills"]


def test_extract_feedback_client_keep_signal_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        sentiment = "positive"
        strengths = "[]"
        concerns = "[]"
        client_keep_signal = "true"
        domain_depth = "false"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    consultant = _consultant_with_feedback("client", "Please keep this consultant.")
    result = extract_feedback(consultant, "client", ScoringConfig())

    assert result.feedback_signals["client"].client_keep_signal is True


def test_extract_feedback_invalid_sentiment_defaults_neutral(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _MockResult:
        sentiment = "excellent"
        strengths = "[]"
        concerns = "[]"
        client_keep_signal = "false"
        domain_depth = "false"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    consultant = _consultant_with_feedback("project", "Some feedback.")
    result = extract_feedback(consultant, "project", ScoringConfig())

    assert result.feedback_signals["project"].sentiment == "neutral"


def test_extract_feedback_empty_source_returns_unchanged(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: None)

    consultant = Consultant(email="test@example.com", name="Test", feedback_text={})
    result = extract_feedback(consultant, "project", ScoringConfig())

    assert result.feedback_signals == {}
