from __future__ import annotations

import pytest
from pydantic import ValidationError

from matcher.config import AppConfig, ScoringConfig, ScoringWeights, load_adjacency


def test_weights_valid_sum_accepted() -> None:
    w = ScoringWeights(
        skill_match=0.35,
        feedback_quality=0.25,
        availability=0.15,
        adaptability=0.15,
        supply_state=0.05,
        performance_trend=0.05,
    )
    assert abs(sum(w.model_dump().values()) - 1.0) < 1e-6


def test_weights_bad_sum_rejected() -> None:
    with pytest.raises(ValidationError):
        ScoringWeights(
            skill_match=0.35,
            feedback_quality=0.25,
            availability=0.15,
            adaptability=0.15,
            supply_state=0.05,
            performance_trend=0.10,
        )


def test_scoring_config_defaults_in_range() -> None:
    sc = ScoringConfig()
    assert 0.0 <= sc.band_strong <= 100.0
    assert 0.0 <= sc.band_partial <= 100.0
    assert 0.0 <= sc.c_exact <= 100.0
    assert 0.0 <= sc.c_prof <= 100.0
    assert 0.0 <= sc.c_adjacent <= 100.0
    assert 0.0 <= sc.c_newjoiner <= 100.0


def test_scoring_config_clamps_band_over_100() -> None:
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sc = ScoringConfig(band_strong=150.0)
    assert sc.band_strong == 100.0
    assert any("band_strong" in str(warning.message) for warning in w)


def test_scoring_config_clamps_credit_below_zero() -> None:
    import warnings

    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        sc = ScoringConfig(c_exact=-10.0)
    assert sc.c_exact == 0.0
    assert any("c_exact" in str(warning.message) for warning in w)


def test_app_config_from_yaml_loads_scoring_config(tmp_path: object) -> None:
    from pathlib import Path

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.scoring_config.band_strong == 75.0
    assert config.scoring_config.neutral_baseline == 50.0


def test_load_adjacency_lowercases_keys() -> None:
    from pathlib import Path

    adj = load_adjacency(Path("config/skill_adjacency.yaml"))
    assert "kotlin" in adj
    assert "java" in adj["kotlin"]


def test_feedback_weights_valid_sum_accepted() -> None:
    sc = ScoringConfig(
        feedback_weight_project=0.5, feedback_weight_client=0.3, feedback_weight_beach=0.2
    )
    total = sc.feedback_weight_project + sc.feedback_weight_client + sc.feedback_weight_beach
    assert abs(total - 1.0) < 1e-6


def test_feedback_weights_bad_sum_rejected() -> None:
    with pytest.raises(ValidationError):
        ScoringConfig(
            feedback_weight_project=0.5, feedback_weight_client=0.3, feedback_weight_beach=0.3
        )


def test_yaml_loads_new_feedback_fields() -> None:
    from pathlib import Path
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.scoring_config.feedback_sent_pos == 80.0
    assert config.scoring_config.adapt_pts_transitions == 15.0
    assert config.scoring_config.trend_improving == 100.0
