from __future__ import annotations

from matcher.config import ScoringConfig
from matcher.models.score import DimensionScore, ScoredCandidate
from matcher.scoring.ranker import rank_candidates

_CFG = ScoringConfig()


def _candidate(
    email: str,
    total_score: float,
    avail_raw: float = 50.0,
    supply_raw: float = 100.0,
    data_confidence: float = 1.0,
) -> ScoredCandidate:
    return ScoredCandidate(
        consultant_email=email,
        consultant_name=email,
        total_score=total_score,
        rank=0,
        data_confidence=data_confidence,
        dimensions=[
            DimensionScore(
                name="availability", raw_score=avail_raw,
                weight=0.15, weighted_score=avail_raw * 0.15,
            ),
            DimensionScore(
                name="supply_state", raw_score=supply_raw,
                weight=0.05, weighted_score=supply_raw * 0.05,
            ),
        ],
    )


def test_rank_sorted_by_total_score_descending() -> None:
    candidates = [
        _candidate("a@x.com", total_score=60.0),
        _candidate("b@x.com", total_score=80.0),
        _candidate("c@x.com", total_score=70.0),
    ]
    result = rank_candidates(candidates, _CFG)
    assert result[0].consultant_email == "b@x.com"
    assert result[1].consultant_email == "c@x.com"
    assert result[2].consultant_email == "a@x.com"


def test_rank_assigned_correctly() -> None:
    candidates = [_candidate("a@x.com", 80.0), _candidate("b@x.com", 60.0)]
    result = rank_candidates(candidates, _CFG)
    assert result[0].rank == 1
    assert result[1].rank == 2


def test_equal_total_scores_share_rank() -> None:
    candidates = [
        _candidate("a@x.com", total_score=70.0, avail_raw=50.0, supply_raw=100.0),
        _candidate("b@x.com", total_score=70.0, avail_raw=50.0, supply_raw=100.0),
    ]
    result = rank_candidates(candidates, _CFG)
    assert result[0].rank == result[1].rank


def test_tiebreak_by_availability_score() -> None:
    candidates = [
        _candidate("low_avail@x.com", total_score=70.0, avail_raw=40.0),
        _candidate("high_avail@x.com", total_score=70.0, avail_raw=90.0),
    ]
    result = rank_candidates(candidates, _CFG)
    assert result[0].consultant_email == "high_avail@x.com"


def test_tiebreak_by_data_confidence() -> None:
    candidates = [
        _candidate("low_conf@x.com", total_score=70.0, avail_raw=80.0, data_confidence=0.5),
        _candidate("high_conf@x.com", total_score=70.0, avail_raw=80.0, data_confidence=1.0),
    ]
    result = rank_candidates(candidates, _CFG)
    assert result[0].consultant_email == "high_conf@x.com"


def test_tiebreak_by_supply_state_score() -> None:
    candidates = [
        _candidate("low_supply@x.com", total_score=70.0, avail_raw=80.0, supply_raw=40.0),
        _candidate("high_supply@x.com", total_score=70.0, avail_raw=80.0, supply_raw=100.0),
    ]
    result = rank_candidates(candidates, _CFG)
    assert result[0].consultant_email == "high_supply@x.com"


def test_empty_list_returns_empty() -> None:
    assert rank_candidates([], _CFG) == []
