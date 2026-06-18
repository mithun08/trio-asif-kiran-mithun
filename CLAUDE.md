# Demand-Supply Matcher — Claude Instructions

## Project Overview

Local CLI staffing recommendation engine. Five-stage pipeline: Ingest → Normalise → Index → Match → Explain. Deterministic scoring core; LLM only at the edges (extraction, semantic assist, explanation).

Entry point: `dsm` CLI (`src/matcher/cli.py`). Main package: `src/matcher/`.

## Commands

```bash
make install      # uv sync --extra dev
make lint         # uv run ruff check src/ tests/
make fmt          # uv run ruff format src/ tests/
make typecheck    # uv run mypy src/
make test-unit    # uv run pytest tests/unit/ -v
make test         # uv run pytest tests/ -v
uv run dsm --help
```

## Tech Stack

- **Python 3.12+**, managed by `uv` (lockfile: `uv.lock`), tool pinning via `mise`
- **Pydantic v2** for all data models — no plain dicts crossing module boundaries
- **DSPy** for all LLM interactions — typed signatures in `src/matcher/llm/modules.py`
- **Presidio + spaCy** — scrub PII before any external call (`src/matcher/privacy/scrubber.py`)
- **Milvus Lite** — vector index built at ingest, loaded at match time
- **structlog** — all observability via `src/matcher/observability/run_log.py`

## Architecture Constraints

- The LLM **never sets a rank**. Ranks come from `src/matcher/scoring/ranker.py` only.
- Each pipeline stage (`src/matcher/pipeline/`) must be independently unit-testable.
- Config is externalised in `config/default.yaml`; no magic numbers in source code.
- `data/` is gitignored — never commit source data files.
- `DSM_OPENROUTER_API_KEY` must be set via `.env` or environment; never hardcode.

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
| PII scrubber | `src/matcher/privacy/scrubber.py` |
| Run logging | `src/matcher/observability/run_log.py` |
| Scoring weights | `config/default.yaml` |
| Skill adjacency map | `config/skill_adjacency.yaml` |
| Specs | `docs/` |

## Scoring Weights (from config/default.yaml)

| Dimension | Weight |
|---|---|
| skill_match | 0.35 |
| feedback_quality | 0.25 |
| availability | 0.15 |
| adaptability | 0.15 |
| supply_state | 0.05 |
| performance_trend | 0.05 |

## Code Style

- No comments unless the WHY is non-obvious
- No docstrings unless an interface is public and non-obvious
- `from __future__ import annotations` at the top of every module
- Prefer `raise NotImplementedError` stubs over partial implementations
- All functions have typed signatures; mypy strict must pass
