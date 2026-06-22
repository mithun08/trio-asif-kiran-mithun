# Slice 2 — Implementation Plan: First LLM Contact + PII Gate

| Field | Value |
|---|---|
| Source | `docs/PLAN.md` §Slice 2 |
| Specs cross-referenced | `PRD_refined.md` (FRs), `TECHNICAL_DESIGN.md` (§4.4, §5.1), `SCORING_SPEC.md` (§3.2, §3.4, §3.6, §7) |
| Scope | First LLM contact, PII scrubber, extraction grounding, three LLM-driven dimensions, PDF + feedback ingest |
| Out of scope | FR-21 semantic skill matching (optional in PLAN, deferred), explanations (Slice 3), JSON output (Slice 3), OCR (Slice 4), eval harness (Slice 4), gap analysis (Slice 3), Milvus, sentence-transformers |
| Predecessor | Slice 1 (commit `3b8c9a6`) — deterministic core, three dimensions held at neutral 50 |

---

## Context

Slice 1 shipped a fully deterministic scoring pipeline; the three dimensions sourced from soft text are placeholders returning the configured `neutral_baseline` (50):

- `score_feedback_quality` — `src/matcher/scoring/dimensions.py:114-123`
- `score_adaptability` — `src/matcher/scoring/dimensions.py:126-135`
- `score_performance_trend` — `src/matcher/scoring/dimensions.py:138-147`

Slice 2 replaces these placeholders by feeding LLM-extracted signals over PII-scrubbed source text into the same deterministic scoring shell. Because this is the **first time text leaves the machine**, the PII scrub gate (TDD §5.1) and extraction grounding guardrail (TDD §4.4) ship in this slice — not later (`docs/PLAN.md:73-77`).

Profile PDFs in `data/profiles/*.pdf` add per-skill proficiency that the workbook does not carry — e.g. `aarav_krishnan_pp.pdf` reveals `Kotlin (expert)`, which Slice 1 collapses to proficiency=3 by default. This matters for the `c_prof = 70` path. Feedback Markdown in `data/project_feedback/*.md` keys consultants by email and is the raw source for the feedback / adaptability / trend dimensions.

**Goal:** signals for feedback quality, adaptability and performance trend produced by grounded LLM extraction over PII-scrubbed source text; deterministic scoring per SCORING_SPEC §3.2 / §3.4 / §3.6.

---

## What the source data actually contains

### `data/profiles/*.pdf` — Parity Partners template + free-form

Files named `<first>_<last>[_pp].pdf` (e.g. `aarav_krishnan_pp.pdf`). The `_pp` suffix denotes the Parity Partners template. Free-form profiles are also present. Skills appear with proficiency markers (`expert`, `working`). No password protection. Image-only scanned PDFs are out of scope for Slice 2 (FR-48 → Slice 4), but must be flagged not dropped.

### `data/project_feedback/*.md` — Markdown keyed by email

Sample (`Aarav - Backend.md`):

```
# Feedback - Aarav Krishnan

**Email (key):** aarav.krishnan@paritypartners.example
*Synthetic project & client feedback - free text, no ratings. New joiners have none.*

## Project feedback - Meridian Pay
Engagement review: re-architected the card-auth service in Kotlin; deep payments domain expertise. Has not worked with Terraform/IaC.

## Client feedback - Meridian Pay
"Please keep Aarav as long as possible - he is central to the ledger rebuild."
```

Section headings (`## Project feedback`, `## Client feedback`, optional `## Beach feedback`) are the source-of-truth for FR-22's three composite buckets.

---

## YAGNI scope decisions

| Topic | Decision | Rationale |
|---|---|---|
| FR-21 semantic skill matching (sentence-transformers + numpy cosine) | **Defer.** | PLAN.md line 75 marks it "Optionally"; Slice 1's static adjacency map already covers the fixture data. Re-evaluate after the Slice 4 eval. |
| `SkillAmbiguityResolution` DSPy signature | **Remove.** | Only used by FR-21. |
| `CandidateExplanation` DSPy signature | **Leave the stub untouched.** | Slice 3 territory. |
| OCR / image-only PDFs (FR-48) | **Defer to Slice 4.** | Never silently drop — unreadable PDFs flag `data_gaps=["profile_pdf_unreadable"]`. |
| JSON output (FR-52) | **Defer to Slice 3.** | PLAN.md line 103 allows pulling forward "if convenient"; not needed for Slice 2's done criterion. |
| Ingestion summary reports (FR-49/50) | **Defer to Slice 4.** | Collect the unmatched-record list, do not render. |
| Performance-trend-over-time history | **Defer.** | Slice 2 classifies the current text's direction. Multi-snapshot history is roadmap v2. |

