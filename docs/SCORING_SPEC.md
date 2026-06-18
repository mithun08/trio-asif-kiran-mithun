# Demand-Supply Matcher — Scoring Specification
**Parity Partners · Staffing Recommendation Engine**

| Field | Value |
|---|---|
| Version | 1.0 |
| Date | 2026-06-15 |
| Status | Draft for review |
| Companion | PRD (`PRD_refined.md`), Technical Design Document (`TECHNICAL_DESIGN.md`) |

> **Purpose.** This document closes the FR-18–26 scoring gap: it defines the exact math that turns a (role, consultant) pair into per-dimension scores, a weighted overall score, and a confidence level. It is the authoritative reference for implementing the ranking engine.
>
> **Convention.** Every dimension is scored on a **0–100** scale. All numeric constants below are **defaults and must be configurable** (FR-28); they are shown as `name = default`.

---

# 1. Pipeline

```
(role, consultant)
   → 1. Hard filters        → eliminated? → routed to gap analysis (never silently dropped)
   → 2. Per-dimension score → six scores, each 0–100
   → 3. Weighted aggregate  → overall 0–100
   → 4. Confidence level    → High / Medium / Low
   → 5. Explanation         → grounded NL (deterministic ranking, LLM explains)
```

Ranking, weighting, and tiebreaks are **deterministic Python**. The LLM is used only to *extract structured signals* from free text (feedback, profiles) and to *write* explanations — never to set a score or rank directly (see TDD §4.4).

---

# 2. Hard Filters (pass/fail, pre-scoring)

A consultant must pass **all** applicable filters to be scored. Failing candidates are not discarded — they feed gap analysis (FR-35/36).

### 2.1 Location (FR-13, FR-14) — *revised per decision 2026-06-15*
- **Non-co-located roles (Co-location = No), incl. Remote-India:** no location filter. All pass.
- **Co-located roles (Co-location = Yes): strictly local only.** Pass **only** if the consultant's normalised home location == the role's normalised city.
  - The `<City>-open` relocation column (e.g. `Chennai-open`) does **not** grant a pass to non-locals for the hard filter.
  - Relocation-willing non-locals (`<City>-open = Yes`) are **surfaced in gap analysis** as nearest alternatives when local supply is thin, with a "willing to relocate" note. This preserves FR-43 (never silently exclude).

> This supersedes the original FR-13 relocation exception. Update FR-13 in the PRD accordingly.

### 2.2 Availability (FR-15, FR-16)
Let `days_late = available_date − role_start` (negative ⇒ available before the target start).

| Supply state | `available_date` | Hard-filter rule |
|---|---|---|
| Beach | now | Always passes (available immediately). |
| New joiner | Join Date | Pass if `days_late ≤ new_joiner_buffer = 7`. |
| Rolling off — high/medium confidence | Roll-off Date | Pass if `days_late ≤ rolloff_buffer = 5`. |
| Rolling off — **low confidence** | Roll-off Date | **Always passes** (FR-16) — included with an uncertainty warning and an availability penalty (§3.3). Never eliminated on date alone. |

Medium-confidence roll-offs that pass are flagged "date uncertain" (FR-17).

---

# 3. Dimension Scores

Default weights (FR-18), configurable, must sum to 100% (FR-51):

| Dimension | Weight | Owns |
|---|---|---|
| Skill match | `w_skill = 35%` | Technical/domain fit |
| Feedback quality | `w_feedback = 25%` | **Level** of past performance |
| Availability fit | `w_avail = 15%` | How soon / how certain |
| Adaptability | `w_adapt = 15%` | **Learnability** / breadth |
| Supply state | `w_supply = 5%` | Bench vs roll-off vs joiner |
| Performance trend | `w_trend = 5%` | **Direction** of performance |

> **No double-counting (decision 2026-06-15).** Trajectory lives in exactly one place — the **performance-trend** dimension owns *direction*; feedback-quality owns *level only*; adaptability owns *learnability*. The original FR-23 ±10/−15% feedback modifier is **removed** (its role is the performance-trend dimension). Update FR-23 in the PRD accordingly.

## 3.1 Skill match (FR-19–21)

**Per-skill credit.** For each **required** skill of the role, take the *best* credit achievable across the consultant's skills, resolved in order (first hit wins):

| Match type | Credit (default, configurable) |
|---|---|
| Exact skill, proficiency meets/exceeds role requirement | `c_exact = 100` |
| Exact skill, proficiency below requirement (e.g. role wants `expert`, consultant `working`) | `c_prof = 70` |
| Adjacent skill (static map FR-20, or semantic/embedding match FR-21) | `c_adjacent = 60` |
| New-joiner unverified skill (skill present but "from CV", FR-19) | `c_newjoiner = 40` |
| No match | `0` |

