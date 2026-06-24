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

## Status Summary

| Item | Status | Blocker | Sign-off |
|---|---|---|---|
| Config keys added | ✅ 2026-06-24 | No | — |
| Validators specified | ✅ 2026-06-24 | No | — |
| Model selection confirmed | ✅ 2026-06-24 | No (defaults work) | Security pending |
| Constraint relaxation strategy | ✅ 2026-06-24 | No | — |
| PII rehydration approach | ✅ 2026-06-24 | No | — |
| Grounding mechanism | ✅ 2026-06-24 | No | — |

**Next step:** Slice 3 implementation ready to begin (all design decisions documented).
