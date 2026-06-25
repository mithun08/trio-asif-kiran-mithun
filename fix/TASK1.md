# TASK1 — snapshot_id Completeness

## Context

**File**: `src/matcher/cli.py:141-142`

Current code:
```python
stat = workbook.stat()
snapshot_id = hashlib.sha256(f"{stat.st_mtime}{stat.st_size}".encode()).hexdigest()[:16]
```

The `snapshot_id` is written into every `RunOutput` as the audit trail identifier. It currently
hashes only the Excel workbook's mtime+size. A change to any PDF profile, feedback markdown,
`config/default.yaml`, or `skill_adjacency.yaml` produces the same `snapshot_id` as before,
making the audit trail unreliable: two runs with different inputs appear identical.

**Evidence of missing inputs**:
- `cli.py:77`: `ingest_consultants(config.data_dir / "profiles", ...)` — reads all PDFs
- `cli.py:79`: `ingest_feedback(config.data_dir / "project_feedback", ...)` — reads all markdowns
- `cli.py:60`: `AppConfig.from_yaml(Path("config/default.yaml"))` — reads scoring config
- `cli.py:60`: `load_adjacency(Path("config/skill_adjacency.yaml"))` — reads skill graph

---

## Implementation

### Step 1 — Create a helper function in `cli.py`

Add above the `match` command (before line 40), after the existing imports:

```python
def _compute_snapshot_id(
    workbook: Path,
    profiles_dir: Path,
    feedback_dir: Path,
) -> str:
    h = hashlib.sha256()

    for path in sorted([
        workbook,
        Path("config/default.yaml"),
        Path("config/skill_adjacency.yaml"),
    ]):
        if path.exists():
            s = path.stat()
            h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())

    for directory in (profiles_dir, feedback_dir):
        if directory.exists():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    s = path.stat()
                    h.update(f"{path.name}:{s.st_mtime}:{s.st_size}".encode())

    return h.hexdigest()[:16]
```

**Rationale for mtime+size rather than file content hash**: reading content of 50 PDFs on
every `dsm match` call adds I/O proportional to corpus size. mtime+size is O(1) per file via
`stat()` syscall, sufficient to detect any write, and consistent with how the workbook was
already handled. Content hashing would be strictly better for reproducibility but the
incremental ingest (TASK5) will supersede this by storing extracted signals separately.

### Step 2 — Replace the snapshot_id line in `match` command (`cli.py:141-142`)

Remove:
```python
stat = workbook.stat()
snapshot_id = hashlib.sha256(f"{stat.st_mtime}{stat.st_size}".encode()).hexdigest()[:16]
```

Replace with:
```python
snapshot_id = _compute_snapshot_id(
    workbook,
    config.data_dir / "profiles",
    config.data_dir / "project_feedback",
)
```

### Step 3 — Annotate with embedding model version once TASK7 is complete

After TASK7 lands, extend `_compute_snapshot_id` to accept an `embedding_model: str` parameter
and include `h.update(embedding_model.encode())`. Wire it from `config.yaml:embedding.model`.
Add a comment at the call site: `# TODO(TASK7): add embedding_model arg after vector index lands`

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `src/matcher/cli.py` | 141-142 | Replace two-line snapshot with `_compute_snapshot_id()` call |
| `src/matcher/cli.py` | ~38 (before `match`) | Add `_compute_snapshot_id()` helper function |

No new files. No new dependencies.

---

## Validation & Verification

### V1 — Unit test: deterministic across identical inputs
```
tests/unit/test_snapshot_id.py
```
- Create `_compute_snapshot_id` with a tmp dir containing:
  - a fake workbook file
  - one fake PDF in `profiles/`
  - one fake markdown in `project_feedback/`
  - fake `config/default.yaml` and `config/skill_adjacency.yaml`
- Call twice — assert results are equal (deterministic)

### V2 — Unit test: changes when a PDF changes
- Modify the fake PDF's mtime via `os.utime()`
- Call again — assert result differs from V1

### V3 — Unit test: changes when config changes
- Modify `config/default.yaml` mtime
- Call again — assert result differs from V1

### V4 — Unit test: missing directories don't raise
- Call with non-existent `profiles_dir` and `feedback_dir`
- Assert no exception; result is a 16-char hex string

### V5 — Integration: mypy strict passes
```
uv run mypy src/matcher/cli.py
```
Expected: no new errors.

### V6 — Integration: existing unit tests still pass
```
uv run pytest tests/unit/ -v
```
Expected: all green (snapshot_id is not currently tested, so no regressions).

### V7 — Manual: two consecutive `dsm match` runs produce the same snapshot_id
Run `dsm match ROLE-01 --json | jq .snapshot_id` twice with no file changes.
Assert both values are identical.

### V8 — Manual: snapshot_id changes after touching a feedback file
```
touch data/project_feedback/any_file.md
dsm match ROLE-01 --json | jq .snapshot_id
```
Assert value differs from V7 baseline.

---

## Acceptance Criteria

- [ ] All V1–V4 unit tests pass
- [ ] `uv run mypy src/` passes with no new errors
- [ ] `uv run pytest tests/unit/ -v` all green
- [ ] Two consecutive runs with identical files produce identical `snapshot_id`
- [ ] Touching any PDF, markdown, or YAML changes the `snapshot_id`
