from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from matcher.models.consultant import Consultant
from matcher.pipeline.ingest import ingest_consultants

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
    b"xref\n0 4\n0000000000 65535 f \n"
    b"0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n190\n%%EOF"
)


def _make_consultant(name: str = "Test Consultant", email: str = "test@example.com") -> Consultant:
    return Consultant(name=name, email=email)


def test_profile_enriches_raw_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)

    def _mock_convert(self: Any, path: str) -> Any:
        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return "Skills: Python (expert). Location: London."

        return _FakeDoc()

    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", _mock_convert)

    consultant = _make_consultant(name="Test Consultant")
    result = ingest_consultants(tmp_path, [consultant])

    assert len(result) == 1
    assert result[0].raw_profile_text != ""


def test_missing_pdf_adds_unmatched_gap(tmp_path: Path) -> None:
    consultant = _make_consultant(name="Ghost Person")
    result = ingest_consultants(tmp_path, [consultant])

    assert len(result) == 1
    assert "profile_pdf_unmatched" in result[0].data_gaps


def test_unreadable_pdf_lowers_confidence(tmp_path: Path) -> None:
    pdf_path = tmp_path / "corrupt_person_pp.pdf"
    pdf_path.write_bytes(b"this is not a valid pdf file")

    consultant = _make_consultant(name="Corrupt Person")
    result = ingest_consultants(tmp_path, [consultant])

    assert len(result) == 1
    assert result[0].data_confidence < 1.0
    assert "profile_pdf_unreadable" in result[0].data_gaps


def test_missing_profiles_dir_returns_unchanged() -> None:
    consultant = _make_consultant()
    result = ingest_consultants(Path("/nonexistent/path"), [consultant])

    assert result == [consultant]
