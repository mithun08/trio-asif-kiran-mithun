from __future__ import annotations

from matcher.config import ScoringConfig, ScoringWeights
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill, Role
from matcher.scoring.dimensions import has_domain_evidence, score_skill_match

_CFG = ScoringConfig()
_W = ScoringWeights()
_ADJ: dict[str, list[str]] = {
    "kotlin": ["java", "scala"],
    "java": ["kotlin", "scala"],
    "python": ["python3", "django"],
}


def _role(*skills: RequiredSkill) -> Role:
    return Role(id="R1", title="T", required_skills=list(skills))


def _consultant(*skills: Skill, supply_state: str = "beach") -> Consultant:
    return Consultant(
        email="c@test.com",
        name="C",
        skills=list(skills),
        supply_state=supply_state,  # type: ignore[arg-type]
    )


def test_exact_match_no_proficiency_requirement() -> None:
    role = _role(RequiredSkill(name="Kotlin"))
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0


def test_exact_match_proficiency_met() -> None:
    role = _role(RequiredSkill(name="Kotlin", required_proficiency=3))
    c = _consultant(Skill(name="Kotlin", proficiency=5))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0


def test_exact_match_proficiency_not_met() -> None:
    role = _role(RequiredSkill(name="Kotlin", required_proficiency=5))
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 70.0


def test_adjacent_skill_scores_60() -> None:
    role = _role(RequiredSkill(name="Kotlin"))
    c = _consultant(Skill(name="Java", proficiency=4))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 60.0


def test_no_match_scores_0() -> None:
    role = _role(RequiredSkill(name="Rust"))
    c = _consultant(Skill(name="Python", proficiency=4))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 0.0


def test_case_insensitive_exact_match() -> None:
    role = _role(RequiredSkill(name="kotlin"))
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0


def test_nice_to_have_adds_bonus() -> None:
    role = _role(
        RequiredSkill(name="Rust", mandatory=True),
        RequiredSkill(name="Python", mandatory=False),
    )
    c = _consultant(Skill(name="Python", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 0.0 + _CFG.nth_bonus_per


def test_nice_to_have_bonus_capped() -> None:
    optionals = [RequiredSkill(name=f"skill{i}", mandatory=False) for i in range(10)]
    role = _role(RequiredSkill(name="Kotlin", mandatory=True), *optionals)
    skills = [Skill(name="Kotlin", proficiency=3)] + [
        Skill(name=f"skill{i}", proficiency=3) for i in range(10)
    ]
    c = _consultant(*skills)
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == min(100.0 + _CFG.nth_bonus_cap, 100.0)


def test_nice_to_have_absence_no_penalty() -> None:
    role = _role(
        RequiredSkill(name="Kotlin", mandatory=True),
        RequiredSkill(name="Python", mandatory=False),
    )
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0


def test_new_joiner_fallback_credit() -> None:
    role = _role(RequiredSkill(name="Rust"))
    c = _consultant(Skill(name="Python", proficiency=3), supply_state="new_joiner")
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == _CFG.c_newjoiner


def test_mean_over_multiple_required_skills() -> None:
    role = _role(RequiredSkill(name="Kotlin"), RequiredSkill(name="Rust"))
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == (100.0 + 0.0) / 2


def test_excluded_skill_held_applies_penalty() -> None:
    role = Role(
        id="R1",
        title="T",
        required_skills=[RequiredSkill(name="Kotlin")],
        exclude_skills=["Scala"],
    )
    c = _consultant(Skill(name="Kotlin", proficiency=3), Skill(name="Scala", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0 - _CFG.skill_exclude_penalty_per


def test_excluded_skill_not_held_no_penalty() -> None:
    role = Role(
        id="R1",
        title="T",
        required_skills=[RequiredSkill(name="Kotlin")],
        exclude_skills=["Rust"],
    )
    c = _consultant(Skill(name="Kotlin", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0


def test_excluded_skill_penalty_capped() -> None:
    role = Role(
        id="R1",
        title="T",
        required_skills=[RequiredSkill(name="Kotlin")],
        exclude_skills=["Scala", "Java", "Rust"],
    )
    c = _consultant(
        Skill(name="Kotlin", proficiency=3),
        Skill(name="Scala", proficiency=3),
        Skill(name="Java", proficiency=3),
        Skill(name="Rust", proficiency=3),
    )
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score == 100.0 - _CFG.skill_exclude_penalty_cap


def test_excluded_skill_never_drops_below_zero() -> None:
    role = Role(
        id="R1",
        title="T",
        required_skills=[RequiredSkill(name="Obscure")],
        exclude_skills=["Scala"],
    )
    c = _consultant(Skill(name="Scala", proficiency=3))
    result = score_skill_match(c, role, _ADJ, _W, _CFG)
    assert result.raw_score >= 0.0


def test_has_domain_evidence_true_on_exact_match() -> None:
    req = RequiredSkill(name="Kotlin")
    consultants = [_consultant(Skill(name="Kotlin", proficiency=3))]
    assert has_domain_evidence(req, consultants, _ADJ, _CFG) is True


def test_has_domain_evidence_true_on_adjacent_match() -> None:
    req = RequiredSkill(name="Kotlin")
    consultants = [_consultant(Skill(name="Java", proficiency=3))]
    assert has_domain_evidence(req, consultants, _ADJ, _CFG) is True


def test_has_domain_evidence_false_ignores_new_joiner_fallback() -> None:
    # Regression guard: a new_joiner consultant gets a flat c_newjoiner credit
    # from score_skill_match/_best_credit regardless of actual skill overlap —
    # has_domain_evidence must not treat that fallback as real evidence, or a
    # nonsense skill like "plumber" would look domain-relevant just because
    # the pool has any new-joiner.
    req = RequiredSkill(name="Plumber")
    consultants = [_consultant(Skill(name="Python", proficiency=3), supply_state="new_joiner")]
    assert score_skill_match(consultants[0], _role(req), _ADJ, _W, _CFG).raw_score == (
        _CFG.c_newjoiner
    )
    assert has_domain_evidence(req, consultants, _ADJ, _CFG) is False


def test_has_domain_evidence_false_on_empty_pool() -> None:
    req = RequiredSkill(name="Kotlin")
    assert has_domain_evidence(req, [], _ADJ, _CFG) is False
