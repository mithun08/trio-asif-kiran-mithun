from __future__ import annotations

from datetime import date

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.scoring.dimensions import score_availability

_CFG = ScoringConfig()
_W = ScoringWeights()


def _role(start: date | None = date(2026, 7, 1)) -> Role:
    return Role(id="R1", title="T", start_date=start)


def _consultant(
    available_from: date | None = None,
    supply_state: str = "beach",
    rolloff_confidence: str = "high",
) -> Consultant:
    return Consultant(
        email="c@test.com",
        name="C",
        available_from=available_from,
        supply_state=supply_state,  # type: ignore[arg-type]
        rolloff_confidence=rolloff_confidence,  # type: ignore[arg-type]
    )


def test_beach_available_from_none_scores_100() -> None:
    c = _consultant(supply_state="beach")
    result = score_availability(c, _role(), _W, _CFG)
    assert result.raw_score == 100.0


def test_days_late_zero_scores_100() -> None:
    c = _consultant(available_from=date(2026, 7, 1), supply_state="rolling_off")
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert result.raw_score == 100.0


def test_days_late_at_horizon_scores_0() -> None:
    c = _consultant(available_from=date(2026, 7, 31), supply_state="rolling_off")
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert result.raw_score == 0.0


def test_days_late_beyond_horizon_clamped_to_0() -> None:
    c = _consultant(available_from=date(2026, 9, 1), supply_state="rolling_off")
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert result.raw_score == 0.0


def test_available_before_start_date_scores_100() -> None:
    c = _consultant(available_from=date(2026, 6, 1), supply_state="rolling_off")
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert result.raw_score == 100.0


def test_no_start_date_returns_neutral_50() -> None:
    c = _consultant(supply_state="beach")
    result = score_availability(c, _role(start=None), _W, _CFG)
    assert result.raw_score == 50.0
    assert "no start date" in result.evidence


def test_low_confidence_rolloff_applies_30_pct_penalty() -> None:
    c = _consultant(
        available_from=date(2026, 7, 1), supply_state="rolling_off", rolloff_confidence="low"
    )
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert abs(result.raw_score - 100.0 * (1.0 - 0.30)) < 0.01


def test_high_confidence_no_penalty() -> None:
    c = _consultant(
        available_from=date(2026, 7, 1), supply_state="rolling_off", rolloff_confidence="high"
    )
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert result.raw_score == 100.0


def test_medium_confidence_applies_10_pct_penalty() -> None:
    c = _consultant(
        available_from=date(2026, 7, 1), supply_state="rolling_off", rolloff_confidence="medium"
    )
    result = score_availability(c, _role(start=date(2026, 7, 1)), _W, _CFG)
    assert abs(result.raw_score - 100.0 * 0.90) < 0.01


def test_dimension_weight_is_0_15() -> None:
    c = _consultant(supply_state="beach")
    result = score_availability(c, _role(), _W, _CFG)
    assert result.weight == 0.15
