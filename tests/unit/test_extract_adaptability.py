from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.llm.extract import extract_adaptability
from matcher.models.consultant import Consultant


def test_extract_adaptability_maps_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        tech_transitions = "3"
        learning_speed_mentions = "true"
        cross_domain = "2"
        upskilling = "false"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    consultant = Consultant(email="test@example.com", name="Test")
    result = extract_adaptability(consultant, "Some profile text.", ScoringConfig())

    assert result.adaptability_signals is not None
    assert result.adaptability_signals.tech_transitions == 3
    assert result.adaptability_signals.learning_speed_mentions is True
    assert result.adaptability_signals.cross_domain == 2
    assert result.adaptability_signals.upskilling is False


def test_extract_adaptability_invalid_int_defaults_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    class _MockResult:
        tech_transitions = "not-a-number"
        learning_speed_mentions = "false"
        cross_domain = "N/A"
        upskilling = "false"
        evidence_spans = "[]"

    monkeypatch.setattr("dspy.Predict.__call__", lambda self, **kwargs: _MockResult())

    consultant = Consultant(email="test@example.com", name="Test")
    result = extract_adaptability(consultant, "Some text.", ScoringConfig())

    assert result.adaptability_signals is not None
    assert result.adaptability_signals.tech_transitions == 0
    assert result.adaptability_signals.cross_domain == 0
