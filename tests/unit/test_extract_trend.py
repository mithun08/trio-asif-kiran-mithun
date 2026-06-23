from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.llm.extract import extract_trend
from matcher.models.consultant import Consultant


def _make_consultant() -> Consultant:
    return Consultant(email="test@example.com", name="Test User")


def test_extract_trend_improving(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        trend = "improving"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    result = extract_trend(_make_consultant(), "Good progress notes.", ScoringConfig())
    assert result.performance_trend == "improving"


def test_extract_trend_invalid_defaults_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        trend = "rocketing"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    result = extract_trend(_make_consultant(), "Some text.", ScoringConfig())
    assert result.performance_trend == "unknown"


def test_extract_trend_stable(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        trend = "stable"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    result = extract_trend(_make_consultant(), "Consistent performance.", ScoringConfig())
    assert result.performance_trend == "stable"
