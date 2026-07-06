from __future__ import annotations

import os
import time
from pathlib import Path

from matcher.models.consultant import Consultant
from matcher.pipeline.store import (
    hash_consultant_sources,
    hash_file,
    load_store,
    load_text_cache,
    save_store,
    save_text_cache,
)


def test_store_roundtrip(tmp_path: Path) -> None:
    c = Consultant(email="alice@example.com", name="Alice", source_hash="abc123")
    path = tmp_path / "store.json"
    save_store([c], path)
    loaded = load_store(path)
    assert len(loaded) == 1
    assert loaded[0].email == "alice@example.com"
    assert loaded[0].source_hash == "abc123"


def test_hash_deterministic(tmp_path: Path) -> None:
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    h1 = hash_consultant_sources(f, [])
    h2 = hash_consultant_sources(f, [])
    assert h1 == h2


def test_hash_changes_on_mtime(tmp_path: Path) -> None:
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    h1 = hash_consultant_sources(f, [])
    time.sleep(0.01)
    os.utime(f, None)
    h2 = hash_consultant_sources(f, [])
    assert h1 != h2


def test_load_store_missing(tmp_path: Path) -> None:
    result = load_store(tmp_path / "nonexistent.json")
    assert result == []


def test_hash_file_deterministic(tmp_path: Path) -> None:
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    assert hash_file(f) == hash_file(f)


def test_hash_file_changes_on_mtime(tmp_path: Path) -> None:
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    h1 = hash_file(f)
    time.sleep(0.01)
    os.utime(f, None)
    h2 = hash_file(f)
    assert h1 != h2


def test_hash_file_missing_path() -> None:
    missing = Path("/nonexistent/profile.pdf")
    assert hash_file(missing) == hash_file(missing)


def test_text_cache_roundtrip(tmp_path: Path) -> None:
    cache = {
        "jane_pp.pdf": {
            "validity_key": "abc",
            "raw_text": "hi",
            "data_gaps": [],
            "confidence_factor": 1.0,
        }
    }
    path = tmp_path / "profile_text_cache.json"
    save_text_cache(cache, path)
    loaded = load_text_cache(path)
    assert loaded == cache


def test_load_text_cache_missing(tmp_path: Path) -> None:
    result = load_text_cache(tmp_path / "nonexistent.json")
    assert result == {}
