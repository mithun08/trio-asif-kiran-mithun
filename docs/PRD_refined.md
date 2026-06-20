# Demand-Supply Matcher — Product Requirements Document
**Parity Partners · Staffing Recommendation Engine**

| Field | Value |
|---|---|
| Version | 4.1 (product PRD) |
| Date | 2026-06-17 |
| Status | Draft for review |
| Companion | Technical Design Document (architecture, NFRs, security implementation, AI/LLM design) |

> **Scope of this document:** product context and **functional requirements** only. All technical design — architecture, technology stack, non-functional requirements, data storage/flow, security implementation, and AI/LLM engineering — lives in the companion **Technical Design Document (TDD)**.
>
> **Legend:** `> ⚠ Missing Information` flags gaps requiring stakeholder input.
>
> **Changes in v4.1** (team guidance 2026-06-17): output representation moves from a precise match percentage to **discrete signals + bands** (FR-30, new FR-55, AC-2, AC-9, and the band-threshold parameters). The weighted score is retained as an internal sort key only. See `SCORING_SPEC.md` §4.

---

# Executive Summary

Parity Partners staffs consultants onto client engagements through a weekly forum, today driven by a manually maintained spreadsheet. The process is slow, inconsistent, and structurally biased: familiar candidates are favoured, feedback data is ignored at decision time, supply gaps surface too late, and the reasoning behind placements is never recorded.

The Demand-Supply Matcher is a **decision-support tool** (not an automated staffing system) that produces a defensible, explainable, bias-reduced shortlist for any open role. It ingests the existing demand-supply workbook, consultant profile PDFs, and project feedback files, then ranks candidates across six weighted dimensions and explains every recommendation in natural language traceable to source data.

**v1 is a CLI tool** optimised for the weekly forum prep cycle and urgent ad-hoc fills. Success means cutting forum prep time by more than half while raising the quality and auditability of staffing decisions. The intent is explicitly to support human judgment on trade-offs — not to replace the forum or auto-assign people.

---

# Problem Statement

Parity Partners assigns consultants to client engagements via a weekly forum, currently coordinated through a spreadsheet maintained by hand. The current process suffers from the following concrete failures:

- **Visibility bias** — well-known consultants are repeatedly surfaced; others are overlooked.
- **Feedback ignored at decision time** — project and client feedback exists but is not consulted when matching.
- **Forum dynamics over merit** — group discussion and seniority can override the best objective fit.
- **Late supply-gap discovery** — unfillable roles are identified only in the forum, too late to act.
- **No institutional memory** — the reasoning behind placement decisions is not recorded or reusable.
- **Role-title nuance lost** — titles such as "AI Architect" map imperfectly to underlying needs (e.g. a Tech Lead with AI SDLC exposure).
- **Informal relationship handling** — stakeholder preferences and client sensitivities are managed ad hoc and inconsistently.

**Vision:** A decision-support tool that produces a defensible, explainable, bias-reduced shortlist for any open role, so that human judgment is applied to trade-offs rather than to searching.

> ⚠ Missing Information — **Quantified baseline.** The current cost of the problem is not quantified (e.g. average forum prep hours per week, number of open roles per cycle, current mis-placement or attrition rate). Without a baseline, the ">50% prep-time reduction" target cannot be validated.

---

# Goals and Success Metrics

## Goals

1. Produce a ranked, explainable shortlist for any open role before the weekly forum.
2. Reduce structural bias by grounding recommendations in feedback and skills data rather than visibility.
3. Surface supply gaps early, with constraint-specific explanations and nearest alternatives.
4. Establish auditable, reproducible reasoning for every recommendation.

## Success Metrics

| Metric | Target | Measurement Method |
|---|---|---|
| Shortlist generation time (single role) | < 5 s | Automated timing log |
| Batch generation time (all open roles) | < 60 s | Automated timing log |
| Forum prep time reduction | > 50% vs. baseline | Pre/post user survey + time tracking |
| Recommendation follow rate | > 60% in first quarter | Requires v2 feedback loop |
| Gap detection coverage | 100% of unfillable roles produce an explanation | Eval suite |
| Eval pass rate | 70–85% | Automated eval harness (see TDD) |
| Profile data coverage | > 90% of consultants at high/medium extraction confidence | Ingestion report |

> Performance, reliability, and other engineering targets are specified as Non-Functional Requirements in the TDD.

> ⚠ Missing Information — **Follow-rate dependency.** "Recommendation follow rate > 60%" cannot be measured in v1 because tracking outcomes is out of scope until v2. Either move this metric to v2 or define a manual interim capture method.

