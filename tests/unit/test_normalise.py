from __future__ import annotations

from matcher.models.consultant import Consultant
from matcher.pipeline.normalise import (
    canonicalise_locations,
    dedup_by_email,
    normalise_location,
)


def _consultant(email: str, location: str = "London") -> Consultant:
    return Consultant(email=email, name=email, location=location)


def test_bangalore_to_bengaluru() -> None:
    assert normalise_location("Bangalore") == "Bengaluru"


def test_bengaluru_unchanged() -> None:
    assert normalise_location("Bengaluru") == "Bengaluru"


def test_remote_india_variants() -> None:
    assert normalise_location("Remote (India)") == "Remote-India"
    assert normalise_location("remote-India") == "Remote-India"
    assert normalise_location("Remote-India") == "Remote-India"


def test_unknown_location_returned_as_is() -> None:
    assert normalise_location("Singapore") == "Singapore"


def test_canonicalise_locations_normalises_each_consultant() -> None:
    consultants = [
        _consultant("a@x.com", "Bangalore"),
        _consultant("b@x.com", "Bengaluru"),
    ]
    result = canonicalise_locations(consultants)
    assert all(c.location == "Bengaluru" for c in result)


def test_canonicalise_locations_returns_new_list() -> None:
    original = [_consultant("a@x.com", "Bangalore")]
    result = canonicalise_locations(original)
    assert result[0] is not original[0]
    assert original[0].location == "Bangalore"


def test_dedup_by_email_keeps_first() -> None:
    consultants = [
        _consultant("Alice@Example.com"),
        _consultant("alice@example.com"),
    ]
    result = dedup_by_email(consultants)
    assert len(result) == 1
    assert result[0].name == "Alice@Example.com"


def test_dedup_by_email_no_duplicates_unchanged() -> None:
    consultants = [_consultant("a@x.com"), _consultant("b@x.com")]
    result = dedup_by_email(consultants)
    assert len(result) == 2


def test_dedup_by_email_case_insensitive() -> None:
    consultants = [
        _consultant("User@Domain.COM"),
        _consultant("user@domain.com"),
        _consultant("USER@DOMAIN.COM"),
    ]
    result = dedup_by_email(consultants)
    assert len(result) == 1
