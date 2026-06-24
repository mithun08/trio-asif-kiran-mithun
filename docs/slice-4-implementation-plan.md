# Slice 4 — Implementation Plan: Production Hardening + Eval Harness

| Field | Value |
|---|---|
| Source | `docs/PLAN.md` §Slice 4 (lines 123–143) |
| Specs cross-referenced | `PRD_refined.md` (FR-44/45/48/49/50/53, AC-6/AC-8/AC-10, NFR-09/NFR-11, "Evaluation Expectations" lines 306–319), `TECHNICAL_DESIGN.md` (§5.1 carry-over, §5.2 zero-retention), `SCORING_SPEC.md` (unchanged) |
| Scope | OCR for scanned PDFs (FR-48), ingestion + unmatched reports (FR-49/50), malformed-file robustness (FR-53), stale-date / ambiguous free-text (FR-44/45), eval harness (DeepEval primary, Promptfoo optional) against `evals/golden/`, observability + cost telemetry (NFR-09), provider zero-retention config (TDD §5.2) |
| Out of scope | Milvus / vector store at scale, DSPy optimisation, Markdown/HTML reporting, anything Slices 1–3 already shipped |
| Predecessor | Slice 3 (explanations, gap report, JSON output) — six dimensions scored, PII scrub wired, `RunOutput` envelope in place |

---

## Context

Slices 1–3 took the pipeline from a deterministic shortlist to a grounded, explained, machine-readable recommendation. Slice 4 is the **boundary work** — what happens when inputs are bad, what operators see, what the system promises about the provider, and how it is measured against a labelled truth set. PLAN.md line 127 names the build set; this plan turns that bullet list into file-by-file deltas against the current `main`.

### What's already true on `main` (validated against the repo, 2026-06-24)

- **OCR (FR-48):** Docling is the PDF extractor (`src/matcher/pipeline/ingest.py:178-187`); on failure it returns `("", ["profile_pdf_unreadable"], 0.7)`. No image-only detection, no OCR retry, no `pytesseract` / `ocrmypdf` / `easyocr` in `pyproject.toml`.
- **Ingestion summary (FR-49/50):** `Consultant.data_gaps` is already populated (Slice 1/2); orphan feedback files are logged via `logging` (`ingest.py:269,274`). **No structured `IngestionReport` is built or surfaced.** `cli.py:64-71` defines an `ingest` Typer command that only `echo`'s its arguments — a pure stub.
- **Robustness (FR-53):** Column-missing on a sheet raises a clear `ValueError` (`ingest.py:74-77,131-132`). Missing sheet (`wb["Open Roles"]`, `ingest.py:71`) raises an unwrapped `KeyError`; unreadable workbook propagates `openpyxl` errors. No `test_robustness.py`.
- **Stale-date / ambiguous (FR-44/45):** No past-date warning anywhere in `filters.py` or `ingest.py`; `Role.start_date` is parsed but never compared to "today". CLI accepts a `role_id` only (`cli.py:26`) — no free-text path. No `test_stale_date.py`.
- **Observability (NFR-09):** `src/matcher/observability/run_log.py` exports four `structlog` helpers — `log_run_start`, `log_stage_timing`, `log_llm_usage`, `log_data_quality`. **None are called from `cli.py` or any pipeline module.** Primitive exists; wiring does not.
- **Zero-retention (TDD §5.2):** `src/matcher/llm/client.py:12-19` builds `dspy.LM` with only `api_key + api_base + temperature + max_retries`. No `extra_headers`, no `extra_body`, no provider allow-list, no retention flag. TDD §5.2 (lines 173–177) is the unimplemented contract.
- **Eval harness:** `tests/evals/deepeval_suite.py` is a 5-line skeleton comment; `tests/evals/promptfoo.yaml` has `tests: []`. `evals/golden/roles.yaml` does not exist. PLAN.md lines 32–39 say start it on day one — Slice 4 consumes whatever the parallel track produced.
- **AC-8 latency:** No timing instrumentation. Wall-clock is observable from outside; per-stage timings are not.

---

## YAGNI scope decisions

