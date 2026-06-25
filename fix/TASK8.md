# TASK8 — Eval-in-CI Gate

## Context

**Files**: `.github/workflows/ci.yml`, `tests/evals/test_deepeval_golden.py`,
`tests/evals/deepeval_suite.py`, `pyproject.toml`

Three verified gaps:

**Gap 1 — No eval job in CI**: `ci.yml:1-52` has three jobs: `lint`, `typecheck`,
`unit-test`. There is no eval job. The `Makefile` has an `eval` target
(`make eval` runs `pytest tests/evals/test_deepeval_golden.py`) but it is never invoked
in CI.

**Gap 2 — Golden file missing (gate trivially skips)**: `test_deepeval_golden.py:8` sets
`GOLDEN_PATH = Path("evals/golden/roles.yaml")`. `test_deepeval_golden.py:12-15`:
```python
def _entries() -> list[dict]:
    if not GOLDEN_PATH.exists():
        return []
    return (yaml.safe_load(GOLDEN_PATH.read_text()) or {}).get("entries", [])
```
If the file does not exist (it is under `evals/`, which is adjacent to `data/` — likely
gitignored), `golden_entries` is `[]`, the fixture calls `pytest.skip()`. A CI job would
always pass via skip. There is no committed synthetic golden file.

**Gap 3 — `deepeval` not confirmed in CI**: `pyproject.toml:35` shows `deepeval>=0.21` is
in `dev` extras. `ci.yml:18` runs `uv sync --extra dev`. So `deepeval` IS installed in CI.
However, `test_deepeval_golden.py:27` has `pytest.importorskip("deepeval")` — which skips
rather than fails if the import fails. This is redundant now that it's in deps, but
confirms the gate won't error if deepeval ever changes.

**Additional gap**: The existing `test_deepeval_golden.py` only tests ranking pass rate
against golden entries. It does not test:
- Explanation faithfulness (grounding in dimension scores)
- Extraction field accuracy
- p95 latency
- Cost per run

The plan calls for these thresholds — they need fixtures and tests before the CI gate is
meaningful.

---

## Implementation

### Step 1 — Create synthetic golden file `evals/golden/roles.yaml`

The golden file must use synthetic data (no real consultant data) to be safely committed.
Create `evals/golden/roles.yaml` with at least 5 entries covering all test kinds:

```yaml
# Synthetic golden dataset for CI eval gate.
# All names, emails, and role IDs are fictional.
entries:
  - role_id: "EVAL-01"
    kind: exact
    description: "Senior Python engineer — expect high-skill candidate to appear in top 3"
    expected_top_emails:
      - "alice.test@example.com"

  - role_id: "EVAL-02"
    kind: exact
    description: "Java developer — expect adjacent skills (Kotlin) to rank"
    expected_top_emails:
      - "bob.test@example.com"

  - role_id: "EVAL-03"
    kind: negative
    description: "C++ embedded role — Python-only consultants must NOT appear in top 3"
    expected_top_emails:
      - "python.only@example.com"

  - role_id: "EVAL-04"
    kind: unfillable
    description: "Requires skills with zero supply"
    expected_top_emails: []

  - role_id: "EVAL-05"
    kind: exact
    description: "Candidate with strong positive feedback should rank above equal-skill candidate"
    expected_top_emails:
      - "highfeedback.test@example.com"
```

**Note**: These entries reference synthetic role IDs. The eval test at
`test_deepeval_golden.py:55-58` skips entries where the `role_id` is not found in the
ingested roles. This means the EVAL-* IDs will be silently skipped unless they are also
added to the test workbook or a fixture workbook. See Step 2.

### Step 2 — Create a synthetic fixture workbook for CI

The current eval test (`test_deepeval_golden.py:44-48`) uses `WORKBOOK_PATH =
Path("data/demand-supply.xlsx")`. Real data cannot be committed. Options:

**Option A (preferred)**: Create a separate test workbook fixture `evals/fixtures/eval_data.xlsx`
with synthetic roles and consultants matching the golden file's EVAL-* IDs. Update
`test_deepeval_golden.py` to use `evals/fixtures/eval_data.xlsx` when `data/demand-supply.xlsx`
is absent.