**Bonus items intentionally included** (not in PLAN.md Slice 2 Build line, but cheap and aligned):

- **FR-42 contradiction flagging** for PDF-reported `location` / `grade` — PDF extraction surfaces these fields anyway; flagging mismatches (workbook authoritative) is a one-line cost.
- **`--no-llm` CLI flag** for offline diagnostic runs — useful for iterating on the deterministic core without billing tokens.

---

## Pipeline ordering (cli.py)

```
AppConfig.from_yaml
    ↓
configure_dspy_cache(cache_dir)            ← writes to .cache/dspy/
    ↓
configure_lm(config)                       ← dspy.LM, OpenRouter, temperature=0
    ↓
ingest_roles(workbook)
    ↓
ingest_consultants_from_workbook(workbook) ← Slice 1: three supply tabs
    ↓
ingest_consultants(profiles_dir, workbook_consultants)
    ↓                                       ← Docling PDF extraction, merge by email
ingest_feedback(feedback_dir, consultants)
    ↓                                       ← Markdown parse, link by email
canonicalise_locations(consultants)
    ↓
dedup_by_email(consultants)                ← MUST run before scrub_pii (avoid wasted scrub)
    ↓
scrub_pii(consultants)                     ← MUST run before extract_signals (TDD §5.1)
    ↓
extract_signals(consultants)               ← LLM extraction over scrubbed text (grounding)
    ↓
match_role(role, consultants, …)           ← Slice 1 dimensions, now with real data
    ↓
print_results(ranked, gaps, config)        ← Slice 1 render
```

`--no-llm` skips `configure_lm` and `extract_signals`; the remaining pipeline falls back to Slice 1 neutral-50 behaviour.

---

## Model changes

### `src/matcher/models/consultant.py`

Add five fields (all defaulted — Slice 1 fixtures still construct cleanly):

```python
feedback_text: dict[str, str] = Field(default_factory=dict)
    # keys: "project" | "client" | "beach"
feedback_signals: dict[str, FeedbackSignal] = Field(default_factory=dict)
adaptability_signals: AdaptabilitySignals | None = None
performance_trend: Literal["improving", "stable", "declining", "unknown"] = "unknown"
pii_token_map: dict[str, str] = Field(default_factory=dict)
```

### `src/matcher/models/signals.py` (NEW)

```python
class FeedbackSignal(BaseModel):
    sentiment: Literal["positive", "neutral", "negative"]
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    client_keep_signal: bool = False   # scored only when source == "client"
    domain_depth: bool = False
    evidence_spans: list[str] = Field(default_factory=list)

class AdaptabilitySignals(BaseModel):
    tech_transitions: int = 0
    learning_speed_mentions: bool = False
    cross_domain: int = 0
    upskilling: bool = False
    evidence_spans: list[str] = Field(default_factory=list)
```

`client_keep_signal` is extracted on every source for completeness but only **scored** when the source key is `"client"` (per SCORING_SPEC §7 worked example: client = 80+10 = 90; project = 80+5 = 85).

---

## Config changes

### `src/matcher/config.py` — extend `ScoringConfig`

Add 19 new fields, defaults from SCORING_SPEC §6. All clamped + reported per FR-51.

**Feedback (9):**

```python
feedback_weight_project: float = 0.5
feedback_weight_client:  float = 0.3
feedback_weight_beach:   float = 0.2
feedback_sent_pos:     float = 80.0
feedback_sent_neutral: float = 50.0
feedback_sent_neg:     float = 20.0
feedback_kw_keep:    float = 10.0   # client-source only
feedback_kw_domain:  float =  5.0
feedback_kw_concern: float = 10.0
```

`@model_validator(mode="after")` mirroring `ScoringWeights._check_sum` (`config.py:20-25`) asserts `feedback_weight_*` sum to 1.0.

**Adaptability (6):**

```python
adapt_pts_transitions: float = 15.0
adapt_pts_learning:    float = 10.0
adapt_pts_crossdomain: float = 10.0
adapt_pts_upskill:     float = 10.0
adapt_min_transitions: int = 2
adapt_min_crossdomain: int = 2
```

**Trend (3):**