| Topic | Decision | Rationale |
|---|---|---|
| OCR engine | Reuse the existing **Docling** dependency with OCR enabled on the second pass. Detect "image-only" by first-pass extracted-text length below `ocr.text_floor_chars` (default 50). No new heavy dependency. | TDD §3 line 77 lists Docling as the document tool covering FR-48; one dependency is cheaper than two. |
| Ambiguous free-text (FR-44) | New `--free-text "<spec>"` flag on `dsm match`. Rule-based extractor (regex over title / location / skill / start-date tokens) flags unresolved slots; prompts via stderr. `--yes` flag accepts defaults non-interactively (eval/CI). **No new LLM call.** | PLAN.md line 102 + AC-10 line 304. Cost discipline. |
| Stale-date warning (FR-45) | Pure deterministic check after `_parse_date` in `ingest_roles` (`ingest.py:94`). Past dates emit a warning into `IngestionReport.warnings`; run continues. | PLAN.md line 136. Cheap. |
| `IngestionReport` (FR-49/50) | New Pydantic model attached to `RunOutput.ingestion_report` and printed in stderr text mode. Counts: profiles parsed, low-confidence, feedback matched/unmatched, supply-tab consultants without profile, free-form warnings. | PRD lines 193–194; satisfies AC-6. |
| Robustness wrapping (FR-53) | Single `IngestionError(file, problem)` exception in `models/errors.py`. Wrap `load_workbook` (`ingest.py:70,122`), sheet access (`ingest.py:71,126`), feedback file open. PDF errors keep their structured-flag path (already correct). | AC-10 line 304. One exception type, consistent surface. |
| Observability wiring (NFR-09) | `stage_timer(name)` context manager in `observability/timing.py` calls existing `log_stage_timing` (`run_log.py:12`) on exit. CLI wraps each stage: `ingest`, `normalise`, `extract`, `match`, `explain`, `render`. **No rewrite of `run_log.py`.** | Reuses primitives at `run_log.py:5-25`. |
| Cost / token telemetry | Tap `dspy.settings.lm.history[-1]` after each LM call in `extract.py`, `explain_module.py`, `skill_inference.py` and feed `log_llm_usage(task, tokens, cost_usd, cache_hit)`. Aggregate into `RunTelemetry`. | TDD §5; existing primitive `run_log.py:16-17` already accepts these fields. |
| Zero-retention provider config (TDD §5.2) | Pass `extra_headers={"X-Title": "demand-supply-matcher", "HTTP-Referer": "https://demand-supply-matcher.local"}` + `extra_body={"provider": {"data_collection": "deny"}}` to `dspy.LM(...)`. Add `config.allowed_models: list[str]`; startup fails if any of `model_extraction / model_explain / model_skill_inference` is outside the list. | TDD §5.2 lines 173–177. OpenRouter privacy-aware routing per their public API. **User input required** (see §Inputs needed). |
| Eval harness — primary | **DeepEval** suite at `tests/evals/test_deepeval_golden.py` using `GEval(metric="explanation_faithfulness")` + `AnswerRelevancyMetric` against `evals/golden/roles.yaml`. Replaces the 5-line skeleton at `deepeval_suite.py:3-4`. | PLAN.md line 129; DeepEval already in `pyproject.toml`. |
| Eval harness — secondary | **Promptfoo** populated in `tests/evals/promptfoo.yaml` (currently `tests: []`) as a snapshot comparison. **Optional**, gated behind `make eval-promptfoo`. | PLAN.md line 129 says "optionally Promptfoo". |
| Golden dataset | `evals/golden/roles.yaml` — 8–12 roles, each with `role_id`, `expected_top_emails`, `notes`, **negatives**, one **unfillable**. Matches the PRD "Evaluation Expectations" table (lines 311–317). | PLAN.md lines 32–39. |
| Eval pass-rate gate | `make eval` asserts pass rate ∈ **[0.70, 0.85]**. A 100% pass is itself a failure signal (PLAN.md line 137) — the suite is rejected for not discriminating. | PLAN.md lines 137 + 319. |
| Latency benchmark (AC-8) | New `tests/integration/test_latency_ac8.py` using `time.perf_counter()` (no `pytest-benchmark` dependency). Asserts single-role < 5 s warm-cache, batch < 60 s. **Skipped** when `data/` absent. | PRD line 302. |
| Markdown/HTML report | **Deferred to a v2 roadmap.** Slice 3 already ships terminal text + JSON. | PRD lines 332 — listed as a product gap, not in PLAN.md line 127. |
| New observability transport | Local JSONL only (`.cache/run-log.jsonl`). No OTEL exporter, no remote sink. | PLAN.md line 142; cost discipline. |

