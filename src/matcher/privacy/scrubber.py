from __future__ import annotations


def scrub_text(text: str) -> tuple[str, dict[str, str]]:
    """Detect and redact PII from text using Presidio; return scrubbed text and token map."""
    raise NotImplementedError


def rehydrate_text(scrubbed_text: str, token_map: dict[str, str]) -> str:
    """Replace pseudonymised tokens with original values for local output."""
    raise NotImplementedError
