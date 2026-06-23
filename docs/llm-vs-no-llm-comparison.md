# LLM-On vs --no-llm Mode: Comparison Analysis

**Branch:** `llm-implementation` | **Slice:** 2 | **Date:** 2026-06-23

---

## 1. What the Two Modes Are

| Mode | Command | Description |
|---|---|---|
| **LLM-on** | `dsm match ROLE-01 --top 5` | Full pipeline: Docling PDF extraction → PII scrub → DSPy LLM extraction → deterministic scoring |
| **no-llm** | `dsm match ROLE-01 --top 5 --no-llm` | Partial pipeline: Docling PDF extraction → PII scrub → deterministic scoring only (no LLM calls) |

Both modes run the same deterministic core (skill match, availability, supply state). The difference is in the three **LLM-sourced dimensions**, which in `--no-llm` mode are held at the configured `neutral_baseline` (50).

---

## 2. Scoring Dimension Breakdown

### Weight allocation

| Dimension | Weight | Source |
|---|---|---|
| `skill_match` | 0.35 | Deterministic — Excel workbook + adjacency map |
| `feedback_quality` | 0.25 | **LLM** (sentiment, keep signal, domain depth, concerns) |
| `availability` | 0.15 | Deterministic — date arithmetic |
| `adaptability` | 0.15 | **LLM** (tech transitions, learning speed, cross-domain, upskilling) |
| `supply_state` | 0.05 | Deterministic — beach / rolling-off / new joiner |
| `performance_trend` | 0.05 | **LLM** (improving / stable / declining / unknown) |

45 % of the total score is LLM-sourced. 55 % is deterministic in both modes.

### What each mode produces for the three LLM dimensions

| Mode | `feedback_quality` | `adaptability` | `performance_trend` |
|---|---|---|---|
| `--no-llm` | 50.0 (neutral) | 50.0 (neutral) | 50.0 (neutral) |
| LLM-on | Extracted from project / client / beach feedback text | Extracted from combined profile + feedback text | Classified from combined text |

### Scoring formula for each LLM dimension (LLM-on mode)

**`feedback_quality`** — weighted composite of up to three feedback sources:

```
sub_score(source) = sentiment_base + keep_bonus + domain_bonus − concern_penalty
  where:
    sentiment_base  = 80 (positive) | 50 (neutral) | 20 (negative)
    keep_bonus      = +10  only when source == "client" AND client_keep_signal
    domain_bonus    = +5   when domain_depth == true
    concern_penalty = −10  when concerns list is non-empty

composite = 0.50 × project_sub + 0.30 × client_sub + 0.20 × beach_sub
missing source → sub_score = 50 (neutral)
```

**`adaptability`**:
```
score = 50 + (15 if tech_transitions ≥ 2)
           + (10 if learning_speed_mentions)
           + (10 if cross_domain ≥ 2)
           + (10 if upskilling)
clamped to [0, 100]
```

**`performance_trend`**:
```
improving → 100  |  stable → 70  |  declining → 30  |  unknown → 50
```

---

## 3. Concrete Scoring Example — Aarav Krishnan vs ROLE-01

Derived from `data/project_feedback/Aarav - Backend.md` (SCORING_SPEC §7 worked example).

### Feedback signals extracted by LLM

| Source | Text excerpt | Signals |
|---|---|---|
| **project** | "re-architected the card-auth service in Kotlin; deep payments domain expertise. Has not worked with Terraform/IaC." | sentiment=positive, domain_depth=true, concerns=["no Terraform"] |
| **client** | "Please keep Aarav as long as possible — he is central to the ledger rebuild." | sentiment=positive, client_keep_signal=true |
| **beach** | *(not present)* | missing → neutral 50 |

### Score comparison

| Dimension | `--no-llm` | LLM-on | Delta |
|---|---|---|---|
| `feedback_quality` | 50.0 | **79.5** | +29.5 |
| `adaptability` | 50.0 | **95.0** | +45.0 |
| `performance_trend` | 50.0 | **100.0** | +50.0 |
| `skill_match` | same | same | 0 |
| `availability` | same | same | 0 |
| `supply_state` | same | same | 0 |

**feedback_quality** calculation:
```
project_sub  = 80 + 5 (domain) = 85
client_sub   = 80 + 10 (keep)  = 90
beach_sub    = 50 (missing)
composite    = 0.5 × 85 + 0.3 × 90 + 0.2 × 50 = 42.5 + 27 + 10 = 79.5
```

### Weighted total-score contribution (LLM dims only)

| Mode | LLM dims contribution | Combined delta |
|---|---|---|
| `--no-llm` | 0.25 × 50 + 0.15 × 50 + 0.05 × 50 = **22.50 pts** | — |
| LLM-on (Aarav) | 0.25 × 79.5 + 0.15 × 95 + 0.05 × 100 = **39.12 pts** | **+16.62 pts** |

