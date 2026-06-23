from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.pipeline.extract import extract_signals


def _make_full_consultant(index: int) -> Consultant:
    return Consultant(
        email=f"consultant{index}@example.com",
        name=f"Consultant {index}",
        raw_profile_text=f"Profile text for consultant {index}.",
        feedback_text={
            "project": f"Project feedback {index}.",
            "client": f"Client feedback {index}.",
            "beach": f"Beach feedback {index}.",
        },
    )


def test_cold_run_call_count(monkeypatch: pytest.MonkeyPatch) -> None:
    call_count = 0

    class _MockResult:
        sentiment = "positive"
        strengths = "[]"
        concerns = "[]"
        client_keep_signal = "false"
        domain_depth = "false"
        evidence_spans = "[]"
        trend = "stable"
        tech_transitions = "1"
        learning_speed_mentions = "false"
        cross_domain = "1"
        upskilling = "false"
        skills_json = "[]"
        location = ""
        grade = ""

    def _count_and_return(self: object, **kwargs: object) -> _MockResult:
        nonlocal call_count
        call_count += 1
        return _MockResult()

    monkeypatch.setattr("dspy.Predict.__call__", _count_and_return)

    consultants = [_make_full_consultant(i) for i in range(5)]
    extract_signals(consultants, ScoringConfig())

    expected = 5 * 6
    assert call_count == expected, f"Expected {expected} calls, got {call_count}"
