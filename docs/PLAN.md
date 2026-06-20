# Demand-Supply Matcher — Implementation Plan

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-06-17 |
| Companion | `PRD_refined.md`, `TECHNICAL_DESIGN.md`, `SCORING_SPEC.md` |

> This is the build plan. It slices the work so each stage is independently testable and ships value before the next begins. Build deterministic first, add the LLM only at the edges, and add production machinery last. Milvus is out of scope at POC scale — semantic matching uses local embeddings + numpy.

---

## How to use this with Claude Code

Work **one slice at a time**. For each slice:

1. Start in **plan mode** — ask Claude to read this file, the three specs, and `CLAUDE.md`, then propose an approach for the current slice only. Review the plan before it writes code.
2. **Tests first.** Have Claude write the tests listed under "Tests" for the slice *before* the implementation, then implement until they pass. The tests below are the definition of done.
3. Keep the slice's scope tight — don't let Claude pull forward later-slice features (it will want to add Milvus and DSPy early; the spec says don't).
4. Run the slice's **manual check** on the real workbook to confirm it behaves sensibly, not just that tests pass.
5. Commit, then move to the next slice.

Run tests with `uv run pytest`. Run the CLI with `uv run matcher ...`.

> **Inputs you provide (not Claude Code)** — needed when you reach the slice, none block Slice 1:
> - **Slice 2:** OpenRouter model choice per task + API key (in env); the PII allow/deny field list (what the scrubber may let through).
> - **Slice 3:** the output artifact format (terminal text vs shareable Markdown/HTML report).
> - **Throughout:** the real data in `data/`, and a seed skill-adjacency map + canonical location list (Claude can draft these once it sees the data).

---

## Parallel track (start now, not a slice) — Golden dataset

The eval target (70–85% pass rate) can't be measured without a labelled set of roles → expected shortlists. It needs human curation and has the longest lead time, so start it on day one alongside Slice 1.

- Pick 8–12 roles from `demand-supply.xlsx`. For each, write the shortlist you'd expect and a one-line reason.
- Include **negative** cases (e.g. "Manual Tester must NOT appear for the AI Architect role") and at least one **unfillable** role (tests gap analysis).
- Store as `evals/golden/roles.yaml` (role id → ordered expected candidate emails + notes).
- This is the ruler for Slice 4's eval harness. Keep adding to it as you learn the data.

---

## Slice 1 — Deterministic core (no LLM, no embeddings)

**Goal:** type a Role ID, get a ranked shortlist printed as bands + signals, end-to-end on the real workbook, with zero LLM calls.

**Build (FRs):** FR-01, FR-03, FR-06, FR-11, FR-12, FR-13/14/15/16/17 (hard filters), FR-18 (weighted sort key), FR-19/20 (skill via static adjacency map), FR-26 (rolloff penalty), FR-27 (tiebreaks), FR-28/51 (config + validation), FR-29 (shortlist size), FR-30/55 (bands + signals output), FR-31 (confidence — it's deterministic), FR-34 (snapshot timestamp), FR-43 (no silent drop). Modules: `models/`, `ingest/workbook.py`, `normalize/`, `filters.py`, `scoring/{skill,availability,supply_state}.py`, `rank.py`, `render/text.py`, `config.py`.

**Done when:** AC-1, AC-2, AC-5, AC-7 pass, and output shows bands (Strong/Partial/Gap) + "N of 3 strong" — never a percentage.

**Tests:**

*Automated (`tests/`):*
- `test_config.py` — weights summing to 100 accepted; a bad sum is rejected or normalised with a reported correction; band thresholds and credits in range; out-of-range values clamped + reported (FR-51).
- `test_normalize.py` — "Bangalore" → "Bengaluru"; "Remote (India)" / "remote-India" / "Remote-India" all reconcile to one canonical (FR-11); duplicate emails across tabs collapse to one consultant (FR-12).
- `test_filters.py` — beach always passes availability; rolling-off high/medium passes only within 5 days, fails beyond; new joiner within 7 days; **low-confidence rolloff is never eliminated** (FR-16); co-located role passes strictly local only, relocation-open non-local does NOT pass the hard filter (FR-13).
- `test_scoring_skill.py` — exact=100, proficiency-below=70, adjacent (via static map)=60, no match=0; nice-to-have adds bonus, never penalises absence; mean over required skills; a missing required skill pulls the mean down (counts as 0).
- `test_scoring_availability.py` — 0 days late → 100; ≥30 days late → 0; low-confidence rolloff applies the 30% penalty to this dimension only.
- `test_scoring_supply.py` — beach=100, rolloff=70, new joiner=40.
- `test_bands.py` — score ≥75 → Strong, 40–74 → Partial, <40 → Gap; signals-met count equals number of Strong dimensions.
- `test_rank.py` — tiebreak order availability → feedback-confidence → supply-state; genuine ties listed at the same rank.
- `test_guardrails.py` — a candidate failing any hard filter never appears in the ranked list; no consultant is silently dropped (FR-43); all dimension scores are within 0–100.

*Manual / CLI:*
- `uv run matcher ROLE-01` on the real workbook → returns a ranked shortlist, no crash, output is bands + signals (not a %).
- Run it twice and diff → **identical** output (deterministic; satisfies the Slice-1 part of AC-9).
- Sanity: a beach consultant whose skills match the role should land near the top; someone missing the core skill should be lower with a "Gap" on skill.

---

## Slice 2 — First LLM contact (extraction) + PII gate

**Goal:** add the three LLM-extracted dimensions (feedback quality, adaptability, performance trend). Because this is the first time text leaves the machine, the PII scrub-before-send gate and the extraction grounding guardrail ship **in this slice** — not later.

**Build (FRs):** FR-07/08/09 (profile + feedback ingest), FR-22/23/24 (feedback composite, trajectory owned by trend only, missing = neutral 50), FR-25 (adaptability), performance trend (FR-18), the PII scrub (TDD §5.1), extraction grounding (TDD §4.4). Optionally semantic skill matching via **local** sentence-transformers + numpy cosine (FR-21) — local, so it does not pass through the PII gate. Modules: `ingest/{profiles,feedback}.py`, `normalize/pii.py`, `llm/{client,extract}.py`, `scoring/{feedback,adaptability,trend}.py`.

> **Build the PII gate and its test FIRST, before wiring any real extraction.** Do not send real feedback text to the hosted LLM until the scrub is verified. Use synthetic fixtures during development.

> **Input from you:** OpenRouter model per task + API key in env, and the PII allow/deny field list.

**Done when:** the PII test passes, extraction produces grounded signals that map to bands, and AC-6 holds (gaps flagged, never silently dropped).

**Tests:**

*Automated:*
- `test_pii_gate.py` — **the most important test.** Mock the LLM client to capture the outgoing payload; assert no email, phone, or name pattern is present in any text sent (TDD §5.1). A failure here is a release blocker.
- `test_extract_feedback.py` — given fixture feedback text, the extracted signal object (sentiment, strengths, concerns, keep-signal, domain-depth) matches expected; mock the LLM with canned responses for determinism.
- `test_grounding.py` — when the (mocked) LLM returns a claim with no support in the source text, it is flagged and **not** scored (TDD §4.4).
- `test_feedback_scoring.py` — signal → sub-score per the rule table (positive=80, +keep=10, +domain=5, −concern=10, clamped); composite = 0.5·project + 0.3·client + 0.2·beach; a missing source uses the 50 baseline and is flagged; all-missing → 50 + "no feedback" flag (FR-24).
- `test_adaptability.py` — additive rubric from the four signals; no evidence stays at neutral 50.
- `test_cost.py` — count LLM calls per single-role run; assert it stays within the expected bound (cost discipline / NFR-11).

*Manual / CLI:*
- With caching on and `temperature=0`, run the same role twice → **stable signals and bands** (NFR-04 / AC-9); exact rank order may shuffle slightly and that's acceptable.
- Spot-check a consultant with strong known feedback → Feedback band = Strong; a new joiner with no feedback → neutral, flagged, not penalised to zero.

---

## Slice 3 — Explanations, gap analysis, JSON output

**Goal:** turn rankings into grounded natural-language explanations and handle the "no good match" cases gracefully.

**Build (FRs):** FR-32 (grounded NL explanation), FR-33 (why-not-higher), FR-35/36/37 (gap analysis, partial matches, no-skills inference), FR-52 (JSON output — pull forward to Slice 1 if convenient), FR-38/39/40/41 (informational signals), FR-46/47 (notes + sector as soft signals). Modules: `explain.py`, `gap.py`, `render/json.py`.

**Done when:** AC-3 and AC-4 pass.

> **Input from you:** the output artifact format (terminal text vs shareable Markdown/HTML report).

**Tests:**

*Automated:*
- `test_explain_grounding.py` — explanations reference only data points present in the candidate's evidence; state "no data" rather than invent; no fact appears that isn't in the inputs (DeepEval groundedness or assertion-based).
- `test_explain_why_not.py` — a lower-ranked candidate's explanation names the specific reason (missing skill, availability delay, unverified) (FR-33).
- `test_gap_analysis.py` — an unfillable role never returns empty; names the failing constraint; shows bench distribution; lists nearest alternatives with the constraint relaxed (AC-4 / FR-35). Partial matches ranked by fewest gaps, each gap assessed for bridgeability via adaptability (FR-36).
- `test_json_output.py` — JSON parses, validates against the expected schema, contains the per-dimension bands, signals, confidence, and snapshot timestamp.

*Manual / CLI:*
- Run a role with a clear trade-off (great skills, bad availability) → confirm the explanation surfaces the gap prominently rather than burying it.
- Run an unfillable role → confirm a useful gap explanation, not an empty list.

---

## Slice 4 — Production hardening + eval harness

**Goal:** make it robust on messy inputs and measurable against the golden set. (PII scrubbing is NOT here — it shipped in Slice 2.)

**Build (FRs):** FR-48 (scanned/OCR PDFs), FR-49/50 (ingestion + unmatched reports), FR-53 (malformed-file robustness), the eval harness (DeepEval, optionally Promptfoo) against `evals/golden/`, observability/cost telemetry (NFR-09), provider zero-retention config (TDD §5.2). Modules: OCR path in `ingest/profiles.py`, `evals/`, run-logging.

**Done when:** AC-8, AC-10, and the Evaluation Expectations table in the PRD all pass.

**Tests:**

*Automated:*
- `test_robustness.py` — corrupt PDF, missing tab, missing required column, unreadable workbook each produce a specific error naming the file and problem, with no crash (FR-53 / AC-10).
- `test_scanned_pdf.py` — image-only PDF is OCR'd or flagged low-confidence and never silently dropped (FR-48).
- `test_stale_date.py` — a past start date warns and proceeds; ambiguous free-text prompts for confirmation (FR-44/45 / AC-10).
- `evals/` suite — run against the golden set; assert the pass rate lands in **70–85%**. A 100% pass rate is itself a failure signal (insufficient negative coverage) — make sure negatives are present.

*Manual / CLI:*
- Single-role run < 5 s; batch run < 60 s on the reference dataset (AC-8). If breached, apply the latency levers in the TDD (precompute embeddings, cache, batch explanation calls).
- Confirm each run emits the structured log: tokens, cost, per-stage timings, data-quality flags, config version (NFR-09).

---

## Key reminders carried from the specs

- **Output is signals + bands, never a precise match percentage** (FR-55). True from Slice 1.
- **PII scrub-before-send lives with the first LLM call** (Slice 2), not at the end.
- **Milvus is out at POC scale** — local embeddings + numpy until volume genuinely demands a vector store.
- **Cheapest call is the one you don't make** — Slice 1 has zero LLM; guardrails use small/rule-based filters, not extra LLM calls.
- **The tools are a toolbox** — add DSPy optimisation, the second eval tool, and Milvus only when the simpler path proves insufficient.
