# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Demand-Supply Matcher — Claude Instructions

## Project Overview

Local CLI staffing recommendation engine. Five-stage pipeline: Ingest → Normalise → Index → Match → Explain. Deterministic scoring core; LLM only at the edges (extraction, semantic assist, explanation).

Entry point: `dsm` CLI (`src/matcher/cli.py`). Main package: `src/matcher/`.

**Current state:** All five pipeline stages, all 6 scoring dimensions, the vector index (`pipeline/index.py`), and DSPy explanation generation (`pipeline/explain.py`) are implemented. Free-text queries additionally support negation (`exclude_*` on `Role`, parsed via `pipeline/free_text_role.py`'s LLM path, with a deterministic regex fallback under `--no-llm`).

## Commands

```bash
make install      # uv sync --extra dev
make lint         # uv run ruff check src/ tests/
make fmt          # uv run ruff format src/ tests/
make typecheck    # uv run mypy src/
make test-unit    # uv run pytest tests/unit/ -v
make test-int     # uv run pytest tests/integration/ -v
make test         # uv run pytest tests/ -v

# Run a single test
uv run pytest tests/unit/test_scoring.py::test_name -v

# CLI
uv run dsm match "Senior Python Engineer" --top 5
uv run dsm ingest --data-dir data/ --force
```

## Tech Stack

- **Python 3.12+**, managed by `uv` (lockfile: `uv.lock`), tool pinning via `mise`
- **Pydantic v2** for all data models — no plain dicts crossing module boundaries
- **DSPy** for all LLM interactions — typed signatures in `src/matcher/llm/modules.py`; LLM responses are cached in `.cache/dspy/`
- **docling** (+ RapidOCR fallback) — PDF profile text extraction (`pipeline/ingest.py:_extract_pdf_text`); output cached per-file in `.cache/profile_text_cache.json` (`pipeline/store.py`)
- **dateparser** — deterministic relative-date resolution for free-text queries (`pipeline/free_text_role.py:resolve_relative_date`), always called with an explicit `RELATIVE_BASE` — never let it read the system clock itself
- **Presidio + spaCy** — scrub PII before any external call (`src/matcher/privacy/scrubber.py`)
- **Milvus Lite** — vector index at `.cache/milvus/`, built at ingest, loaded at match time; embedding model is `all-MiniLM-L6-v2` (local, via `sentence-transformers` — no text leaves the machine)
- **structlog** — all observability via `src/matcher/observability/run_log.py`
- **deepeval + promptfoo** — LLM output eval suite in `tests/evals/`

## Architecture Constraints

- The LLM **never sets a rank**. Ranks come from `src/matcher/scoring/ranker.py` only.
- Each pipeline stage (`src/matcher/pipeline/`) must be independently unit-testable.
- Config is externalised in `config/default.yaml`; no magic numbers in source code. Load via `AppConfig.from_yaml()`.
- `data/` is gitignored — never commit source data files.
- `DSM_OPENROUTER_API_KEY` must be set via `.env` or environment; never hardcode.
- PII scrubbing (`normalise.scrub_pii`) must run before any consultant data is passed to LLM calls.

## Data Flow

```
data/roles.xlsx        → ingest.ingest_roles()       → list[Role]
data/profiles/*.pdf    → ingest.ingest_consultants()  → list[Consultant]
data/feedback/*.md     → ingest.ingest_feedback()     → list[Consultant] (enriched)
                          reconcile.reconcile_external_people(): admits people who
                          exist only as an orphaned profile+feedback pair (identity
                          corroboration, exact-name match), Low confidence, flagged
                          normalise: dedup, canonicalise locations, scrub PII
                          index: embed + store in Milvus Lite
dsm match <role>       → free_text_role.parse() if --free-text (LLM: exclude_* negation;
                          --no-llm: deterministic regex fallback, no negation)
                          filters.apply_hard_filters(): availability, location/supply-state
                          exclusion, admitted-external held out of availability filter
                          dimensions.score_*() × 6 (skill_match penalises exclude_skills)
                          ranker.rank_candidates()
                          explain.generate_explanations() via DSPy → OpenRouter
                       → list[ScoredCandidate], auto-persisted to .cache/snapshots/
```

## Key File Locations

| Concern | File |
|---|---|
| CLI commands | `src/matcher/cli.py` |
| App config / env vars | `src/matcher/config.py` |
| Pydantic models | `src/matcher/models/` |
| Pipeline stages | `src/matcher/pipeline/` |
| Scoring dimensions (6) | `src/matcher/scoring/dimensions.py` |
| Hard filters | `src/matcher/scoring/filters.py` |
| DSPy signatures | `src/matcher/llm/modules.py` |
| Free-text query parsing (negation, dates) | `src/matcher/pipeline/free_text_role.py` |
| Identity reconciliation (orphaned profile+feedback) | `src/matcher/pipeline/reconcile.py` |
| PII scrubber | `src/matcher/privacy/scrubber.py` |
| Run logging | `src/matcher/observability/run_log.py` |
| Snapshot archive (retention policy) | `src/matcher/observability/snapshot_archive.py` |
| LLM-signal + OCR-text caches | `src/matcher/pipeline/store.py` |
| Scoring weights | `config/default.yaml` |
| Skill adjacency map | `config/skill_adjacency.yaml` |
| Specs | `docs/` |
| Shared test fixtures | `tests/conftest.py` |

## Scoring

Weights and thresholds all live in `config/default.yaml` — never hardcode them.

| Dimension | Weight | Notes |
|---|---|---|
| skill_match | 0.35 | exact → adjacent (0.70) → vector similarity (0.65); `Role.exclude_skills` applies a penalty (`skill_exclude_penalty_per`/`_cap`), not a hard drop |
| feedback_quality | 0.25 | |
| availability | 0.15 | hard filter at 30 days; admitted-external consultants always fail this filter (no real availability data) |
| adaptability | 0.15 | |
| supply_state | 0.05 | |
| performance_trend | 0.05 | |

`Role.exclude_locations`/`exclude_supply_states` (from free-text negation) are hard filters in `scoring/filters.py`, not scored dimensions.

## Code Style

- No comments unless the WHY is non-obvious
- No docstrings unless an interface is public and non-obvious
- `from __future__ import annotations` at the top of every module
- Prefer `raise NotImplementedError` stubs over partial implementations
- All functions have typed signatures; mypy strict must pass
