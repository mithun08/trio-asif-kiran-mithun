from __future__ import annotations

from pathlib import Path

from matcher.models.consultant import Consultant
from matcher.pipeline.ingest import ingest_feedback

_SAMPLE_MARKDOWN = """# Feedback - Test User

**Email (key):** test@example.com

## Project feedback - Alpha Project
Great work on the backend refactor.

## Client feedback - Alpha Project
"Keep Test User on the project."

## Beach feedback
Studying cloud certifications.
"""


def _make_consultant(email: str = "test@example.com") -> Consultant:
    return Consultant(name="Test User", email=email)


def test_three_sections_populate_correct_keys(tmp_path: Path) -> None:
    md_file = tmp_path / "feedback.md"
    md_file.write_text(_SAMPLE_MARKDOWN, encoding="utf-8")

    consultant = _make_consultant()
    result = ingest_feedback(tmp_path, [consultant])

    assert len(result) == 1
    ft = result[0].feedback_text
    assert "project" in ft
    assert "client" in ft
    assert "beach" in ft


def test_missing_email_key_is_skipped(tmp_path: Path) -> None:
    md_file = tmp_path / "no_email.md"
    md_file.write_text("# Feedback\n\nNo email key here.\n", encoding="utf-8")

    consultant = _make_consultant()
    result = ingest_feedback(tmp_path, [consultant])

    assert result[0].feedback_text == {}


def test_orphan_email_is_skipped(tmp_path: Path) -> None:
    md_file = tmp_path / "orphan.md"
    md_file.write_text(
        "**Email (key):** nobody@unknown.com\n\n## Project feedback\nSome text.\n",
        encoding="utf-8",
    )

    consultant = _make_consultant()
    result = ingest_feedback(tmp_path, [consultant])

    assert result[0].feedback_text == {}


def test_section_text_is_stripped(tmp_path: Path) -> None:
    md_file = tmp_path / "feedback.md"
    md_file.write_text(_SAMPLE_MARKDOWN, encoding="utf-8")

    consultant = _make_consultant()
    result = ingest_feedback(tmp_path, [consultant])

    for text in result[0].feedback_text.values():
        assert text == text.strip()
