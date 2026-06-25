# TASK5 — Incremental Ingest

## Context

**Files**: `src/matcher/cli.py`, `src/matcher/pipeline/extract.py`

Every `dsm match` invocation (`cli.py:72-115`) runs the full pipeline:
1. Re-reads all Excel sheets (ingest)
2. Re-parses all PDFs via docling/OCR (ingest)
3. Re-scrubs all PII (normalise)
4. Re-runs all LLM extraction calls (extract)

For 50 consultants with 3 feedback sources each, step 4 alone is `50 × (2 + 3)` = 250 LLM
calls on every `dsm match` run, regardless of whether any source file changed. With DSPy's
disk cache at `.cache/dspy/`, repeated extraction of unchanged text may hit cache — but cache
keying depends on the exact prompt string, and any model config change or prompt change
(e.g. TASK3 adding SYSTEM RULE preambles) will bust the cache.

**Structural gap identified in plan evaluation**: The current `dsm ingest` command
(`cli.py:174-199`) does NOT call `extract_signals()`. It only reads and reports on ingestion
quality. Incremental ingest requires moving extraction into `dsm ingest` and persisting the
results, so that `dsm match` can consume the persisted signals instead of re-extracting.

**Design decision**: `dsm ingest` becomes the LLM-heavy phase. `dsm match` becomes purely
deterministic (scoring, ranking, explanation generation). This maps to the CLAUDE.md
architecture: "Each pipeline stage must be independently unit-testable."

---

## Implementation

### Step 1 — Define the persisted store format

Create `src/matcher/pipeline/store.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from matcher.models.consultant import Consultant


_STORE_FILE = ".cache/extracted_consultants.json"


def load_store(store_path: Path) -> list[Consultant]:
    if not store_path.exists():
        return []
    raw = json.loads(store_path.read_text())
    return [Consultant.model_validate(item) for item in raw]


def save_store(consultants: list[Consultant], store_path: Path) -> None:
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(
        json.dumps([c.model_dump(mode="json") for c in consultants], indent=2)
    )
```

**Rationale for JSON over pickle**: CLAUDE.md explicitly hardened against pickle
(`client.py:12-17`, the restrict_pickle comment). JSON is human-readable, diff-able,
and immune to arbitrary code execution. Pydantic v2 `model_dump(mode="json")` serialises
all fields including `date`, `Literal`, and nested models.

### Step 2 — Add file hash tracking to `Consultant` model

Add an optional field to `Consultant` (`models/consultant.py`):

```python
source_hash: str = ""
```

This field stores the SHA-256 hex digest of the files that were used to populate this
consultant's extraction fields (PDF + feedback markdowns). When `dsm ingest` runs, it
computes and stores this hash. On subsequent runs, it recomputes the hash and skips
extraction if the hash is unchanged.

### Step 3 — Create `_hash_consultant_sources()` in `pipeline/ingest.py` or `store.py`

```python
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
```

**Same rationale as TASK1**: mtime+size via `stat()` is O(1) per file, sufficient to detect
any write. Full content hashing would require reading all PDFs on every ingest run.

### Step 4 — Extend `dsm ingest` command to run LLM extraction

In `cli.py`, update the `ingest` command (`cli.py:174-199`):

```python
@app.command()
def ingest(
    data_dir: str = typer.Option("data/", "--data-dir", help="Directory containing source files"),
    force: bool = typer.Option(False, "--force", help="Force re-ingest even if index is current"),
    output_json: bool = typer.Option(False, "--json", help="Emit JSON output"),
    no_llm: bool = typer.Option(False, "--no-llm", help="Skip LLM extraction"),
) -> None:
```

Add LLM extraction block after normalise:

```python
    # Load existing store to check which consultants need re-extraction
    store_path = config.cache_dir / "extracted_consultants.json"
    existing_store = load_store(store_path) if not force else []
    existing_by_email = {c.email.casefold(): c for c in existing_store}

    # Compute source hashes and skip unchanged consultants
    consultants_to_extract = []
    consultants_unchanged = []
    for consultant in consultants:
        pdf_path = config.data_dir / "profiles" / f"{consultant.email}.pdf"  # convention
        feedback_paths = [
            config.data_dir / "project_feedback" / f"{consultant.email}_{source}.md"
            for source in consultant.feedback_text.keys()
        ]
        current_hash = hash_consultant_sources(
            pdf_path if pdf_path.exists() else None,
            [p for p in feedback_paths if p.exists()],
        )
        existing = existing_by_email.get(consultant.email.casefold())
        if existing is not None and existing.source_hash == current_hash and not force:
            # Reuse previously extracted signals, update non-extracted fields
            consultants_unchanged.append(
                existing.model_copy(update={
                    "available_from": consultant.available_from,
                    "supply_state": consultant.supply_state,
                    "rolloff_confidence": consultant.rolloff_confidence,
                    "days_on_beach": consultant.days_on_beach,
                })
            )
        else:
            consultants_to_extract.append(
                consultant.model_copy(update={"source_hash": current_hash})
            )

    if not no_llm and consultants_to_extract:
        configure_dspy_cache(config.cache_dir)
        configure_lm(config)
        extracted = extract_signals(consultants_to_extract, config.scoring_config)
    else:
        extracted = consultants_to_extract

    all_consultants = consultants_unchanged + extracted
    save_store(all_consultants, store_path)
```