**Option B**: Make `test_deepeval_golden.py` use an environment variable to locate the
workbook:
```python
WORKBOOK_PATH = Path(os.environ.get("DSM_EVAL_WORKBOOK", "data/demand-supply.xlsx"))
```
Set `DSM_EVAL_WORKBOOK=evals/fixtures/eval_data.xlsx` in the CI job.

**Recommended: Option A** — the CI job should not depend on environment variables to find
test fixtures. The fixture workbook is committed alongside the golden YAML.

Create `evals/fixtures/eval_data.xlsx` as a minimal Excel file with:
- A `Roles` sheet with EVAL-01 through EVAL-05 role definitions
- A `Supply` sheet with synthetic consultant records whose emails match the golden file

Use `openpyxl` to generate this file programmatically in a script:
`scripts/generate_eval_fixtures.py` — run once, commit the output.

### Step 3 — Add a p95 latency eval test

Create `tests/evals/test_latency_eval.py`:

```python
from __future__ import annotations

import time
import statistics
import pytest
from pathlib import Path


@pytest.mark.skip(reason="requires real data — run with DSM_EVAL_WORKBOOK set")
def test_match_p95_latency_under_threshold() -> None:
    """p95 latency for dsm match (no LLM) must be under 500ms for 10 roles."""
    from matcher.config import AppConfig, load_adjacency
    from matcher.pipeline.ingest import (
        ingest_consultants_from_workbook,
        ingest_roles,
    )
    from matcher.pipeline.match import match_role
    from matcher.pipeline.normalise import canonicalise_locations, dedup_by_email, scrub_pii

    config = AppConfig.from_yaml(Path("config/default.yaml"))
    adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))
    workbook = config.data_dir / "demand-supply.xlsx"

    roles = ingest_roles(workbook)
    consultants = ingest_consultants_from_workbook(workbook)
    consultants = canonicalise_locations(consultants)
    consultants = dedup_by_email(consultants)
    consultants = scrub_pii(consultants)

    latencies: list[float] = []
    for role in roles[:10]:
        t0 = time.perf_counter()
        match_role(role, consultants, adjacency_map, config.weights, config.scoring_config)
        latencies.append((time.perf_counter() - t0) * 1000)

    p95 = statistics.quantiles(latencies, n=20)[18]
    assert p95 < 500, f"p95 latency {p95:.0f}ms exceeds 500ms threshold"
```

This test is marked `skip` by default — it runs only when explicitly called or in a
nightly CI job with real data. The threshold (500ms p95 for no-LLM match) is deterministic
scoring only — achievable without network calls.

### Step 4 — Add explanation faithfulness eval to `deepeval_suite.py`

Populate `tests/evals/deepeval_suite.py` (currently empty, `deepeval_suite.py:1-4`):

```python
from __future__ import annotations

from typing import Any


def build_faithfulness_test_cases(
    candidates: list[Any],
    consultants: list[Any],
) -> list[Any]:
    """Build DeepEval LLMTestCase objects for explanation faithfulness."""
    try:
        from deepeval.test_case import LLMTestCase
    except ImportError:
        return []

    cases = []
    for sc in candidates:
        if not sc.explanation:
            continue
        dim_texts = [f"{d.name}: {d.raw_score:.1f}" for d in sc.dimensions]
        context = " | ".join(dim_texts)
        cases.append(
            LLMTestCase(
                input=context,
                actual_output=sc.explanation,
                expected_output="",
                context=[context],
            )
        )
    return cases
```

### Step 5 — Add eval job to `ci.yml`

Add a new job after `unit-test`:

```yaml
  eval:
    runs-on: ubuntu-latest
    needs: [unit-test]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v4
        with:
          enable-cache: true
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: uv sync --extra dev
      - name: Download spaCy model
        run: uv run python -m spacy download en_core_web_sm
      - name: Run eval suite
        run: uv run pytest tests/evals/test_deepeval_golden.py -v
        env:
          DSM_EVAL_WORKBOOK: evals/fixtures/eval_data.xlsx
```

**Rationale for `needs: [unit-test]`**: The eval job exercises the full pipeline stack. If
unit tests fail, the eval is likely to fail for unrelated reasons. Sequencing avoids noise.