A consultant with strong signals can gain up to ~16–22 points on their total score versus neutral. This is enough to shift 2–3 band boundaries or overtake multiple candidates.

---

## 4. Consistency

### `--no-llm` mode

Verified with back-to-back identical runs (diff output = empty):

```
Run 1  ROLE-01: #1 Vikram Iyer, #2 Vivaan Hegde, #3 Deepak Shetty …
Run 2  ROLE-01: #1 Vikram Iyer, #2 Vivaan Hegde, #3 Deepak Shetty …
diff: IDENTICAL
```

`--no-llm` is **fully deterministic** — same input always produces byte-identical output. No randomness, no network calls, no model loading variability beyond the initial Docling PDF extraction (which is also deterministic for the same PDF content).

### LLM-on mode

| Condition | Consistency |
|---|---|
| **Cold run (no cache)** | `temperature=0` in DSPy config. GPT-4o-mini at temperature=0 is nearly deterministic but can vary by up to 1 token between API calls. Band classifications (Strong/Partial/Gap) should be stable; exact rank may shuffle once (FR-55 allows this). |
| **Warm run (DSPy cache hit)** | **Byte-identical** to first cold run. DSPy caches on `(module + input hash)`. Same scrubbed text → same hash → same cached output → identical scores. |
| **Cache cleared** | Re-extracts; should match prior run within band-level tolerance due to temperature=0. |

**Conclusion:** For production use, warm-cache LLM runs are as deterministic as `--no-llm`. Cold runs should be treated as advisory-rank-stable, not byte-identical.

---

## 5. Efficiency

### Measured wall-clock time (`--no-llm`)

| Role | Run time |
|---|---|
| ROLE-01 | ~93s |
| ROLE-02 | ~96s |
| ROLE-04 | ~120s |

All runs dominated by **Docling PDF loading** (51 PDFs × ~1.8s average = ~92s). The scoring and matching itself is milliseconds.

### Estimated LLM-on time (cold — no cache)

```
Docling extraction:           ~90–120s  (same as --no-llm)
LLM API calls (gpt-4o-mini):
  ~20 consultants with PDFs → 1 profile call each       =  20 calls
  ~30 consultants with feedback × avg 2 sources each   =  60 calls
  ~35 consultants × (1 adaptability + 1 trend)          =  70 calls
  Total cold calls:                                     ~150 calls
  At ~1.5–3s/call (gpt-4o-mini P50 latency):           ~225–450s

Estimated cold run total:                               ~315–570s  (5–10 min)
```

### Estimated LLM-on time (warm — full cache hit)

```
Docling extraction:  ~90–120s  (unchanged — not cached)
LLM calls:           ~0s       (all cache hits)

Estimated warm run:  ~90–120s  (same as --no-llm)
```

### Summary table

| Metric | `--no-llm` | LLM-on (cold) | LLM-on (warm) |
|---|---|---|---|
| Wall time per role | ~90–120s | ~315–570s | ~90–120s |
| LLM API calls | 0 | ~150 | 0 (cache) |
| Deterministic | ✓ | Advisory (band-stable) | ✓ |
| PDF extraction | ✓ Docling | ✓ Docling | ✓ Docling |
| PII scrubbing | ✓ Presidio | ✓ Presidio | ✓ Presidio |

> **Note:** Docling model loading (OCR + layout) dominates run time in both modes. A future optimisation is to cache the extracted raw text to disk and skip Docling on subsequent runs if the PDF is unchanged.

---

## 6. Cost Estimate (LLM-on, gpt-4o-mini pricing)

gpt-4o-mini: $0.15 / 1M input tokens, $0.60 / 1M output tokens (2026 OpenRouter pricing).

| Call type | ~Input tokens | ~Output tokens | Calls | Cost |
|---|---|---|---|---|
| `ProfileExtraction` | ~800 | ~200 | 20 | $0.0027 |
| `FeedbackSignalExtraction` | ~600 | ~150 | 60 | $0.0063 |
| `AdaptabilitySignalExtraction` | ~1 000 | ~100 | 35 | $0.0057 |
| `PerformanceTrendExtraction` | ~1 000 | ~50 | 35 | $0.0054 |
| **Total (cold run)** | | | **~150** | **~$0.02** |

A complete cold run costs approximately **$0.02 per role query** with gpt-4o-mini. Warm (cached) runs cost **$0.00**.

Over 8 roles × 1 cold run per week: ~$0.16 / week.

---

## 7. Coverage — Who Gets LLM Enrichment

