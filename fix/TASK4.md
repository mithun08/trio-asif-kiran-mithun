# TASK4 — Model Fallback & Budget Guard

## Context

**Files**: `src/matcher/llm/client.py`, `src/matcher/pipeline/explain.py`,
`src/matcher/observability/telemetry.py`, `src/matcher/config.py`

Three verified gaps:

**Gap 1 — Fallback not wired**: `config.py:211` declares
`model_fallback: str = "anthropic/claude-3-haiku"`. `client.py:22-31` creates the primary
LM only. DSPy's `dspy.LM` has `max_retries=3` (`client.py:29`) which retries on transient
errors using the **same** model. There is no cross-model fallback.

**Gap 2 — `explain.py` bypasses `configure_lm()`**: `explain.py:21-27` constructs its own
`dspy.LM` inline:
```python
explanation_lm = dspy.LM(
    model=config.model_explain,
    api_key=config.openrouter_api_key,
    api_base="https://openrouter.ai/api/v1",
    temperature=0,
    max_retries=3,
)
```
Any fallback or budget guard added to `configure_lm()` does not cover explanation calls.
Explanation uses `model_explain = "openai/gpt-4o"` — the most expensive model in the stack.

**Gap 3 — No budget ceiling**: `telemetry.py:13-19` accumulates `total_cost_usd` and
`total_tokens` via `record_llm_call()`. `models/telemetry.py:6-11` stores these fields.
Neither enforces a ceiling. An unbounded run with 50 consultants × 6 LLM calls + N
explanation calls has no abort mechanism.

**Important interaction with TASK6 (async extraction)**: `client.py:31` uses
`dspy.configure(lm=lm)` which sets a **global mutable** DSPy LM. A naive fallback that
calls `dspy.configure(lm=fallback_lm)` on failure would race with concurrent extraction
workers. The fix is to use `dspy.context(lm=...)` for all LM calls — a context manager that
scopes the LM to the current call stack. `explain_module.py:63` already does this correctly:
`with dspy.context(lm=explanation_lm):`. This task must adopt the same pattern for
extraction calls to be safe when TASK6 adds concurrency.

---

## Implementation

### Step 1 — Change `configure_lm()` to return the primary LM (`client.py`)

Current signature: `def configure_lm(config: AppConfig) -> None`

Change to return the configured LM so callers can use `dspy.context(lm=...)` instead of
relying on the global:

```python
def configure_lm(config: AppConfig) -> dspy.LM:
    ...
    lm = dspy.LM(...)
    dspy.configure(lm=lm)  # keep for backwards compat with code not yet migrated
    return lm
```

Also create a second factory function:

```python
def make_lm(model: str, config: AppConfig) -> dspy.LM:
    """Create a dspy.LM for any model, using the same base config."""
    return dspy.LM(
        model=model,
        api_key=config.openrouter_api_key,
        api_base="https://openrouter.ai/api/v1",
        temperature=0,
        max_retries=2,
        extra_headers={"X-Title": "demand-supply-matcher"},
        extra_body={"provider": {"data_collection": config.provider.data_collection}},
    )
```

### Step 2 — Add `BudgetExceededError` to `src/matcher/models/errors.py`

```python
class BudgetExceededError(RuntimeError):
    pass
```

### Step 3 — Add budget ceiling check to `telemetry.py`

Add a function:
```python
def check_budget(max_cost_usd: float, max_tokens: int) -> None:
    """Raise BudgetExceededError if current run has exceeded configured limits."""
    from matcher.models.errors import BudgetExceededError

    if max_cost_usd > 0 and current_telemetry.total_cost_usd > max_cost_usd:
        raise BudgetExceededError(
            f"Run cost ${current_telemetry.total_cost_usd:.4f} exceeds "
            f"budget ${max_cost_usd:.4f}"
        )
    if max_tokens > 0 and current_telemetry.total_tokens > max_tokens:
        raise BudgetExceededError(
            f"Run used {current_telemetry.total_tokens} tokens, "
            f"exceeds budget {max_tokens}"
        )
```

### Step 4 — Add budget config fields to `AppConfig` (`config.py`)

