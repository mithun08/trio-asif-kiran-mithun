from __future__ import annotations

from pathlib import Path

import pytest

from matcher.pipeline.ingest import ingest_consultants_from_workbook, ingest_roles

_WORKBOOK = Path("data/demand-supply.xlsx")


def test_ingest_roles_count() -> None:
    roles = ingest_roles(_WORKBOOK)
    assert len(roles) == 8


def test_ingest_roles_ids() -> None:
    roles = ingest_roles(_WORKBOOK)
    ids = [r.id for r in roles]
    assert ids[0] == "ROLE-01"
    assert "ROLE-08" in ids


def test_ingest_roles_first_role_fields() -> None:
    role = ingest_roles(_WORKBOOK)[0]
    assert role.id == "ROLE-01"
    assert "Kotlin" in role.title or "Backend" in role.title
    assert role.start_date is not None
    assert len(role.required_skills) >= 1


def test_ingest_roles_skill_proficiency_parsed() -> None:
    role = ingest_roles(_WORKBOOK)[0]
    kotlin_skill = next((s for s in role.required_skills if "Kotlin" in s.name), None)
    assert kotlin_skill is not None
    assert kotlin_skill.required_proficiency == 5


def test_ingest_roles_location_split_and_normalised() -> None:
    role = ingest_roles(_WORKBOOK)[0]
    assert len(role.locations) >= 1
    assert "Bengaluru" in role.locations


def test_ingest_roles_missing_column_raises_value_error(tmp_path: Path) -> None:
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Open Roles"
    ws.append(["Open Roles title"])
    ws.append(["Role ID", "Title"])
    ws.append(["ROLE-X", "Test"])
    path = tmp_path / "bad.xlsx"
    wb.save(path)
    with pytest.raises(ValueError, match="missing columns"):
        ingest_roles(path)


def test_ingest_consultants_total_count() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    assert len(consultants) == 35


def test_ingest_consultants_supply_states() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    states = {c.supply_state for c in consultants}
    assert states == {"beach", "rolling_off", "new_joiner"}


def test_ingest_consultants_beach_available_from_is_none() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    beach = [c for c in consultants if c.supply_state == "beach"]
    assert all(c.available_from is None for c in beach)


def test_ingest_consultants_rolling_off_has_dates() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    rolling = [c for c in consultants if c.supply_state == "rolling_off"]
    assert all(c.available_from is not None for c in rolling)


def test_ingest_consultants_rolling_off_confidence_set() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    rolling = [c for c in consultants if c.supply_state == "rolling_off"]
    confidences = {c.rolloff_confidence for c in rolling}
    assert confidences <= {"high", "medium", "low"}
    assert "low" in confidences


def test_ingest_consultants_new_joiners_have_join_dates() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    joiners = [c for c in consultants if c.supply_state == "new_joiner"]
    assert all(c.available_from is not None for c in joiners)


def test_ingest_consultants_skills_parsed() -> None:
    consultants = ingest_consultants_from_workbook(_WORKBOOK)
    with_skills = [c for c in consultants if c.skills]
    assert len(with_skills) > 0
    assert all(isinstance(s.name, str) and s.name for c in with_skills for s in c.skills)
