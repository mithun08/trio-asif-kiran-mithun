from __future__ import annotations

from matcher.models.consultant import Consultant

_LOCATION_MAP: dict[str, str] = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "remote (india)": "Remote-India",
    "remote-india": "Remote-India",
    "remote india": "Remote-India",
    "chennai": "Chennai",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
}


def normalise_location(loc: str) -> str:
    return _LOCATION_MAP.get(loc.strip().casefold(), loc.strip())


def canonicalise_locations(consultants: list[Consultant]) -> list[Consultant]:
    return [c.model_copy(update={"location": normalise_location(c.location)}) for c in consultants]


def dedup_by_email(consultants: list[Consultant]) -> list[Consultant]:
    seen: dict[str, Consultant] = {}
    for c in consultants:
        seen.setdefault(c.email.casefold(), c)
    return list(seen.values())


def scrub_pii(consultants: list[Consultant]) -> list[Consultant]:
    raise NotImplementedError
