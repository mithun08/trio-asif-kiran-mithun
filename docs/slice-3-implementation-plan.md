# Slice 3 — Implementation Plan: Explanations, Gap Analysis, JSON Output

| Field | Value |
|---|---|
| Source | `docs/PLAN.md` §Slice 3 (lines 99-120) |
| Specs cross-referenced | `PRD_refined.md` (FR-30/31/32/33/35/36/37/38/39/40/41/46/47/52, AC-3/AC-4), `TECHNICAL_DESIGN.md` (§4.4 grounding), `SCORING_SPEC.md` (§5 confidence) |
| Scope | Grounded NL explanation, why-not-higher, gap analysis (unfillable / partial / no-skills), confidence levels, informational signals, JSON output |
| Out of scope | OCR / scanned PDFs (FR-48), eval harness (DeepEval / Promptfoo), observability/cost telemetry, robustness fuzz, Milvus, sentence-transformers, batch / priority ordering (FR-54) — all Slice 4 |
| Predecessor | Slice 2 (extraction + PII gate); all six dimensions scored, PII scrub wired |

---

## Context

Slice 1 shipped a deterministic ranking core; Slice 2 added the three LLM-extracted dimensions and the PII scrub-before-send gate. Six dimensions now score real signals and `DimensionScore.evidence` already carries structured tags (e.g. `"mandatory mean=80.0"`, `"days_late=12"`, `"positive sentiment"`, `"no client feedback"`). Slice 3 turns those signals into **grounded natural-language explanations**, handles the **"no good match"** cases gracefully, and emits a **machine-readable JSON envelope** so the output can drive the v2 feedback loop and reproducibility checks.

### What's already true on `main` (validated against the repo, 2026-06-24)

- `pipeline/explain.py` is a single `raise NotImplementedError` stub (`src/matcher/pipeline/explain.py:12`).
- `CandidateExplanation` DSPy signature is already defined and ready to call (`src/matcher/llm/modules.py:18-24`).
- The text renderer already prints bands and signals-met (`src/matcher/render/text.py:8-27`); `band()` lives at `src/matcher/scoring/ranker.py:20-23`.
- `cli.py` accepts `--json` but does not branch on it (`src/matcher/cli.py:28`); no `render/json.py` exists.
- `AppConfig.model_explain = "openai/gpt-4o"` is loaded from YAML (`config.py:156`, `default.yaml:58`) — currently unused.
- `configure_lm` hardcodes `config.model_extraction` for the global DSPy LM (`src/matcher/llm/client.py:13`). Slice 3 must route explanation calls without disturbing extraction.
- `match_role` returns `(ranked, hard_rejected)` with the rejects holding a single string reason (`match.py:56-65`). FR-35/36 need this structured into a richer report with relaxed-constraint alternatives.
- `Role` carries `description` (the `Notes / Constraints` column — `ingest.py:95`) but **no** `sector` field. FR-46/47 expect both to feed the recommendation reasoning.
- No `confidence_level` on `ScoredCandidate`; the FR-31 rule table in `SCORING_SPEC.md:194-200` is not yet implemented.
- PII scrubber exists with `rehydrate_text` (`privacy/scrubber.py:70`); consultants carry `pii_token_map`. Slice 2 keeps tokens out of dimension evidence — Slice 3 must preserve that invariant for explanations.
- `RunOutput` (`models/output.py`) is Pydantic and serialisable; not assembled today.

---

## YAGNI scope decisions

