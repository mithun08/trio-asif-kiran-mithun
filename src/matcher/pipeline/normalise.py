from __future__ import annotations

from matcher.models.consultant import Consultant


def dedup_by_email(consultants: list[Consultant]) -> list[Consultant]:
    """Deduplicate consultants by email (case-insensitive), merging duplicate records."""
    raise NotImplementedError


def canonicalise_locations(consultants: list[Consultant]) -> list[Consultant]:
    """Normalise location strings to canonical forms using the configured location list."""
    raise NotImplementedError


def scrub_pii(consultants: list[Consultant]) -> list[Consultant]:
    """Run Presidio PII detection and scrub direct identifiers before external LLM calls."""
    raise NotImplementedError