Add to `AppConfig`:
```python
max_cost_usd_per_run: float = Field(default=0.0, description="0 = no limit")
max_tokens_per_run: int = Field(default=0, description="0 = no limit")
```

Add to `AppConfig.from_yaml()`:
```python
return cls(
    ...
    max_cost_usd_per_run=raw.get("budget", {}).get("max_cost_usd_per_run", 0.0),
    max_tokens_per_run=raw.get("budget", {}).get("max_tokens_per_run", 0),
)
```

Add to `config/default.yaml`:
```yaml
budget:
  max_cost_usd_per_run: 0.0   # 0 = no limit; set e.g. 1.50 to enforce $1.50 ceiling
  max_tokens_per_run: 0       # 0 = no limit
```

### Step 5 — Call budget check after each LLM call in `extract.py`

In `llm/extract.py`, after each `_tap_lm_history()` call, add:
```python
from matcher.observability.telemetry import check_budget
# after _tap_lm_history(...)
# Note: config is passed through to all extract_* functions already
_check_budget_if_configured(config)
```

Create a small helper at module level:
```python
def _check_budget_if_configured(config: ScoringConfig) -> None:
    # ScoringConfig does not carry budget; budget lives on AppConfig.
    # Budget checking in extract is done via telemetry directly.
    # Called from pipeline/extract.py which has access to AppConfig.
    pass
```

**Revised approach**: thread `AppConfig` through `extract_signals()` instead of only
`ScoringConfig`. Update `pipeline/extract.py:extract_signals()` signature:

```python
def extract_signals(
    consultants: list[Consultant],
    config: ScoringConfig,
    app_config: AppConfig | None = None,
) -> list[Consultant]:
```

After each consultant's extraction block, call:
```python
if app_config is not None:
    from matcher.observability.telemetry import check_budget
    check_budget(app_config.max_cost_usd_per_run, app_config.max_tokens_per_run)
```

Update `cli.py:114` to pass `app_config=config`.

### Step 6 — Fix `explain.py` to use `make_lm()` and add fallback

Replace `explain.py:21-27`:
```python
explanation_lm = dspy.LM(
    model=config.model_explain,
    ...
)
```
With:
```python
from matcher.llm.client import make_lm
explanation_lm = make_lm(config.model_explain, config)
fallback_lm = make_lm(config.model_fallback, config)
```

In the per-candidate loop (`explain.py:31-47`), wrap the `generate_explanation` call:
```python
try:
    updated = generate_explanation(sc, ranked_above, role, consultant, explanation_lm, ...)
except Exception:
    updated = generate_explanation(sc, ranked_above, role, consultant, fallback_lm, ...)
result.append(updated)
```

**Rationale for try/except over checking status codes**: DSPy wraps provider errors as Python
exceptions. The fallback should trigger on any LM call failure (timeout, 5xx, rate limit),
which all surface as exceptions. A second failure on the fallback model is allowed to
propagate — the `generate_explanations()` caller can choose to catch or let it surface.

### Step 7 — Wire extraction fallback in `extract.py`

For each `dspy.Predict(...)` call in `llm/extract.py`, wrap with try/fallback pattern:

```python
# Example for extract_profile:
predictor = dspy.Predict(ProfileExtraction)
try:
    with dspy.context(lm=primary_lm):
        result = predictor(raw_text=consultant.raw_profile_text)
except Exception:
    with dspy.context(lm=fallback_lm):
        result = predictor(raw_text=consultant.raw_profile_text)
```

This requires passing `primary_lm` and `fallback_lm` into the extract functions. Update
`extract_profile`, `extract_feedback`, `extract_adaptability`, `extract_trend` to accept
`lm: dspy.LM` and `fallback_lm: dspy.LM` parameters.

