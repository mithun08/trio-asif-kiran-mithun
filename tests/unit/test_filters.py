from __future__ import annotations

from datetime import date

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.scoring.filters import apply_hard_filters


def _role(
    start: date | None = date(2026, 7, 1),
    co_located: bool = False,
    location: str = "Bengaluru",
) -> Role:
    return Role(
        id="R1",
        title="Test",
        start_date=start,
        co_located=co_located,
        locations=[location] if location else [],
    )


def _consultant(
    supply_state: str = "beach",
    available_from: date | None = None,
    rolloff_confidence: str = "high",
    location: str = "Bengaluru",
) -> Consultant:
    return Consultant(
        email=f"{supply_state}-{available_from}-{rolloff_confidence}@test.com",
        name="Test",
        supply_state=supply_state,  # type: ignore[arg-type]
        available_from=available_from,
        rolloff_confidence=rolloff_confidence,  # type: ignore[arg-type]
        location=location,
    )


def test_beach_always_passes_availability() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="beach")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_rolling_off_high_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 7, 5), rolloff_confidence="high"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_rolling_off_high_beyond_buffer_fails() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 8, 1), rolloff_confidence="high"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert len(rejected) == 1
    assert rejected[0][1] == "availability: too late"


def test_rolling_off_medium_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 7, 3), rolloff_confidence="medium"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_rolling_off_medium_adds_date_uncertain_warning() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 7, 3), rolloff_confidence="medium"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert "date uncertain" in passing[0].data_gaps


def test_rolling_off_low_always_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 9, 1), rolloff_confidence="low"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_rolling_off_low_adds_availability_uncertain_warning() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 9, 1), rolloff_confidence="low"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert "availability uncertain" in passing[0].data_gaps


def test_new_joiner_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="new_joiner", available_from=date(2026, 7, 7))
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_new_joiner_beyond_buffer_fails() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="new_joiner", available_from=date(2026, 7, 15))
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert len(rejected) == 1


def test_no_start_date_skips_availability_filter() -> None:
    role = _role(start=None)
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 12, 1), rolloff_confidence="high"
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_co_located_role_blocks_non_local() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Mumbai")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert rejected[0][1] == "location_mismatch"


def test_co_located_role_allows_matching_location() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Bengaluru")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_non_co_located_role_passes_all_locations() -> None:
    role = _role(co_located=False)
    consultants = [_consultant(location=loc) for loc in ["Mumbai", "Chennai", "Delhi"]]
    passing, rejected = apply_hard_filters(consultants, role)
    assert len(passing) == 3


def test_co_located_normalises_location_before_compare() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Bangalore")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1


def test_disable_availability_filter_lets_late_consultant_pass() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 9, 1), rolloff_confidence="high"
    )
    passing, rejected = apply_hard_filters([c], role, disable_availability_filter=True)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_disable_location_filter_lets_wrong_location_pass() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Mumbai")
    passing, rejected = apply_hard_filters([c], role, disable_location_filter=True)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_both_disabled_all_pass() -> None:
    role = _role(start=date(2026, 7, 1), co_located=True, location="Bengaluru")
    consultants = [
        _consultant(
            supply_state="rolling_off",
            available_from=date(2026, 9, 1),
            rolloff_confidence="high",
            location="Mumbai",
        ),
        _consultant(location="Delhi"),
    ]
    passing, rejected = apply_hard_filters(
        consultants, role, disable_availability_filter=True, disable_location_filter=True
    )
    assert len(passing) == 2
    assert len(rejected) == 0


def test_exclude_location_hard_drops_regardless_of_co_located() -> None:
    role = _role(co_located=False, location="").model_copy(
        update={"exclude_locations": ["Chennai"]}
    )
    c = _consultant(location="Chennai")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert rejected[0][1] == "location_excluded"


def test_exclude_location_normalises_before_compare() -> None:
    role = _role(co_located=False, location="").model_copy(
        update={"exclude_locations": ["Bangalore"]}
    )
    c = _consultant(location="Bengaluru")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert rejected[0][1] == "location_excluded"


def test_exclude_location_absent_passes() -> None:
    role = _role(co_located=False, location="").model_copy(
        update={"exclude_locations": ["Chennai"]}
    )
    c = _consultant(location="Mumbai")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_exclude_supply_state_hard_drops() -> None:
    role = _role().model_copy(update={"exclude_supply_states": ["new_joiner"]})
    c = _consultant(supply_state="new_joiner", available_from=date(2026, 7, 1))
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert rejected[0][1] == "supply_state_excluded"


def test_exclude_supply_state_absent_passes() -> None:
    role = _role().model_copy(update={"exclude_supply_states": ["new_joiner"]})
    c = _consultant(supply_state="beach")
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_admitted_external_fails_availability_filter() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="beach").model_copy(
        update={"data_gaps": ["admitted_external", "no_workbook_record"]}
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 0
    assert len(rejected) == 1
    assert rejected[0][1] == "availability unknown (admitted-external record)"


def test_admitted_external_passes_when_availability_filter_disabled() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="beach").model_copy(
        update={"data_gaps": ["admitted_external", "no_workbook_record"]}
    )
    passing, rejected = apply_hard_filters([c], role, disable_availability_filter=True)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_admitted_external_skipped_when_no_start_date() -> None:
    role = _role(start=None)
    c = _consultant(supply_state="beach").model_copy(
        update={"data_gaps": ["admitted_external", "no_workbook_record"]}
    )
    passing, rejected = apply_hard_filters([c], role)
    assert len(passing) == 1
    assert len(rejected) == 0


def test_default_args_unchanged() -> None:
    role = _role(co_located=True, location="Bengaluru", start=date(2026, 7, 1))
    c_pass = _consultant(location="Bengaluru")
    c_fail = _consultant(location="Mumbai")
    passing, rejected = apply_hard_filters([c_pass, c_fail], role)
    assert len(passing) == 1
    assert len(rejected) == 1
