from __future__ import annotations

from pathlib import Path

import pytest

from matcher.models.consultant import Consultant
from matcher.pipeline import reconcile as reconcile_mod
from matcher.pipeline.reconcile import reconcile_external_people

_FEEDBACK = """# Feedback - {name}

**Email (key):** {email}

## Project feedback - Acme Corp

Dependable engineer; delivered without concerns.
"""


def _write_feedback(d: Path, filename: str, name: str, email: str) -> None:
    (d / filename).write_text(_FEEDBACK.format(name=name, email=email), encoding="utf-8")


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    profiles = tmp_path / "profiles"
    feedback = tmp_path / "project_feedback"
    profiles.mkdir()
    feedback.mkdir()
    return profiles, feedback


@pytest.fixture(autouse=True)
def _stub_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        reconcile_mod, "_extract_pdf_text_cached", lambda p, o, c: ("resume text", [], 1.0)
    )


def test_admits_corroborated_external_person(dirs: tuple[Path, Path]) -> None:
    profiles, feedback = dirs
    (profiles / "jane_doe_pp.pdf").write_bytes(b"%PDF-")
    _write_feedback(feedback, "Jane.md", "Jane Doe", "jane.doe@x.example")

    result_consultants, res = reconcile_external_people([], profiles, feedback)

    assert len(result_consultants) == 1
    admitted = result_consultants[0]
    assert admitted.email == "jane.doe@x.example"
    assert admitted.data_confidence < 0.5
    assert "admitted_external" in admitted.data_gaps
    assert "no_workbook_record" in admitted.data_gaps
    assert admitted.feedback_text
    assert res.admitted and not res.quarantined


def test_quarantines_feedback_without_profile(dirs: tuple[Path, Path]) -> None:
    _, feedback = dirs
    profiles, _ = dirs
    _write_feedback(feedback, "Ghost.md", "Ghost Person", "ghost@x.example")

    result_consultants, res = reconcile_external_people([], profiles, feedback)

    assert result_consultants == []
    assert res.admitted == []
    assert "Ghost.md" in res.unlinkable_feedback
    assert any("no corroborating profile" in q for q in res.quarantined)


def test_quarantines_profile_without_feedback(dirs: tuple[Path, Path]) -> None:
    profiles, feedback = dirs
    (profiles / "lonely_prof_pp.pdf").write_bytes(b"%PDF-")

    result_consultants, res = reconcile_external_people([], profiles, feedback)

    assert result_consultants == []
    assert any("no corroborating feedback" in q for q in res.quarantined)


def test_quarantines_invalid_email(dirs: tuple[Path, Path]) -> None:
    profiles, feedback = dirs
    (profiles / "jane_doe_pp.pdf").write_bytes(b"%PDF-")
    _write_feedback(feedback, "Jane.md", "Jane Doe", "not-an-email")

    _, res = reconcile_external_people([], profiles, feedback)

    assert res.admitted == []
    assert any("invalid/missing email" in q for q in res.quarantined)


def test_ambiguous_profile_name_is_quarantined(dirs: tuple[Path, Path]) -> None:
    profiles, feedback = dirs
    (profiles / "jane_doe_pp.pdf").write_bytes(b"%PDF-")
    (profiles / "jane_doe.pdf").write_bytes(b"%PDF-")  # second Jane Doe -> ambiguous
    _write_feedback(feedback, "Jane.md", "Jane Doe", "jane.doe@x.example")

    _, res = reconcile_external_people([], profiles, feedback)

    assert res.admitted == []
    assert any("ambiguous profile name" in q for q in res.quarantined)


def test_skips_feedback_already_linked_to_workbook(dirs: tuple[Path, Path]) -> None:
    profiles, feedback = dirs
    (profiles / "jane_doe_pp.pdf").write_bytes(b"%PDF-")
    _write_feedback(feedback, "Jane.md", "Jane Doe", "jane.doe@x.example")
    existing = [Consultant(email="jane.doe@x.example", name="Jane Doe")]

    result_consultants, res = reconcile_external_people(existing, profiles, feedback)

    assert len(result_consultants) == 1  # no new person admitted
    assert res.admitted == []
    assert res.quarantined == []
