from __future__ import annotations

import pytest

from matcher.config import ScoringConfig
from matcher.scoring.ranker import band

_CFG = ScoringConfig()


@pytest.mark.parametrize("score,expected", [
    (75.0, "Strong"),
    (100.0, "Strong"),
    (80.0, "Strong"),
    (74.9, "Partial"),
    (40.0, "Partial"),
    (50.0, "Partial"),
    (39.9, "Gap"),
    (0.0, "Gap"),
    (20.0, "Gap"),
])
def test_band_thresholds(score: float, expected: str) -> None:
    assert band(score, _CFG) == expected


def test_band_at_strong_boundary() -> None:
    assert band(_CFG.band_strong, _CFG) == "Strong"


def test_band_just_below_strong() -> None:
    assert band(_CFG.band_strong - 0.1, _CFG) == "Partial"


def test_band_at_partial_boundary() -> None:
    assert band(_CFG.band_partial, _CFG) == "Partial"


def test_band_just_below_partial() -> None:
    assert band(_CFG.band_partial - 0.1, _CFG) == "Gap"