**Note on PDF path convention**: the exact path where PDF files are stored per consultant
depends on how `ingest_consultants()` works. The hash computation must use the actual path
that was read. This means `ingest_consultants()` should return (or accept) path metadata.
A simpler approach: hash the entire `profiles/` and `project_feedback/` directories,
per consultant, by scanning for files matching the consultant's email prefix.

### Step 5 — Update `dsm match` to read from store when available

In `cli.py`, in the `match` command, after normalise (before extract):

```python
    store_path = config.cache_dir / "extracted_consultants.json"
    if not no_llm and store_path.exists():
        stored = load_store(store_path)
        stored_by_email = {c.email.casefold(): c for c in stored}
        # Merge stored extraction signals into freshly ingested consultants
        consultants = [
            stored_by_email.get(c.email.casefold(), c)
            for c in consultants
        ]
        # Only run LLM extraction for consultants not in the store
        consultants_needing_extract = [
            c for c in consultants if c.email.casefold() not in stored_by_email
        ]
        if consultants_needing_extract:
            extracted_new = extract_signals(consultants_needing_extract, config.scoring_config)
            extracted_map = {c.email.casefold(): c for c in extracted_new}
            consultants = [extracted_map.get(c.email.casefold(), c) for c in consultants]
    elif not no_llm:
        # No store: full extraction as before
        consultants = extract_signals(consultants, config.scoring_config)
```

Remove the existing extract block at `cli.py:112-115`.

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `src/matcher/models/consultant.py` | end | Add `source_hash: str = ""` field |
| `src/matcher/pipeline/store.py` | new | `load_store()`, `save_store()` |
| `src/matcher/pipeline/store.py` | new | `hash_consultant_sources()` |
| `src/matcher/cli.py` | 174-199 | Extend ingest: add LLM extraction, hash tracking, store write |
| `src/matcher/cli.py` | 112-115 | Replace unconditional extract with store-aware extract |

No new external dependencies. `hashlib` and `json` are stdlib.

---

## Validation & Verification

### V1 — Unit test: `save_store` then `load_store` round-trips a Consultant
```python
from matcher.pipeline.store import load_store, save_store
from matcher.models.consultant import Consultant

def test_store_roundtrip(tmp_path):
    c = Consultant(email="alice@example.com", name="Alice", source_hash="abc123")
    path = tmp_path / "store.json"
    save_store([c], path)
    loaded = load_store(path)
    assert len(loaded) == 1
    assert loaded[0].email == "alice@example.com"
    assert loaded[0].source_hash == "abc123"
```

### V2 — Unit test: `hash_consultant_sources` is deterministic
```python
def test_hash_deterministic(tmp_path):
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    h1 = hash_consultant_sources(f, [])
    h2 = hash_consultant_sources(f, [])
    assert h1 == h2

def test_hash_changes_on_mtime(tmp_path):
    f = tmp_path / "profile.pdf"
    f.write_bytes(b"data")
    h1 = hash_consultant_sources(f, [])
    import os, time; time.sleep(0.01); os.utime(f, None)
    h2 = hash_consultant_sources(f, [])
    assert h1 != h2
```

### V3 — Unit test: `load_store` returns empty list for missing file
```python
def test_load_store_missing(tmp_path):
    result = load_store(tmp_path / "nonexistent.json")
    assert result == []
```

### V4 — Integration: `dsm ingest --no-llm` creates store file
```
uv run dsm ingest --no-llm
ls .cache/extracted_consultants.json
```
Expected: file exists.

### V5 — Integration: second `dsm ingest --no-llm` is faster (skip unchanged)
Run twice, measure wall time. Second run should be shorter or equal (no LLM, no OCR re-parse
because the store is read-only in `--no-llm` mode — this tests the store read path).

### V6 — Integration: `dsm match --no-llm` uses store when present
```
uv run dsm ingest --no-llm
uv run dsm match ROLE-01 --no-llm --top 3
```
Expected: completes without error; consultants in output match store contents.

### V7 — Integration: `--force` flag bypasses hash check
```
uv run dsm ingest --force --no-llm
```
Expected: store is fully rebuilt even if no files changed.

### V8 — mypy
```
uv run mypy src/
```
Expected: `source_hash: str = ""` is `str` — no mypy issues. `store.py` types clean.

### V9 — Full unit suite
```
uv run pytest tests/unit/ -v
```
Expected: all green. The `Consultant` model now has `source_hash` field — any unit test
constructing a `Consultant` without it still works because `source_hash = ""` is the default.

---

## Acceptance Criteria

- [ ] `Consultant` has `source_hash: str = ""` field
- [ ] `store.py` exists with `load_store()`, `save_store()`, `hash_consultant_sources()`
- [ ] `dsm ingest` creates `.cache/extracted_consultants.json`
- [ ] `dsm ingest` skips unchanged consultants on second run (hash match)
- [ ] `dsm match` reads from store when present, re-extracts only new/changed consultants
- [ ] `--force` flag triggers full rebuild
- [ ] V1–V3 unit tests pass
- [ ] `uv run mypy src/` passes
- [ ] `uv run pytest tests/unit/ -v` all green
