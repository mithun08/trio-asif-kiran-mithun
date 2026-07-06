from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.pipeline.normalise import normalise_location

_ROLLOFF_BUFFER = 5
_NEW_JOINER_BUFFER = 7


def _check_availability(consultant: Consultant, role: Role) -> tuple[bool, str | None]:
    if role.start_date is None:
        return True, None

    if "admitted_external" in consultant.data_gaps:
        # No workbook supply/availability record exists for this person, so
        # the default supply_state="beach" would otherwise wrongly pass them
        # as available now — treat unknown availability conservatively.
        return False, "availability unknown (admitted-external record)"

    if consultant.supply_state == "beach":
        return True, None

    if consultant.supply_state == "rolling_off" and consultant.rolloff_confidence == "low":
        return True, "availability uncertain"

    if consultant.available_from is None:
        return True, None

    days_late = max(0, (consultant.available_from - role.start_date).days)

    if consultant.supply_state == "rolling_off":
        if consultant.rolloff_confidence == "medium" and days_late <= _ROLLOFF_BUFFER:
            return True, "date uncertain"
        return days_late <= _ROLLOFF_BUFFER, None

    if consultant.supply_state == "new_joiner":
        return days_late <= _NEW_JOINER_BUFFER, None

    return True, None


def _check_location(consultant: Consultant, role: Role) -> tuple[bool, str | None]:
    consultant_loc = normalise_location(consultant.location)
    if role.exclude_locations and consultant_loc in {
        normalise_location(loc) for loc in role.exclude_locations
    }:
        return False, "location_excluded"

    if not role.co_located or not role.locations:
        return True, None
    if consultant_loc != normalise_location(role.locations[0]):
        return False, "location_mismatch"
    return True, None


def _check_supply_exclusion(consultant: Consultant, role: Role) -> bool:
    return consultant.supply_state not in role.exclude_supply_states


def apply_hard_filters(
    consultants: list[Consultant],
    role: Role,
    *,
    disable_availability_filter: bool = False,
    disable_location_filter: bool = False,
) -> tuple[list[Consultant], list[tuple[Consultant, str]]]:
    passing: list[Consultant] = []
    rejected: list[tuple[Consultant, str]] = []
    for c in consultants:
        warning: str | None = None
        if not _check_supply_exclusion(c, role):
            rejected.append((c, "supply_state_excluded"))
            continue
        if not disable_availability_filter:
            passes_avail, warning = _check_availability(c, role)
            if not passes_avail:
                rejected.append((c, warning or "availability: too late"))
                continue
        if not disable_location_filter:
            passes_loc, loc_reason = _check_location(c, role)
            if not passes_loc:
                rejected.append((c, loc_reason or "location_mismatch"))
                continue
        updated = c.model_copy(update={"data_gaps": c.data_gaps + [warning]}) if warning else c
        passing.append(updated)
    return passing, rejected
