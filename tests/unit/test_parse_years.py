from __future__ import annotations

import pytest

from matcher.llm.extract import _parse_years


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (5, 5.0),
        (7, 7.0),
        (2.5, 2.5),
        ("5", 5.0),
        ("2.5", 2.5),
        ("12+", 12.0),
        ("3-5", 3.0),
        ("~10 years", 10.0),
        ("unknown", 0.0),
        ("", 0.0),
        (None, 0.0),
    ],
)
def test_parse_years(raw: object, expected: float) -> None:
    assert _parse_years(raw) == expected


def test_parse_years_custom_default() -> None:
    assert _parse_years("n/a", default=1.0) == 1.0
