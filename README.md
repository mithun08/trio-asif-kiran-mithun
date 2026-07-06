# Demand-Supply Matcher

A local CLI staffing recommendation engine. Produces ranked, explainable shortlists matching consultants to open roles — reducing structural bias and surfacing supply gaps.

## Architecture

Two-phase pipeline: **Ingest** (LLM-heavy, cached) → **Match** (deterministic, fast)

```
                         ┌─────────────────────────────────────────────────┐
  demand-supply.xlsx ───►│  dsm ingest                                      │
  profiles/*.pdf  ──────►│                                                  │
  project_feedback/*.md ►│  1. Ingest & Parse                               │
                         │     • Workbook reader (Pydantic models)          │
                         │     • Docling PDF extraction (+ OCR fallback)    │
                         │     • Feedback parser (keyed by email)           │
                         │                                                  │
                         │  2. Normalise                                    │
                         │     • Identity reconciliation: admits people     │
                         │       who exist only as a profile+feedback pair  │
                         │       (corroborated exact-name match), Low       │
                         │       confidence, flagged                        │
                         │     • Location canonicalisation                  │
                         │     • Dedup by email                             │
                         │     • PII scrub (Presidio — email, phone,        │
                         │       person, organisation); post-scrub gate     │
                         │                                                  │
                         │  3. Extract signals (async, concurrent)          │
                         │     • Skills, grade, location from PDF (DSPy)    │
                         │     • Sentiment, strengths, concerns from        │
                         │       feedback (DSPy)                            │
                         │     • Adaptability + performance trend (DSPy)    │
                         │     • Cross-model fallback + budget guard        │
                         │                                                  │
                         │  4. Index                                        │
                         │     • Embed skills → Milvus Lite (local)         │
                         │     • Persist extracted signals to JSON store    │
                         └───────────────────┬─────────────────────────────┘
                                             │  .cache/extracted_consultants.json
                                             │  .cache/milvus/skills.db
                                             ▼
  role (ID | free-text) ─►┌─────────────────────────────────────────────────┐
                         │  dsm match                                       │
                         │                                                  │
                         │  4b. Free-text parsing (if --free-text)          │
                         │     • LLM: skills w/ require/prefer/exclude      │
                         │       polarity, include/exclude locations,       │
                         │       exclude supply-states, relative dates      │
                         │       ("in 15 days", "ASAP") resolved            │
                         │       deterministically — never by the LLM       │
                         │     • --no-llm: regex fallback, no negation      │
                         │                                                  │
                         │  5. Match per role                               │
                         │     a. Hard filters: location, availability,     │
                         │        exclude_locations/exclude_supply_states;  │
                         │        admitted-external always fail avail.      │
                         │     b. Skill match — three tiers:                │
                         │        exact → adjacency map → vector similarity │
                         │        (excluded skills penalise, not drop)      │
                         │     c. Score 6 dimensions (weighted)             │
                         │     d. Rank + tiebreak                           │
                         │     e. Gap analysis if all filtered              │
                         │                                                  │
                         │  6. Explain (DSPy → OpenRouter)                  │
                         │     • NL explanations grounded in dimension data │
                         │     • Text + JSON output; every run persisted    │
                         │       to .cache/snapshots/ (retention-pruned)    │
                         └─────────────────────────────────────────────────┘
```

**Key invariants:**
- The LLM never sets a rank — only arithmetic scoring does. This holds for free-text negation too: the LLM parses `exclude_*` criteria, deterministic code decides drop-vs-penalty.
- `dsm ingest` is the LLM-heavy phase; `dsm match` is purely deterministic
- Unchanged consultants are skipped on re-ingest (source file hash check); raw PDF text extraction (docling/OCR) is cached independently, per-file, so unchanged profiles never re-run OCR either
- No text leaves the machine except for LLM extraction/explanation calls to OpenRouter
- PII is scrubbed before any LLM call; post-scrub assertion gate enforces fail-closed
- Date resolution in free-text queries is deterministic (`dateparser`, pinned to an explicit reference date) — never the LLM, never the system clock inside the resolver itself

## Scoring

Six weighted dimensions — all weights and thresholds live in `config/default.yaml`:

| Dimension | Weight | Notes |
|---|---|---|
| `skill_match` | 0.35 | exact (100) → adjacency map (60) → vector similarity (65) → new joiner (40); free-text `exclude` skills apply a penalty (not a hard drop) |
| `feedback_quality` | 0.25 | project (50%) + client (30%) + beach (20%) sentiment weighted average |
| `availability` | 0.15 | days-late penalty; hard-filtered at 30 days; admitted-external consultants (no real availability data) always fail this filter |
| `adaptability` | 0.15 | tech transitions, learning speed, cross-domain, upskilling signals |
| `supply_state` | 0.05 | beach (100) → rolling off (70) → new joiner (40) |
| `performance_trend` | 0.05 | improving (100) → stable (70) → declining (30) |

