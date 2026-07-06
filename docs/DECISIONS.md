# Demand-Supply Matcher — Architecture Decisions

## Model Selection (Slice 2+3) — Confirmed 2026-06-24

**Models in use:**
- `model_extraction`: `openai/gpt-4o-mini` (Slice 2: PDF/feedback extraction, profile parsing)
- `model_explain`: `openai/gpt-4o` (Slice 3: NL explanation generation, skill inference)
- `model_fallback`: `anthropic/claude-3-haiku` (fallback if primary unavailable)

**Rationale:**
- Extraction is high-volume, deterministic-friendly (fewer tokens per call) → cheaper model acceptable
- Explanations are low-volume, user-facing (quality matters for forum prep) → higher-quality model
- Fallback provides cost safety + diversity (avoids single-vendor outage)

**Configuration:**
- Models are configurable in `config/default.yaml` and overridable via environment (`DSM_MODEL_EXTRACTION`, etc.)
- OpenRouter routing enables provider diversity and cost optimization
- Response caching (DSPy) ensures repeated queries on unchanged data return cached results (cost discipline)

**Status:** ✅ Confirmed for Slice 2+3 development. Security/compliance sign-off pending per TDD §5.2 (zero-retention provider requirements).

---

## Config Parameterization (Slice 3) — 2026-06-24

**New configurable parameters added for Slice 3:**

| Key | Default | Range | FR | Purpose |
|---|---|---|---|---|
| `confidence_high_min_projects` | 2 | [1, ∞) | FR-31 | Minimum Parity Partners projects needed for "High" confidence |
| `confidence_medium_min_sources` | 1 | [1, ∞) | FR-31 | Minimum feedback sources for "Medium" confidence (vs. "Low") |
| `beach_long_days` | 60 | [30, 365] | FR-40 | Threshold days on beach before flagging (informational only) |
| `skill_infer_min` | 0.5 | [0.0, 1.0] | FR-37 | Confidence floor for inferred-skills acceptance; below → skip skill dimension |
| `gap_top_n` | 3 | [1, ∞) | FR-35 | Number of alternatives per constraint-relaxation pass (availability, then location) |

**Sourcing:** All thresholds derived from SCORING_SPEC §5 (confidence) and PRD requirements.

**Validation:** Pydantic validators with sensible bounds; out-of-range values clamped + warned (FR-51).

**Added 2026-07-06** (see the three decision sections below for context):

| Key | Default | Range | FR | Purpose |
|---|---|---|---|---|
| `skill_exclude_penalty_per` / `skill_exclude_penalty_cap` | 15 / 30 | [0, 100] | FR-02 | Per-match penalty / cap for skills excluded via free-text negation |
| `observability.snapshot_retention` | 50 | `0` = unlimited | — | Number of persisted `dsm match` run snapshots to retain |

---

## Constraint Relaxation Strategy (Slice 3) — 2026-06-24

**Approach:** Two-pass deterministic relaxation for unfillable roles (FR-35).

1. **Pass 1:** Disable availability hard-filter → rank candidates who exceed buffer; take top `gap_top_n`
2. **Pass 2:** Disable location hard-filter → rank candidates from different cities; take top `gap_top_n`

**Rationale:**
- Availability is easier to relax (dates slip; buffers exist for this)
- Location is harder (relocation requires consent); tackled second
- Deterministic: no LLM cost, reproducible across runs
- Explainable: each alternative carries a "relaxed: <filter>" flag

**Implementation:** `match_role(disable_availability_filter=True)` and `match_role(disable_location_filter=True)` called from `pipeline/gap.py`.

---

## PII Handling in Explanations (Slice 3) — 2026-06-24

**Extension of Slice 2 scrub-before-send paradigm:**

- **Inbound:** Feedback/profile text sent to LLM is pre-scrubbed by Presidio (Slice 2 invariant)
- **Outbound:** Explanation text returned from LLM is post-processed by `rehydrate_text(text, consultant.pii_token_map)` to restore names/emails locally before display (Slice 3 addition)