- A **new joiner's** matched skills are capped at `c_newjoiner = 40` (unverified), unless corroborated by a profile/feedback source.
- Non-technical required skills (e.g. *"payments domain"*) are matched from profile/feedback **evidence** via semantic match, not only the Key Skills list.

**Aggregation (decision: mean over required + capped bonus).**
```
skill_required = mean( best_credit(s) for s in required_skills )      # missing required ⇒ 0 in the mean
skill_bonus    = min( nth_bonus_per * (# nice_to_have matched), nth_bonus_cap )
skill_score    = min(100, skill_required + skill_bonus)
```
Defaults: `nth_bonus_per = 5`, `nth_bonus_cap = 10`. Nice-to-have skills never penalise on absence (FR-04).

If the role lists **no** required skills (FR-37): attempt to infer from the title; if inference confidence < `skill_infer_min = 0.5`, **skip** this dimension and renormalise the remaining weights, with a flag in output.

## 3.2 Feedback quality (FR-22, FR-24) — hybrid

**Step 1 — LLM extraction (DSPy).** For each available source, extract a structured, grounded signal object: `{ sentiment: pos|neutral|neg, strengths[], concerns[], client_keep_signal: bool, domain_depth: bool }`. Grounded only in the source text; no inference (TDD §4.4).

**Step 2 — Deterministic scoring.** Map each source's signal to a 0–100 sub-score via a configurable rule table:
```
base by sentiment:           positive = 80, neutral = 50, negative = 20
+ strong_client_keep_signal: + kw_keep = 10   (e.g. "keep as long as possible")
+ explicit_domain_depth:     + kw_domain = 5
− material_concern:          − kw_concern = 10  (concern relevant to the role)
clamp 0..100
```
**Step 3 — Composite (FR-22):**
```
feedback_score = 0.5*project + 0.3*client + 0.2*beach
```
**Missing data (FR-24).** A missing source = `neutral_baseline = 50` (not 0) and is flagged. If **all** feedback is missing (typical for new joiners), `feedback_score = 50` with a "no feedback" flag.

## 3.3 Availability fit (FR-26) — pure days-to-available decay

```
base_avail = clamp( 100 − k * max(0, days_late), 0, 100 )
             where k = 100 / avail_horizon_days
availability_score = base_avail * (1 − rolloff_penalty[confidence])
```
Defaults: `avail_horizon_days = 30` (so 0 days late ⇒ 100; ≥30 days late ⇒ 0); consultants available on/before start (`days_late ≤ 0`, e.g. beach) ⇒ `base_avail = 100`.
Roll-off confidence penalty (FR-26), applied **only to this dimension**: `high = 0%`, `medium = 10%`, `low = 30%`.

## 3.4 Adaptability (FR-25) — hybrid

**Step 1 — LLM/NLP extraction** of four signals from profile + feedback: `tech_transitions` (distinct tech eras/stacks), `learning_speed_mentions`, `cross_domain` (distinct sectors), `upskilling` (certs, guilds, beach learning).

**Step 2 — Deterministic additive rubric:**
```
adaptability_score = clamp(
    neutral_baseline                       # 50
  + adapt_pts_transitions * has(tech_transitions ≥ 2)   # +15
  + adapt_pts_learning    * has(learning_speed_mentions) # +10
  + adapt_pts_crossdomain * has(cross_domain ≥ 2)        # +10
  + adapt_pts_upskill     * has(upskilling)              # +10
, 0, 100)
```
No evidence ⇒ stays at `neutral_baseline = 50`.

## 3.5 Supply state (FR-18) — discrete, configurable

| State | Score (default) |
|---|---|
| Beach | `supply_beach = 100` |
| Rolling off | `supply_rolloff = 70` |
| New joiner | `supply_newjoiner = 40` |

## 3.6 Performance trend (FR-18) — discrete, configurable

Direction inferred (LLM/NLP) from feedback over time and beach-feedback trajectory.

| Trend | Score (default) |
|---|---|
| Improving | `trend_improving = 100` |
| Stable | `trend_stable = 70` |
| Declining | `trend_declining = 30` |
| Unknown / no evidence | `neutral_baseline = 50` |

---

# 4. Overall Score & Tiebreaks

```
overall = Σ ( w_i * dimension_i ) / Σ w_i            # 0..100; Σw = 100 by default
```
If a dimension is skipped (e.g. FR-37 no inferable skills), its weight is removed and the remainder renormalised.

**Tiebreakers (FR-27), in order:** availability (sooner wins) → feedback confidence (more data wins) → supply state (beach > rolling off > new joiner). If still tied, list both at the same rank.

---

# 5. Confidence Level (FR-31)

