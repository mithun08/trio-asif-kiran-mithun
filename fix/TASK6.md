# TASK6 — Async Extraction

## Context

**File**: `src/matcher/pipeline/extract.py:13-42`

Current implementation is a sequential for-loop:
```python
def extract_signals(consultants: list[Consultant], config: ScoringConfig) -> list[Consultant]:
    result: list[Consultant] = []
    for consultant in consultants:
        ...
        consultant = extract_profile(consultant, config)
        for source in list(consultant.feedback_text.keys()):
            consultant = extract_feedback(consultant, source, config)
        ...
        consultant = extract_adaptability(consultant, combined_text, config)
        consultant = extract_trend(consultant, combined_text, config)
        result.append(consultant)
    return result
```

Per-consultant call count (verified from `extract.py` logic):
- `extract_profile`: 1 call (+ 1 retry on parse failure: `extract.py:113-115`)
- `extract_feedback`: 1 call per feedback source key in `consultant.feedback_text`
- `extract_adaptability`: 1 call
- `extract_trend`: 1 call

For a consultant with 3 feedback sources: `1 + 3 + 1 + 1 = 6` blocking calls in series.
For 50 consultants: up to 300 sequential LLM calls. At ~1–2 seconds each, this is 5–10
minutes in serial.

**Prerequisites — this task depends on TASK4 and TASK5**:

1. **TASK4 dependency**: TASK4 changes all DSPy calls to use `dspy.context(lm=...)` instead
   of the global `dspy.settings.lm`. This is required before async can be added safely.
   Without it, concurrent extraction workers share a global mutable LM reference that a
   fallback-triggered `dspy.configure(lm=fallback_lm)` call would corrupt.

2. **TASK5 dependency**: TASK5 separates ingest extraction (which can now be async) from
   the `dsm match` hot path. After TASK5, extraction only runs in `dsm ingest`, not on
   every `dsm match`. This changes the target of async: it is `dsm ingest`'s extraction
   phase, not `dsm match`.

---

## Implementation

### Step 1 — Make `extract_signals_async()` in `pipeline/extract.py`

Add an async variant alongside the existing sync version. The existing `extract_signals()`
is kept as a synchronous wrapper for backwards compatibility and `--no-llm` paths.

```python
import asyncio
from matcher.llm.extract import (
    extract_adaptability,
    extract_feedback,
    extract_profile,
    extract_trend,
)


async def _extract_one(
    consultant: Consultant,
    config: ScoringConfig,
    semaphore: asyncio.Semaphore,
    primary_lm: object | None,
    fallback_lm: object | None,
) -> Consultant:
    async with semaphore:
        loop = asyncio.get_running_loop()

        has_profile = bool(consultant.raw_profile_text.strip())
        has_feedback = bool(consultant.feedback_text)

        if not has_profile and not has_feedback:
            return consultant.model_copy(
                update={"data_gaps": [*consultant.data_gaps, "no feedback"]}
            )

        if has_profile:
            consultant = await loop.run_in_executor(
                None, extract_profile, consultant, config, primary_lm, fallback_lm
            )

        for source in list(consultant.feedback_text.keys()):
            consultant = await loop.run_in_executor(
                None, extract_feedback, consultant, source, config, primary_lm, fallback_lm
            )

        combined_parts = [consultant.raw_profile_text] + list(consultant.feedback_text.values())
        combined_text = "\n".join(part for part in combined_parts if part.strip())

        if combined_text.strip():
            consultant = await loop.run_in_executor(
                None, extract_adaptability, consultant, combined_text, config, primary_lm, fallback_lm
            )
            consultant = await loop.run_in_executor(
                None, extract_trend, consultant, combined_text, config, primary_lm, fallback_lm
            )

        return consultant


async def extract_signals_async(
    consultants: list[Consultant],
    config: ScoringConfig,
    max_workers: int = 5,
    primary_lm: object | None = None,
    fallback_lm: object | None = None,
) -> list[Consultant]:
    semaphore = asyncio.Semaphore(max_workers)
    tasks = [
        _extract_one(c, config, semaphore, primary_lm, fallback_lm)
        for c in consultants
    ]
    return list(await asyncio.gather(*tasks))
```

**Rationale for `run_in_executor` rather than native async**: DSPy's `dspy.Predict.__call__`
is synchronous — it makes blocking HTTP calls internally via `litellm`. There is no
`dspy.Predict.acall()` in the pinned `dspy-ai>=2.4`. `run_in_executor(None, ...)` offloads
each blocking call to the default `ThreadPoolExecutor`, achieving I/O concurrency without
requiring DSPy to be refactored. The GIL is released during I/O, so threads actually
overlap on network waits.

**Rationale for `max_workers=5`**: OpenRouter's default rate limit is ~60 requests/minute
per key. At 6 calls per consultant, 5 concurrent consultants = 30 concurrent requests peak.
This stays comfortably under rate limits while reducing total wall time by ~5×. Make this
configurable via `config/default.yaml` (`llm.max_concurrent_extractions: 5`).

### Step 2 — Add `max_concurrent_extractions` to config

In `AppConfig` (`config.py`):
```python
max_concurrent_extractions: int = Field(default=5, ge=1, le=20)
```

In `AppConfig.from_yaml()`:
```python
max_concurrent_extractions=raw.get("llm", {}).get("max_concurrent_extractions", 5),
```

In `config/default.yaml` under `llm:`:
```yaml
llm:
  temperature: 0
  cache_dir: ".cache/dspy"
  max_retries: 3
  max_concurrent_extractions: 5
```