---

## What Slice 4 ships

**Build (FRs / NFRs):** FR-44 (ambiguous free-text), FR-45 (stale-date), FR-48 (scanned PDF / OCR), FR-49 (ingestion summary), FR-50 (unmatched detection), FR-53 (graceful failure), NFR-09 (observability), NFR-11 (cost discipline carry-over), TDD §5.2 (zero-retention).

**Done when:** AC-6 ingestion summary present and never silently drops, AC-8 latency budgets hold on the reference dataset, AC-10 robustness + stale-date + ambiguity holds, eval pass rate ∈ [0.70, 0.85] over the golden set.

| Feature | FR / Spec | Where it lives |
|---|---|---|
| OCR re-try for scanned PDFs | FR-48 | `pipeline/ingest.py::_extract_pdf_text` (extend) |
| Ingestion report (counts + warnings) | FR-49, FR-50, AC-6 | New `pipeline/ingestion_report.py`; `models/ingestion_report.py` |
| Graceful malformed-file errors | FR-53, AC-10 | New `models/errors.py::IngestionError`; wrapping in `ingest.py` |
| Free-text role + ambiguity prompt | FR-44, AC-10 | New `normalise/free_text_role.py`; CLI flag |
| Past start-date warning | FR-45, AC-10 | New `pipeline/stale_date.py`; called from CLI |
| Stage timings + structlog sink | NFR-09 | New `observability/timing.py`; extend `observability/run_log.py` |
| LLM token + cost telemetry | NFR-09, NFR-11 | Hooks in `llm/extract.py`, `llm/explain_module.py`, `llm/skill_inference.py` |
| Zero-retention provider config | TDD §5.2 | Edit `llm/client.py`; new `config.allowed_models` |
| Golden dataset | PLAN.md §parallel | `evals/golden/roles.yaml` |
| DeepEval suite + pass-rate gate | PLAN.md line 129/137 | `tests/evals/test_deepeval_golden.py` |
| Promptfoo (optional) | PLAN.md line 129 | `tests/evals/promptfoo.yaml` |
| Latency benchmark | AC-8 | `tests/integration/test_latency_ac8.py` |
| Real `dsm ingest` subcommand | FR-49/50 | Replace stub at `cli.py:64-71` |

---

## Pipeline ordering (`cli.py`)

```
configure_log_sink(config.observability.log_path)
log_run_start(snapshot_id, config_version)
configure_lm(config)                              ← validates allowed_models, injects retention headers
    ↓
with stage_timer("ingest"):
    roles, consultants, feedback = ingest_*(...)
ingestion_report = ingestion_report.build(roles, consultants, feedback_dir)
    ↓
role = resolve_role(role_id_or_free_text)         ← FR-44 if --free-text
warnings = stale_date.check(role, today)          ← FR-45
ingestion_report.warnings.extend(warnings)
    ↓
with stage_timer("normalise"): consultants = ...
with stage_timer("extract"):    consultants = extract_signals(...)   ← logs llm_usage
with stage_timer("match"):      ranked, hard_rejected = match_role(...)
with stage_timer("gap"):        gap_report = build_gap_report(...)
with stage_timer("confidence_and_flags"): ...
with stage_timer("explain"):    ranked = generate_explanations(...)  ← logs llm_usage
    ↓
run_telemetry = telemetry.snapshot()
run_output = RunOutput(..., ingestion_report=..., run_telemetry=...)
with stage_timer("render"):
    render.json.print_results(run_output)   OR   render.text.print_results(run_output)
log_data_quality(unmatched, low_confidence)
```

`--no-llm` skips `extract` and `explain` stages; telemetry still records zero LM calls. `--free-text` replaces role-by-id lookup with `free_text_role.parse(...)`. `--yes` short-circuits the ambiguity prompt with default assumptions and logs each.

---

## Model changes

### `src/matcher/models/errors.py` (NEW)
```python
class IngestionError(Exception):
    def __init__(self, file: Path, problem: str) -> None:
        super().__init__(f"{file}: {problem}")
        self.file = file
        self.problem = problem
```