**Rationale:** Slice 2 invariants keep PII tokens out of evidence; this rehydration is a defensive safety net in case a hallucination bypasses the guardrail and emits a token.

**Implementation:** `llm/explain_module.py` rehydrates both explanation and why_not_higher fields before returning.

---

## Explanation Grounding Mechanism (Slice 3) — 2026-06-24

**Requirement (TDD §4.4):** Explanations must cite only data points present in the evidence package.

**Enforcement:** Cheap regex validation on dimension names (Strong/Partial/Gap), not LLM-based grounding (cost discipline).

- Input to `dspy.Predict(CandidateExplanation)`: role title, sector, per-dim (name, band, evidence) triples
- Post-processing: regex over returned explanation text; if unrecognized dimension name or unsourced claim detected, flag with `"explanation_ungrounded"` and return empty explanation
- Never crashes; always surfaces the issue as a data-quality flag

**Alternative considered:** LLM-based grounding (e.g. semantic similarity to evidence) — rejected due to cost + latency.

---

## Test Plan Organization (Slice 3) — 2026-06-24

Tests structured in 7 phases, ordered by build dependency:

- **Phase A (Models & config):** Pydantic round-trip + config loading
- **Phase B (Confidence & info flags):** Pure deterministic, no LLM
- **Phase C (Gap analysis):** Filter relaxation logic, ranked partial matches
- **Phase D (Skill inference):** LLM-mocked SkillInference signature
- **Phase E (Explanation):** Grounding, why-not-higher, PII rehydration (all mocked)
- **Phase F (Rendering):** JSON + text output serialization
- **Phase G (Integration):** End-to-end CLI run against fixture workbook

**Coverage note:** Filter parameters (`skip_skill_dim`, `disable_availability_filter`, `disable_location_filter`) are tested implicitly in gap-analysis tests (Phase C), not as isolated unit tests. Explicit unit tests are optional for coverage improvement.

---

## Identity Reconciliation for Orphaned Profile+Feedback — 2026-07-06

**Problem:** 15 of 35 real feedback files were orphaned — the person existed only as a profile PDF + a feedback file, with no workbook row and no matching email (contradicts PRD Assumption 1). The old pipeline silently dropped them (FR-50 was report-only), wasting the richest feedback signal.

**Decision:** The workbook stays the primary roster, but a person absent from it can be admitted when a valid profile **and** valid feedback corroborate the same identity (exact full-name match). Ambiguous names or single-source records are quarantined and reported, never guessed — no source is trusted blindly.

**Rationale:**
- Corroboration (two independent sources agreeing) is a much safer identity signal than either source alone.
- Admitting rather than dropping directly answers the sourcing team's #1 discovery-phase complaint (feedback isn't captured/linked cleanly).
- Admitted people enter at reduced/Low `data_confidence`, flagged `admitted_external` — never silently treated as equivalent to a verified workbook record.

**Follow-up decision (same day):** admitted-external people have no real availability data (no supply-sheet row). They are held out of any availability-filtered match rather than defaulting to "available now" — see SCORING_SPEC §2.2.

**Implementation:** `pipeline/reconcile.py:reconcile_external_people()`. Result on real data: 15 admitted, 0 quarantined, `feedback_unmatched` 15 → 0.

---

## Free-Text Query Negation + Deterministic Date Resolution — 2026-07-06

**Problem:** the free-text parser was regex-over-known-vocabulary with no negation handling and no relative-date resolution — "not based in Chennai" and "available ASAP" were silently dropped.

**Decision:** parse free text into a typed `QuerySpec` (skills with `require`/`prefer`/`exclude` polarity, include/exclude locations, exclude supply-states, a verbatim date phrase) via a new DSPy signature (`QueryParse`), then apply polarity deterministically — the LLM parses, it never decides drop-vs-rank. Excluded skills are a scoring penalty (not a hard drop, since a strong candidate may hold the excluded skill alongside required ones); excluded locations/supply-states are hard filters.