### Step 3 — Update `dsm ingest` to call `extract_signals_async()`

In `cli.py`, in the `ingest` command (after TASK5 lands), replace:
```python
extracted = extract_signals(consultants_to_extract, config.scoring_config)
```
With:
```python
extracted = asyncio.run(
    extract_signals_async(
        consultants_to_extract,
        config.scoring_config,
        max_workers=config.max_concurrent_extractions,
        primary_lm=primary_lm,
        fallback_lm=fallback_lm,
    )
)
```

Where `primary_lm` and `fallback_lm` are the LM objects returned from `configure_lm()` /
`make_lm()` (TASK4).

### Step 4 — Keep `extract_signals()` sync for `--no-llm` and match paths

The synchronous `extract_signals()` continues to exist unchanged. `dsm match`'s fallback
path (for consultants not in the store) can use the sync version since it will be a minority
of calls after TASK5.

### Step 5 — Add embedding batch call optimisation

Once TASK7 (vector index) is implemented, the embedding step should be batched rather than
one-at-a-time. Add a note in `pipeline/index.py`:

```python
# Batch embedding: pass all skill texts at once to SentenceTransformer.encode()
# rather than one skill per call. sentence-transformers handles batching internally.
# model.encode(["skill1", "skill2", ...], batch_size=32, show_progress_bar=False)
```

This is documented here because it shares the same thread-safety concern as async extraction:
the `SentenceTransformer` model object is not thread-safe by default if shared across threads.
Use one model instance per `asyncio.run()` call, or use a `threading.Lock` guard.

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `src/matcher/pipeline/extract.py` | new function | Add `_extract_one()`, `extract_signals_async()` |
| `src/matcher/config.py` | AppConfig | Add `max_concurrent_extractions: int` |
| `config/default.yaml` | `llm:` section | Add `max_concurrent_extractions: 5` |
| `src/matcher/cli.py` | ingest command | Replace sync extract with `asyncio.run(extract_signals_async(...))` |

No new external dependencies. `asyncio` is stdlib.

---

## Validation & Verification

### V1 — Unit test: `extract_signals_async` produces same result as sync version

```python
import asyncio
from unittest.mock import patch, MagicMock
from matcher.pipeline.extract import extract_signals, extract_signals_async
from matcher.models.consultant import Consultant

def test_async_matches_sync_result():
    consultant = Consultant(email="a@b.com", name="A", raw_profile_text="")
    with patch("matcher.pipeline.extract.extract_profile", side_effect=lambda c, *_: c), \
         patch("matcher.pipeline.extract.extract_feedback", side_effect=lambda c, *_: c), \
         patch("matcher.pipeline.extract.extract_adaptability", side_effect=lambda c, *_: c), \
         patch("matcher.pipeline.extract.extract_trend", side_effect=lambda c, *_: c):
        sync_result = extract_signals([consultant], MagicMock())
        async_result = asyncio.run(extract_signals_async([consultant], MagicMock()))
    assert sync_result[0].email == async_result[0].email
```

### V2 — Unit test: semaphore limits concurrency

Use a `threading.Event` to track max simultaneous calls:

```python
def test_max_workers_respected():
    import threading
    active = []
    lock = threading.Lock()
    max_seen = 0

    def slow_extract(c, *args):
        nonlocal max_seen
        with lock:
            active.append(1)
            max_seen = max(max_seen, len(active))
        time.sleep(0.05)
        with lock:
            active.pop()
        return c

    consultants = [Consultant(email=f"{i}@b.com", name=str(i)) for i in range(10)]
    with patch("matcher.pipeline.extract.extract_profile", side_effect=slow_extract):
        asyncio.run(extract_signals_async(consultants, MagicMock(), max_workers=3))

    assert max_seen <= 3
```

### V3 — Unit test: order of output matches order of input

```python
def test_output_order_preserved():
    emails = ["a@b.com", "c@d.com", "e@f.com"]
    consultants = [Consultant(email=e, name=e) for e in emails]
    with patch(...):  # no-op patches
        result = asyncio.run(extract_signals_async(consultants, MagicMock()))
    assert [c.email for c in result] == emails
```

**Rationale**: `asyncio.gather(*tasks)` preserves task order by design. This test confirms
the implementation does not inadvertently sort or reorder.

### V4 — Integration: `dsm ingest --no-llm` still works (sync path)

```
uv run dsm ingest --no-llm
```
Expected: completes, store file written, no `asyncio` error.

### V5 — Integration: wall-time measurement (optional, informational)

With a real OpenRouter key, time `dsm ingest` before and after this change with 10+
consultants. Expected: >3× speedup at `max_workers=5` with network I/O dominating.

### V6 — mypy
```
uv run mypy src/matcher/pipeline/extract.py src/matcher/config.py
```
Expected: no new errors. `asyncio` types from stdlib, fully typed.

### V7 — Full unit suite
```
uv run pytest tests/unit/ -v
```
Expected: all green.

---

## Acceptance Criteria

- [ ] `extract_signals_async()` exists with `asyncio.Semaphore` worker limit
- [ ] `max_concurrent_extractions` config field added (default 5)
- [ ] `dsm ingest` uses async extraction path
- [ ] `dsm match`'s fallback extraction path uses sync version (minority of calls)
- [ ] Output order is preserved (matches input list order)
- [ ] V1–V3 unit tests pass
- [ ] `uv run mypy src/` passes
- [ ] `uv run pytest tests/unit/ -v` all green
- [ ] **TASK4 must be merged first** (dspy.context pattern required for thread safety)
- [ ] **TASK5 must be merged first** (async extraction lives in `dsm ingest`)
