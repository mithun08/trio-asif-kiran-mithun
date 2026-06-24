from __future__ import annotations

import time
from pathlib import Path

import pytest

WORKBOOK_PATH = Path("data/demand-supply.xlsx")
WALL_CLOCK_LIMIT_S = 5.0


@pytest.fixture(autouse=True)
def require_workbook() -> None:
    if not WORKBOOK_PATH.exists():
        pytest.skip("workbook not found")


def test_match_no_llm_warm_path_under_5s() -> None:
    from typer.testing import CliRunner

    from matcher.cli import app

    runner = CliRunner()
    start = time.perf_counter()
    result = runner.invoke(app, ["match", "ROLE-01", "--no-llm"])
    elapsed = time.perf_counter() - start
    assert result.exit_code == 0, result.output
    assert elapsed < WALL_CLOCK_LIMIT_S, (
        f"warm path took {elapsed:.2f}s, limit {WALL_CLOCK_LIMIT_S}s"
    )
