from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.models.role import Role
from matcher.pipeline.normalise import normalise_location

_ROLLOFF_BUFFER = 5
_NEW_JOINER_BUFFER = 7


def _check_availability(consultant: Consultant, role: Role) -> tuple[bool, str | None]:
    if role.start_date is None:
        return True, None

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


def _check_location(consultant: Consultant, role: Role) -> bool:
    if not role.co_located or not role.locations:
        return True
    return normalise_location(consultant.location) == normalise_location(role.locations[0])


def apply_hard_filters(consultants: list[Consultant], role: Role) -> list[Consultant]:
    result: list[Consultant] = []
    for c in consultants:
        passes_avail, warning = _check_availability(c, role)
        if not passes_avail:
            continue
        if not _check_location(c, role):
            continue
        result.append(c.model_copy(update={"data_gaps": c.data_gaps + [warning]}) if warning else c)
    return result
