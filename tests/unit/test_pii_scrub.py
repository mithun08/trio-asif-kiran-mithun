from __future__ import annotations

import re

from matcher.privacy.scrubber import rehydrate_text, scrub_text

_EMAIL_RE = re.compile(r"[\w.+\-]+@[\w\-]+\.[\w.]+")
_PHONE_RE = re.compile(r"\+?\d[\d\s\-()\\.]{7,}")


def test_scrub_removes_email() -> None:
    text = "Contact me at alice@example.com for details."
    scrubbed, _ = scrub_text(text)
    assert not _EMAIL_RE.search(scrubbed)


def test_scrub_removes_phone() -> None:
    text = "Call me at +91-9876543210 anytime."
    scrubbed, _ = scrub_text(text)
    assert not _PHONE_RE.search(scrubbed)


def test_rehydrate_roundtrip() -> None:
    text = "Email me: test@example.com, call: +44-7700900000."
    scrubbed, token_map = scrub_text(text)
    recovered = rehydrate_text(scrubbed, token_map)
    assert recovered == text


def test_empty_text_returns_empty() -> None:
    scrubbed, token_map = scrub_text("")
    assert scrubbed == ""
    assert token_map == {}


def test_no_pii_text_returns_unchanged() -> None:
    text = "This text has no personal information whatsoever."
    scrubbed, token_map = scrub_text(text)
    assert scrubbed == text
    assert token_map == {}