| Consultant category | LLM enrichment | Fallback |
|---|---|---|
| Has PDF + feedback | Full: profile skills enriched, all 3 LLM dims scored | — |
| Has PDF only | Profile enriched; feedback/adapt/trend = 50 (neutral) | "no client/project/beach feedback" evidence |
| Has feedback only | Feedback dims scored; profile skills = workbook defaults | — |
| New joiner (no feedback) | Skipped entirely; "no feedback" flagged | All 3 dims = 50, `data_gaps=["no feedback"]` |
| Unreadable PDF | `data_confidence × 0.7`; `data_gaps=["profile_pdf_unreadable"]` | Scores remain but confidence reduced |
| Unmatched PDF | `data_gaps=["profile_pdf_unmatched"]` | Workbook data only |

The pipeline never drops a workbook consultant regardless of data quality (FR-43). Missing data degrades confidence scores, not presence.

---

## 8. Ranking Impact Across Observed Roles

### ROLE-01 (top 5, `--no-llm`)

```
#1  Vikram Iyer     [1 of 6 strong]
#2  Vivaan Hegde    [2 of 6 strong]
#3  Deepak Shetty  [1 of 6 strong]
#4  Karan Mehta    [2 of 6 strong]
#4  Rahul Nanda    [2 of 6 strong]
```

**With LLM-on**, consultants with strong client feedback (Karan Mehta's feedback: "We extended him twice"; "trusted to run planning") would receive higher `feedback_quality` and `adaptability` scores. This would likely:
- Promote Karan Mehta (currently #4 due to tie-break) above candidates with weaker feedback
- Differentiate the three-way #4 tie using feedback evidence
- Expand the "strong" signal count for top candidates

### ROLE-02 (only 2 candidates pass hard filters)

```
#1  Karthik Subramanian  [2 of 6 strong]
#2  Sandeep Reddy        [2 of 6 strong]  gaps: skill_match
```

With only 2 viable candidates, LLM enrichment does not change the rank ordering but would provide richer evidence on *why* Karthik outranks Sandeep.

### ROLE-04 (top 5, `--no-llm`)

```
#1  Priya Menon   [3 of 6 strong]
#2  Deepak Shetty [2 of 6 strong]
#3  Deepa Sharma  [1 of 6 strong]
#4  Karan Mehta   [2 of 6 strong]  gaps: skill_match
#4  Rahul Nanda   [2 of 6 strong]  gaps: skill_match
```

Priya Menon at #1 with 3-of-6 strong would likely consolidate her lead with LLM-on. The #4 tie between Karan Mehta and Rahul Nanda would be broken by their respective feedback quality.

---

## 9. Safety and Data Quality

Both modes run the full PII gate:

| Step | `--no-llm` | LLM-on |
|---|---|---|
| Presidio PII scrubbing | ✓ Runs on all text | ✓ Same — runs BEFORE LLM calls |
| Token map stored | ✓ `consultant.pii_token_map` | ✓ Same |
| Raw PII ever sent to API | N/A (no API calls) | **Never** — scrub_pii is an invariant gating step |
| Grounding check | N/A | ✓ Evidence spans verified against scrubbed source text |
| Evidence floor (FR-10) | N/A | ✓ `data_confidence × 0.7` if `len(grounded_spans) < 1` |

The PII gate test (`tests/unit/test_pii_gate.py`) is a release blocker — it asserts that no email, phone, or consultant name appears in any captured LLM payload across all calls.

---

## 10. When to Use Each Mode

| Use case | Recommended mode |
|---|---|
| Offline / no API key | `--no-llm` |
| Iterating on scoring weights / config changes | `--no-llm` (instant feedback, deterministic) |
| CI / automated regression tests | `--no-llm` (no token cost, no flakiness) |
| First production run for a new dataset | LLM-on cold (pays token cost once, caches) |
| Subsequent production queries (same data) | LLM-on warm (cache hits, same speed as `--no-llm`) |
| Debugging dimension behaviour | `--no-llm` (fewer moving parts) |
| Final candidate report for stakeholders | LLM-on (full 6-dimension scoring with evidence) |

---

## 11. Summary

| Factor | `--no-llm` | LLM-on (cold) | LLM-on (warm) |
|---|---|---|---|
| Dimensions scored with real data | 3 of 6 | 6 of 6 | 6 of 6 |
| LLM dims value | 50 (neutral) | Real extracted signals | Real extracted signals |
| Max score uplift from LLM dims | 0 pts | ~16–22 pts per consultant | ~16–22 pts |
| Ranking precision | Skill + availability + supply only | Full 6-dim differentiation | Full 6-dim differentiation |
| Run time | ~90–120s | ~315–570s | ~90–120s |
| Cost per role | $0.00 | ~$0.02 | $0.00 |
| Deterministic | ✓ Always | Band-stable (temperature=0) | ✓ Always |
| PII protection | ✓ | ✓ | ✓ |
| Suitable for CI | ✓ | ✗ (cost + latency) | ✓ (if cache pre-warmed) |
| Suitable for production report | Partial (45% of score is untapped) | ✓ | ✓ |
