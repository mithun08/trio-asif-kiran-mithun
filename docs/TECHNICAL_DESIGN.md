# Demand-Supply Matcher — Technical Design Document
**Parity Partners · Staffing Recommendation Engine**

| Field | Value |
|---|---|
| Version | 1.1 |
| Date | 2026-06-17 |
| Status | Draft for review |
| Companion | Product Requirements Document (PRD) — `PRD_refined.md` |

> **Changes in v1.1** (per team review 2026-06-17): (1) tech stack reframed as a *toolbox* — use only what is genuinely needed, with a lean default path; (2) explicit embedding-model decision added (local `sentence-transformers`); (3) cost discipline made a first-class principle (ROI from day one; Slice-1 = zero LLM); (4) guardrails use small classifier/SLM models, not extra LLM calls, and grounding now covers extraction as well as explanation; (5) reproducibility target reframed around stable *signals/bands* rather than exact ranks.

> **Scope of this document:** all technical design — architecture, technology stack, non-functional requirements, data model/flow/storage, security & privacy implementation, AI/LLM engineering, observability, and technical risks. Product context and functional requirements (FR-xx) live in the PRD; this document references FR IDs rather than restating them.
>
> **Legend:** `> ⚠ Missing Information` flags gaps requiring stakeholder or engineering decision.

---

# 1. Architecture Overview

The Demand-Supply Matcher is a **local Python CLI application** that calls hosted LLMs via the **OpenRouter API**. It is a GenAI, retrieval-augmented decision-support tool: deterministic scoring logic is combined with LLM-based extraction, semantic matching, and explanation generation.

```
                         ┌─────────────────────────────────────────────┐
  demand-supply.xlsx ───►│  1. Ingest & Parse                           │
  profiles/*.pdf  ──────►│     • Workbook reader (Pydantic models)      │
  project_feedback/*.md ►│     • Docling PDF extraction (+ OCR)         │
                         │     • Feedback parser (keyed by email)       │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
                         │  2. Normalise & Resolve                      │
                         │     • Identity reconciliation: admit         │
                         │       orphaned profile+feedback pairs not    │
                         │       in the supply sheet, via corroborated  │
                         │       name match (Low confidence, flagged)   │
                         │     • Location canonicalisation (FR-11)      │
                         │     • Dedup by email (FR-12)                 │
                         │     • Confidence scoring + data-gap flags    │
                         │     • PII detection/scrubbing (Presidio)     │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
                         │  3. Index (one-off / on refresh)             │
                         │     • Embed skills/roles/profiles            │
                         │     • Store vectors in Milvus Lite           │
                         └───────────────────┬─────────────────────────┘
                                             ▼
  role (ID | free-text) ─►┌─────────────────────────────────────────────┐
                         │  4. Match per role                           │
                         │     a. Hard filters (FR-13..17)              │
                         │     b. Skill match: static map + vector sim  │
                         │        (Milvus) + LLM judgment (FR-19..21)   │
                         │     c. Score 6 dimensions (FR-18..27)        │
                         │     d. Rank + tiebreak (FR-27)               │
                         │     e. Gap analysis if needed (FR-35..37)    │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
                         │  5. Explain & Render (DSPy → OpenRouter)     │
                         │     • NL explanations grounded in data       │
                         │     • Text + JSON output, snapshot timestamp │
                         └─────────────────────────────────────────────┘
```

**Design principles**
- **Deterministic core, LLM at the edges.** Filtering, weighting, ranking, and tiebreaks are pure deterministic Python. The LLM is used for extraction (free-form PDFs), semantic similarity assists, ambiguity resolution, and explanation generation — never as the final arbiter of rank.
- **Stateless per run.** Each run reads a snapshot of the source files and produces output; no mutable application database in v1.
- **Pipeline stages are independently testable** (NFR-07).

---

# 2. Technology Stack

