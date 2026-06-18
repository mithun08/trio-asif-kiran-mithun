# Demand-Supply Matcher

A local CLI staffing recommendation engine for Parity Partners. Produces ranked, explainable shortlists matching consultants to open roles — reducing structural bias and surfacing supply gaps.

## Architecture

Five-stage pipeline: **Ingest → Normalise → Index → Match → Explain**

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
                         │     • Location canonicalisation              │
                         │     • Dedup by email                         │
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
                         │     a. Hard filters (location, availability) │
                         │     b. Skill match: static map + vector sim  │
                         │        (Milvus) + LLM judgment               │
                         │     c. Score 6 dimensions                    │
                         │     d. Rank + tiebreak                       │
                         │     e. Gap analysis if needed                │
                         └───────────────────┬─────────────────────────┘
                                             ▼
                         ┌─────────────────────────────────────────────┐
                         │  5. Explain & Render (DSPy → OpenRouter)     │
                         │     • NL explanations grounded in data       │
                         │     • Text + JSON output, snapshot timestamp │
                         └─────────────────────────────────────────────┘
```

- Deterministic scoring core (no LLM in the ranking logic)
- LLM at the edges only: PDF extraction, semantic assist, explanation generation
- Stateless per run — reads a snapshot, produces output, no mutable database

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12+ |
| Dependency management | uv |
| Tool pinning | mise |
| Data models | Pydantic v2 |
| Document extraction | Docling (PDF + OCR) |
| LLM orchestration | DSPy |
| LLM access | OpenRouter API |
| PII scrubbing | Presidio + spaCy |
| Vector store | Milvus Lite |
| Evaluation | Promptfoo + DeepEval |

## Quick Start

```bash
# Install dependencies
make install

# Ingest source files and build the vector index
dsm ingest --data-dir data/

# Match consultants for a role
dsm match "role-001" --top 5

# Emit JSON output
dsm match "Senior Python Engineer" --json
```

## Development

```bash
make install      # install all deps including dev extras
make lint         # ruff check
make fmt          # ruff format
make typecheck    # mypy strict
make test-unit    # unit tests
make test         # all tests
```

## Configuration

Edit `config/default.yaml` to adjust scoring weights, model IDs, similarity thresholds, and cache paths. All values can be overridden via environment variables prefixed with `DSM_`.

Required environment variable:

```bash
DSM_OPENROUTER_API_KEY=<your-key>
```

## Project Structure

```
src/matcher/
  cli.py            # Typer CLI entry point (dsm)
  config.py         # Pydantic settings + YAML loader
  models/           # role, consultant, score, output
  pipeline/         # ingest → normalise → index → match → explain
  scoring/          # deterministic filters + 6-dimension scorer + ranker
  llm/              # DSPy signatures and cache helpers
  privacy/          # Presidio PII scrub / rehydrate
  observability/    # structured run logging (structlog)
tests/
  unit/             # per-stage unit tests
  integration/      # end-to-end pipeline tests
  evals/            # Promptfoo scenarios + DeepEval groundedness suite
config/
  default.yaml      # scoring weights, model IDs, thresholds
  skill_adjacency.yaml  # static skill synonym map
```

## Specifications

- [Product Requirements Document](docs/PRD_refined.md)
- [Technical Design](docs/TECHNICAL_DESIGN.md)
- [Scoring Specification](docs/SCORING_SPEC.md)
