from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from matcher.observability import telemetry as _tel
from matcher.pipeline.free_text_role import parse, resolve_relative_date

_TODAY = date(2026, 7, 6)


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    return lm


def _mock_lm_with_history(prompt_tokens: int = 50, completion_tokens: int = 20) -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    lm.model = "openai/gpt-4o-mini"
    lm.history = [
        {
            "usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            "cost": 0.001,
            "model": "openai/gpt-4o-mini",
        }
    ]
    return lm


def _mock_result(**overrides: str) -> MagicMock:
    defaults = {
        "title": "Senior Python Engineer",
        "skills_json": '[{"name": "Python", "polarity": "require", "min_proficiency": null}]',
        "include_locations_json": "[]",
        "exclude_locations_json": "[]",
        "exclude_supply_states_json": "[]",
        "relative_start_phrase": "",
    }
    defaults.update(overrides)
    result = MagicMock()
    for key, value in defaults.items():
        setattr(result, key, value)
    return result


# ---- deterministic fallback (--no-llm), unchanged regex behavior ----


def test_deterministic_finds_known_skill_and_location() -> None:
    role, ambiguities = parse(
        "Need a Python Engineer in Chennai starting 2026-08-01",
        known_locations={"Chennai"},
        known_skills={"Python"},
    )
    assert role.required_skills[0].name == "Python"
    assert role.locations == ["Chennai"]
    assert role.start_date == date(2026, 8, 1)
    assert ambiguities == []


def test_deterministic_flags_missing_skill_location_date() -> None:
    _role, ambiguities = parse("hello there", known_locations=set(), known_skills=set())
    assert "skills: no recognised skills found" in ambiguities
    assert "location: no recognised location found" in ambiguities
    assert "start_date: no date found in text" in ambiguities


def test_deterministic_ignores_negation() -> None:
    # Known limitation of the deterministic fallback — no polarity concept.
    role, _ambiguities = parse(
        "Python engineer, not based in Chennai",
        known_locations={"Chennai"},
        known_skills={"Python"},
    )
    assert role.locations == ["Chennai"]
    assert role.exclude_locations == []


# ---- resolve_relative_date ----


def test_resolve_iso_date() -> None:
    assert resolve_relative_date("2026-08-15", _TODAY) == date(2026, 8, 15)


def test_resolve_asap() -> None:
    assert resolve_relative_date("ASAP", _TODAY) == _TODAY


def test_resolve_immediately() -> None:
    assert resolve_relative_date("start immediately", _TODAY) == _TODAY


def test_resolve_tomorrow() -> None:
    assert resolve_relative_date("tomorrow", _TODAY) == date(2026, 7, 7)


def test_resolve_next_week() -> None:
    assert resolve_relative_date("next week", _TODAY) == date(2026, 7, 13)


def test_resolve_next_month_bare() -> None:
    assert resolve_relative_date("next month", _TODAY) == date(2026, 8, 1)


def test_resolve_mid_next_month() -> None:
    assert resolve_relative_date("mid of next month", _TODAY) == date(2026, 8, 15)
    assert resolve_relative_date("middle next month", _TODAY) == date(2026, 8, 15)


def test_resolve_end_of_next_month() -> None:
    assert resolve_relative_date("end of next month", _TODAY) == date(2026, 8, 31)


def test_resolve_end_of_next_month_short_month() -> None:
    assert resolve_relative_date("end of next month", date(2026, 1, 15)) == date(2026, 2, 28)


def test_resolve_in_n_days() -> None:
    assert resolve_relative_date("in 10 days", _TODAY) == date(2026, 7, 16)


def test_resolve_in_n_weeks() -> None:
    assert resolve_relative_date("in 2 weeks", _TODAY) == date(2026, 7, 20)


def test_resolve_in_n_months() -> None:
    assert resolve_relative_date("in 3 months", _TODAY) == date(2026, 10, 6)


def test_resolve_unrecognised_phrase_returns_none() -> None:
    assert resolve_relative_date("sometime soon-ish", _TODAY) is None


def test_resolve_empty_phrase_returns_none() -> None:
    assert resolve_relative_date("", _TODAY) is None


# ---- LLM path ----


def test_llm_path_records_telemetry() -> None:
    _tel.reset()
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = _mock_result()
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            parse(
                "Senior Python engineer",
                set(),
                set(),
                lm=_mock_lm_with_history(),
                today=_TODAY,
            )
    assert _tel.current_telemetry.llm_calls == 1
    assert _tel.current_telemetry.total_tokens == 70


def test_llm_path_parses_require_skill() -> None:
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = _mock_result()
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, _ = parse("Senior Python engineer", set(), set(), lm=_mock_lm(), today=_TODAY)
    assert role.required_skills[0].name == "Python"
    assert role.required_skills[0].mandatory is True


def test_llm_path_parses_exclude_skill_not_hard_dropped_from_required() -> None:
    result = _mock_result(
        skills_json=(
            '[{"name": "Kotlin", "polarity": "require", "min_proficiency": null},'
            ' {"name": "Scala", "polarity": "exclude", "min_proficiency": null}]'
        )
    )
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, _ = parse("Kotlin but not Scala", set(), set(), lm=_mock_lm(), today=_TODAY)
    assert [s.name for s in role.required_skills] == ["Kotlin"]
    assert role.exclude_skills == ["Scala"]


def test_llm_path_parses_exclude_location() -> None:
    result = _mock_result(exclude_locations_json='["Chennai"]')
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, _ = parse(
                "Python engineer, not based in Chennai", set(), set(), lm=_mock_lm(), today=_TODAY
            )
    assert role.exclude_locations == ["Chennai"]


def test_llm_path_normalises_include_location_and_sets_co_located() -> None:
    result = _mock_result(include_locations_json='["Bangalore"]')
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, _ = parse(
                "Python engineer in Bangalore", set(), set(), lm=_mock_lm(), today=_TODAY
            )
    assert role.locations == ["Bengaluru"]
    assert role.co_located is True


def test_llm_path_parses_exclude_supply_state() -> None:
    result = _mock_result(exclude_supply_states_json='["new_joiner"]')
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, _ = parse(
                "Python engineer, not a new joiner", set(), set(), lm=_mock_lm(), today=_TODAY
            )
    assert role.exclude_supply_states == ["new_joiner"]


def test_llm_path_resolves_relative_start_phrase() -> None:
    result = _mock_result(relative_start_phrase="ASAP")
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, ambiguities = parse(
                "Python engineer, available ASAP", set(), set(), lm=_mock_lm(), today=_TODAY
            )
    assert role.start_date == _TODAY
    assert not any("start_date" in a for a in ambiguities)


def test_llm_path_unresolvable_phrase_flags_ambiguity() -> None:
    result = _mock_result(relative_start_phrase="sometime soon-ish")
    with patch("matcher.pipeline.free_text_role.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = result
        with patch("matcher.pipeline.free_text_role.dspy.context"):
            role, ambiguities = parse("Python engineer", set(), set(), lm=_mock_lm(), today=_TODAY)
    assert role.start_date is None
    assert any("could not resolve phrase" in a for a in ambiguities)