| Level | Condition |
|---|---|
| **High** | ≥ 2 Parity Partners projects **and** internal feedback present **and** skills verified (profile or feedback corroborated) |
| **Medium** | exactly 1 Parity Partners project, **or** a single feedback source, **or** some unverified skills |
| **Low** | new joiner, **or** no Parity Partners feedback, **or** low-confidence profile extraction |

Low-confidence roll-offs (§2.2) additionally carry an availability-uncertainty warning regardless of level.

---

# 6. New / Changed Configurable Parameters

In addition to Appendix A of the PRD:

| Category | Parameter | Default |
|---|---|---|
| Skill | `nth_bonus_per` / `nth_bonus_cap` | 5 / 10 |
| Skill | `skill_infer_min` (title-inference confidence floor) | 0.5 |
| Feedback | sentiment bases (pos/neutral/neg) | 80 / 50 / 20 |
| Feedback | `kw_keep` / `kw_domain` / `kw_concern` | +10 / +5 / −10 |
| Availability | `avail_horizon_days` | 30 |
| Adaptability | `adapt_pts_transitions/learning/crossdomain/upskill` | 15 / 10 / 10 / 10 |
| Supply state | beach / rolloff / newjoiner | 100 / 70 / 40 |
| Performance trend | improving / stable / declining | 100 / 70 / 30 |
| Global | `neutral_baseline` (missing soft signals) | 50 |

---

# 7. Worked Example — Aarav Krishnan vs ROLE-01

**Role (ROLE-01):** Senior Backend Engineer (Kotlin) – Payments, Meridian Pay, financial services. Required: `Kotlin (expert); Spring Boot; payments domain`. Co-location **No**. Start 2026-06-22. Notes: *"Kotlin depth is the hard requirement; regulated platform."*

**Consultant (Rolling Off):** Aarav Krishnan, Lead Consultant, Bengaluru. Key Skills: Kotlin, Java, Spring Boot, Kafka, AWS. Profile proficiencies: Kotlin (expert), Java (expert), Spring Boot (expert), Kafka (working), AWS (working). Current client Meridian Pay; **Roll-off 2026-08-18, confidence low**. Feedback: *"re-architected the card-auth service in Kotlin; deep payments domain expertise. Has not worked with Terraform/IaC."* Client: *"keep Aarav as long as possible — central to the ledger rebuild."*

**Hard filters**
- Location: role is non-co-located → no filter → **pass**.
- Availability: rolling-off, **low confidence** → passes via FR-16 (with warning + penalty), although `days_late = 2026-08-18 − 2026-06-22 = 57` days is well past the 5-day buffer.

**Dimension scores**

| Dimension | Calculation | Score |
|---|---|---|
| Skill (35%) | Kotlin exp→exp = 100; Spring Boot exp ≥ req = 100; payments domain (feedback evidence) = 100 → mean = **100**; no nice-to-have | **100** |
| Feedback (25%) | project: positive + domain depth = 80+5 = 85; client: positive + keep-signal = 80+10 = 90 (capped logic) ; beach: none = 50 → 0.5·85 + 0.3·90 + 0.2·50 = 42.5+27+10 | **79.5** |
| Availability (15%) | days_late = 57 ≥ horizon 30 → base = 0; ×(1−0.30 low) | **0** |
| Adaptability (15%) | base 50 + transitions(≥2)=15 + cross-domain(payments/health/retail/public ≥2)=10 + upskilling(CKA, guilds)=10 | **85** |
| Supply state (5%) | Rolling off | **70** |
| Performance trend (5%) | Improving (cost −40%, weekly→daily deploys, mentoring) | **100** |

**Overall**
```
= 0.35·100 + 0.25·79.5 + 0.15·0 + 0.15·85 + 0.05·70 + 0.05·100
= 35 + 19.875 + 0 + 12.75 + 3.5 + 5
= 76.1 / 100
```
**Confidence:** Medium (exactly 1 Parity project + verified skills). Plus **availability-uncertainty warning** (low-confidence roll-off, ~57 days past start, client pushing to extend).

**Interpretation the tool would surface:** *Perfect skills and payments-domain fit, strong client pull — but realistically unavailable for the target start and the roll-off is unconfirmed. Strong candidate only if the start can slip or the extension falls through.* This is exactly the trade-off a human should weigh — the system ranks him on merit but makes the availability risk impossible to miss.

---

# 8. Notes for PRD/TDD sync

Applying this spec requires three edits to the PRD:
1. **FR-13** — co-location is strictly local; relocation-open non-locals move to gap analysis.
2. **FR-23** — remove the feedback trajectory modifier; trajectory is owned by the performance-trend dimension.
3. **FR-18–26 "Missing Information" note** — resolved; replace with a pointer to this spec.
