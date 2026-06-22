from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant
from matcher.scoring.dimensions import score_supply_state

_CFG = ScoringConfig()


def _consultant(supply_state: str) -> Consultant:
    return Consultant(email="c@test.com", name="C", supply_state=supply_state)  # type: ignore[arg-type]


def test_beach_scores_100() -> None:
    result = score_supply_state(_consultant("beach"), _CFG)
    assert result.raw_score == 100.0


def test_rolling_off_scores_70() -> None:
    result = score_supply_state(_consultant("rolling_off"), _CFG)
    assert result.raw_score == 70.0


def test_new_joiner_scores_40() -> None:
    result = score_supply_state(_consultant("new_joiner"), _CFG)
    assert result.raw_score == 40.0


def test_dimension_name() -> None:
    result = score_supply_state(_consultant("beach"), _CFG)
    assert result.name == "supply_state"


def test_dimension_weight_is_0_05() -> None:
    result = score_supply_state(_consultant("beach"), _CFG)
    assert result.weight == 0.05
