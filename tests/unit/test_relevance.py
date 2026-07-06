from __future__ import annotations

from unittest.mock import MagicMock, patch

from matcher.config import ScoringConfig
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role
from matcher.pipeline.relevance import check_domain_plausibility, check_skill_evidence

_CFG = ScoringConfig()
_ADJ: dict[str, list[str]] = {}


def _role(*skills: RequiredSkill, title: str = "T") -> Role:
    return Role(id="R1", title=title, required_skills=list(skills))


def _consultant(*skills: Skill, supply_state: str = "beach") -> Consultant:
    return Consultant(
        email="c@test.com",
        name="C",
        skills=list(skills),
        supply_state=supply_state,  # type: ignore[arg-type]
    )


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.__class__.__name__ = "LM"
    return lm


def _mock_result(**overrides: str) -> MagicMock:
    result = MagicMock()
    for key, value in {"in_domain": "true", "reason": "", "plausible": "true"}.items():
        setattr(result, key, overrides.get(key, value))
    return result


# ---- tier 1a: consultant skill evidence ----


def test_tier1a_passes_when_consultant_evidence_exists() -> None:
    role = _role(RequiredSkill(name="Python"))
    consultants = [_consultant(Skill(name="Python", proficiency=3))]
    verdict = check_skill_evidence(role, consultants, [role], _ADJ, _CFG)
    assert verdict is not None
    assert verdict.in_domain is True


def test_tier1a_ignores_new_joiner_fallback() -> None:
    role = _role(RequiredSkill(name="Plumber"))
    consultants = [_consultant(Skill(name="Python", proficiency=3), supply_state="new_joiner")]
    verdict = check_skill_evidence(role, consultants, [], _ADJ, _CFG)
    assert verdict is not None
    assert verdict.in_domain is False


def test_returns_none_when_no_skills_parsed() -> None:
    role = _role(title="Unknown Role")
    assert check_skill_evidence(role, [], [], _ADJ, _CFG) is None


# ---- tier 1b: role-vocabulary evidence (supply gap, not out-of-domain) ----


def test_tier1b_passes_on_role_vocab_match_with_zero_supply() -> None:
    # "leadership" is a real skill required by some role in the workbook, even
    # though no current consultant has it — a supply gap, not an out-of-domain query.
    other_role = _role(RequiredSkill(name="Leadership"), title="Other")
    query_role = _role(RequiredSkill(name="leadership"))
    verdict = check_skill_evidence(query_role, [], [other_role, query_role], _ADJ, _CFG)
    assert verdict is not None
    assert verdict.in_domain is True


def test_tier1b_does_not_rescue_true_nonsense() -> None:
    role = _role(RequiredSkill(name="Plumber"))
    verdict = check_skill_evidence(role, [], [], _ADJ, _CFG)
    assert verdict is not None
    assert verdict.in_domain is False


# ---- tier 1c: LLM escalation when 1a+1b both miss ----


def test_tier1c_rescues_plausible_novel_skill() -> None:
    role = _role(RequiredSkill(name="Rust"))
    with patch("matcher.pipeline.relevance.dspy.ChainOfThought") as mock_cot:
        mock_cot.return_value.return_value = _mock_result(plausible="true")
        with patch("matcher.pipeline.relevance.dspy.context"):
            verdict = check_skill_evidence(
                role, [], [], _ADJ, _CFG, lm=_mock_lm(), query_text="Rust engineer"
            )
    assert verdict is not None
    assert verdict.in_domain is True
    mock_cot.assert_called_once()


def test_tier1c_still_rejects_true_nonsense() -> None:
    role = _role(RequiredSkill(name="Plumber"))
    with patch("matcher.pipeline.relevance.dspy.ChainOfThought") as mock_cot:
        mock_cot.return_value.return_value = _mock_result(
            plausible="false", reason="plumbing is an unrelated trade"
        )
        with patch("matcher.pipeline.relevance.dspy.context"):
            verdict = check_skill_evidence(
                role, [], [], _ADJ, _CFG, lm=_mock_lm(), query_text="plumber"
            )
    assert verdict is not None
    assert verdict.in_domain is False
    assert "plumbing" in verdict.reason


def test_tier1c_skipped_without_lm_falls_back_to_reject() -> None:
    role = _role(RequiredSkill(name="Plumber"))
    verdict = check_skill_evidence(role, [], [], _ADJ, _CFG, lm=None)
    assert verdict is not None
    assert verdict.in_domain is False


def test_tier1c_only_invoked_when_1a_and_1b_both_miss() -> None:
    role = _role(RequiredSkill(name="Python"))
    consultants = [_consultant(Skill(name="Python", proficiency=3))]
    with patch("matcher.pipeline.relevance.dspy.ChainOfThought") as mock_cot:
        check_skill_evidence(
            role, consultants, [role], _ADJ, _CFG, lm=_mock_lm(), query_text="python engineer"
        )
    mock_cot.assert_not_called()


# ---- tier 2: classifier fallback when no skills were parsed at all ----


def test_tier2_trips_on_off_domain_query() -> None:
    role = _role(title="Unknown Role")
    with patch("matcher.pipeline.relevance.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = _mock_result(
            in_domain="false", reason="this is a math question, not a staffing request"
        )
        with patch("matcher.pipeline.relevance.dspy.context"):
            verdict = check_domain_plausibility("what is 47 * 12", role, lm=_mock_lm())
    assert verdict is not None
    assert verdict.in_domain is False
    assert "math" in verdict.reason


def test_tier2_passes_legitimate_skill_less_query() -> None:
    role = _role(title="Bench availability")
    with patch("matcher.pipeline.relevance.dspy.Predict") as mock_predict:
        mock_predict.return_value.return_value = _mock_result(in_domain="true")
        with patch("matcher.pipeline.relevance.dspy.context"):
            verdict = check_domain_plausibility(
                "who is on the bench right now", role, lm=_mock_lm()
            )
    assert verdict is not None
    assert verdict.in_domain is True


def test_tier2_returns_none_without_lm() -> None:
    role = _role(title="Unknown Role")
    assert check_domain_plausibility("hello there", role, lm=None) is None


def test_tier2_returns_none_when_skills_were_parsed() -> None:
    role = _role(RequiredSkill(name="Python"))
    assert check_domain_plausibility("python engineer", role, lm=_mock_lm()) is None