### `src/matcher/models/ingestion_report.py` (NEW)
```python
class IngestionReport(BaseModel):
    profiles_parsed: int = 0
    profiles_low_confidence: list[str] = Field(default_factory=list)   # emails
    feedback_matched: int = 0
    feedback_unmatched: list[str] = Field(default_factory=list)        # file paths
    supply_without_profile: list[str] = Field(default_factory=list)    # emails
    warnings: list[str] = Field(default_factory=list)                  # FR-45, FR-44 ambiguities, …
```

### `src/matcher/models/telemetry.py` (NEW)
```python
class RunTelemetry(BaseModel):
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
    llm_calls: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hits: int = 0

    @computed_field
    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.llm_calls if self.llm_calls else 0.0
```

### `src/matcher/models/output.py` (edit)
Add:
```python
ingestion_report: IngestionReport | None = None
run_telemetry: RunTelemetry | None = None
```

---

## Config changes

### `src/matcher/config.py` (extend)

```python
class ObservabilityConfig(BaseModel):
    log_path: Path = Path(".cache/run-log.jsonl")
    enable_telemetry: bool = True

class OCRConfig(BaseModel):
    enabled: bool = True
    text_floor_chars: int = 50          # first-pass below this → OCR retry
    confidence_floor: float = 0.6

class ProviderConfig(BaseModel):
    data_collection: Literal["deny", "allow"] = "deny"

class AppConfig(BaseModel):
    ...
    allowed_models: list[str] = Field(default_factory=list)
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    ocr: OCRConfig = Field(default_factory=OCRConfig)
    provider: ProviderConfig = Field(default_factory=ProviderConfig)
```

Validators: if `allowed_models` is non-empty, `model_extraction / model_explain / model_skill_inference` must each appear in it.

### `config/default.yaml` (extend)

```yaml
allowed_models:                       # User to confirm with security/compliance.
  - openai/gpt-4o-mini
  - openai/gpt-4o
  - anthropic/claude-3-haiku
observability:
  log_path: ".cache/run-log.jsonl"
  enable_telemetry: true
ocr:
  enabled: true
  text_floor_chars: 50
  confidence_floor: 0.6
provider:
  data_collection: deny
```

Editing any of these alters behaviour with no code change (AC-7 / FR-28 / FR-51) — extends the `test_config.py` pattern.

---

## File-by-file changes