**Date resolution — library over hand-rolled regex.** Initially hand-rolled (regex list per phrase pattern); replaced with the `dateparser` library after live testing surfaced "after 15 days" resolving to nothing (regex only matched "in N days") and an LLM-JSON-fallback-mode artifact (stray quote characters wrapping the extracted phrase) that a growing regex list would keep re-encountering per new phrasing. `dateparser` is always called with an explicit `RELATIVE_BASE=<today>` — it never reads the system clock — preserving the same determinism/testability the hand-rolled version had. Small special-cases are kept for staffing shorthand no date library understands ("ASAP", "immediately", "now", "today").

**Implementation:** `models/query_spec.py`, `llm/modules.py:QueryParse`, `pipeline/free_text_role.py` (`resolve_relative_date`, `_parse_with_llm`). The old regex-only parser is kept as the `--no-llm` fallback (no negation support there — acceptable since the LLM path is the primary flow, and `--no-llm` is documented as fully deterministic but weaker).

---

## OCR/Text-Extraction Caching + Snapshot Retention — 2026-07-06

**Problem (caching):** `dsm match`/`dsm ingest` re-ran docling PDF text extraction (+ RapidOCR fallback) fresh on every invocation for every profile, even though only the *LLM-derived* signals one layer up were cached (`.cache/extracted_consultants.json`) — the raw text-extraction step had no equivalent, and its output was frequently computed only to be discarded (any consultant already in the LLM-signal store has their whole record replaced by the stored version, making the freshly-recomputed text pure waste). This was the dominant cost of a `dsm match` run (~130s).

**Decision:** cache `_extract_pdf_text`'s output per-file, keyed by file mtime+size (same hashing style as `hash_consultant_sources`) plus an OCR-config fingerprint (so changing `text_floor_chars`/`confidence_floor` correctly invalidates). Failed extractions are deliberately **not** cached, so a transient failure still retries next run rather than becoming permanently stuck. Verified live: ~130s → ~4.2s warm; touching one profile added back only ~4.5s (that profile alone re-extracting).

**Problem (retention):** TDD §5.4 flagged "define whether/where input snapshots and outputs are persisted, and for how long" as missing information — `dsm match`'s JSON output was never persisted, only printed.

**Decision:** every `dsm match` run auto-persists its full output to `.cache/snapshots/<timestamp>_<run_id>.json`, pruned to the newest `snapshot_retention` (default 50, `0` = unlimited — config-driven like every other threshold in this project, not a policy debate to resolve before shipping something). Persistence failures never break the actual match result (`try/except OSError`).

**Implementation:** `pipeline/store.py` (`hash_file`, `load_text_cache`/`save_text_cache`), `pipeline/ingest.py:_extract_pdf_text_cached`, `observability/snapshot_archive.py`.

---

## Status Summary

| Item | Status | Blocker | Sign-off |
|---|---|---|---|
| Config keys added | ✅ 2026-06-24 | No | — |
| Validators specified | ✅ 2026-06-24 | No | — |
| Model selection confirmed | ✅ 2026-06-24 | No (defaults work) | Security pending |
| Constraint relaxation strategy | ✅ 2026-06-24 | No | — |
| PII rehydration approach | ✅ 2026-06-24 | No | — |
| Grounding mechanism | ✅ 2026-06-24 | No | — |
| Identity reconciliation (admitted-external) | ✅ 2026-07-06 | No | — |
| Free-text negation + date resolution | ✅ 2026-07-06 | No | — |
| OCR/text-extraction caching | ✅ 2026-07-06 | No | — |
| Snapshot retention policy | ✅ 2026-07-06 | No | — |

**Next step:** Slice 3 implementation ready to begin (all design decisions documented). Remaining open items from `SOLUTION_VS_THEMES.md`'s backlog: closed-loop feedback/outcome capture, DSPy compile spike, `skill_vector_similarity` threshold sweep, output-guardrail classifier.