```python
trend_improving: float = 100.0
trend_stable:    float =  70.0
trend_declining: float =  30.0
```

**Extraction confidence (1):**

```python
extract_min_spans: int = 1     # FR-10 floor
```

### `config/default.yaml`

Add the 19 keys under `scoring.config`. Editing any of them must alter scoring with no code change (AC-7 / FR-28 / FR-51); verified in `test_config.py` extensions.

---

## File-by-file changes

| File | Status | Change |
|---|---|---|
| `src/matcher/privacy/scrubber.py` | stub → impl | Implement `scrub_text` + `rehydrate_text` using Presidio analyzer + anonymizer. Detect `EMAIL_ADDRESS`, `PHONE_NUMBER`, `PERSON`, plus a configurable client-name `PatternRecognizer`. Returns `(scrubbed_text, token_map)`. |
| `src/matcher/llm/cache.py` | stub → impl | `configure_dspy_cache(cache_dir)` — set DSPy disk cache to `cache_dir / "dspy"`. |
| `src/matcher/llm/client.py` | **NEW** | `configure_lm(config: AppConfig) -> None`. Calls `dspy.configure(lm=dspy.LM(model=config.model_extraction, api_key=config.openrouter_api_key, api_base="https://openrouter.ai/api/v1", temperature=0, max_retries=3))`. Raises if `openrouter_api_key` is empty when invoked outside `--no-llm`. |
| `src/matcher/llm/modules.py` | edit | Keep + refine `ProfileExtraction` (add `evidence_spans` output). Remove `SkillAmbiguityResolution`. Add `FeedbackSignalExtraction`, `AdaptabilitySignalExtraction`, `PerformanceTrendExtraction`. Each output the SCORING_SPEC fields plus `evidence_spans` (substrings of input). |
| `src/matcher/llm/extract.py` | **NEW** | Wrappers: `extract_profile`, `extract_feedback`, `extract_adaptability`, `extract_trend`. Each runs the grounding check: every claim whose `evidence_spans` substring is not present in the input is dropped; if any are dropped, append `"ungrounded_<dim>"` to `data_gaps` (TDD §4.4). |
| `src/matcher/models/signals.py` | **NEW** | `FeedbackSignal`, `AdaptabilitySignals` (see Model changes). |
| `src/matcher/models/consultant.py` | edit | Five new defaulted fields (see Model changes). |
| `src/matcher/pipeline/ingest.py` | stub → impl | `ingest_consultants(profiles_dir, workbook_consultants)`: walk `*.pdf`, Docling extracts raw text, merge into workbook consultants by name → email match (Docling-extracted email used when present). On unmatched PDF, log (FR-50 scaffold) and survive workbook consultant with `data_gaps=["profile_pdf_unmatched"]`. On unreadable PDF, `data_gaps=["profile_pdf_unreadable"]` and `data_confidence *= 0.7`. Missing `profiles_dir` warns, does not crash. **Never drops a workbook consultant (FR-43).** `ingest_feedback(feedback_dir, consultants)`: read `*.md`, parse `**Email (key):** <email>`, split by `## Project feedback`, `## Client feedback`, `## Beach feedback`, populate `consultant.feedback_text` keyed by `"project" \| "client" \| "beach"`. Orphan markdown logged. |
| `src/matcher/pipeline/normalise.py` | stub → impl | `scrub_pii(consultants)`: scrub `raw_profile_text` + each `feedback_text[source]` per consultant; store combined token-map on `consultant.pii_token_map`. If anything was redacted, append `"pii_scrubbed"` to `data_gaps`. <br><br>**Invariant:** `DimensionScore.evidence` strings emitted from extraction/scoring carry only deterministic structured tags (`"positive sentiment"`, `"domain depth"`, `"no client feedback"`, source labels) — never raw prose. This prevents `<PERSON_0>` tokens from leaking into rendered output. |
| `src/matcher/pipeline/extract.py` | **NEW** | `extract_signals(consultants)`. Per consultant: <br>**(a) Profile** — if `raw_profile_text` non-empty, call `extract_profile`. On `skills_json` JSON parse failure, retry once at `temperature=0`, then flag `"profile_extraction_parse_failed"` and skip skill enrichment. PDF skill proficiency overrides workbook default 3 (FR-08); new PDF-only skills are appended. **FR-42:** PDF-reported `location` / `grade` are never applied; contradictions append `"location_mismatch_with_profile"` / `"grade_mismatch_with_profile"` to `data_gaps`. <br>**(b) Feedback** — for each source present in `feedback_text`, call `extract_feedback` → `consultant.feedback_signals[source]`. <br>**(c) Adapt + trend** — if any feedback OR profile text exists, call `extract_adaptability` and `extract_trend` over the combined text. <br>**FR-10:** when a signal's `len(evidence_spans) < config.extract_min_spans`, `consultant.data_confidence *= 0.7` and the signal is flagged. <br>Consultants with no feedback AND no profile text skip extraction — neutral baseline + `"no feedback"` flag (FR-24). |
| `src/matcher/scoring/dimensions.py` | edit | Replace bodies of the three placeholder functions: <br><br>**`score_feedback_quality`** — per-source sub-score `= sentiment_base + (kw_keep if source == "client" else 0)·signal.client_keep_signal + kw_domain·signal.domain_depth − kw_concern·has_concern`, clamped 0..100. Composite `0.5·project + 0.3·client + 0.2·beach`. Missing source → `neutral_baseline` (50) + `"no <source> feedback"` evidence flag. All-missing → 50 + `"no feedback"` (FR-24). Worked example (Aarav, SCORING_SPEC §7): client = 80+10 = 90, project = 80+5 = 85, beach absent = 50 → composite ≈ 79.5. <br><br>**`score_adaptability`** — `clamp(50 + 15·(transitions ≥ adapt_min_transitions) + 10·learning_speed_mentions + 10·(cross_domain ≥ adapt_min_crossdomain) + 10·upskilling, 0, 100)`. No signals → 50. <br><br>**`score_performance_trend`** — discrete map `improving=100, stable=70, declining=30, unknown=50`. |
| `src/matcher/config.py` | edit | 19 new `ScoringConfig` fields (see Config changes) + sum-to-1.0 validator. |
| `config/default.yaml` | edit | 19 new keys under `scoring.config` (see Config changes). |
| `src/matcher/cli.py` | edit | Wire the new pipeline stages (see Pipeline ordering). Add `--no-llm` flag (`bool`, default `False`) that skips `configure_lm` + `extract_signals`. |
| `pyproject.toml` | no change | `presidio-analyzer`, `presidio-anonymizer`, `spacy`, `dspy-ai`, `docling` already declared (lines 16-21). |
| `tests/conftest.py` | edit | Add fixtures: `synthetic_feedback_text`, `consultant_with_pii_in_text`, `mock_dspy_lm` (context manager that patches `dspy.LM.__call__` and captures every payload — drives `test_pii_gate` and the extract tests). |

