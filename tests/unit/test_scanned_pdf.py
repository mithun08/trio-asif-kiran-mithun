from __future__ import annotations

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

_call_count = 0


def test_ocr_retry_triggered_for_short_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "short_text_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)

    global _call_count
    _call_count = 0

    def _mock_convert(self: Any, path: str) -> Any:
        global _call_count
        _call_count += 1

        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    if _call_count == 1:
                        return "hi"
                    return "This is a much longer OCR-extracted text from the scanned document."

        return _FakeDoc()

    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", _mock_convert)

    consultant = Consultant(name="Short Text", email="short@example.com")
    ocr_cfg = OCRConfig(enabled=True, text_floor_chars=50, confidence_floor=0.6)
    result = ingest_consultants(tmp_path, [consultant], ocr_config=ocr_cfg)

    assert len(result) == 1
    assert "profile_pdf_ocr_used" in result[0].data_gaps


def test_ocr_disabled_gives_low_confidence_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "short_text_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)

    def _mock_convert(self: Any, path: str) -> Any:
        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return "hi"

        return _FakeDoc()

    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", _mock_convert)

    consultant = Consultant(name="Short Text", email="short@example.com")
    ocr_cfg = OCRConfig(enabled=False, text_floor_chars=50, confidence_floor=0.6)
    result = ingest_consultants(tmp_path, [consultant], ocr_config=ocr_cfg)

    assert len(result) == 1
    assert "profile_pdf_low_confidence" in result[0].data_gaps


def test_ocr_disabled_consultant_never_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pdf_path = tmp_path / "short_text_pp.pdf"
    pdf_path.write_bytes(_MINIMAL_PDF)

    def _mock_convert(self: Any, path: str) -> Any:
        class _FakeDoc:
            class document:
                @staticmethod
                def export_to_text() -> str:
                    return "x"

        return _FakeDoc()

    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", _mock_convert)

    consultant = Consultant(name="Short Text", email="short@example.com")
    ocr_cfg = OCRConfig(enabled=False, text_floor_chars=50)
    result = ingest_consultants(tmp_path, [consultant], ocr_config=ocr_cfg)
    assert len(result) == 1
