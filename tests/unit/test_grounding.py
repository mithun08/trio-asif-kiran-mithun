from __future__ import annotations

from matcher.llm.extract import _check_grounding


def test_in_source_span_is_kept() -> None:
    source = "deep payments domain expertise demonstrated."
    grounded, any_dropped = _check_grounding(["payments domain"], source)

    assert grounded == ["payments domain"]
    assert any_dropped is False


def test_out_of_source_span_is_dropped() -> None:
    source = "payments domain expertise."
    grounded, any_dropped = _check_grounding(["space lasers"], source)

    assert grounded == []
    assert any_dropped is True


def test_mixed_spans_partial_grounding() -> None:
    source = "payments domain expertise."
    grounded, any_dropped = _check_grounding(["payments domain", "space lasers"], source)

    assert grounded == ["payments domain"]
    assert any_dropped is True


def test_empty_spans_no_drop() -> None:
    grounded, any_dropped = _check_grounding([], "any text")

    assert grounded == []
    assert any_dropped is False


def test_empty_string_span_excluded() -> None:
    source = "some text"
    grounded, any_dropped = _check_grounding(["", "some text"], source)

    assert grounded == ["some text"]
    assert any_dropped is True