---

## Existing utilities to reuse

| Utility | File:line | How |
|---|---|---|
| `AppConfig.openrouter_api_key`, `AppConfig.cache_dir`, `AppConfig.model_extraction` | `src/matcher/config.py:96-102` | Already loaded from `.env` via `pydantic-settings`. New `configure_lm` consumes these directly. |
| `dedup_by_email` | `src/matcher/pipeline/normalise.py:27` | Used between PDF merge and PII scrub. |
| `Consultant.data_gaps` / `data_confidence` | `src/matcher/models/consultant.py:23-24` | Already plumbed through ranker for FR-43; Slice 2 just appends flags. |
| `ScoringConfig.neutral_baseline = 50` | `src/matcher/config.py:54` | Already clamped + used by Slice 1 placeholders. Slice 2 keeps "missing = neutral, never zero" via this constant. |
| `DimensionScore.evidence` | `src/matcher/models/score.py:11` | Already used to surface text in output. Slice 2 emits structured tags through here (never raw scrubbed prose). |
| `_PROFICIENCY_MAP` | `src/matcher/pipeline/ingest.py:14-21` | Reuse to translate PDF-extracted proficiency text (`"expert"` / `"working"` / …) → 1-5. |
| `ScoringWeights._check_sum` | `src/matcher/config.py:20-25` | Pattern mirrored by the new `feedback_weight_*` sum-to-1.0 validator. |

---

## Test plan (TDD — write tests RED first, per PLAN.md step 2)

Tests are ordered by build dependency. PLAN.md line 86 calls `test_pii_gate` the most important test — a failure is a release blocker.

### Phase A — PII gate (release blocker; build FIRST)

