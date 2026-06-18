from __future__ import annotations

from pathlib import Path

from matcher.models.consultant import Consultant
from matcher.models.role import Role


def ingest_roles(xlsx_path: Path) -> list[Role]:
    """Parse demand-supply workbook → list of Role objects."""
    raise NotImplementedError


def ingest_consultants(profiles_dir: Path) -> list[Consultant]:
    """Parse PDF profiles via Docling → list of Consultant objects."""
    raise NotImplementedError


def ingest_feedback(feedback_dir: Path, consultants: list[Consultant]) -> list[Consultant]:
    """Parse feedback markdown files and attach to matching consultants by email."""
    raise NotImplementedError
