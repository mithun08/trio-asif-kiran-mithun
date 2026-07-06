from __future__ import annotations

import json
from pathlib import Path

import pytest

WORKBOOK_PATH = Path("data/demand-supply.xlsx")


@pytest.fixture(autouse=True)
def require_workbook() -> None:
    if not WORKBOOK_PATH.exists():
        pytest.skip("workbook not found")


def test_match_json_includes_ingestion_report_and_telemetry() -> None:
    from typer.testing import CliRunner

    from matcher.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["match", "ROLE-01", "--json", "--no-llm"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    assert parsed.get("ingestion_report") is not None
    assert parsed.get("run_telemetry") is not None


def test_match_no_llm_zero_llm_calls() -> None:
    from typer.testing import CliRunner

    from matcher.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["match", "ROLE-01", "--json", "--no-llm"])
    assert result.exit_code == 0, result.output
    parsed = json.loads(result.output)
    tel = parsed.get("run_telemetry", {})
    assert tel.get("llm_calls", -1) == 0


def test_match_persists_a_snapshot_file() -> None:
    from typer.testing import CliRunner

    from matcher.cli import app
    from matcher.config import AppConfig

    snapshot_dir = AppConfig.from_yaml(Path("config/default.yaml")).observability.snapshot_dir
    before = set(snapshot_dir.glob("*.json")) if snapshot_dir.exists() else set()

    runner = CliRunner()
    result = runner.invoke(app, ["match", "ROLE-01", "--json", "--no-llm"])
    assert result.exit_code == 0, result.output

    after = set(snapshot_dir.glob("*.json"))
    new_files = after - before
    assert len(new_files) == 1

    from matcher.models.output import RunOutput

    saved = RunOutput.model_validate_json(new_files.pop().read_text())
    assert saved.role_id == "ROLE-01"
    assert saved.run_id