| Topic | Decision | Rationale |
|---|---|---|
| FR-37 LLM title→skills inference | **One new DSPy signature** returning a skills list + a confidence float; if `< skill_infer_min = 0.5`, the skill dimension is skipped and remaining weights renormalised. | PLAN.md line 102; `SCORING_SPEC.md:99,213`. |
| Constraint-relaxation logic for FR-35 | **Two relaxation passes only** — drop hard availability filter, drop hard location filter. Each pass yields up to `gap_top_n` alternatives, each labelled with the relaxed constraint. | PLAN.md line 102; cheap and deterministic. |
| Bridgeability (FR-36) | **Derived from the partial-match candidate's `adaptability` raw score**, banded High/Medium/Low. No new LLM call. | Adaptability already captures the four signals (`dimensions.py:170-212`). |
| Explanation model routing | **Per-call `dspy.context(lm=…)` override** for `CandidateExplanation`, using `config.model_explain`. Extraction stays on `config.model_extraction`. | Avoids mutating the global LM state. |
| Why-not-higher reference candidate | **Rank N-1 (the candidate immediately above)**, compared dim-by-dim. Rank 1 gets `why_not_higher == ""`. | Most informative trade-off for a human reader. FR-33 says "when relevant". |
| Confidence derivation | **Pure-deterministic** from `consultant.feedback_signals` count, profile-vs-workbook proficiency diff (verified vs unverified), `supply_state == "new_joiner"`, and `data_confidence`. | Implements `SCORING_SPEC` §5 without an LLM. |
| `Role.sector` ingest | Add `sector: str = ""` + populate from the existing `Sector` column the workbook has (currently ignored — see `slice-1-implementation-plan.md:25`). | Single ingest-line change. |
| Days on Beach (FR-40) | Add `Consultant.days_on_beach: int = 0` from the existing `Days on Beach` column (Beach sheet). Missing column → 0, flag suppressed. | Cheap; PLAN.md line 102 lists FR-40. |
| Promptfoo / DeepEval gates | **Defer to Slice 4.** | PLAN.md line 129 puts the eval harness in Slice 4. |
| Markdown / HTML report | **Defer.** Terminal text + JSON only in v1. | Slice 4 reporting bundle (FR-49/50) can wrap. |
| FR-39 stakeholder graph | **Surface what extraction already produces** (`client_keep_signal`, `concerns`, `strengths`). Structured stakeholder graph is roadmap v2. | Cost discipline. |
| FR-31 thresholds | **3 new config keys** so AC-7 holds (tunable without code change). | Pattern from Slices 1/2. |

---

## What Slice 3 ships

**Build (FRs):** FR-32 (grounded NL explanation), FR-33 (why-not-higher), FR-35 (no-empty-result, nearest alternatives), FR-36 (partial matches + bridgeability), FR-37 (skill inference), FR-38/39/40/41 (informational signals), FR-46 (Notes as soft signal), FR-47 (Sector as soft signal), FR-52 (JSON output).
**Plus carry-over:** FR-31 confidence level (deferred from Slice 1; AC-2 / FR-30 needs it in the output).
**Done when:** AC-3 and AC-4 pass; AC-9 (reproducibility) still holds; JSON output validates and round-trips.

| Feature | FR | Where it lives |
|---|---|---|
| Grounded NL explanation per candidate | FR-32 | `pipeline/explain.py` + `llm/explain_module.py` |
| Why-not-higher rationale | FR-33 | `pipeline/explain.py` with rank-N-1 context |
| No-empty-result + nearest alternatives | FR-35 | New `pipeline/gap.py` |
| Partial-match ranking + bridgeability | FR-36 | `pipeline/gap.py` |
| Skill inference from title | FR-37 | `pipeline/gap.py` + `llm/skill_inference.py` |
| Confidence level High/Medium/Low | FR-31, FR-30 | New `scoring/confidence.py` |
| Notes/Constraints as soft signal | FR-46 | `Role.description` (already ingested) → fed to explanation context |
| Sector as soft signal | FR-47 | New `Role.sector` + `"sector_match"` info_flag |
| Grade mismatch flag | FR-38 | New `scoring/info_flags.py` |
| Stakeholder/keep/concern signals surfaced | FR-39 | `scoring/info_flags.py` (already extracted, just exposed) |
| Beach > 60 days flag | FR-40 | `scoring/info_flags.py` (config-driven threshold) |
| New-joiner unverified-skills marker | FR-41 | `scoring/info_flags.py` |
| JSON output | FR-52 | New `render/json.py` + CLI wiring |

---

## Pipeline ordering (`cli.py`)

