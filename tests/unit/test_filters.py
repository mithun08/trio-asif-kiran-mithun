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
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_rolling_off_high_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 7, 5), rolloff_confidence="high"
    )
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_rolling_off_high_beyond_buffer_fails() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 8, 1), rolloff_confidence="high"
    )
    result = apply_hard_filters([c], role)
    assert len(result) == 0


def test_rolling_off_medium_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 7, 3), rolloff_confidence="medium"
    )
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_rolling_off_low_always_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 9, 1), rolloff_confidence="low"
    )
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_rolling_off_low_adds_availability_uncertain_warning() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 9, 1), rolloff_confidence="low"
    )
    result = apply_hard_filters([c], role)
    assert "availability uncertain" in result[0].data_gaps


def test_new_joiner_within_buffer_passes() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="new_joiner", available_from=date(2026, 7, 7))
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_new_joiner_beyond_buffer_fails() -> None:
    role = _role(start=date(2026, 7, 1))
    c = _consultant(supply_state="new_joiner", available_from=date(2026, 7, 15))
    result = apply_hard_filters([c], role)
    assert len(result) == 0


def test_no_start_date_skips_availability_filter() -> None:
    role = _role(start=None)
    c = _consultant(
        supply_state="rolling_off", available_from=date(2026, 12, 1), rolloff_confidence="high"
    )
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_co_located_role_blocks_non_local() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Mumbai")
    result = apply_hard_filters([c], role)
    assert len(result) == 0


def test_co_located_role_allows_matching_location() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Bengaluru")
    result = apply_hard_filters([c], role)
    assert len(result) == 1


def test_non_co_located_role_passes_all_locations() -> None:
    role = _role(co_located=False)
    consultants = [_consultant(location=loc) for loc in ["Mumbai", "Chennai", "Delhi"]]
    result = apply_hard_filters(consultants, role)
    assert len(result) == 3


def test_co_located_normalises_location_before_compare() -> None:
    role = _role(co_located=True, location="Bengaluru")
    c = _consultant(location="Bangalore")
    result = apply_hard_filters([c], role)
    assert len(result) == 1
