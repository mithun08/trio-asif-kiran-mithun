from __future__ import annotations

from pathlib import Path
from typing import Any

from matcher.models.consultant import Consultant
from matcher.models.role import Role


def build_index(consultants: list[Consultant], roles: list[Role], index_dir: Path) -> None:
    """Embed skills/roles/profiles and store vectors in Milvus Lite."""
    raise NotImplementedError


def load_index(index_dir: Path) -> Any:
    """Load an existing Milvus Lite collection from disk."""
    raise NotImplementedError
