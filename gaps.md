# Implementation Gaps: TASK1–TASK8

All gaps are grounded in file reads. Each entry cites the spec source (`fix/TASK*.md`) and the actual code location where the gap exists or the implementation is absent.

---

## TASK1 — snapshot_id Completeness

### GAP 1.1 — Missing unit test V3: config file change detection

**Spec** (`fix/TASK1.md` V3): "Modify `config/default.yaml` mtime → assert result differs from V1."

**Reality**: `tests/unit/test_snapshot_id.py` has four tests — `test_deterministic`, `test_changes_on_pdf_mtime`, `test_changes_on_workbook_mtime`, `test_missing_directories_dont_raise`. None of them modify `config/default.yaml` or `config/skill_adjacency.yaml` mtime and assert the snapshot changes. The code paths at `cli.py:51-58` that hash the two YAML config files are untested.

---

### GAP 1.2 — Embedding model version not included in snapshot_id (TASK1 Step 3)

**Spec** (`fix/TASK1.md` Step 3): "After TASK7 lands, extend `_compute_snapshot_id` to accept `embedding_model: str` parameter and include `h.update(embedding_model.encode())`. Wire it from `config.yaml:embedding.model`. Add a comment at the call site: `# TODO(TASK7): add embedding_model arg after vector index lands`."

**Reality**:
- `cli.py:44-67`: `_compute_snapshot_id(workbook, profiles_dir, feedback_dir)` — no `embedding_model` parameter.
- `cli.py:213-217`: call site has no TODO comment.
- `config/default.yaml:75-77`: `embedding.model: "all-MiniLM-L6-v2"` exists but `AppConfig.from_yaml()` at `config.py:250-284` never reads the `embedding:` section. The model name is not surfaced through `AppConfig` at all.

---

## TASK2 — PII Scrub Hardening

No gaps. All three acceptance criteria are met:
- `scrubber.py:8`: `ORGANIZATION` added to `_ENTITIES`.
- `scrubber.py:83-87`: `assert_no_residual_pii()` raises on email/phone patterns.
- `normalise.py:45,52`: gate called after each `scrub_text()` invocation.

---

## TASK3 — Prompt Injection Defence

### GAP 3.1 — Canary test body unconditionally skips; no assertion is ever reached

**Spec** (`fix/TASK3.md` Step 2 / acceptance criteria): "Create canary regression tests in `tests/evals/test_injection_canary.py` with parametrized adversarial strings."

**Reality**: `tests/evals/test_injection_canary.py:14-22`:

```python
@pytest.mark.parametrize("canary", CANARY_INJECTION_STRINGS)
def test_canary_does_not_alter_sentiment(canary: str) -> None:
    pytest.importorskip("dspy")
    import dspy
    from matcher.llm.modules import FeedbackSignalExtraction  # noqa: F401
    with dspy.context(lm=None):
        pytest.skip("requires live LM — run with DSM_OPENROUTER_API_KEY set")
```

`pytest.skip()` is called inside `dspy.context(lm=None)` which does not suppress it. The test always skips. No prediction is ever made, so the SYSTEM RULE boundary markers in `modules.py` are never exercised — not even with a mock LM. The test stubs the required strings but makes no assertion.

---

## TASK4 — Model Fallback & Budget Guard

### GAP 4.1 — Async extraction path (`_extract_one`) missing budget check

**Spec** (`fix/TASK4.md` Step 5): "After each consultant's extraction block, call `check_budget(app_config.max_cost_usd_per_run, app_config.max_tokens_per_run)`."

**Reality**:
- Sync path `extract_signals()` at `pipeline/extract.py:53-55` correctly calls `check_budget()` after each consultant.
- Async path `_extract_one()` at `pipeline/extract.py:60-103` has signature `(consultant, config, semaphore, primary_lm, fallback_lm)` — no `app_config` parameter. It never calls `check_budget()`.
- `extract_signals_async()` at `pipeline/extract.py:106-115` also has no `app_config` parameter.
- `dsm ingest` calls `extract_signals_async()` (`cli.py:306-313`) with no budget enforcement. A 50-consultant async ingest has no mid-run abort on cost or token overrun.

---

## TASK5 — Incremental Ingest

No gaps. All acceptance criteria are met:
- `store.py`: `load_store()`, `save_store()`, `hash_consultant_sources()` implemented.
- `consultant.py:35`: `source_hash: str = ""` field present.
- `cli.py:269-298`: ingest computes source hash per consultant, skips unchanged.
- `cli.py:146-173`: match loads from store by email, re-extracts only new consultants.
- `cli.py:252`: `--force` flag present.

---

## TASK6 — Async Extraction

### GAP 6.1 — Async path missing budget check (same root as GAP 4.1)

**Spec** (`fix/TASK6.md`): TASK6 depends on TASK4 for budget-guarded extraction.

**Reality**: `_extract_one()` (`pipeline/extract.py:60-103`) carries no `app_config` reference. The async ingest path (`cli.py:306-313`) has no per-consultant budget enforcement. Described in detail under GAP 4.1.

---

### GAP 6.2 — Missing note about batching embedding calls for TASK7

**Spec** (`fix/TASK6.md`): "Include note about batching embedding calls when TASK7 lands."

**Reality**: `pipeline/extract.py:60-115` (the entire async extraction implementation) contains no such comment. No mention of embedding call batching anywhere in the async code path.

---

## TASK7 — Vector Index & Skill Matching

### GAP 7.1 — Embedding model hardcoded; not configurable via AppConfig

**Spec** (`fix/TASK7.md` Step 1, cross-referencing TASK1 Step 3): Wire embedding model name from `config.yaml:embedding.model` into `AppConfig`, then into `_compute_snapshot_id` and `index.py`.