| Layer | Technology | Purpose | Primary FRs supported |
|---|---|---|---|
| Language / runtime | **Python 3.12+** | Core implementation | All |
| Dependency mgmt | **uv** | Fast, reproducible Python environments & locking | NFR-04, NFR-07 |
| Toolchain / env mgmt | **mise** (https://github.com/jdx/mise) | Pin tool & runtime versions across machines | NFR-04, NFR-07 |
| Data models & validation | **Pydantic** | Typed models for roles, consultants, profiles, scores; config schema & validation | FR-51, all data handling |
| Document extraction | **Docling** | Layout-aware PDF parsing + OCR for scanned profiles | FR-07, FR-08, FR-48 |
| LLM orchestration | **DSPy** | Prompt modules, structured outputs, prompt optimisation, response caching | FR-21, FR-32, FR-33, FR-37, FR-44 |
| LLM access | **OpenRouter API** | Hosted model access (model-agnostic routing) | FR-21, FR-32, etc. |
| PII / NLP | **Presidio + spaCy** | Detect and scrub PII before external LLM calls; NLP feature extraction | Security (§5) |
| Embedding model | **sentence-transformers** (local, e.g. `all-MiniLM-L6-v2` / `bge-small`) | Generate skill/role/profile embeddings on-device — privacy-aligned (no text leaves the machine) | FR-21, FR-36 |
| Vector store | **Milvus Lite** *(deferred)* | Embedded vector storage & semantic retrieval | FR-21, FR-36 |
| Date resolution | **dateparser** | Deterministic relative-date resolution ("in 15 days", "next month") for free-text role queries — always called with an explicit reference date, never the system clock, to preserve reproducibility (NFR-04) | FR-44 |
| Evaluation | **Promptfoo + DeepEval** *(one is sufficient to start)* | LLM eval, regression testing, quality gates | Eval suite (§6) |

> **Toolbox principle (team guidance 2026-06-17).** The stack above is a *menu, not a mandate* — adopt each tool only when it earns its place. The lean default path is: static adjacency map (no vector store) → in-memory `numpy` cosine similarity at POC scale (~50 consultants) → a single eval tool → minimal LLM orchestration (Instructor or DSPy). Milvus Lite, the second eval tool, and DSPy's prompt-optimisation are **deferred** until the simpler path proves insufficient. This keeps cost and complexity proportional to the POC.

> **Embedding generation (resolves prior gap).** The vector store was specified without naming what *produces* the vectors. Decision: generate embeddings locally with `sentence-transformers` so no profile/feedback text is sent off-device for the similarity step. Consultant vectors are precomputed at ingest; the role is embedded at query time; similarity is cosine. The resulting similarity feeds the deterministic skill scorer (FR-21 adjacent/semantic credit) — it does not set a score directly.

> ⚠ Missing Information — **OpenRouter model selection.** Specify the model(s) per task (extraction vs. reasoning vs. explanation), default model, fallback routing, and per-task token limits. See §4.

---

# 3. Non-Functional Requirements

> NFR-04 and NFR-05 are **revised** from PRD v3.0 to reflect the OpenRouter-based architecture; the original "no cloud dependencies" and absolute determinism guarantees no longer hold.

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | Single-role latency | < 5 s (see latency note below) |
| NFR-02 | Batch latency (all open roles) | < 60 s |
| NFR-03 | Data ingestion (50 profiles + feedback + XLSX), incl. extraction & embedding | < 10 minutes |
| NFR-04 *(revised)* | **Reproducibility (practical).** Given a fixed input snapshot, pinned model, `temperature=0`, and fixed config, the **signals and bands** that drive each recommendation shall be stable across runs. Exact rank order is advisory — minor reshuffling (e.g. #1↔#3) is acceptable, since the output is a recommendation list for human review, not a final decision. DSPy/response caching guarantees identical results on re-run; residual LLM variance is bounded and tolerated by the eval suite. | Stable signals/bands; exact ranks advisory; wording may vary within eval tolerance |
| NFR-05 *(revised)* | **Deployment.** Runs as a local CLI on a developer laptop. Requires outbound network access to the OpenRouter API. No self-hosted server component in v1. | Laptop + network |
| NFR-06 | Reliability / robustness — no unhandled crash on malformed input; degrade gracefully with reported errors (FR-53). Network/API failures retried with backoff, then surfaced. | — |
| NFR-07 | Maintainability — pipeline stages independently unit-testable; config externalised from code. | — |
| NFR-08 | Extensibility — new scoring dimensions, data sources, and LLM tasks addable without rewriting the core pipeline (supports v2–v5 roadmap). | — |
| NFR-09 | Observability — each run emits a structured log: inputs used, data-quality flags, per-stage timings, token/cost usage, and config version. | — |
| NFR-10 | Scalability headroom — targets defined for current volume; behaviour beyond the stated maximum must degrade predictably. | See volume note |
| NFR-11 | **Cost (ROI from day one).** LLM spend bounded per single run and per batch; embeddings cached/reused. Design so the deterministic path handles the bulk of candidates and the LLM is invoked only where unstructured input genuinely needs semantic reading. Slice-1 has **zero** LLM calls. | See cost note (§4) |

> **Latency note (NFR-01).** Per-role LLM calls for explanation generation introduce network round-trips. To meet < 5 s: precompute embeddings at ingest, cache DSPy responses, and parallelise/batch per-candidate explanation calls. Validate against the reference dataset; revise target if unachievable.

> ⚠ Missing Information — **Volume assumptions (NFR-10).** Current and projected maximum consultant count and open-role count are unspecified (NFR-03 cites 50 profiles). Required to size embedding/indexing and validate latency.

---

# 4. AI / LLM Engineering

## 4.1 Prompt & orchestration management (DSPy)
- All LLM interactions implemented as **DSPy modules** with typed signatures; prompts are versioned in code, not free-floating strings.
- Use DSPy's structured-output / typed-prediction support to return Pydantic objects (e.g. extracted profile fields, ambiguity lists, explanation blocks).
- Use DSPy **prompt optimisation** against the golden dataset to tune module prompts; pin compiled prompts for reproducibility.
- Enable **response caching** so repeated runs over an unchanged snapshot return identical results (supports NFR-04).

## 4.2 Model selection strategy
- Tasks split by capability tier: (a) **extraction** (free-form PDF → structured) — mid-tier model; (b) **semantic similarity assist / ambiguity** — mid/low tier; (c) **explanation generation** — higher-quality model for fidelity.
- OpenRouter allows model routing; pin a default per task and a fallback.

> ⚠ Missing Information — Specify the concrete model IDs, default per task, and fallback chain. Confirm whether a single model is acceptable to reduce complexity.

## 4.3 Semantic matching (Milvus Lite)
- At ingest, embed: required-skill strings, role titles/descriptions, and consultant skill/experience text.
- Skill/role similarity (FR-21) resolves in three layers, combined deterministically: (1) exact/normalised string match → (2) static synonym/adjacency map (FR-20) → (3) vector similarity from Milvus, optionally confirmed by an LLM judgment for borderline cases.
- Vector index is rebuilt on data refresh and cached between runs to meet latency targets.

> ⚠ Missing Information — **Layer precedence & thresholds.** Define which layer wins on conflict, the similarity threshold for "adjacent", and whether LLM confirmation is mandatory or only for scores near the threshold.

## 4.4 Hallucination mitigation & guardrails
- **Grounding (explanation):** explanations (FR-32) must cite specific source data points; the explanation module receives only retrieved/structured evidence, and is instructed to state "no data" rather than infer.
- **Grounding (extraction) — extended in v1.1:** LLM-*extracted* signals (sentiment, trend direction, domain-depth, adaptability flags) feed the deterministic scores and therefore influence rank, so they are guardrailed too: each extracted claim must be traceable to spans in the source text; ungrounded extractions are flagged and not scored, rather than trusted. (This closes the gap where only explanations were grounded.)
- **Separation of concerns:** the LLM never sets the numeric rank — it explains a ranking already computed deterministically, so a hallucinated explanation cannot change who is recommended.
- **Cheap input/output filtering:** sanitisation layers before and after LLM calls use **small classifier / SLM models or rules**, not additional general-LLM calls — lower latency and cost. The Presidio PII scrub (§5.1) is the canonical pre-call filter.
- **Validation:** LLM outputs are parsed into Pydantic models; parse failures trigger retry, then a flagged degradation (FR-43), never a silent guess.
- **Eval guardrails:** DeepEval checks for faithfulness/groundedness of explanations *and extractions* against source evidence (§6).

## 4.5 Cost optimisation
- **ROI from day one.** Agentic/LLM spend is under active client scrutiny; the cheapest call is the one you don't make. Slice-1 uses no LLM at all; later slices add LLM only at the extraction/explanation edges.
- Precompute and cache embeddings; reuse across runs (only re-embed changed inputs). Embeddings are generated locally (§2), so they incur no per-token API cost.
- Cache DSPy responses keyed by input snapshot + prompt version.
- Batch per-candidate explanation calls where the API permits.
- Use small classifier/SLM models for guardrail filtering rather than general-LLM calls (§4.4).
- **Token compression (later):** evaluate `Headroom` (token-compression library) *after* the eval suite exists, so any quality degradation from compression is measurable. Do not adopt before there's a baseline.
- Emit per-run token and cost telemetry (NFR-09).

> ⚠ Missing Information — **Cost ceiling.** Define max acceptable LLM spend per single run and per batch run, to drive model-tier and caching decisions.

## 4.6 Monitoring & feedback loops
- v1: structured run logs (tokens, cost, latency, data-quality flags, eval pass rate).
- v2 (roadmap): capture placement outcomes and overrides to close the quality feedback loop and enable prompt/weight re-tuning.

---

# 5. Security, Privacy & Compliance

The data handled is highly sensitive: consultant PII (names, emails, locations, grades), performance/client feedback, and client sensitivities. Because v1 sends data to a third-party LLM via OpenRouter, privacy controls are central, not optional.

## 5.1 PII handling (Presidio + spaCy)
- **Scrub-before-send:** all text destined for OpenRouter passes through a Presidio pipeline that detects and redacts/pseudonymises direct identifiers (names, emails, phone numbers) and client names.
- **Data minimisation:** only the fields required for the task are sent. Skills, anonymised experience summaries, and feedback *content* may be sent; direct identifiers and client names are scrubbed or tokenised, then re-hydrated locally for output.

> ⚠ Missing Information — **Data-minimisation policy.** Confirm the exact allow/deny field list: which attributes may leave the local environment, and which must be scrubbed (proposed default: scrub names/emails/client names; allow skills + anonymised experience + feedback text). Note: feedback text may itself contain names — Presidio must run over feedback content, not just structured fields.

## 5.2 External transmission & provider retention
- OpenRouter routes requests to third-party providers whose logging/training-retention policies vary by provider.
- **Requirement:** pin providers/models that support zero-retention / no-training, and enable OpenRouter's data-policy controls accordingly. Do not rely on scrubbing alone.

> ⚠ Missing Information — Confirm the approved provider list and required retention guarantees with security/compliance.

## 5.3 Data at rest & access control
- Source files, embeddings (Milvus Lite), caches, and generated output/snapshots contain sensitive data and must reside in an access-controlled location.
- v1 access is governed by who can run the CLI and read the source files; define the authorised user group.

> ⚠ Missing Information — **Authorization model.** Performance feedback is sensitive; not every EM should see every consultant's trajectory. Define who may run the tool and view feedback-derived output.

## 5.4 Auditability
- Snapshot timestamp (FR-34) plus persisted input snapshot and JSON output (FR-52) provide a reproducible audit trail for forum decisions.
- **✅ Resolved (2026-07-06).** Every `dsm match` run auto-persists its full JSON output to `.cache/snapshots/<timestamp>_<run_id>.json` (`observability/snapshot_archive.py`), pruned to the newest `snapshot_retention` runs (config-driven, default 50; `0` = unlimited). Each record carries both a `run_id` (unique per invocation) and a `snapshot_id` (a hash of the input data + config state — shared across runs against unchanged data), so a specific run's output and the data snapshot it was produced from are both independently addressable.

## 5.5 Compliance & fairness
- Processing employee performance data may engage data-protection obligations (e.g. India's DPDP Act; GDPR for any EU staff/clients).
- As a tool whose stated purpose is bias reduction, it must be reviewed to ensure it does not launder existing bias in feedback data (links to PRD risk PR1).

> ⚠ Missing Information — Confirm applicable regulatory regime(s) and required fairness governance.

---

# 6. Evaluation & Quality Engineering

Tooling: **DeepEval** (LLM-output quality metrics — faithfulness, relevance, groundedness) and, optionally, **Promptfoo** (prompt/scenario regression, CI gates). *One tool is sufficient to start* (toolbox principle, §2); DeepEval is the default given the groundedness focus.

- The eval categories and 70–85% pass-rate target are defined in the PRD ("Evaluation Expectations").
- DeepEval asserts **groundedness** of both explanations and LLM-extracted signals against supplied evidence (hallucination guardrail, §4.4).
- Scenario checks (exact/adjacent/negative matches, gap analysis, edge cases) run as a regression gate in CI.
- Reproducibility check: re-running the suite over a fixed snapshot yields stable **signals and bands** (NFR-04); exact rank order is not asserted.

> ⚠ Missing Information — **Golden dataset.** A labelled set of roles with expected shortlists/rankings is required; it does not yet exist. Without it the pass-rate target is unmeasurable. Define who curates it and its size.

---

# 7. Observability

Each run emits (NFR-09):
- Structured log: config version, input snapshot id/timestamp, per-stage timings.
- Data-quality report: ingestion summary (FR-49), unmatched records (FR-50), low-confidence extractions (FR-10).
- LLM telemetry: tokens and cost per task, cache hit rate, retry/failure counts.
- Eval results when run in CI.

---

# 8. Dependencies

- **Data availability & quality** — accurate, current workbook, profile PDFs, and feedback files (owners: Staffing / HR / EMs).
- **Canonical location list** — maintained externally; required for FR-11.
- **Skill adjacency / synonym map** — initial curation required for FR-20.
- **OpenRouter access** — API key, approved models, billing, and retention settings.
- **Golden dataset** — for eval (§6).
- **Stakeholder time** — to validate scoring weights, scoring formulas, and the data-minimisation policy.

> ⚠ Missing Information — **Source-file schema contract.** No defined validation ownership for the workbook/PDF templates; upstream format changes can silently break ingestion. Recommend a schema-validation step at ingest (FR-53) and a designated owner.

---

# 9. Technical Risks

| # | Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|---|
| TR1 | LLM/embedding quality insufficient for free-form PDF extraction or semantic matching | High | Medium | Docling + confidence scoring (FR-10), eval gates, human-readable flags; never silently drop (FR-43) |
| TR2 | Per-role LLM latency breaches NFR-01 | Medium | Medium | Precompute embeddings, cache responses, batch/parallelise explanations; revise target if needed |
| TR3 | PII leakage to third-party provider | High | Medium | Presidio scrub-before-send (§5.1), zero-retention providers (§5.2), data-minimisation policy |
| TR4 | LLM non-determinism breaks reproducibility | Medium | Medium | `temperature=0`, pinned model, DSPy caching, eval tolerance (NFR-04) |
| TR5 | Email join key unreliable (typos, alias, case); some people exist only as an orphaned profile PDF + feedback file, absent from the supply sheet entirely | Medium | Medium | Normalisation + unmatched-record report (FR-50); **✅ resolved (2026-07-06)** — `pipeline/reconcile.py` admits orphaned profile+feedback pairs via corroborated exact-name matching (not email alone), entering at reduced/Low confidence and flagged `admitted_external`; ambiguous names or single-source records are quarantined and surfaced, never guessed |
| TR6 | OpenRouter / network outage during forum prep | Medium | Low | Retry with backoff; cache prior results; surface clear error (no offline mode in v1) |
| TR7 | LLM cost overruns | Medium | Medium | Caching, model-tier selection, per-run cost ceiling + telemetry (§4.5) |

---

# 10. Implementation Phases

| Phase | Scope |
|---|---|
| **v1.0 – Core pipeline** | uv/mise project scaffolding; Pydantic models; workbook ingestion; Docling PDF extraction; dedup/normalisation; hard filters; deterministic 6-dimension scoring; ranked output with breakdown; snapshot timestamp. |
| **v1.1 – Semantic & explainability** | Milvus Lite embedding/index; semantic skill matching (FR-21); DSPy explanation modules via OpenRouter (FR-32/33); gap analysis (FR-35–37); confidence levels; informational signals (FR-38–41). |
| **v1.2 – Privacy, robustness & eval** | Presidio scrub-before-send; free-form/scanned PDF handling; ambiguity confirmation (FR-44); data-quality reporting; JSON output (FR-52); config validation (FR-51); Promptfoo/DeepEval suite + golden dataset; observability/telemetry. |

---

# 11. Open Technical Questions

1. **Exact scoring formulas** (skill aggregation, adaptability scoring, trajectory application) — required before the ranking engine; coordinate with Product (PRD open question 3).
2. **OpenRouter model selection** per task, defaults, fallbacks, and cost ceiling (§2, §4.2, §4.5).
3. **Data-minimisation policy** — the field-level allow/deny list for external transmission (§5.1).
4. **Provider retention guarantees** and approved provider list (§5.2).
5. **Authorization model** (§5.3) — still open. *(Snapshot retention policy, §5.4, is resolved — see §5.4.)*
6. **Semantic-match layer precedence and thresholds** (§4.3).
7. **Golden dataset** ownership, size, and labelling process (§6).
8. **Volume ceiling** for sizing and latency validation (NFR-10).