Bands: **Strong** ≥ 75 · **Partial** ≥ 40 · **Gap** < 40

Free-text `exclude_locations`/`exclude_supply_states` are hard filters (not scored dimensions) — a consultant matching either is dropped before scoring, regardless of the co-location setting.

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Dependency management | uv |
| Tool pinning | mise |
| Data models | Pydantic v2 |
| Document extraction | Docling (PDF + OCR); output cached per-file in `.cache/profile_text_cache.json` |
| Date resolution | `dateparser` (relative dates in free-text queries, pinned to an explicit reference date) |
| LLM orchestration | DSPy (typed signatures, disk cache, context-scoped LM) |
| LLM access | OpenRouter API |
| PII scrubbing | Presidio + spaCy (`en_core_web_sm`) |
| Embedding model | `sentence-transformers` (`all-MiniLM-L6-v2`, local) |
| Vector store | Milvus Lite (local file, no server) |
| Observability | structlog (JSONL run log), cost/token telemetry |
| Evaluation | DeepEval + Promptfoo |

## Quick Start

```bash
# Install dependencies
make install

# Set API key
export DSM_OPENROUTER_API_KEY=<your-key>

# Ingest source files, extract signals, build vector index (runs LLM calls)
dsm ingest --data-dir data/

# Match consultants for a role (deterministic — no LLM, reads from cache)
dsm match ROLE-01 --top 5

# Free-text role spec
dsm match --free-text "Senior Python engineer, London, start ASAP"

# Free-text with negation (exclude skill/location/supply-state) + relative date
dsm match --free-text "Kotlin engineer, not based in Chennai, not a new joiner, available in 15 days"

# Emit JSON output
dsm match ROLE-01 --json

# Skip explanation generation
dsm match ROLE-01 --no-explanations

# Run without any LLM calls (offline mode)
dsm ingest --no-llm
dsm match ROLE-01 --no-llm
```

## Development

```bash
make install      # uv sync --extra dev
make lint         # ruff check src/ tests/
make fmt          # ruff format src/ tests/
make typecheck    # mypy strict
make test-unit    # pytest tests/unit/
make test         # pytest tests/
make eval         # pytest tests/evals/test_deepeval_golden.py
```

Run a single test:

```bash
uv run pytest tests/unit/test_scoring.py::test_name -v
```

## Configuration

All scoring weights, model IDs, similarity thresholds, budget limits, and cache paths live in `config/default.yaml`. Values can be overridden via environment variables prefixed `DSM_`.

**Required:**

```bash
DSM_OPENROUTER_API_KEY=<your-key>
```

**Key config sections (`config/default.yaml`):**

```yaml
models:
  extraction: "openai/gpt-4o-mini"   # PDF + feedback signal extraction
  explanation: "openai/gpt-4o"       # candidate explanation generation
  fallback: "anthropic/claude-3-haiku"  # cross-model fallback on LLM failure

llm:
  max_concurrent_extractions: 5      # async extraction parallelism

budget:
  max_cost_usd_per_run: 0.0          # 0 = no limit
  max_tokens_per_run: 0              # 0 = no limit

embedding:
  model: "all-MiniLM-L6-v2"          # local sentence-transformers model

observability:
  snapshot_retention: 50              # dsm match runs to retain; 0 = unlimited

scoring:
  weights: { skill_match: 0.35, ... }
  config: { band_strong: 75, c_vector: 65, skill_exclude_penalty_per: 15, ... }
```

## Security

- **PII scrubbing**: Presidio detects and redacts email, phone, person name, and organisation before any text reaches the LLM. A post-scrub regex gate raises `ValueError` on missed patterns (fail-closed).
- **Prompt injection defence**: All DSPy extraction signatures include a `SYSTEM RULE` preamble and `[DOCUMENT START]` / `[DOCUMENT END]` boundary markers on untrusted input fields.
- **Model safety**: DSPy pickle cache is restricted (`restrict_pickle=True`). Secrets are loaded via env vars only (`secrets_dir=None`).
- **Budget guard**: `check_budget()` enforces configurable cost and token ceilings; raises `BudgetExceededError` mid-run on both sync and async extraction paths.

## Incremental Ingest

`dsm ingest` computes a SHA-256 hash (mtime + size) of each consultant's PDF and feedback files. On subsequent runs it skips unchanged consultants — only new or modified files trigger LLM re-extraction.

```bash
# Force full re-extraction (ignores hashes)
dsm ingest --force
```

