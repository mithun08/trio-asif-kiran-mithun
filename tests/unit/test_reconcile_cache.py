from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from matcher.pipeline.reconcile import reconcile_external_people

_FEEDBACK = """# Feedback - Jane Doe

**Email (key):** jane.doe@x.example

## Project feedback - Acme Corp

Dependable engineer; delivered without concerns.
"""


@pytest.fixture
def dirs(tmp_path: Path) -> tuple[Path, Path]:
    profiles = tmp_path / "profiles"
    feedback = tmp_path / "project_feedback"
    profiles.mkdir()
    feedback.mkdir()
    (feedback / "Jane.md").write_text(_FEEDBACK, encoding="utf-8")
    (profiles / "jane_doe_pp.pdf").write_bytes(b"%PDF-")
    return profiles, feedback


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


def test_reconcile_cache_hit_skips_second_convert_call(
    dirs: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    profiles, feedback = dirs
    mock_convert = _counting_convert("resume text long enough to pass the confidence floor check")
    monkeypatch.setattr("docling.document_converter.DocumentConverter.convert", mock_convert)

    cache: dict[str, Any] = {}
    reconcile_external_people([], profiles, feedback, cache=cache)
    reconcile_external_people([], profiles, feedback, cache=cache)

    assert mock_convert.calls["count"] == 1