**Reality**:
- `pipeline/index.py:9`: `_MODEL_NAME = "all-MiniLM-L6-v2"` — hardcoded constant.
- `cli.py:178`: `SentenceTransformer("all-MiniLM-L6-v2")` — hardcoded string literal.
- `config/default.yaml:75-77` has the `embedding:` section (`model: "all-MiniLM-L6-v2"`), but `AppConfig.from_yaml()` at `config.py:266-284` reads only `models:`, `scoring:`, `llm:`, `observability:`, `ocr:`, `provider:`, `budget:` — the `embedding:` key is never read.
- Changing the embedding model in `config/default.yaml` has no effect on any running code.

---

### GAP 7.2 — `skill_vector_similarity` duplicated in YAML instead of moved

**Spec** (`fix/TASK7.md` Step 1): "Move `skill_vector_similarity` from `scoring.thresholds` into `scoring.config` to unify the config section; thresholds section becomes unused."

**Reality**:
- `config/default.yaml:13`: `scoring.thresholds.skill_vector_similarity: 0.65` — original location, still present.
- `config/default.yaml:59`: `scoring.config.skill_vector_similarity: 0.65` — new location, added.
- The value was duplicated, not moved. `scoring.thresholds` still has three active keys (`skill_exact_match`, `skill_adjacent_match`, `skill_vector_similarity`), contrary to the spec intent of making it unused. The `AppConfig.from_yaml()` bridge at `config.py:257-265` that reads from `thresholds` as a fallback also remains, so the old key is still silently active.

---

### GAP 7.3 — `_compute_snapshot_id` not extended with embedding model version

Same as GAP 1.2. This is the TASK7 side of the same missing cross-task wiring: `_compute_snapshot_id` at `cli.py:44-67` should include `h.update(embedding_model.encode())` after TASK7 landed, but neither the parameter nor the call-site change was made.

---

## TASK8 — Eval-in-CI Gate

### GAP 8.1 — Golden file missing "unfillable" kind entry

**Spec** (`fix/TASK8.md` Step 1 / acceptance criteria): "≥5 entries covering all three kinds: exact, negative, unfillable."

**Reality**: `evals/golden/roles.yaml:1-31` has 5 entries:
- 3 × `kind: exact` (EVAL-01, EVAL-02, EVAL-05)
- 2 × `kind: negative` (EVAL-02, EVAL-03)
- 0 × `kind: unfillable`

The `unfillable` branch in `test_deepeval_golden.py:75-77` (`if not ranked: passed += 1`) is never exercised, meaning it cannot detect a regression where the pipeline incorrectly returns candidates for a role that should yield none.

---

### GAP 8.2 — CI eval job missing `env: DSM_EVAL_WORKBOOK`

**Spec** (`fix/TASK8.md` Step 5): "Set `DSM_EVAL_WORKBOOK=evals/fixtures/eval_data.xlsx` in the CI job."

**Reality**: `.github/workflows/ci.yml:52-68` eval job has no `env:` block. The test mitigates this via auto-detection (`test_deepeval_golden.py:11`: `WORKBOOK_PATH = _REAL_WORKBOOK if _REAL_WORKBOOK.exists() else _FIXTURE_WORKBOOK`), but if `data/demand-supply.xlsx` ever gets committed to CI or the auto-detect logic changes, the explicit env var would be the safe fallback. The spec requirement is unmet.

---

### GAP 8.3 — No thresholds comment block in `test_deepeval_golden.py`

**Spec** (`fix/TASK8.md` Step 6): "Add a comment block at the top of `tests/evals/test_deepeval_golden.py` documenting the [0.70, 0.85] pass rate thresholds and the rationale."

**Reality**: `tests/evals/test_deepeval_golden.py:1-99` has no such comment. The thresholds appear as bare assert values at lines 94 and 97 with inline messages, but the rationale ("below 0.70 = pipeline broken or set too hard; above 0.85 = set not discriminating enough, add negatives") is absent.

---

## Summary Table

| Gap | Task | File | Severity |
|-----|------|------|----------|
| 1.1 | TASK1 | `tests/unit/test_snapshot_id.py` | Low — untested code path (config YAML hashing) |
| 1.2 | TASK1 | `cli.py:44-67`, `config.py:250-284` | Medium — snapshot_id excludes embedding model version; audit trail incomplete post-TASK7 |
| 3.1 | TASK3 | `tests/evals/test_injection_canary.py:14-22` | Medium — injection defence tests are stubs; no assertion ever executes |
| 4.1 | TASK4 | `pipeline/extract.py:60-103` | High — async ingest has no budget abort; cost/token ceiling not enforced on async path |
| 6.1 | TASK6 | `pipeline/extract.py:106-115` | High — same as 4.1; async path was added without carrying forward budget guard |
| 6.2 | TASK6 | `pipeline/extract.py:60-115` | Low — missing comment; no functional impact |
| 7.1 | TASK7 | `pipeline/index.py:9`, `config.py:250-284` | Medium — embedding model change in YAML has no effect on code |
| 7.2 | TASK7 | `config/default.yaml:13,59` | Low — duplicate key; `scoring.thresholds` not cleaned up as specified |
| 7.3 | TASK7 | `cli.py:44-67` | Medium — same root as 1.2; TASK7 cross-task extension not done |
| 8.1 | TASK8 | `evals/golden/roles.yaml` | Medium — unfillable branch in eval test never exercised; regression blind spot |
| 8.2 | TASK8 | `.github/workflows/ci.yml:52-68` | Low — env var absent; auto-detect mitigates for now |
| 8.3 | TASK8 | `tests/evals/test_deepeval_golden.py` | Low — missing documentation comment |