1. **`tests/unit/test_pii_scrub.py`** — `scrub_text("Email asif@ig.com and phone +91-99999")` produces text with no email/phone regex match; `rehydrate_text(scrubbed, token_map)` round-trips exactly.
2. **`tests/unit/test_pii_gate.py`** — `monkeypatch` `dspy.LM.__call__` to capture every outbound payload, capturing **both positional `prompt=` and `messages=` kwargs** (DSPy may use either). Build a fixture consultant whose `feedback_text` contains an email, a phone number, the consultant's own name, and a known client name. Run `extract_signals`. Assert: across every captured payload string, no match for `EMAIL_REGEX`, `PHONE_REGEX`, `consultant.name`, or `client_name`. Also assert at least one call WAS made (guards against silent no-op).

### Phase B — Ingestion

3. **`tests/unit/test_ingest_profiles.py`** — given a 1-page fixture PDF (pre-stored binary under `tests/fixtures/profiles/`), `ingest_consultants(profiles_dir, workbook_consultants)` returns workbook consultants enriched with non-empty `raw_profile_text`. Given a workbook consultant whose PDF is missing, the consultant survives with `data_gaps=["profile_pdf_unmatched"]` (FR-43). Given a corrupt PDF, it survives with `["profile_pdf_unreadable"]` and lowered `data_confidence` (FR-48 partial). Given a non-existent `profiles_dir`, the call returns workbook consultants unchanged with a logged warning.
4. **`tests/unit/test_ingest_feedback.py`** — fixture markdown with all three sections populates `feedback_text["project"]`, `["client"]`, `["beach"]`. Markdown missing the email key is skipped, not raised. Email-only-section-headings markdown lands the right text under the right key.

### Phase C — Extraction + grounding (DSPy mocked)

5. **`tests/unit/test_extract_feedback.py`** — patch `dspy.Predict` to return a canned response; assert correct mapping into `FeedbackSignal`.
6. **`tests/unit/test_extract_adaptability.py`** — same pattern; assert `AdaptabilitySignals` mapping.
7. **`tests/unit/test_extract_trend.py`** — mock returns `"improving"` → `consultant.performance_trend == "improving"`.
8. **`tests/unit/test_grounding.py`** *(TDD §4.4)* — claim with `evidence_spans=["payments domain"]` where the substring IS in source → claim kept. Claim with `evidence_spans=["space lasers"]` (not in source) → claim dropped, `"ungrounded_feedback"` flag added, dim score uses neutral 50.

### Phase D — Scoring

9. **`tests/unit/test_feedback_scoring.py`** — verify SCORING_SPEC §7 modifier shape:
   - **client source**, positive + `client_keep_signal` → 80 + 10 = **90**; same on **project** source ignores `kw_keep` → 80.
   - project source, positive + `domain_depth` → 80 + 5 = **85** (matches Aarav worked example).
   - negative + concern → 20 − 10 = **10** (clamped 0..100).
   - Composite `0.5·project + 0.3·client + 0.2·beach` from default config weights.
   - Missing one source → that source's sub = 50 + `"no <source> feedback"` evidence flag. All-missing → 50 + `"no feedback"` (FR-24).
   - Changing any YAML config key alters the score with no code edit (AC-7).
10. **`tests/unit/test_adaptability.py`** — `(transitions=3, learning=True, cross_domain=2, upskill=True)` → `50 + 15 + 10 + 10 + 10 = 95`. Empty signals → 50. Cap at 100.
11. **`tests/unit/test_trend_scoring.py`** — improving=100, stable=70, declining=30, unknown=50.

### Phase E — Cost discipline (NFR-11)

12. **`tests/unit/test_cost.py`** — patched `dspy.LM` counts calls. With 5 fixture consultants each having all 3 feedback sources + profile text, run `extract_signals`. Assert: ≤ 5 × (1 profile + 3 feedback + 1 adapt + 1 trend) = 30 calls cold. Re-run with the same DSPy cache → 0 new calls (cache-hit verified).

### Manual / CLI checks (against `data/demand-supply.xlsx`)