| File | Status | Change |
|---|---|---|
| `src/matcher/models/errors.py` | **NEW** | `IngestionError(file, problem)`; stringifies as `"<path>: <problem>"`. |
| `src/matcher/models/ingestion_report.py` | **NEW** | `IngestionReport` model (see above). |
| `src/matcher/models/telemetry.py` | **NEW** | `RunTelemetry` model with computed `cache_hit_rate`. |
| `src/matcher/models/output.py` | edit | Add `ingestion_report`, `run_telemetry` fields. |
| `src/matcher/config.py` | edit | Add `allowed_models`, `ObservabilityConfig`, `OCRConfig`, `ProviderConfig` and the cross-field validator (each LM model must appear in `allowed_models` when the list is non-empty). |
| `config/default.yaml` | edit | Mirror the config additions; ship the conservative default allow-list (security to confirm). |
| `src/matcher/pipeline/ingest.py` | edit | Wrap `openpyxl.load_workbook(...)` at lines 70 and 122 in `try/except` → `IngestionError(path, "workbook unreadable")`. Wrap `wb[sheet_name]` (lines 71, 126) → `IngestionError(path, "missing sheet '<name>'")`. Convert existing `ValueError` from missing columns into `IngestionError` for one consistent surface. In `_extract_pdf_text` (line 178): keep first-pass Docling call; if extracted text length < `config.ocr.text_floor_chars` and `config.ocr.enabled`, re-run `DocumentConverter` with OCR options enabled; on success return text + `["profile_pdf_ocr_used"]` flag + `confidence_floor`; on persistent failure return `("", ["profile_pdf_low_confidence"], 0.4)` — never raises, never drops. Pass `AppConfig` through (currently no signature change needed — accept an optional `ocr_config: OCRConfig` arg, default to a sensible no-op when absent). |
| `src/matcher/pipeline/ingestion_report.py` | **NEW** | `build(roles, consultants, feedback_dir, warnings) -> IngestionReport`. Aggregates `consultant.data_gaps` into `profiles_low_confidence`; cross-references supply-tab emails vs profile-derived consultants to populate `supply_without_profile`; walks feedback dir for orphans → `feedback_unmatched`. |
| `src/matcher/pipeline/stale_date.py` | **NEW** | `check(role: Role, today: date) -> list[str]`. Returns `[f"role {role.id} start_date {role.start_date} is in the past"]` when applicable; empty list otherwise. Pure function — unit-testable in isolation. |
| `src/matcher/normalise/free_text_role.py` | **NEW** | `parse(text: str, known_locations: set[str], known_skills: set[str]) -> tuple[Role, list[str]]`. Rule-based: title = first capitalised phrase; locations = those matching `known_locations`; skills = those matching `known_skills`; start_date = first ISO-8601 or `dateutil.parse`-parseable token. Each unresolved slot adds an ambiguity string. **No LLM.** |
| `src/matcher/observability/timing.py` | **NEW** | `@contextmanager def stage_timer(name: str, telemetry: RunTelemetry | None = None)`. Uses `time.perf_counter()`; on exit records `elapsed_ms` into both the structlog event (via `log_stage_timing`) and the in-memory `telemetry.stage_timings_ms`. |
| `src/matcher/observability/run_log.py` | edit | Add `configure_log_sink(path: Path)` that calls `structlog.configure(...)` once per process with a `WriteLoggerFactory(file=path.open("a"))` and a JSON renderer. **All four existing helpers untouched** to preserve the Slice 3 contract. |
| `src/matcher/observability/telemetry.py` | **NEW** | Module-level `current_telemetry: RunTelemetry` plus `snapshot() -> RunTelemetry` and `record_llm_call(task, tokens, cost_usd, cache_hit)`. Single source of truth, called from each LM wrapper. |
| `src/matcher/llm/client.py` | edit | Validate each configured model is in `config.allowed_models` (when non-empty). Build `extra_headers={"X-Title": "demand-supply-matcher"}` and `extra_body={"provider": {"data_collection": config.provider.data_collection}}` and pass to `dspy.LM(...)`. Single-call site; preserves Slice 3 caller contract. |
| `src/matcher/llm/extract.py` | edit | After each `dspy.Predict(...)` call, read `dspy.settings.lm.history[-1]` to get `usage.prompt_tokens + completion_tokens` and `response_ms`; call `telemetry.record_llm_call("extract", tokens, cost_usd, cache_hit)`. **Cost** comes from a small static rate table in `observability/cost_table.py` keyed by model id (loaded from `config/cost_table.yaml`) — no live billing lookup. |
| `src/matcher/llm/explain_module.py` | edit | Same telemetry hook with `task="explain"`. |
| `src/matcher/llm/skill_inference.py` | edit | Same telemetry hook with `task="skill_inference"`. |
| `src/matcher/observability/cost_table.py` | **NEW** | `cost_for(model, prompt_tokens, completion_tokens) -> float`. Reads `config/cost_table.yaml` once. Missing model → 0.0 + warn-once. |
| `config/cost_table.yaml` | **NEW** | Per-million-token prices for the allow-listed models. Seeded with current OpenRouter pricing; user can override. |
| `src/matcher/cli.py` | edit | (a) Configure log sink + telemetry at entry. (b) Wrap each pipeline stage in `stage_timer`. (c) Add `--free-text <str>` and `--yes` options to `match`; when set, route via `free_text_role.parse`; ambiguities print to stderr (or auto-accept under `--yes`). (d) Replace the `ingest` stub (lines 64–71) with a real implementation that runs the ingest pipeline and prints (or `--json`) the `IngestionReport`. (e) Assemble `run_telemetry` into `RunOutput` for both text + JSON paths. |
| `src/matcher/render/text.py` | edit | Add an `IngestionReport` block before the candidate list and a one-line telemetry footer (`run_telemetry: 3.2s total, 4 LLM calls, $0.0023, cache 50%`). When `ingestion_report is None`, skip silently. |
| `src/matcher/render/json.py` | (no change) | Pydantic `model_dump(mode="json")` picks up the two new `RunOutput` fields automatically. |
| `Makefile` | edit | Add `eval`, `eval-promptfoo`, `bench` targets (see Verification §). |
| `tests/evals/test_deepeval_golden.py` | **NEW** | Replaces `tests/evals/deepeval_suite.py` stub. Loads `evals/golden/roles.yaml`, runs the CLI pipeline against each role with the real workbook + cached LLM responses, applies `GEval(criterion="references only data points from supplied evidence")` and an exact-match check (`expected_top_emails` is a subset of `ranked[:n]`). Pass rate must land in `[0.70, 0.85]`; suite fails the build outside that band. |
| `tests/evals/promptfoo.yaml` | edit | Add a `tests:` block of role-spec snapshots (one per golden role). Optional — gated by `make eval-promptfoo`. |
| `evals/golden/roles.yaml` | **NEW** | Seed: 4 exact-match roles, 2 adjacent-skill roles, 1 negative case, 1 unfillable role — see PRD lines 311–317. Each entry: `{role_id, expected_top_emails: [list], notes: str, kind: "exact"|"adjacent"|"negative"|"unfillable"}`. |