---

# Scope

## In Scope (v1)

- Single-role matching via CLI, by Role ID or free-text role description.
- Ranked shortlist with per-dimension band breakdown, signals-met summary, gap analysis, and natural-language reasoning.
- Configurable scoring weights, credit values, and band thresholds (no code change required).
- Batch mode generating a shortlist for every open role in the demand sheet.
- Ingestion of the demand-supply workbook (4 tabs), profile PDFs (template + free-form), and feedback Markdown files.

## Out of Scope (v1)

- Web UI or API server.
- Multi-role team formation, workforce forecasting, capacity planning.
- HRMS/ATS integration, billing/utilisation.
- Consultant-facing features.
- Tracking whether recommendations were followed (deferred to v2).
- Staffing workflow automation / auto-assignment.
- **Cross-role contention resolution.** v1 scores each (role, consultant) pair independently; if one consultant is the top candidate for two roles, v1 surfaces this but does not allocate them to one role. Contention resolution is a team-formation/portfolio-optimisation concern, deferred to v4 (see Roadmap).

---

# User Personas

| Persona | Role | Needs |
|---|---|---|
| **Staffing Manager / EM** (primary) | Prepares and runs matching | Ranked shortlist + explanation + gap alerts before the weekly forum; ad-hoc queries for urgent fills |
| **HOE / Leadership** (secondary) | Reviews and challenges decisions in forum | Defensible, explainable basis for forum decisions; ability to challenge recommendations |
| **Consultant** (future / out of scope) | Subject of matching | View own match history or skill gaps |

> ⚠ Missing Information — **CLI usability & output artifact.** A CLI-only v1 assumes the primary user is comfortable at a command line. Leadership (secondary persona) consumes the output but is unlikely to run the CLI. The output artifact (terminal text, shareable Markdown/HTML report, JSON) must be defined.

---

# Data Inputs

The functional requirements below operate on these inputs. (Storage, parsing, and data-flow design are specified in the TDD.)

## Source Files

| Source | Format | Refresh | Owner |
|---|---|---|---|
| `demand-supply.xlsx` | Excel (4 tabs) | On-demand by Staffer | Staffing manager |
| `profiles/*.pdf` | PDF (template + free-form; no password) | Per joiner / on change | HR / EM |
| `project_feedback/*.md` | Markdown, keyed by email | Per project completion | EMs |

## Open Roles Tab

| Column | Type | Notes |
|---|---|---|
| Role ID | string | Unique (e.g., ROLE-01) |
| Title | string | May imply seniority (e.g., "Senior Backend Engineer") |
| Client | string | Client organisation |
| Sector | string | Industry (e.g., financial services, retail). Soft matching signal, not a hard filter. |
| Required Skills | string | Semicolon-separated. May contain inline qualifiers: `(expert)`, `(nice to have)`. Skills marked `(nice to have)` are preferred — bonus on match, no penalty on absence. |
| Start | date | Target start date |
| Location | string | City or "Remote-India". Canonical office locations are maintained separately and may change; variants must be normalised. |
| Co-location | Yes/No | Whether the team must be physically co-located |
| Priority | High/Medium/Low | |
| Notes / Constraints | string | Critical staffing context. Must be factored into recommendation reasoning. |

## Supply Tabs (Beach / Rolling Off / New Joiners)

**Common columns across all three tabs:**

| Column | Type | Notes |
|---|---|---|
| Name | string | |
| Email | string | Primary key for cross-source joins |
| Grade | string | Senior Consultant / Lead Consultant / Principal Consultant |
| Key Skills | string | Comma-separated. On New Joiners tab, labeled "from CV" — unverified in Parity Partners context. |
| Location | string | Current city or "Remote (India)" |
| Relocation-open | Yes/No | Willingness to work on-site away from home city. Current data uses city-specific column names; system should treat generically. |
| Notes | string | Free-text context |

**Tab-specific columns:**

| Tab | Extra columns |
|---|---|
| Beach | `Days on Beach` (integer) |
| Rolling Off | `Current Client` (string), `Roll-off Date` (date), `Confidence` (low/medium/high) |
| New Joiners | `Join Date` (date) |

## Profile PDFs

Structured profiles (Parity Partners template) contain: name, grade, location, relocation flag, email, years of experience, profile summary, skills with proficiency levels (`expert` / `working`), chronological experience, selected projects, education/certifications. Free-form profiles vary. Image-only scanned PDFs may exist.

