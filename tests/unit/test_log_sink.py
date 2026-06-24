from __future__ import annotations

import json
from pathlib import Path

import pytest

from matcher.observability.run_log import _reset_log_sink, configure_log_sink, log_run_start


@pytest.fixture(autouse=True)
def reset_sink() -> None:
    _reset_log_sink()


def test_configure_log_sink_creates_file(tmp_path: Path) -> None:
    log_path = tmp_path / "sub" / "run-log.jsonl"
    configure_log_sink(log_path)
    log_run_start("test-snap-001", "0.1.0")
    assert log_path.exists()


def test_log_sink_writes_valid_json(tmp_path: Path) -> None:
    log_path = tmp_path / "run-log.jsonl"
    configure_log_sink(log_path)
    log_run_start("snap-abc", "0.1.0")
    lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
    assert len(lines) >= 1
    parsed = json.loads(lines[0])
    assert isinstance(parsed, dict)


def test_configure_log_sink_idempotent(tmp_path: Path) -> None:
    log_path = tmp_path / "run-log.jsonl"
    configure_log_sink(log_path)
    configure_log_sink(log_path)
    log_run_start("snap-xyz", "0.1.0")
    lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1