```
… (Slice 2 pipeline as today) …
match_role(role, consultants, …)              ← (ranked, hard_rejected)
    ↓
gap.build_gap_report(role, ranked, hard_rejected, all_consultants,
                     weights, config, adjacency_map)
    ↓                                           ← FR-35/36/37 — never empty
confidence.attach_confidence_levels(ranked, consultants, config)
    ↓                                           ← FR-31 / FR-30
info_flags.attach_info_flags(ranked, role, consultants, config)
    ↓                                           ← FR-38/39/40/41
explain.generate_explanations(ranked, role, consultants, config)
    ↓                                           ← FR-32/33 (skipped if --no-llm)
RunOutput assembly                              ← FR-34 snapshot, FR-52 envelope
    ↓
render.text.print_results(run_output)   OR   render.json.print_results(run_output)
```

`--no-llm` skips only `generate_explanations` (and `skill_inference` if reached); the rest of Slice 3 (gap report, confidence, info flags, JSON renderer) is deterministic and runs unchanged. A new `--no-explanations` toggle skips the explanation step independently for cost-controlled iteration.

---

## Model changes

### `src/matcher/models/role.py`
Add one field:
```python
sector: str = ""                          # FR-47 soft signal
```
`description` already covers FR-46 — no further change.

### `src/matcher/models/consultant.py`
Add one field:
```python
days_on_beach: int = 0                    # FR-40 informational
```

### `src/matcher/models/score.py`
Add to `ScoredCandidate`:
```python
confidence_level: Literal["High", "Medium", "Low"] = "Medium"   # FR-31 / FR-30
info_flags: list[str] = Field(default_factory=list)             # FR-38/39/40/41
why_not_higher: str = ""                                        # FR-33 (empty for rank 1)
```

### `src/matcher/models/gap.py` (NEW)
```python
class GapReport(BaseModel):
    role_id: str
    failing_constraints: list[str] = Field(default_factory=list)    # FR-35
    bench_distribution: dict[str, int] = Field(default_factory=dict)
        # supply_state → count over all consultants
    nearest_alternatives: list[ScoredCandidate] = Field(default_factory=list)
        # FR-35: relaxed-constraint candidates, each tagged in info_flags
    partial_matches: list[ScoredCandidate] = Field(default_factory=list)
        # FR-36: skill-gap candidates with bridgeability flagged
    inferred_skills: list[str] = Field(default_factory=list)        # FR-37
    inference_confidence: float = 0.0                               # 0..1
    skill_dim_skipped: bool = False                                 # FR-37 → renormalise
    notes: list[str] = Field(default_factory=list)
```

### `src/matcher/models/output.py`
Extend `RunOutput`:
```python
gap_report: GapReport | None = None
role_snapshot: Role | None = None         # FR-46/47 audit trail of what was fed
```

---

## Config changes

### `src/matcher/config.py` — extend `ScoringConfig`

```python
confidence_high_min_projects: int = 2          # SCORING_SPEC §5
confidence_medium_min_sources: int = 1
beach_long_days: int = 60                      # FR-40
skill_infer_min: float = 0.5                   # SCORING_SPEC:213; clamped [0,1]
gap_top_n: int = 3
```

Add the matching `_clamp`-style validators (mirroring `_clamp_penalty` for `skill_infer_min`, plain ints for the rest with sane lower bounds reported via `_clamp` on out-of-range values per FR-51).

### `config/default.yaml`

Under `scoring.config`:
```yaml
confidence_high_min_projects: 2
confidence_medium_min_sources: 1
beach_long_days: 60
skill_infer_min: 0.5
gap_top_n: 3
```

Under `models:` (optional; reads with a sane fallback to `models.extraction`):
```yaml
models:
  …
  skill_inference: "openai/gpt-4o-mini"   # FR-37
```

Editing any of these alters output with no code change (AC-7 / FR-28 / FR-51) — exercised by `test_config.py` extensions.

---

## File-by-file changes