`pipeline/extract.py:extract_signals()` already passes `config: ScoringConfig` — extend it
to also receive `primary_lm: dspy.LM | None` and `fallback_lm: dspy.LM | None`. When `None`,
use the global DSPy LM (preserves `--no-llm` path).

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `src/matcher/llm/client.py` | 8 | Change return type to `dspy.LM`; add `make_lm()` |
| `src/matcher/models/errors.py` | end | Add `BudgetExceededError` |
| `src/matcher/observability/telemetry.py` | end | Add `check_budget()` |
| `src/matcher/config.py` | AppConfig | Add `max_cost_usd_per_run`, `max_tokens_per_run` |
| `config/default.yaml` | end | Add `budget:` section |
| `src/matcher/pipeline/explain.py` | 21-27 | Replace inline LM with `make_lm()` + fallback |
| `src/matcher/llm/extract.py` | all extract_* | Add `lm`/`fallback_lm` params, wrap with `dspy.context` |
| `src/matcher/pipeline/extract.py` | 13 | Extend signature with `app_config`, `primary_lm`, `fallback_lm` |
| `src/matcher/cli.py` | 114, 68 | Pass `app_config=config`; capture LM from `configure_lm()` |

---

## Validation & Verification

### V1 — Unit test: budget check raises when cost exceeded
```python
from matcher.observability import telemetry as _tel
from matcher.models.errors import BudgetExceededError
import pytest

def test_budget_raises_on_cost_exceeded():
    _tel.reset()
    _tel.record_llm_call("test", 1000, 2.00, False)
    with pytest.raises(BudgetExceededError):
        _tel.check_budget(max_cost_usd=1.50, max_tokens=0)

def test_budget_passes_when_zero_limit():
    _tel.reset()
    _tel.record_llm_call("test", 999999, 999.99, False)
    _tel.check_budget(max_cost_usd=0.0, max_tokens=0)  # no raise

def test_budget_raises_on_token_exceeded():
    _tel.reset()
    _tel.record_llm_call("test", 100001, 0.01, False)
    with pytest.raises(BudgetExceededError):
        _tel.check_budget(max_cost_usd=0.0, max_tokens=100000)
```

### V2 — Unit test: `configure_lm` returns a `dspy.LM` instance
```python
from unittest.mock import patch, MagicMock
def test_configure_lm_returns_lm(mock_config):
    with patch("dspy.configure"), patch("dspy.LM", return_value=MagicMock(spec=dspy.LM)) as mock:
        lm = configure_lm(mock_config)
        assert lm is not None
```

### V3 — Unit test: `make_lm` uses same base settings as `configure_lm`
```python
def test_make_lm_uses_deny_data_collection(mock_config):
    lm = make_lm("anthropic/claude-3-haiku", mock_config)
    # Verify extra_body contains data_collection deny
    # (check dspy.LM was called with the right extra_body)
```

### V4 — Unit test: `BudgetExceededError` is in errors module
```python
from matcher.models.errors import BudgetExceededError
assert issubclass(BudgetExceededError, RuntimeError)
```

### V5 — Integration: `--no-llm` path still works after signature changes
```
uv run dsm match ROLE-01 --no-llm --top 3
```
Expected: completes without error. `primary_lm=None` path is exercised.

### V6 — mypy
```
uv run mypy src/
```
Expected: no new errors (note: `dspy.*` has `ignore_missing_imports = true` in `pyproject.toml:59`).

### V7 — Full unit suite
```
uv run pytest tests/unit/ -v
```
Expected: all green.

### V8 — Config round-trip: budget section loads from YAML
```python
from matcher.config import AppConfig
from pathlib import Path
config = AppConfig.from_yaml(Path("config/default.yaml"))
assert config.max_cost_usd_per_run == 0.0
assert config.max_tokens_per_run == 0
```

---

## Acceptance Criteria

- [ ] `configure_lm()` returns `dspy.LM`; `make_lm()` added to `client.py`
- [ ] `BudgetExceededError` added to `errors.py`
- [ ] `check_budget()` added to `telemetry.py`; raises on cost OR token breach
- [ ] `config.py` has `max_cost_usd_per_run` and `max_tokens_per_run`
- [ ] `config/default.yaml` has `budget:` section with both fields defaulting to 0
- [ ] `explain.py` uses `make_lm()` and has fallback on LM failure
- [ ] All `dspy.Predict` calls in `extract.py` use `dspy.context(lm=...)` pattern
- [ ] `--no-llm` path unaffected
- [ ] V1–V4 unit tests pass
- [ ] `uv run mypy src/` passes