---

## Existing utilities to reuse

| Utility | File:line | How |
|---|---|---|
| `log_run_start`, `log_stage_timing`, `log_llm_usage`, `log_data_quality` | `src/matcher/observability/run_log.py:8-25` | Called from CLI and LM wrappers respectively — **wire, don't rewrite**. |
| `Consultant.data_gaps` | populated across `pipeline/ingest.py` | Sole source for `IngestionReport.profiles_low_confidence`. |
| Docling `DocumentConverter` | `pipeline/ingest.py:179` | Accepts OCR options — re-construct on the retry path; no new dependency. |
| `dspy.settings.lm.history` | dspy lib | Token / cost / cache_hit telemetry without a new LLM call. |
| `Role.start_date` | `pipeline/ingest.py:94` | Drives stale-date check (FR-45). |
| `RunOutput` | `src/matcher/models/output.py` | Pydantic envelope already supports nested models — `model_dump(mode="json")` auto-emits the new fields. |
| `_parse_date` | `pipeline/ingest.py` | Reused inside `free_text_role.parse`. |
| `config/skill_adjacency.yaml` | (Slice 1) | Source of `known_skills` for `free_text_role.parse`. |
| `band()` | `scoring/ranker.py:20` | Reused by the eval suite to assert per-dimension expectations. |
| `IngestionError` | new (this slice) | Single error surface across `ingest_roles`, `ingest_consultants`, `ingest_feedback`. |

---

## Test plan (TDD — RED first, per PLAN.md step 2)

Tests are ordered by build dependency.

### Phase A — Models & errors (no LLM, no IO)

1. **`tests/unit/test_models_ingestion_report.py`** *(NEW)* — round-trip through `model_dump_json` / `model_validate_json`; default counts are zero.
2. **`tests/unit/test_models_telemetry.py`** *(NEW)* — `cache_hit_rate == 0` when `llm_calls == 0`; otherwise `cache_hits / llm_calls`; serialises into `RunOutput`.
3. **`tests/unit/test_models_errors.py`** *(NEW)* — `IngestionError(Path("/x.xlsx"), "missing sheet 'Open Roles'")` stringifies as expected; carries the path + problem on the exception object.

### Phase B — Robustness (FR-53 / AC-10)

4. **`tests/unit/test_robustness.py`** *(NEW)* — four cases on `ingest_roles` / `ingest_consultants`: (a) zero-byte workbook → `IngestionError("workbook unreadable")`; (b) workbook missing `Open Roles` sheet → `IngestionError("missing sheet 'Open Roles'")`; (c) workbook missing `Role ID` column → `IngestionError("Open Roles sheet missing columns: {'Role ID'}")`; (d) corrupt PDF → never raises, profile carries `profile_pdf_low_confidence` and surfaces in `IngestionReport`.
5. **`tests/unit/test_scanned_pdf.py`** *(NEW, FR-48)* — fixture image-only PDF: with `ocr.enabled=True` the second-pass extraction yields non-empty text + `profile_pdf_ocr_used` flag; with `ocr.enabled=False` profile lands in `profiles_low_confidence` — **never dropped** (AC-6).
6. **`tests/unit/test_stale_date.py`** *(NEW, FR-44/45)* — past `start_date` → warning in `IngestionReport.warnings`, run continues. `free_text_role.parse("Need a Python dev in Bengaluru next month")` returns a `Role` with `title="Python Developer"`, location `["Bengaluru"]`, plus an ambiguity `"start_date: 'next month' not parseable"`. With `--yes` the ambiguity is recorded but the run proceeds.