- `uv run dsm match ROLE-01 --top 5` twice with `temperature=0` and DSPy cache enabled → **identical bands and signals-met count** (NFR-04 / AC-9; exact rank may shuffle once and that's acceptable per FR-55).
- **Aarav Krishnan vs ROLE-01** (SCORING_SPEC §7 worked example): feedback Strong (≈80), adaptability Strong (≈85), trend Strong (=100), availability Gap, supply Partial. Signals summary: *"5 of 6 strong; 1 gap (availability)."*
- A workbook consultant with no profile PDF → still scored, with `data_gaps=["profile_pdf_unmatched"]` (AC-6 / FR-43).
- A new joiner with no feedback → feedback band = Partial (50), evidence carries `"no feedback"`, **not** a zero / Gap (FR-24).

---

## Verification (end-to-end)

1. **PII gate red-line.** `uv run pytest tests/unit/test_pii_gate.py -v` MUST pass green BEFORE `configure_lm` is wired into the live CLI path (PLAN.md line 77: *"Build the PII gate and its test FIRST"*). If red, halt — do not run against real workbook.
2. `make lint && make typecheck && make test-unit` all green (mypy strict still passing).
3. **Reproducibility.** Cold-cache run of `uv run dsm match ROLE-01` succeeds. Second cold-cache run (`.cache/dspy/` cleared between) and diff: **bands and signals-met count identical** for every candidate (NFR-04 / AC-9 — exact rank is advisory per FR-55). A warm-cache rerun is additionally byte-identical (cache verification).
4. **Cost telemetry.** Manual count of `.cache/dspy/` entries against the 50-consultant reference dataset stays within `test_cost.py`'s asserted bound cold, and at 0 new entries warm.
5. **Spec cross-checks (the FR / AC matrix that Slice 2 unblocks):**
   - **AC-6** (FR-10/43/48): missing-profile and low-evidence consultants survive, flagged. FR-10 enforced via `extract_min_spans` floor lowering `data_confidence`.
   - **AC-9 partial** (FR-55): bands stable across cold runs at `temperature=0`.
   - **FR-07/08**: skill proficiency from PDFs reflected in `consultant.skills`.
   - **FR-09**: feedback files associated by email.
   - **FR-10**: low-confidence extractions flagged (not silently trusted).
   - **FR-12**: dedup by email survives PDF merge — workbook is the join key.
   - **FR-22**: composite weights 0.5 / 0.3 / 0.2 verified in `test_feedback_scoring.py`.
   - **FR-23**: feedback dim carries level only; trend is the sole owner of direction.
   - **FR-24**: missing feedback = 50 + flag, not 0.
   - **FR-25**: adaptability assessed from the four named signals.
   - **FR-42**: PDF-reported location / grade NEVER override workbook; contradictions are flagged.
   - **FR-43**: no silent drops — verified by `test_ingest_profiles.py` flag-survival cases.
   - **TDD §4.4**: extraction-side grounding enforced in `test_grounding.py`.
   - **TDD §5.1**: PII scrub-before-send enforced in `test_pii_gate.py`.

---

## Inputs needed from user (per PLAN.md line 27)

These block live-LLM runs but not the build-out of tests/mocks:

1. **OpenRouter API key** — set as `DSM_OPENROUTER_API_KEY` (the existing `AppConfig` env prefix). Confirm presence before manual checks against real data.
2. **Model choice per task** — default in `config/default.yaml` is `openai/gpt-4o-mini` for extraction. Confirm or substitute.
3. **PII allow/deny field list** (TDD §5.1 open question, PLAN.md line 80). Proposed default: **scrub** `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, plus a configurable client-name list (Meridian Pay, etc.); **allow** skills, anonymised experience text, feedback content. Confirm before extraction is wired to a live API.

---

## Build order (suggested commit shape)

1. **Models + config** — `signals.py`, Consultant fields, `ScoringConfig` extension, `config/default.yaml` keys. Tests: extend `test_config.py` for new validators + sum-to-1.0. Slice 1 behaviour unchanged.
2. **PII scrubber + PII gate test** — implement `scrubber.py`, run `test_pii_scrub.py` + `test_pii_gate.py` green (mocked DSPy). Release-blocker passes.
3. **Ingestion** — `ingest_consultants(profiles_dir, …)` + `ingest_feedback(…)`. Tests: `test_ingest_profiles.py`, `test_ingest_feedback.py`.
4. **LLM client + cache + extraction modules** — `client.py`, `cache.py`, `modules.py`, `extract.py`. Tests: `test_extract_feedback.py`, `test_extract_adaptability.py`, `test_extract_trend.py`, `test_grounding.py`, `test_cost.py`.
5. **Scoring** — replace the three dimension bodies. Tests: `test_feedback_scoring.py`, `test_adaptability.py`, `test_trend_scoring.py`.
6. **CLI wiring + `--no-llm` flag** — final glue in `cli.py`. Run full `tests/unit/` + manual CLI checks.
7. **Manual checks against real data** — Aarav vs ROLE-01, cold/warm cache parity, new-joiner-no-feedback case, missing-PDF case.
