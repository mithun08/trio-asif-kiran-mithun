from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from matcher.cli import _compute_snapshot_id


def test_deterministic(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "alice.pdf").write_bytes(b"pdf")
    feedback = tmp_path / "project_feedback"
    feedback.mkdir()
    (feedback / "alice.md").write_text("feedback")

    r1 = _compute_snapshot_id(wb, profiles, feedback)
    r2 = _compute_snapshot_id(wb, profiles, feedback)
    assert r1 == r2


def test_changes_on_pdf_mtime(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    pdf = profiles / "alice.pdf"
    pdf.write_bytes(b"pdf")
    feedback = tmp_path / "project_feedback"
    feedback.mkdir()

    r1 = _compute_snapshot_id(wb, profiles, feedback)
    time.sleep(0.01)
    os.utime(pdf, None)
    r2 = _compute_snapshot_id(wb, profiles, feedback)
    assert r1 != r2


def test_changes_on_workbook_mtime(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    feedback = tmp_path / "project_feedback"
    feedback.mkdir()

    r1 = _compute_snapshot_id(wb, profiles, feedback)
    time.sleep(0.01)
    os.utime(wb, None)
    r2 = _compute_snapshot_id(wb, profiles, feedback)
    assert r1 != r2


def test_missing_directories_dont_raise(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    result = _compute_snapshot_id(
        wb, tmp_path / "nonexistent_profiles", tmp_path / "nonexistent_fb"
    )
    assert len(result) == 16
    assert result.isalnum()


def test_changes_on_config_mtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    (cfg_dir / "default.yaml").write_text("scoring: {}")
    (cfg_dir / "skill_adjacency.yaml").write_text("adjacency: {}")

    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    feedback = tmp_path / "project_feedback"
    feedback.mkdir()

    r1 = _compute_snapshot_id(wb, profiles, feedback)
    time.sleep(0.01)
    os.utime(cfg_dir / "default.yaml", None)
    r2 = _compute_snapshot_id(wb, profiles, feedback)
    assert r1 != r2


def test_changes_on_embedding_model(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    feedback = tmp_path / "project_feedback"
    feedback.mkdir()

    r1 = _compute_snapshot_id(wb, profiles, feedback, embedding_model="all-MiniLM-L6-v2")
    r2 = _compute_snapshot_id(wb, profiles, feedback, embedding_model="all-mpnet-base-v2")
    assert r1 != r2


def test_embedding_model_empty_string_ignored(tmp_path: Path) -> None:
    wb = tmp_path / "demand-supply.xlsx"
    wb.write_bytes(b"fake")
    r1 = _compute_snapshot_id(wb, tmp_path / "p", tmp_path / "f", embedding_model="")
    r2 = _compute_snapshot_id(wb, tmp_path / "p", tmp_path / "f")
    assert r1 == r2