## Feedback Files

Markdown documents keyed by consultant email. Sections: project feedback (engagement review — hands-on ability, delivery, domain expertise), client feedback (direct quotes or summaries), and optionally beach feedback (trajectory observations). New joiners typically have no feedback.

---

# Functional Requirements

> FR-01 through FR-47 are carried forward from PRD v3.0; FR-48 onward were added during refinement.

### Input

| ID | Requirement |
|---|---|
| FR-01 | The system shall accept a role by Role ID from the demand sheet. |
| FR-02 | The system shall accept a role as a free-text description (e.g., "Senior backend engineer, Python, AWS, FinTech context, start July 1"). |
| FR-03 | The system shall accept a batch command that generates a shortlist for every open role in the demand sheet. |
| FR-04 | The system shall parse the Required Skills field to distinguish required skills from preferred skills marked "(nice to have)". |
| FR-05 | The system shall parse skill proficiency qualifiers (e.g., "expert") from the Required Skills field when present. |

### Data Ingestion

| ID | Requirement |
|---|---|
| FR-06 | The system shall ingest the demand-supply workbook across all four tabs (Open Roles, Beach, Rolling Off, New Joiners). |
| FR-07 | The system shall extract structured data from consultant profile PDFs, handling both the Parity Partners template and free-form formats. |
| FR-08 | The system shall extract skills with proficiency levels (e.g., "expert", "working") from profile PDFs where available. |
| FR-09 | The system shall parse feedback files and associate them with consultants by email. |
| FR-10 | The system shall flag low-confidence profile extractions rather than silently treating them as reliable. |
| FR-11 | The system shall normalise location variants to a configurable list of canonical names, covering both (a) city aliases — mapping to the canonical form used in the data, e.g. "Bangalore" → **"Bengaluru"**; and (b) remote-work forms — reconciling "Remote-India", "remote-India", and "Remote (India)" to a single canonical "Remote-India". Without (b), non-co-location handling silently misfires across tabs. |
| FR-12 | The system shall deduplicate consultant entries across supply tabs using email as the primary key. |
| FR-48 | The system shall handle image-only / scanned PDFs: either via OCR or by flagging them as unextractable and low-confidence. It shall never silently drop such profiles (links to FR-43). |
| FR-49 | The system shall report an ingestion summary per run: counts of profiles parsed, profiles flagged low-confidence, feedback files matched/unmatched, and consultants present in supply tabs without a matching profile. |
| FR-50 | The system shall detect and report consultants present in supply tabs but missing a profile PDF, and feedback files with no matching consultant email. |

### Filtering

| ID | Requirement |
|---|---|
| FR-13 | For co-located roles, the system shall pass only consultants whose home location matches the role's city (**strictly local**). Relocation-open non-locals shall not pass the hard filter but shall be surfaced in gap analysis as nearest alternatives with a "willing to relocate" note (see Scoring Spec §2.1). |
| FR-14 | The system shall not apply location filtering for non-co-location roles (including "Remote-India"). |
| FR-15 | The system shall eliminate consultants who are not available within the start date buffer: 0 days for beach, ≤5 days for rolling off (high/medium confidence), ≤7 days for new joiners. |
| FR-16 | The system shall not eliminate low-confidence roll-off consultants, but shall include them with an uncertainty warning and an availability score penalty. |
| FR-17 | The system shall flag rolling-off consultants with medium-confidence dates as uncertain in the output. |

### Ranking

| ID | Requirement |
|---|---|
| FR-18 | The system shall rank candidates using a weighted score across six dimensions: skill match (default 35%), feedback quality (25%), availability fit (15%), adaptability (15%), supply state (5%), and performance trend (5%). |
| FR-19 | The system shall score skill matches in tiers: exact match (100%), proficiency mismatch (70%), adjacent skill (60%), new joiner unverified (40%), no match (0%). All credit values must be configurable. |
| FR-20 | The system shall maintain a configurable mapping of skill synonyms and adjacency relationships (e.g., Java↔Kotlin, AWS↔Azure). |
| FR-21 | The system shall understand skill and role similarity beyond the static mapping — handling vocabulary mismatches between role descriptions and profiles (e.g., "AI Architect" ↔ "Tech Lead with AI SDLC exposure"). |
| FR-22 | The system shall compute feedback quality as a weighted composite: internal project feedback (50%), client feedback (30%), beach feedback (20%). |
| FR-23 | Trajectory shall be scored exclusively by the performance-trend dimension (FR-18); the feedback-quality dimension reflects performance *level* only. (No separate feedback trajectory modifier — avoids double-counting. See Scoring Spec §3.) |
| FR-24 | The system shall treat missing feedback as neutral (not zero) and flag the data gap in the output. |
| FR-25 | The system shall assess consultant adaptability from: historical technology transitions, feedback mentioning learning speed, cross-domain experience, and upskilling evidence from beach activities. |
| FR-26 | The system shall apply an availability score penalty based on roll-off confidence: 0% for high, 10% for medium, 30% for low. |
| FR-27 | The system shall apply tiebreakers in order: availability (sooner wins) → feedback confidence (more data wins) → supply state (beach > rolling off > new joiner). If still tied, list both at the same rank. |
| FR-28 | All scoring weights, credit values, and band thresholds must be configurable without code changes. |
| FR-51 | The system shall validate at startup that scoring dimension weights sum to 100% (or normalise them) and reject/clamp out-of-range configuration values, reporting any correction. |

