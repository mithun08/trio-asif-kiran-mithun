from __future__ import annotations

from pathlib import Path

from matcher.models.errors import IngestionError


def test_ingestion_error_str() -> None:
    exc = IngestionError(Path("/x.xlsx"), "missing sheet 'Open Roles'")
    assert str(exc) == "/x.xlsx: missing sheet 'Open Roles'"


def test_ingestion_error_file_attr() -> None:
    exc = IngestionError(Path("/data/wb.xlsx"), "workbook unreadable")
    assert exc.file == Path("/data/wb.xlsx")


def test_ingestion_error_problem_attr() -> None:
    exc = IngestionError(Path("/data/wb.xlsx"), "workbook unreadable")
    assert exc.problem == "workbook unreadable"


def test_ingestion_error_is_exception() -> None:
    exc = IngestionError(Path("/x.xlsx"), "bad")
    assert isinstance(exc, Exception)