The extracted signal store at `.cache/extracted_consultants.json` is a plain JSON file — human-readable and diff-able.

**Raw PDF text extraction is cached independently**, one layer below the LLM-signal store: `.cache/profile_text_cache.json` caches docling/OCR output per-file (keyed by file hash + OCR-config fingerprint), so unchanged profiles skip docling/OCR entirely on repeat runs — this is what the LLM-signal skip above doesn't cover on its own, since text extraction previously ran fresh every invocation regardless of whether the LLM re-extraction was skipped. `--force` bypasses both caches.

## Reproducibility

Every `RunOutput` includes a `snapshot_id` — a 16-character hex digest of all inputs (workbook, PDF profiles, feedback files, config YAMLs, embedding model name). Two runs on identical inputs always produce the same `snapshot_id`.

Every `dsm match` run also auto-persists its full JSON output to `.cache/snapshots/<timestamp>_<run_id>.json` (`run_id` is unique per invocation; `snapshot_id` is shared across runs against unchanged data). Pruned to the newest `observability.snapshot_retention` runs (default 50, `0` = unlimited) — no manual `--json > file` redirection needed to keep an audit trail.

## CI

GitHub Actions runs four jobs on every push:

| Job | What it checks |
|---|---|
| `lint` | `ruff check` + `ruff format --check` |
| `typecheck` | `mypy src/` (strict) |
| `unit-test` | `pytest tests/unit/` with coverage |
| `eval` | `pytest tests/evals/test_deepeval_golden.py` against synthetic golden dataset |

The eval job runs deterministic scoring only (no API key required). Pass rate must be in `[0.70, 0.85]` against the committed golden dataset at `evals/golden/roles.yaml`.

## Project Structure

```
src/matcher/
  cli.py                # Typer CLI (dsm ingest, dsm match)
  config.py             # Pydantic settings + YAML loader (AppConfig)
  models/               # role, consultant, score, signals, output, telemetry, query_spec
  pipeline/
    ingest.py           # workbook + PDF + feedback reader
    reconcile.py        # admit orphaned profile+feedback pairs via identity corroboration
    free_text_role.py   # free-text parsing: LLM negation path + regex --no-llm fallback
    normalise.py        # location canonicalisation, dedup, PII scrub
    extract.py          # async signal extraction orchestrator
    store.py            # LLM-signal JSON store + OCR-text cache (load/save/hash)
    index.py            # Milvus Lite build + load
    match.py            # hard filters → score → rank
    explain.py          # LLM explanation generation
    gap.py              # gap analysis when no candidates pass filters
  scoring/
    dimensions.py       # 6 scoring functions + 3-tier _best_credit + exclude-skill penalty
    filters.py          # hard filters (availability, location, exclude_locations/supply_states)
    ranker.py           # sort + band assignment
    confidence.py       # High / Medium / Low confidence levels
    info_flags.py       # long_bench, sector_match, grade_mismatch, skill_gap
  llm/
    modules.py          # DSPy Signature definitions (with injection defence)
    extract.py          # extract_profile, extract_feedback, extract_adaptability, extract_trend
    explain_module.py   # generate_explanation
    client.py           # make_lm, configure_lm (with fallback)
    cache.py            # DSPy disk cache config
  privacy/
    scrubber.py         # scrub_text, rehydrate_text, assert_no_residual_pii
  observability/
    run_log.py          # structlog JSONL sink
    telemetry.py        # cost/token accumulator + check_budget + cache-hit detection
    snapshot_archive.py # persist + prune RunOutput snapshots (retention policy)
    timing.py           # stage_timer context manager
    cost_table.py       # model pricing lookup
  render/
    json.py             # JSON output
    text.py             # human-readable table output
tests/
  unit/                 # per-stage unit tests (399 tests)
  integration/          # end-to-end pipeline tests
  evals/
    test_deepeval_golden.py   # golden pass-rate gate [0.70, 0.85]
    test_injection_canary.py  # static SYSTEM RULE / boundary marker checks
    test_latency_eval.py      # p95 latency guard (skipped by default)
    deepeval_suite.py         # faithfulness test case builder
config/
  default.yaml              # scoring weights, model IDs, thresholds, budget
  skill_adjacency.yaml      # static skill synonym map
evals/
  golden/roles.yaml         # synthetic golden evaluation entries
  fixtures/eval_data.xlsx   # synthetic workbook for CI eval (no real data)
scripts/
  generate_eval_fixtures.py # regenerates evals/fixtures/eval_data.xlsx
```

## Specifications

- [Product Requirements Document](docs/PRD_refined.md)
- [Technical Design](docs/TECHNICAL_DESIGN.md)
- [Scoring Specification](docs/SCORING_SPEC.md)