### Phase C — Observability (NFR-09)

7. **`tests/unit/test_observability_timings.py`** *(NEW)* — running a single-role pipeline (mock LLMs) emits one `stage_timing` structlog event per configured stage; `RunTelemetry.stage_timings_ms` contains the same keys; sum within 5% of wall-clock.
8. **`tests/unit/test_observability_cost.py`** *(NEW, extends `test_cost.py`)* — with `--no-llm`, `RunTelemetry.llm_calls == 0` and `total_cost_usd == 0.0`. With mocked LM history producing `(50 prompt, 30 completion)` tokens and a `cost_table.yaml` priced at `$0.001/1K`, `total_cost_usd ≈ 0.00008` per call.
9. **`tests/unit/test_log_sink.py`** *(NEW)* — `configure_log_sink(tmp_path/"log.jsonl")` plus a single `log_run_start(...)` call writes one JSON line to the file; `jq` parses it.

### Phase D — Zero-retention (TDD §5.2)

10. **`tests/unit/test_provider_retention.py`** *(NEW)* — monkeypatch `dspy.LM` to capture constructor kwargs; assert `extra_headers["X-Title"]` and `extra_body == {"provider": {"data_collection": "deny"}}` are present.
11. **`tests/unit/test_allowed_models.py`** *(NEW)* — `AppConfig(allowed_models=["openai/gpt-4o-mini"], model_extraction="openai/forbidden", ...)` raises a validation error at config load; `allowed_models=[]` skips the check (back-compat); valid combo loads cleanly.

### Phase E — Eval harness (PLAN.md line 129/137)

12. **`tests/evals/test_deepeval_golden.py`** *(NEW)* — loads `evals/golden/roles.yaml`, runs each role through the CLI pipeline (warm cache), applies the faithfulness + exact-match metrics, and **asserts pass rate ∈ [0.70, 0.85]**. Skipped when the workbook or DSPy cache is absent.
13. **`tests/integration/test_latency_ac8.py`** *(NEW)* — single-role wall-clock < 5 s warm-cache; batch over all roles < 60 s. `pytest.skip` when `data/` missing.

### Phase F — CLI integration (FR-49/50 surfacing)

14. **`tests/integration/test_cli_ingest.py`** *(NEW)* — `dsm ingest --data-dir data/ --json` parses cleanly with `json.loads`; contains `profiles_parsed`, `feedback_matched`, etc. Exit code 0 even when warnings exist; exit code 1 only on `IngestionError`.
15. **`tests/integration/test_cli_match_with_telemetry.py`** *(NEW)* — `dsm match ROLE-01 --json` includes both `ingestion_report` and `run_telemetry` under `RunOutput`; round-trips via `RunOutput.model_validate_json`.

### Manual / CLI checks (real workbook)

- `uv run dsm match ROLE-01` → human-readable output **plus** a one-line telemetry footer (`3.2s, 4 LLM calls, $0.0023`).
- `uv run dsm match --free-text "Senior Python engineer in Bengaluru starting 2026-08-01"` → resolves to a `Role`, no ambiguity prompt.
- `uv run dsm match --free-text "Need someone for the auth stuff" --yes` → ambiguities logged, defaults assumed, run completes.
- Corrupt a profile PDF on disk → rerun → `IngestionReport` flags it, no traceback in stderr.
- Rename the `Open Roles` sheet → rerun → `IngestionError: <workbook>: missing sheet 'Open Roles'`; exit code 1; no traceback dump.
- `make eval` → pass-rate ∈ [0.70, 0.85]; 100% triggers a build failure with the message "suite not discriminating — add negatives".
- `time uv run dsm match ROLE-01` (warm cache) → < 5 s on the reference dataset (AC-8).
- `cat .cache/run-log.jsonl | jq '.stage' | sort -u` → emits exactly the configured stage names.
- Run twice with cache → bands, signals, confidence, JSON identical modulo `timestamp` and `run_telemetry`.

---

## Verification (end-to-end)