**Why no `DSM_OPENROUTER_API_KEY`**: The eval job runs `--no-llm` implicitly (no key set,
so `configure_lm()` would fail if called). The golden eval test does not call LLM — it only
runs deterministic scoring. Explanation faithfulness tests (Step 4) are separate and can be
gated behind a key.

### Step 6 — Define regression snapshot

Add a comment block at the top of `tests/evals/test_deepeval_golden.py` documenting the
thresholds and the rationale:

```python
# Eval pass rate thresholds (test_deepeval_golden.py:89-94):
# - Minimum: 0.70 (below this = pipeline broken or golden set too hard)
# - Maximum: 0.85 (above this = golden set not discriminating enough, add negatives)
# These thresholds are calibrated against the synthetic fixture set in evals/fixtures/.
# When adding new golden entries, keep the pass rate in the [0.70, 0.85] window.
```

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `evals/golden/roles.yaml` | new | Synthetic golden entries (5 initial) |
| `evals/fixtures/eval_data.xlsx` | new | Synthetic fixture workbook matching golden IDs |
| `scripts/generate_eval_fixtures.py` | new | Script to regenerate fixture workbook |
| `tests/evals/test_deepeval_golden.py` | 8, 44 | Update paths to use fixture workbook when real data absent |
| `tests/evals/test_latency_eval.py` | new | p95 latency eval test (skipped by default) |
| `tests/evals/deepeval_suite.py` | full | Populate faithfulness test case builder |
| `.github/workflows/ci.yml` | end | Add `eval` job |

---

## Validation & Verification

### V1 — Static: golden file exists and is valid YAML

```bash
python -c "import yaml; data = yaml.safe_load(open('evals/golden/roles.yaml')); print(len(data['entries']), 'entries')"
```
Expected output: `5 entries` (or more).

### V2 — Static: golden entries cover all three `kind` values

```bash
python -c "
import yaml
entries = yaml.safe_load(open('evals/golden/roles.yaml'))['entries']
kinds = {e['kind'] for e in entries}
assert 'exact' in kinds, 'missing exact'
assert 'negative' in kinds, 'missing negative'
assert 'unfillable' in kinds, 'missing unfillable'
print('OK:', kinds)
"
```

### V3 — Local eval run passes before wiring into CI

```
uv run pytest tests/evals/test_deepeval_golden.py -v
```
Expected: test runs (not skipped), pass rate in [0.70, 0.85].

### V4 — Local eval run does NOT call any LLM

Run with no `DSM_OPENROUTER_API_KEY` set:
```
DSM_OPENROUTER_API_KEY="" uv run pytest tests/evals/test_deepeval_golden.py -v
```
Expected: passes (eval test uses deterministic scoring only).

### V5 — CI job added and syntactically valid

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"
```
Expected: no exception (valid YAML).

### V6 — Confirm `deepeval` import works

```bash
uv run python -c "import deepeval; print(deepeval.__version__)"
```
Expected: version string, no ImportError.

### V7 — Confirm `pytest.skip` is NOT triggered on CI (golden file present)

After Step 2 (fixture workbook created), run:
```
uv run pytest tests/evals/test_deepeval_golden.py -v --no-header 2>&1 | grep -v "SKIP"
```
Expected: output shows `PASSED` not `SKIPPED`.

### V8 — Full unit suite unaffected

```
uv run pytest tests/unit/ -v
```
Expected: all green. No changes to unit test code.

---

## Acceptance Criteria

- [ ] `evals/golden/roles.yaml` committed with ≥5 entries covering all three kinds
- [ ] `evals/fixtures/eval_data.xlsx` committed with matching synthetic data
- [ ] `test_deepeval_golden.py` does NOT skip when run locally with fixture workbook
- [ ] Eval pass rate is in [0.70, 0.85] range with the synthetic dataset
- [ ] `ci.yml` has an `eval` job that runs after `unit-test`
- [ ] CI eval job does not require `DSM_OPENROUTER_API_KEY`
- [ ] `deepeval_suite.py` populated with faithfulness test case builder
- [ ] `test_latency_eval.py` exists (skipped by default, documented threshold 500ms p95)
- [ ] V1–V7 checks pass
- [ ] `uv run pytest tests/unit/ -v` all green
