from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from matcher.config import AppConfig, ScoringConfig
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill
from matcher.scoring.dimensions import _best_credit


def _make_consultant(email: str = "a@b.com", skills: list[str] | None = None) -> Consultant:
    skill_objs = [Skill(name=s, proficiency=3, years_experience=1.0) for s in (skills or [])]
    return Consultant(email=email, name="A", skills=skill_objs)


def test_exact_match_no_index() -> None:
    c = _make_consultant(skills=["Python"])
    req = RequiredSkill(name="Python", mandatory=True)
    assert _best_credit(req, c, {}, ScoringConfig()) == 100.0


def test_no_match_no_index_returns_zero() -> None:
    c = _make_consultant(skills=["Java"])
    req = RequiredSkill(name="Python", mandatory=True)
    assert _best_credit(req, c, {}, ScoringConfig()) == 0.0


def _make_mock_model(vec: list[float] | None = None) -> MagicMock:
    enc = MagicMock()
    enc.tolist.return_value = vec or [0.1] * 384
    mock_model = MagicMock()
    mock_model.encode.return_value = enc
    return mock_model


def test_vector_tier_awards_c_vector() -> None:
    # Milvus COSINE metric returns distance = 1 - similarity; a similarity of
    # 0.80 (well above the 0.65 threshold) is reported as distance=0.20.
    mock_client = MagicMock()
    mock_client.search.return_value = [[{"distance": 0.20, "skill_name": "TypeScript"}]]

    c = _make_consultant(skills=["TypeScript"])
    req = RequiredSkill(name="JavaScript", mandatory=True)
    config = ScoringConfig()
    result = _best_credit(req, c, {}, config, mock_client, _make_mock_model())
    assert result == config.c_vector


def test_vector_tier_skipped_below_threshold() -> None:
    # similarity=0.40 (below threshold) is reported as distance=0.60.
    mock_client = MagicMock()
    mock_client.search.return_value = [[{"distance": 0.60, "skill_name": "TypeScript"}]]

    c = _make_consultant(skills=["TypeScript"])
    req = RequiredSkill(name="JavaScript", mandatory=True)
    result = _best_credit(req, c, {}, ScoringConfig(), mock_client, _make_mock_model())
    assert result == 0.0


def test_vector_tier_high_distance_regression() -> None:
    # Regression for a real bug: a high *distance* (0.80, i.e. low similarity
    # 0.20 — genuinely dissimilar skills, e.g. "plumber" vs "kafka" on the
    # real trained index) must NOT be awarded credit. The original code
    # compared raw distance >= threshold directly, which is backwards for a
    # distance metric and inflated credit for dissimilar skill pairs.
    mock_client = MagicMock()
    mock_client.search.return_value = [[{"distance": 0.80, "skill_name": "Kafka"}]]

    c = _make_consultant(skills=["Kafka"])
    req = RequiredSkill(name="Plumber", mandatory=True)
    result = _best_credit(req, c, {}, ScoringConfig(), mock_client, _make_mock_model())
    assert result == 0.0


def test_scoring_config_has_vector_fields() -> None:
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.scoring_config.skill_vector_similarity == 0.65
    assert config.scoring_config.c_vector == 65.0
