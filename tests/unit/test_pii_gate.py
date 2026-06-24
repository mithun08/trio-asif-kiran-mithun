from __future__ import annotations

import re

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.pipeline.extract import extract_signals
from matcher.pipeline.normalise import scrub_pii

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()\\.]{7,}")


def test_no_pii_reaches_llm(
    consultant_with_pii_in_text: Consultant,
    mock_dspy_lm: list[str],
) -> None:
    scrubbed_consultants = scrub_pii([consultant_with_pii_in_text])
    extract_signals(scrubbed_consultants, ScoringConfig())

    assert len(mock_dspy_lm) >= 1, "Expected at least one LLM call but none were made"

    for payload in mock_dspy_lm:
        assert not _EMAIL_RE.search(payload), f"Email found in LLM payload: {payload!r}"
        assert not _PHONE_RE.search(payload), f"Phone found in LLM payload: {payload!r}"
        assert consultant_with_pii_in_text.name not in payload, (
            f"Consultant name found in LLM payload: {payload!r}"
        )
