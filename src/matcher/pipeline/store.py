from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from matcher.models.consultant import Consultant


def load_store(store_path: Path) -> list[Consultant]:
    if not store_path.exists():
        return []
    raw = json.loads(store_path.read_text())
    return [Consultant.model_validate(item) for item in raw]


def save_store(consultants: list[Consultant], store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps([c.model_dump(mode="json") for c in consultants], indent=2))


def hash_consultant_sources(
    pdf_path: Path | None,
    feedback_paths: list[Path],
) -> str:
    h = hashlib.sha256()
    for path in sorted(filter(None, [pdf_path, *feedback_paths])):
        if path.exists():
            s = path.stat()
            h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())
    return h.hexdigest()


def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    if path.exists():
        s = path.stat()
        h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())
    return h.hexdigest()


def load_text_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    if not cache_path.exists():
        return {}
    raw: dict[str, dict[str, Any]] = json.loads(cache_path.read_text())
    return raw


def save_text_cache(cache: dict[str, dict[str, Any]], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))