| File | Status | Change |
|---|---|---|
| `src/matcher/models/role.py` | edit | Add `sector: str = ""`. |
| `src/matcher/models/consultant.py` | edit | Add `days_on_beach: int = 0`. |
| `src/matcher/models/score.py` | edit | Add `confidence_level`, `info_flags`, `why_not_higher`. |
| `src/matcher/models/gap.py` | **NEW** | `GapReport` (see above). |
| `src/matcher/models/output.py` | edit | Add `gap_report`, `role_snapshot`. |
| `src/matcher/pipeline/ingest.py` | edit | Pull `Sector` (Open Roles) and `Days on Beach` (Beach sheet) columns — currently ignored per `slice-1-implementation-plan.md:25,36`. Missing columns must NOT crash (FR-53). |
| `src/matcher/scoring/confidence.py` | **NEW** | `attach_confidence_levels(candidates, consultants, config) -> list[ScoredCandidate]`. Implements FR-31 deterministically from feedback-signal sources count, profile-vs-workbook proficiency diff (verified vs unverified default proficiency=3), `supply_state == "new_joiner"` (→ Low), and `data_confidence` (low extraction confidence → Low). |
| `src/matcher/scoring/info_flags.py` | **NEW** | `attach_info_flags(candidates, role, consultants, config)`. Emits per-candidate string flags: `"grade_mismatch"` (FR-38, against a small grade↔role-seniority map externalised on `ScoringConfig` or `config/grade_map.yaml`), `"client_keep_signal"` / `"concern: <text>"` (FR-39, from feedback signals), `"beach_long: 87d"` (FR-40, when `days_on_beach > beach_long_days`), `"new_joiner_skills_unverified"` (FR-41), and `"sector_match"` (FR-47, case-insensitive match of `role.sector` against profile text or feedback strengths/concerns). Pure-deterministic; no LLM. |
| `src/matcher/pipeline/gap.py` | **NEW** | `build_gap_report(role, ranked, hard_rejected, all_consultants, weights, config, adjacency_map) -> GapReport`. Three branches: <br>**(a) all rejected (FR-35):** name failing filter(s) by inspecting `hard_rejected` reasons; build `bench_distribution`; call `match_role` twice with `disable_availability_filter=True` and `disable_location_filter=True` respectively, taking top `gap_top_n` from each and tagging the relaxed constraint in `info_flags` (`"relaxed: availability"` / `"relaxed: location"`). <br>**(b) role has zero `required_skills` (FR-37):** call `llm.skill_inference.infer_skills_from_title`; if `confidence ≥ skill_infer_min`, inject skills into a `role.model_copy(update={"required_skills": …})` and re-run `match_role`; if below, set `skill_dim_skipped=True` and re-run `match_role(skip_skill_dim=True)`. Either way `gap_report.inferred_skills` and `inference_confidence` are populated. <br>**(c) role has required skills but no full match in `ranked`** (best candidate's skill band ≠ Strong) **(FR-36):** rank partial-match candidates by `(num_missing_skills ASC, adaptability_raw DESC)`; tag each entry's `info_flags` with `"bridgeability: High\|Medium\|Low"` derived from adaptability band. <br>**Note:** branches are not mutually exclusive — (b) followed by (a) or (c) is possible. Branch (a) handler is gated on `len(ranked) == 0`. |
| `src/matcher/pipeline/match.py` | edit | Accept `skip_skill_dim: bool = False`. When set, drop `skill_match` from the dim list and renormalise the remaining five weights to sum to 1.0 **without mutating** the passed `ScoringWeights` (build a local copy). Also accept `disable_availability_filter: bool = False`, `disable_location_filter: bool = False` and pass them through to `apply_hard_filters`. Defaults preserve Slice 2 behaviour. |
| `src/matcher/scoring/filters.py` | edit | Plumb the two `disable_*` booleans through `apply_hard_filters`. When `disable_availability_filter`, `_check_availability` is bypassed (always returns `(True, "relaxed: availability")`). Same shape for location. Default behaviour unchanged. |
| `src/matcher/llm/modules.py` | edit | Refine `CandidateExplanation` to add an optional `why_not_higher_context: str = dspy.InputField(desc="JSON of dim deltas vs rank N-1; empty for rank 1")` input and a `why_not_higher: str = dspy.OutputField()` output. Add `SkillInference` signature: inputs `role_title: str`, `role_description: str`; outputs `skills_json: str`, `confidence: str` (parsed to float — DSPy emits strings reliably). |
| `src/matcher/llm/explain_module.py` | **NEW** | Wraps `dspy.Predict(CandidateExplanation)` inside `with dspy.context(lm=explanation_lm):` where `explanation_lm = dspy.LM(model=config.model_explain, …)` constructed once per run. Returns `(explanation, why_not_higher)` strings. **PII rehydration:** apply `rehydrate_text(text, consultant.pii_token_map)` to both strings before returning (safety net — Slice-2 invariant keeps tokens out of `evidence`, but a hallucination could still emit one). **Grounding guardrail (TDD §4.4):** before accepting, check the explanation only references dimension names actually present in the fed evidence (cheap regex on dim-name vocabulary). On violation, return `("", "")` and let `explain.generate_explanations` flag `"explanation_ungrounded"`. |
| `src/matcher/llm/skill_inference.py` | **NEW** | Wraps `dspy.Predict(SkillInference)`. Parses `skills_json` (with the existing safe-JSON pattern used in `llm/extract.py`) and `confidence` (clamped to `[0.0, 1.0]`). Returns `(skills: list[str], confidence: float)`. |
| `src/matcher/pipeline/explain.py` | stub → impl | `generate_explanations(candidates, role, consultants, config) -> list[ScoredCandidate]`. Per candidate: <br>1. Build the evidence package — role title, description (FR-46), sector (FR-47), per-dim `(name, band, evidence)` triples, info_flags. <br>2. If `rank > 1`, build the `why_not_higher_context` as a JSON of (dim_name, this_raw, above_raw, delta_band) for each dim relative to candidates[rank-2]. <br>3. Call `explain_module.explain(…)`. <br>4. On parse failure → append `"explanation_failed"` to `info_flags`; keep `explanation=""`. Never crash. <br>5. On grounding failure → append `"explanation_ungrounded"`. <br>Returns the candidate list with `explanation` and `why_not_higher` populated. Consultants are keyed by `consultant_email`. |
| `src/matcher/render/text.py` | edit | Extend output: per-candidate confidence level line, `info_flags` line, `why_not_higher` line (when non-empty), and a separate "Gap report" block when `gap_report.failing_constraints` non-empty (lists constraints, bench distribution, alternatives, inferred skills, partial matches with bridgeability). Keep `[N of K strong]` summary. |
| `src/matcher/render/json.py` | **NEW** | `print_json_results(run_output: RunOutput) -> None`. Single call: `json.dumps(run_output.model_dump(mode='json'), indent=2, default=str)` to stdout. **Schema is the canonical Pydantic dump** of `RunOutput` — no hand-rolled shape, no drift. Snapshot timestamp (FR-34) and `config_version` already on `RunOutput`. |
| `src/matcher/cli.py` | edit | Assemble `RunOutput` (snapshot_id = sha256 of `data/demand-supply.xlsx` `mtime + size`, role_snapshot = role, gap_report from `build_gap_report`). Wire `--json` to branch between `render.text` and `render.json`. Add `--with-explanations / --no-explanations` (default ON) for cost-controlled iteration. |
| `tests/conftest.py` | edit | Add fixtures: `mock_explanation_lm` (patches the `dspy.Predict(CandidateExplanation)` call path to return a canned deterministic explanation that references only fed dim names), `mock_skill_inference_lm`, `role_no_skills`, `unfillable_role`, `consultant_with_pii_token_map`. |

---

## Existing utilities to reuse

| Utility | File:line | How |
|---|---|---|
| `band()` | `src/matcher/scoring/ranker.py:20` | Drive per-dim band labels in JSON + text + explanation context. Already used by `render/text.py:16`. |
| `rehydrate_text()` | `src/matcher/privacy/scrubber.py:70` | Post-process explanation strings to restore names/emails — safety net in `explain_module.py`. |
| `Consultant.pii_token_map` | `src/matcher/models/consultant.py:33` | Lookup table per consultant, passed to `rehydrate_text`. |
| `DimensionScore.evidence` | `src/matcher/models/score.py:11` | Already populated by every scoring function in `dimensions.py`. **The** grounding source for explanations — explanations cite from here, not from raw text. |
| `rank_candidates` + `_sort_key` | `src/matcher/scoring/ranker.py:11-37` | Reused for gap-report relaxation re-runs (same code path, different filter inputs). |
| `RunOutput` | `src/matcher/models/output.py` | Pydantic envelope; `model_dump(mode='json')` is the JSON output. |
| `consultant.adaptability_signals` | populated by `extract.py` (Slice 2) | Drives FR-36 bridgeability band — no new LLM call. |
| `score_skill_match` | `src/matcher/scoring/dimensions.py:30` | Reused after FR-37 inferred skills are injected into the Role. |
| `dspy.context(lm=...)` | dspy lib | Per-call LM override (avoids re-`configure`-ing the global LM). |
| `apply_hard_filters` | `src/matcher/scoring/filters.py:43` | Extended with two disable booleans — keeps the FR-35 relaxation cheap. |
| Safe JSON parse pattern | existing in `llm/extract.py` | Reused by `llm/skill_inference.py` to read `skills_json` / `confidence`. |

---

## Test plan (TDD — RED first, per PLAN.md step 2)

Tests are ordered by build dependency.

### Phase A — Models & config (no LLM)

1. **`tests/unit/test_models_score.py`** *(extend)* — `confidence_level` accepts `"High"|"Medium"|"Low"`, defaults `"Medium"`; `info_flags` and `why_not_higher` default empty.
2. **`tests/unit/test_models_gap.py`** *(NEW)* — `GapReport` round-trips through `model_dump_json` / `model_validate_json`.
3. **`tests/unit/test_config.py`** *(extend)* — five new keys load from YAML; defaults preserved when key absent; `skill_infer_min` clamped to `[0, 1]` with a warning when out of range.
4. **`tests/unit/test_ingest_sector_daysonbeach.py`** *(NEW)* — `Sector` column populates `Role.sector`; absent column → empty string, no crash. `Days on Beach` from Beach sheet → `Consultant.days_on_beach`; rolling-off / new-joiner consultants → 0.

### Phase B — Confidence & info flags (pure deterministic)

5. **`tests/unit/test_confidence.py`** *(NEW)* — `SCORING_SPEC` §5 truth table:
   - 2 Parity project + 1 client feedback + skills verified → `"High"`.
   - 1 project feedback only → `"Medium"`.
   - `supply_state == "new_joiner"` → `"Low"`.
   - All feedback empty + verified skills → `"Low"` (no-feedback path).
   - Threshold change in YAML alters result (AC-7).
6. **`tests/unit/test_info_flags.py`** *(NEW)* — Senior role + Associate grade → `"grade_mismatch"` (FR-38). `days_on_beach = 87`, threshold 60 → `"beach_long: 87d"` (FR-40). `supply_state == "new_joiner"` → `"new_joiner_skills_unverified"` (FR-41). `feedback_signals["client"].client_keep_signal` true → `"client_keep_signal"` (FR-39). `role.sector == "Financial Services"` mentioned in profile → `"sector_match"` (FR-47).

### Phase C — Gap analysis (FR-35/36/37, no LLM)

7. **`tests/unit/test_gap_unfillable.py`** *(NEW)* (AC-4) — Role requires `Cobol`; no consultant has it AND none is co-located → `gap_report.failing_constraints` includes both; `nearest_alternatives` non-empty, each carrying the relaxed-constraint label; `bench_distribution == {"beach": N, "rolling_off": M, "new_joiner": K}`. **Output is never empty.**
8. **`tests/unit/test_gap_partial_match.py`** *(NEW)* (FR-36) — Role with 3 skills; best consultant matches 2. `partial_matches` ordered by `(missing_count ASC, adaptability DESC)`; each entry's `info_flags` contains `"bridgeability: High|Medium|Low"`.

### Phase D — Skill inference (FR-37, LLM-mocked)

9. **`tests/unit/test_gap_skill_inference.py`** *(NEW)* — Role with empty `required_skills`. Mocked `SkillInference` returns `(["Python","FastAPI"], confidence=0.8)` → `gap_report.inferred_skills == ["Python","FastAPI"]`, scoring proceeds with inferred skills, `skill_dim_skipped=False`. Same mock with `confidence=0.3` → `skill_dim_skipped=True`, dim weight redistributed, candidates still ranked.

### Phase E — Explanation (LLM-mocked)

10. **`tests/unit/test_explain_grounding.py`** *(NEW)* (FR-32 / TDD §4.4) — `mock_explanation_lm` returns text citing a dim name not in the fed evidence → candidate ends with `explanation=""` and `info_flags` contains `"explanation_ungrounded"`. Reciprocal: explanation citing only fed dims → kept verbatim.
11. **`tests/unit/test_explain_why_not_higher.py`** *(NEW)* (FR-33) — Rank-2 candidate gets `why_not_higher` populated; rank-1 candidate gets `why_not_higher == ""`.
12. **`tests/unit/test_explain_pii_rehydration.py`** *(NEW)* — Consultant with `pii_token_map = {"<PERSON_0>": "Aarav Krishnan"}`; mock explanation returning `"<PERSON_0> showed strong …"` → after rehydration reads `"Aarav Krishnan showed strong …"`. Empty `pii_token_map` → no-op.

### Phase F — Rendering (FR-52)

13. **`tests/unit/test_render_json.py`** *(NEW)* — `RunOutput` with two candidates and a `GapReport` serialises via the JSON renderer; output parses with `json.loads`; round-trip via `RunOutput.model_validate` recovers structural equality; `timestamp` is an ISO-8601 string; `confidence_level` present per candidate.
14. **`tests/unit/test_render_text.py`** *(NEW)* — Confidence level, info flags, and why-not-higher all appear in text output for a sample candidate. Gap section appears when `gap_report.failing_constraints` non-empty.

### Phase G — Integration

15. **`tests/integration/test_pipeline_slice3.py`** *(NEW)* — CLI run end-to-end with mocked LLMs (cache enabled), against a 5-consultant fixture workbook, against (a) a normal role, (b) an unfillable role, (c) a role with no `required_skills`. Each path returns AC-3 / AC-4-conformant output in **both** text and JSON modes. Snapshot timestamp and `config_version` present in JSON.

### Cost discipline (NFR-11 carryover)

16. **`tests/unit/test_cost.py`** *(extend)* — total LLM calls per single-role run = extraction calls (Slice 2 bound) + `len(ranked)` explanation calls + at most 1 skill-inference call. Warm cache → 0 new calls.

### Manual / CLI checks (real workbook)

- `uv run dsm match ROLE-01` → human-readable explanation for top-5, `why_not_higher` on ranks 2..5, confidence level per candidate.
- `uv run dsm match ROLE-01 --json | jq .candidates[0].explanation` → parseable, non-empty.
- `uv run dsm match <unfillable-role-id>` → never-empty output; constraint named; bench distribution shown; relaxed-constraint candidates listed.
- A role with no `Required Skills` populated → inferred-skills flag visible (or "skill dimension skipped" when confidence < `skill_infer_min`).
- Run twice with cache → bands, signals-met count, confidence level **identical** (AC-9). Explanation text identical (cache hit at `temperature=0`).
- A consultant whose name was scrubbed (Slice 2) → final explanation contains the actual name, not the token.

---

## Verification (end-to-end)

1. `make lint && make typecheck && make test-unit && make test-int` all green.
2. **AC-3 spot-check (FR-32/33)**: the text output for ROLE-01 shows a 1–3 sentence explanation per candidate; ranks ≥ 2 carry a `why_not_higher` line referencing the gap relative to the candidate above.
3. **AC-4 spot-check (FR-35)**: hand-author (or pick) a role where no consultant passes hard filters. CLI output: failing constraint named, bench distribution printed, alternatives listed under "Relaxed-constraint candidates".
4. **AC-9 carryover (FR-34/52/55)**: cold-run and warm-run of the same role command produce identical bands, signals-met, confidence levels, and JSON serialisation modulo `timestamp`.
5. **PII rehydration end-to-end**: `grep -E '<(PERSON|EMAIL_ADDRESS|PHONE_NUMBER)_[0-9]+>'` against the rendered text/JSON returns zero matches.
6. **Cost discipline (NFR-11)**: `test_cost.py` extension holds; warm-cache rerun adds no new LLM calls.
7. **Spec cross-checks (FR / AC matrix Slice 3 unblocks):**
   - **AC-3 / FR-32 / FR-33** — `test_explain_grounding.py`, `test_explain_why_not_higher.py`, manual check.
   - **AC-4 / FR-35** — `test_gap_unfillable.py`, manual check.
   - **FR-36** — `test_gap_partial_match.py`.
   - **FR-37** — `test_gap_skill_inference.py`.
   - **FR-38/39/40/41** — `test_info_flags.py`.
   - **FR-46/47** — `test_ingest_sector_daysonbeach.py` + integration check that `role.description` and `role.sector` appear in the evidence package fed to DSPy.
   - **FR-31 / FR-30** — `test_confidence.py` + `test_render_text.py`.
   - **FR-52 / AC-9** — `test_render_json.py` + `test_pipeline_slice3.py`.
   - **TDD §4.4 (explanation grounding)** — `test_explain_grounding.py`.

---

## Inputs needed from user (per PLAN.md line 28)

These block live-LLM runs and final polish, but not the build-out of tests/mocks:

1. **Output artifact format** — terminal text only (default), or also a shareable Markdown/HTML report? Plan assumes terminal text + JSON for v1; a Markdown wrapper can be added in Slice 4.
2. **Confirm `model_explain = "openai/gpt-4o"`** (default in `config/default.yaml:58`) vs a cheaper alternative (e.g. `gpt-4o-mini`) for cost discipline. Default kept unless changed.
3. **Grade implied-seniority map** for FR-38 — small dict needed (e.g. `"Senior" → ["Senior Consultant", "Lead Consultant"]`). Plan stubs one entry; user to extend.
4. **Sector match policy** — exact string match (default) vs. title-keyword extraction. Plan defaults to case-insensitive exact match of `role.sector` against `consultant.raw_profile_text` and feedback strengths/concerns, surfaced as the `"sector_match"` info_flag (not scored).

---

## Build order (suggested commit shape)

1. **Models + config** — `Role.sector`, `Consultant.days_on_beach`, `ScoredCandidate.{confidence_level, info_flags, why_not_higher}`, `GapReport`, `RunOutput.gap_report` / `role_snapshot`, 5 new `ScoringConfig` keys + YAML mirror. Tests: model + config extensions. Slice 2 behaviour unchanged.
2. **Ingest extensions** — pull Sector + Days on Beach columns; FR-53 graceful when missing. Tests: `test_ingest_sector_daysonbeach.py`.
3. **Confidence + info flags (pure deterministic)** — `scoring/confidence.py`, `scoring/info_flags.py`. Tests: `test_confidence.py`, `test_info_flags.py`.
4. **Gap analysis (no LLM)** — `pipeline/gap.py` + `match.py` parameter extensions + `filters.py` boolean plumbing. Tests: `test_gap_unfillable.py`, `test_gap_partial_match.py`.
5. **Skill inference (FR-37)** — `llm/modules.py` (`SkillInference`), `llm/skill_inference.py`, wire into `pipeline/gap.py`. Tests: `test_gap_skill_inference.py` (mocked LM).
6. **Explanation (FR-32/33)** — `llm/modules.py` refinement, `llm/explain_module.py`, `pipeline/explain.py` impl. Tests: `test_explain_grounding.py`, `test_explain_why_not_higher.py`, `test_explain_pii_rehydration.py`.
7. **JSON + text renderer extensions** — `render/json.py`, `render/text.py` extensions, `RunOutput` assembly in `cli.py`, `--json` and `--no-explanations` wiring. Tests: `test_render_json.py`, `test_render_text.py`.
8. **Integration + manual checks** — `tests/integration/test_pipeline_slice3.py`; cold/warm cache reproducibility; PII rehydration sweep; cost discipline rerun.
