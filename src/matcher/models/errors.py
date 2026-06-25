from __future__ import annotations

from pathlib import Path


class IngestionError(Exception):
    def __init__(self, file: Path, problem: str) -> None:
        super().__init__(f"{file}: {problem}")
        self.file = file
        self.problem = problem


class BudgetExceededError(RuntimeError):
    pass