1. `make lint && make typecheck && make test-unit && make test-int && make eval` all green.
2. **AC-6 spot-check (FR-49/50)** — `dsm ingest --json` returns a structured report; consultants without profiles and orphan feedback files are both listed.
3. **AC-8 spot-check** — `time uv run dsm match ROLE-01` (warm cache) < 5 s; `time uv run dsm match --batch` (all roles) < 60 s.
4. **AC-10 spot-check** — three manual scenarios above each produce the expected message + non-zero exit code (or warning + exit 0).
5. **Zero-retention sanity (TDD §5.2)** — capture outbound HTTPS with `mitmproxy` (manual, one-off); confirm `X-Title` header + `provider.data_collection=deny` in the JSON body.
6. **Eval pass-rate** — `make eval` shows pass rate ∈ [0.70, 0.85]. A 100% pass deliberately fails the gate ("suite not discriminating — add negatives").
7. **Telemetry sanity (NFR-09)** — `cat .cache/run-log.jsonl | jq '.event' | sort | uniq -c` shows `run_start`, `stage_timing × N`, `llm_usage × M`, `data_quality`.
8. **Cost discipline (NFR-11)** — `test_observability_cost.py` holds; warm-cache rerun adds `cache_hits` only, no new tokens.
9. **Spec cross-checks (FR / AC matrix Slice 4 unblocks):**
   - **AC-6 / FR-43/48/49/50** — `test_scanned_pdf.py`, `test_robustness.py`, manual ingest check.
   - **AC-8** — `test_latency_ac8.py`.
   - **AC-10 / FR-44/45/53** — `test_robustness.py`, `test_stale_date.py`, manual check.
   - **NFR-09** — `test_observability_timings.py`, `test_log_sink.py`.
   - **NFR-11** — `test_observability_cost.py`.
   - **TDD §5.2** — `test_provider_retention.py`, `test_allowed_models.py`.
   - **PRD Evaluation Expectations** — `test_deepeval_golden.py`.

---

## Inputs needed from user (per PLAN.md line 28 + TDD §5.2 line 177)

These block live runs + final sign-off, but not the build-out of tests/mocks:

1. **Approved provider/model allow-list** (TDD §5.2 line 177 explicitly flags this) — Plan defaults to `openai/gpt-4o-mini`, `openai/gpt-4o`, `anthropic/claude-3-haiku` with OpenRouter `data_collection: deny`. Security/compliance to confirm.
2. **Golden dataset seed list** — 8–12 roles per the parallel track (PLAN.md lines 32–39). If not started, Slice 4 author drafts an initial set from the workbook; user reviews before the eval gate is enforced.
3. **Eval cadence** — every PR (CI) or nightly only? Plan defaults to: deterministic asserts every PR, faithfulness asserts nightly.
4. **Observability sink** — local JSONL (default) vs forwarding to an external tracer? Plan defaults to `.cache/run-log.jsonl`; OTEL exporter explicitly out of scope.
5. **Cost table source** — initial seed via OpenRouter public pricing; user to confirm whether `config/cost_table.yaml` should be regenerated periodically.

---

## Build order (suggested commit shape)

1. **Models + config + cost table** — `IngestionError`, `IngestionReport`, `RunTelemetry`, `ObservabilityConfig`, `OCRConfig`, `ProviderConfig`, `allowed_models`, `config/cost_table.yaml`. Tests: Phase A.
2. **Robustness wrapping + OCR retry + stale-date + free-text parser** — `pipeline/ingest.py` edits, `pipeline/stale_date.py`, `normalise/free_text_role.py`, `pipeline/ingestion_report.py`. Tests: Phase B.
3. **Observability wiring** — `observability/timing.py`, `observability/telemetry.py`, `observability/cost_table.py`, `configure_log_sink`. Tests: Phase C.
4. **LM telemetry hooks** — edits to `llm/extract.py`, `llm/explain_module.py`, `llm/skill_inference.py`. Tests folded into Phase C.
5. **Zero-retention + allow-list** — `llm/client.py` edits. Tests: Phase D.
6. **Golden dataset seed + DeepEval suite + Promptfoo file + latency benchmark + Makefile targets** — Tests: Phase E.
7. **CLI surfacing** — `--free-text`, `--yes`, real `dsm ingest`, render footer + ingestion block; integration tests Phase F + manual sweep.
