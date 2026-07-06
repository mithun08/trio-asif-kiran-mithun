from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest

from matcher.config import OCRConfig
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


_LONG_TEXT = (
    "Skills: Python (expert), Java (advanced). Location: London, five years experience."
)


def test_profile_enriches_raw_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)

    def _mock_convert(self: Any, path: str) -> Any:
        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return "Skills: Python (expert), Java (advanced). Location: London."

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


def _counting_convert(text: str) -> Any:
    calls = {"count": 0}

    def _mock_convert(self: Any, path: str) -> Any:
        calls["count"] += 1

        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return text

        return _FakeDoc()

    _mock_convert.calls = calls  # type: ignore[attr-defined]
    return _mock_convert


def test_cache_hit_skips_second_convert_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)
    mock_convert = _counting_convert(_LONG_TEXT)
    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", mock_convert)

    cache: dict[str, Any] = {}
    consultant = _make_consultant(name="Test Consultant")

    first = ingest_consultants(tmp_path, [consultant], cache=cache)
    second = ingest_consultants(tmp_path, [consultant], cache=cache)

    assert mock_convert.calls["count"] == 1
    assert first[0].raw_profile_text == second[0].raw_profile_text


def test_cache_invalidated_by_mtime_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)
    mock_convert = _counting_convert(_LONG_TEXT)
    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", mock_convert)

    cache: dict[str, Any] = {}
    consultant = _make_consultant(name="Test Consultant")
    ingest_consultants(tmp_path, [consultant], cache=cache)

    time.sleep(0.01)
    os.utime(pdf_path, None)
    ingest_consultants(tmp_path, [consultant], cache=cache)

    assert mock_convert.calls["count"] == 2


def test_cache_invalidated_by_ocr_config_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)
    mock_convert = _counting_convert(_LONG_TEXT)
    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", mock_convert)

    cache: dict[str, Any] = {}
    consultant = _make_consultant(name="Test Consultant")
    ingest_consultants(
        tmp_path, [consultant], ocr_config=OCRConfig(text_floor_chars=50), cache=cache
    )
    ingest_consultants(
        tmp_path, [consultant], ocr_config=OCRConfig(text_floor_chars=10), cache=cache
    )

    assert mock_convert.calls["count"] == 2


def test_failed_extraction_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pdf_path = tmp_path / "test_consultant_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)
    calls = {"count": 0}

    def _mock_convert(self: Any, path: str) -> Any:
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("transient failure")

        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return _LONG_TEXT

        return _FakeDoc()

    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", _mock_convert)

    cache: dict[str, Any] = {}
    consultant = _make_consultant(name="Test Consultant")

    first = ingest_consultants(tmp_path, [consultant], cache=cache)
    second = ingest_consultants(tmp_path, [consultant], cache=cache)

    assert "profile_pdf_unreadable" in first[0].data_gaps
    assert second[0].raw_profile_text != ""
    assert calls["count"] == 2