> **Resolved.** The exact aggregation math for all six dimensions (skill aggregation, feedback hybrid scoring, availability decay, adaptability rubric, supply-state and performance-trend mappings), neutral baselines, banding, the internal weighted sort key, and a worked numeric example are specified in the companion **Scoring Specification** (`SCORING_SPEC.md`).

### Output & Explainability

| ID | Requirement |
|---|---|
| FR-29 | The system shall return a ranked shortlist of up to N candidates per role (default 5, configurable up to 10). |
| FR-30 | Each candidate in the shortlist shall include: per-dimension **band** (Strong / Partial / Gap) and a **signals-met summary** (e.g. "5 of 6 strong; 1 gap") as the primary breakdown, plus skills matched, skills missing or unverified, strengths, trade-offs, and a confidence level (High/Medium/Low). The numeric overall score is an internal sort key (see FR-55) and is not the headline figure. |
| FR-31 | Confidence levels shall be assigned as: High = 2+ Parity Partners projects + internal feedback + verified skills; Medium = 1 Parity Partners project, or single feedback source, or some unverified skills; Low = new joiner, no Parity Partners feedback, or low-confidence profile extraction. |
| FR-32 | The system shall generate a natural-language explanation for each recommendation, traceable to specific data points (skill evidence, feedback quotes, availability dates). |
| FR-33 | The system shall explain why a candidate was not ranked higher when relevant (e.g., missing skill, unverified experience, availability delay). |
| FR-34 | Every output shall include a snapshot timestamp indicating the data version used. |
| FR-52 | The system shall support a machine-readable output format (e.g., JSON) in addition to human-readable text, to enable the v2 feedback loop and reproducibility checks. |
| FR-54 | In batch mode, the system shall order role outputs by the role **Priority** column (High → Medium → Low) and shall flag, informationally, when a single consultant appears as a top-N candidate for more than one role (cross-role contention). Resolving contention (allocating the consultant to one role) is out of scope for v1. Priority does not otherwise affect per-role scoring or tiebreaks. |
| FR-55 | The system shall present per-candidate fit primarily as **discrete signals and bands** (Strong / Partial / Gap per dimension, plus a signals-met count), not as a precise match percentage. The weighted overall score (Scoring Spec §4.1) is used only to order candidates and shall not be surfaced as a precise figure. Exact rank order is **advisory**: minor reshuffling (e.g. #1↔#3) between runs is acceptable, since the output is a recommendation list for human review. Stability is required at the level of bands and signals, not exact position. |

### Gap Analysis

| ID | Requirement |
|---|---|
| FR-35 | The system shall never return an empty result. When no candidates pass hard filters, it shall explain which filter failed, show the bench distribution, and display nearest alternatives with the failing constraint relaxed. |
| FR-36 | When no consultant matches all required skills, the system shall show partial matches ranked by fewest gaps, with each gap explained and assessed for bridgeability using adaptability signals. |
| FR-37 | When a role has no required skills listed, the system shall attempt to infer skills from the role title. If inference confidence is low, skip skill scoring and rank on remaining dimensions. Flag in output. |

### Informational Signals

| ID | Requirement |
|---|---|
| FR-38 | The system shall flag grade mismatches between the consultant's seniority and the role title's implied seniority. This is informational, not a hard filter or scoring factor. |
| FR-39 | The system shall surface available relationship signals: stakeholder dynamics from feedback, prior experience with the same client, and client sensitivity context. These are presented for human judgment, not scored. |
| FR-40 | The system shall flag consultants on the beach for more than 60 days (configurable). This is surfaced for human judgment, not auto-penalised. |
| FR-41 | The system shall flag new joiner skills as unverified in Parity Partners context using a visual indicator in the output. |

### Data Quality & Robustness

| ID | Requirement |
|---|---|
| FR-42 | The supply sheet shall be authoritative for availability state. Contradictions with profile data shall be flagged, not resolved. |
| FR-43 | The system shall not silently exclude any consultant due to data quality issues (extraction failures, missing feedback, low-confidence profiles). |
| FR-44 | When free-text role input is ambiguous, the system shall extract what it can, surface the ambiguities with proposed defaults, and ask for confirmation before proceeding. |
| FR-45 | When a role's start date is in the past, the system shall warn that the role may be stale and proceed with matching against the current snapshot. |
| FR-46 | The system shall factor the Notes/Constraints column from the Open Roles tab into the recommendation reasoning. |
| FR-47 | The system shall use the Sector column as a soft signal when assessing consultant fit (e.g., prior experience in the same industry is a positive signal). |
| FR-53 | The system shall fail gracefully on malformed input files (missing tab, missing required column, corrupt PDF, unreadable workbook), reporting the specific file and problem rather than crashing. |

---

# User Workflows

**Workflow 1 — Pre-forum preparation (primary)**
1. Staffing Manager refreshes source files (workbook, profiles, feedback).
2. Runs batch mode for all open roles, or single-role mode per priority role.
3. System ingests data, reports ingestion summary, generates shortlists.
4. Manager reviews ranked shortlists, explanations, and gap alerts.
5. Manager brings output to the Thursday forum.

**Workflow 2 — Urgent ad-hoc fill**
1. Manager runs the matcher for a single role (by ID or free-text) on demand.
2. System returns a shortlist with availability-feasibility highlighted.
3. Manager acts immediately.

**Workflow 3 — Gap discovery**
1. Matcher run yields no candidates passing hard filters.
2. System explains which constraint failed, shows bench distribution, and lists nearest alternatives with the constraint relaxed (FR-35).
3. Manager decides on relaxation, sourcing, or deferral.

---

# Acceptance Criteria

Representative, testable criteria derived from the FRs and workflows. (Full eval suite is specified in the TDD.)

- **AC-1 (FR-01/03):** Given a valid Role ID, the CLI returns a ranked shortlist; given the batch command, it returns one shortlist per open role.
- **AC-2 (FR-29/30/55):** Each shortlist contains ≤ N candidates (default 5), each with a per-dimension band (Strong/Partial/Gap), a signals-met summary, skills matched/missing, strengths, trade-offs, and a High/Medium/Low confidence level. The numeric score is not presented as a precise match percentage.
- **AC-3 (FR-32/33):** Every recommendation includes a NL explanation citing specific data points, and explains why lower-ranked candidates ranked below higher ones where relevant.
- **AC-4 (FR-35):** For an unfillable role, output is never empty; it names the failing constraint, shows bench distribution, and lists nearest relaxed-constraint alternatives.
- **AC-5 (FR-13/14/15):** Hard filters behave exactly per buffer rules; non-co-location roles apply no location filter.
- **AC-6 (FR-10/43/48):** Low-confidence/scanned/failed extractions are flagged and never silently dropped; ingestion summary reports counts.
- **AC-7 (FR-28/51):** Changing any weight/credit/band threshold in config alters output with no code change; invalid weight sums are rejected or normalised with a reported correction.
- **AC-8 (Success Metrics):** Single-role run < 5 s; batch run < 60 s on the reference dataset.
- **AC-9 (FR-34/52/55):** Identical inputs + config produce stable **signals and bands** for each candidate (reproducibility approach defined in TDD); exact rank order is advisory and minor reshuffling is acceptable; a machine-readable output is available.
- **AC-10 (FR-44/45/53):** Ambiguous free-text prompts for confirmation; past start dates warn and proceed; malformed files produce a specific error, not a crash.

## Evaluation Expectations

The eval suite (tooling and golden dataset specified in the TDD) shall cover at least:

| Category | Example |
|---|---|
| Exact match | Java Engineer → Java Engineer role ranks #1 |
| Adjacent match | Kotlin role → Java Engineer with high adaptability ranks in top 3 |
| Negative | AI Architect role → Manual Tester does not appear in top 5 |
| Explainability | Every recommendation references specific data points |
| Gap analysis | Unfillable roles produce constraint-specific gap explanation |
| Edge cases | Stale dates flagged, extraction failures handled, ambiguous input surfaced |

Target eval pass rate: **70–85%** (100% indicates insufficient test coverage).

---

# Product Risks

(Technical and security risks are covered in the TDD.)

| # | Risk | Impact | Mitigation |
|---|---|---|---|
| PR1 | Tool reinforces existing bias via biased feedback data | High | Treat feedback as one weighted signal; surface, don't auto-decide; keep human-in-the-loop; periodic fairness review |
| PR2 | Users distrust or ignore recommendations | High | Strong explainability (FR-32/33); discrete signals over opaque percentages (FR-55); involve EMs in tuning weights; transparent gap analysis |
| PR3 | Stale / inconsistent source data drives bad recommendations | Medium | Snapshot timestamp (FR-34); stale-date warnings (FR-45); ingestion summary (FR-49) |
| PR4 | Output not actionable for non-CLI leadership audience | Medium | Define shareable output artifact (see Personas gap) |

---

# Assumptions

(Confirm each.)

1. Email is a reliable, unique identifier present across all sources.
2. The supply sheet is authoritative for availability (FR-42).
3. The primary user can operate a CLI and read its output.
4. The Parity Partners profile template is stable enough to parse reliably.
5. New joiner skills ("from CV") are unverified and should be discounted, not excluded.
6. Feedback data, where present, is honest and broadly comparable across EMs.

---

# Open Questions

1. What is the quantified baseline for forum prep time and role/consultant volume?
2. What output artifact do users need (terminal, Markdown/HTML report, JSON), and is the CLI usable for the primary persona?
3. ~~Exact scoring formulas~~ — **Resolved** in `SCORING_SPEC.md` (skill aggregation, hybrid feedback/adaptability scoring, availability decay, level mappings, banding, worked example).
4. How will the v1-unmeasurable "follow rate" metric be captured before v2?
5. Which regulatory regime applies to processing this employee performance data, and what fairness governance is required? *(compliance decision; implementation in TDD)*

---

# Configurable Parameters

All parameters below must be configurable without code changes.

| Category | Parameter | Default |
|---|---|---|
| **Matching** | Start date buffer — rolling off | 5 days |
| | Start date buffer — new joiner | 7 days |
| | Extended beach flag threshold | 60 days |
| **Scoring weights** | Skill match | 35% |
| | Feedback quality | 25% |
| | Availability fit | 15% |
| | Adaptability | 15% |
| | Supply state | 5% |
| | Performance trend | 5% |
| **Skill scoring** | Adjacent skill credit | 60% |
| | Proficiency mismatch credit | 70% |
| | New joiner verification discount | 40% |
| **Availability** | Roll-off confidence penalty — high | 0% |
| | Roll-off confidence penalty — medium | 10% |
| | Roll-off confidence penalty — low | 30% |
| **Feedback** | Internal project weight | 50% |
| | Client feedback weight | 30% |
| | Beach feedback weight | 20% |
| **Supply state** | Beach | 100 |
| | Rolling off | 70 |
| | New joiner | 40 |
| **Performance trend** | Improving | 100 |
| | Stable | 70 |
| | Declining | 30 |
| **Baselines** | Neutral baseline (missing soft signals) | 50 |
| **Output bands** | `band_strong` (Strong band floor) | 75 |
| | `band_partial` (Partial band floor) | 40 |
| **Output** | Default shortlist size | 5 |
| | Maximum shortlist size | 10 |

> The feedback trajectory modifier was removed (see FR-23) to avoid double-counting; trajectory is scored by the Performance-trend dimension above. The full scoring-parameter set (skill credits, evidence/adjacent tiers, availability decay, adaptability points, keyword weights, band thresholds) is specified in `SCORING_SPEC.md` §6.

---

# Future Roadmap

| Phase | Capability |
|---|---|
| v2 | **Feedback loop** — record which candidate was placed and why overrides happened. Enables recommendation quality tracking. |
| v2 | **Living skill matrix** — update skills from post-project feedback, beach activity, certifications instead of static profile extraction. |
| v3 | **Dynamic skill adjacency** — learn adjacency weights from placement history. |
| v3 | **Client context store** — client feedback history, stakeholder preferences, sensitivity flags. |
| v4 | **Team formation** — optimise multi-role staffing for a single engagement. |
| v5 | **Availability forecasting** — forward-looking availability timeline; proactive staffing and bench risk alerts. |
| v5 | **Portfolio optimisation** — cross-role staffing optimisation and demand forecasting. |
