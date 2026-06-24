from __future__ import annotations

from typing import Any

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
    from matcher.privacy.scrubber import scrub_text

    scrubbed_list = []
    for consultant in consultants:
        combined_token_map: dict[str, str] = {}
        update: dict[str, Any] = {}

        scrubbed_profile, profile_map = scrub_text(consultant.raw_profile_text)
        combined_token_map.update(profile_map)
        update["raw_profile_text"] = scrubbed_profile

        scrubbed_feedback: dict[str, str] = {}
        for source, feedback_content in consultant.feedback_text.items():
            scrubbed_content, feedback_map = scrub_text(feedback_content)
            combined_token_map.update(feedback_map)
            scrubbed_feedback[source] = scrubbed_content
        if scrubbed_feedback:
            update["feedback_text"] = scrubbed_feedback

        update["pii_token_map"] = combined_token_map

        if combined_token_map:
            update["data_gaps"] = [*consultant.data_gaps, "pii_scrubbed"]

        scrubbed_list.append(consultant.model_copy(update=update))

    return scrubbed_list
