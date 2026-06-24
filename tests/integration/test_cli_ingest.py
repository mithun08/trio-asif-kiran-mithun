from __future__ import annotations

import json
from pathlib import Path

import pytest

WORKBOOK_PATH = Path("data/demand-supply.xlsx")


@pytest.fixture(autouse=True)
def require_workbook() -> None:
    if not WORKBOOK_PATH.exists():
        pytest.skip("workbook not found")


def test_ingest_json_output_valid(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from matcher.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["ingest", "--json"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert "profiles_parsed" in parsed
    assert "feedback_matched" in parsed


def test_ingest_bad_workbook_exits_1(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from matcher.cli import app

    bad_xlsx = tmp_path / "bad.xlsx"
    bad_xlsx.write_bytes(b"not a workbook")
    runner = CliRunner()
    result = runner.invoke(app, ["ingest", f"--data-dir={tmp_path}"])
    assert result.exit_code == 1
