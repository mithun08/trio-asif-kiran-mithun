# Slice 1 — Implementation Plan (Deterministic Core)

| Field | Value |
|---|---|
| Source | `docs/PLAN.md` §Slice 1 |
| Verified against | All source files read directly; workbook schema inspected |
| Scope | Zero LLM, zero embeddings |

---

## What the workbook actually contains

Read directly from `data/demand-supply.xlsx`. Row 1 is a title; Row 2 is headers; data starts Row 3.

**Sheet: Open Roles**
| Column | Maps to |
|---|---|
| `Role ID` | `Role.id` |
| `Title` | `Role.title` |
| `Required Skills` | `Role.required_skills` (format: `"Kotlin (expert); Spring Boot; payments domain"`) |
| `Start` | `Role.start_date` |
| `Location` | `Role.locations[0]` (normalised) |
| `Co-location` | `Role.co_located` (`"Yes"` → True) |
| `Notes / Constraints` | `Role.description` |
| `Client`, `Sector`, `Priority` | ignored in Slice 1 |

**Sheet: Beach** — supply_state = `"beach"` implicit from tab
| Column | Maps to |
|---|---|
| `Name` | `Consultant.name` |
| `Email` | `Consultant.email` |
| `Grade` | `Consultant.grade` |
| `Key Skills` | `Consultant.skills` (comma-separated, no proficiency in workbook) |
| `Location` | `Consultant.location` |
| `Notes` | `Consultant.raw_profile_text` |
| `Days on Beach`, `#` | ignored in Slice 1 |

`available_from` = None (available immediately); scored as days_late ≤ 0 → base_avail = 100.

**Sheet: Rolling Off** — supply_state = `"rolling_off"` implicit from tab
| Column | Maps to |
|---|---|
| `Name`, `Email`, `Grade`, `Key Skills`, `Location`, `Notes` | same as Beach |
| `Roll-off Date` | `Consultant.available_from` |
| `Confidence` | `Consultant.rolloff_confidence` (`"low"` / `"high"`) |
| `Current Client`, `#` | ignored in Slice 1 |

**Sheet: New Joiners** — supply_state = `"new_joiner"` implicit from tab
| Column | Maps to |
|---|---|
| `Name`, `Email`, `Grade`, `Location`, `Notes` | same as Beach |
| `Key Skills (from CV)` | `Consultant.skills` (comma-separated) |
| `Join Date` | `Consultant.available_from` |
| `#` | ignored in Slice 1 |

---

## Model changes

### `src/matcher/models/consultant.py`
Add two fields (both have defaults — existing fixtures in `conftest.py` continue to work):
```python
supply_state: Literal["beach", "rolling_off", "new_joiner"] = "beach"
rolloff_confidence: Literal["high", "medium", "low"] = "high"
```

### `src/matcher/models/role.py`
Add two fields (both have defaults):
```python
from datetime import date
co_located: bool = False
start_date: date | None = None
```

### `src/matcher/models/score.py`
Add one field to `ScoredCandidate` (needed by `rank_candidates` for the "feedback confidence" tiebreak in Slice 1; `data_confidence` flows from `Consultant`):
```python
data_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
```

### `src/matcher/models/role.py` — `RequiredSkill`
Add one field (enables the c_prof = 70 path when a role specifies a required proficiency level, e.g. `"Kotlin (expert)"`):
```python
required_proficiency: int | None = None  # 1–5 scale; None = any proficiency accepted
```

Proficiency text → int mapping used at ingest:
- `"expert"` → 5
- `"working"` / `"experienced"` / `"proficient"` → 3
- `"beginner"` / `"learning"` → 1

---

## Config changes

### `src/matcher/config.py`
Add a `ScoringConfig` model (all values configurable per FR-28/51, sourced from `config/default.yaml`):

```python
class ScoringConfig(BaseModel):
    # bands
    band_strong: float = 75.0
    band_partial: float = 40.0
    # skill credits
    c_exact: float = 100.0
    c_prof: float = 70.0
    c_adjacent: float = 60.0
    c_newjoiner: float = 40.0
    nth_bonus_per: float = 5.0
    nth_bonus_cap: float = 10.0
    # availability
    avail_horizon_days: int = 30
    rolloff_buffer: int = 5
    new_joiner_buffer: int = 7
    rolloff_penalty_high: float = 0.0
    rolloff_penalty_medium: float = 0.10
    rolloff_penalty_low: float = 0.30
    # supply scores
    supply_beach: float = 100.0
    supply_rolloff: float = 70.0
    supply_newjoiner: float = 40.0
    # neutral baseline (for Slice 2 placeholder dimensions)
    neutral_baseline: float = 50.0
```

Extend `AppConfig`:
```python
scoring_config: ScoringConfig = Field(default_factory=ScoringConfig)
```

Extend `from_yaml()` to load `scoring.config` section from YAML.

Add a standalone loader (not on `AppConfig` to keep it simple):
```python
def load_adjacency(path: Path = Path("config/skill_adjacency.yaml")) -> dict[str, list[str]]:
    ...
```

### `config/default.yaml`
Add under `scoring:`:
```yaml
scoring:
  weights:       # (already present)
    ...
  thresholds:    # (already present)
    ...
  config:
    band_strong: 75
    band_partial: 40
    c_exact: 100
    c_prof: 70
    c_adjacent: 60
    c_newjoiner: 40
    nth_bonus_per: 5
    nth_bonus_cap: 10
    avail_horizon_days: 30
    rolloff_buffer: 5
    new_joiner_buffer: 7
    rolloff_penalty_high: 0.0
    rolloff_penalty_medium: 0.10
    rolloff_penalty_low: 0.30
    supply_beach: 100
    supply_rolloff: 70
    supply_newjoiner: 40
    neutral_baseline: 50
```

### `config/skill_adjacency.yaml`
Replace empty `adjacency: {}` with seed entries (enough to make tests pass):
```yaml
adjacency:
  python: [python3, django, flask, fastapi]
  kotlin: [java, scala]
  java: [kotlin, scala, spring boot]
  aws: [gcp, azure, cloud]
  kubernetes: [k8s, docker, openshift]
  terraform: [pulumi, ansible]
  react: [vue, angular, javascript, typescript]
  postgresql: [mysql, sqlite, sql]
  kafka: [rabbitmq, activemq, sqs]
  spring boot: [spring, java ee, quarkus]
```

---

## Function signature changes

All stubs verified by direct file read. These are the actual changes needed:

| File | Current signature | New signature |
|---|---|---|
| `scoring/dimensions.py` | `score_skill_match(consultant, role)` | `score_skill_match(consultant, role, adjacency_map, config)` |
| `scoring/dimensions.py` | `score_availability(consultant, role)` | `score_availability(consultant, role, config)` |
| `scoring/dimensions.py` | `score_supply_state(consultant)` | `score_supply_state(consultant, config)` |
| `pipeline/match.py` | `match_role(role, consultants, top_n=5)` | `match_role(role, consultants, adjacency_map, config, top_n=5)` |

The three LLM-dependent stubs (`score_feedback_quality`, `score_adaptability`, `score_performance_trend`) change from `raise NotImplementedError` to returning a neutral-50 `DimensionScore` — no signature change.

`apply_hard_filters` keeps its existing `list[Consultant]` return. The filtered-out set is computed in `match_role` as `all_emails - passing_emails`.

---

## Implementation order — tests first

### Step 1 — Config validation
**File:** `tests/unit/test_config.py` (create)

Tests:
- Weights summing to 1.0 accepted; bad sum (e.g. 0.9) rejected or normalised with a correction reported
- Band thresholds in range 0–100
- Skill credits in range 0–100
- Out-of-range values clamped + reported (FR-51)

**Implement:** validators on `ScoringWeights` (sum check) and `ScoringConfig` (range checks) in `src/matcher/config.py`.

---

### Step 2 — Normalise
**File:** `tests/unit/test_normalize.py` (replace placeholder)

Tests per PLAN.md:
- `"Bangalore"` → `"Bengaluru"`
- `"Remote (India)"`, `"remote-India"`, `"Remote-India"` → one canonical form
- Duplicate emails (case-insensitive) collapse to one `Consultant` (FR-12)

**Implement:** `dedup_by_email()` and `canonicalise_locations()` in `src/matcher/pipeline/normalise.py`.

Location canonical map (hardcoded in `normalise.py` — small and stable at POC scale):
```python
_LOCATION_MAP = {
    "bangalore": "Bengaluru",
    "bengaluru": "Bengaluru",
    "remote (india)": "Remote-India",
    "remote-india": "Remote-India",
    "remote india": "Remote-India",
    "chennai": "Chennai",
    "mumbai": "Mumbai",
    "delhi": "Delhi",
    "hyderabad": "Hyderabad",
    "pune": "Pune",
}
```

---

### Step 3 — Ingest
**File:** `tests/unit/test_ingest.py` (replace placeholder)

Tests:
- `ingest_roles("demand-supply.xlsx")` → 9 roles (rows 3–11 in Open Roles tab); fields populated correctly
- `ingest_consultants_from_workbook("demand-supply.xlsx")` → consultants from all 3 supply tabs; `supply_state` set from tab name
- Missing required column → named `ValueError`, not a crash

**Implement in `src/matcher/pipeline/ingest.py`:**

```python
def ingest_roles(xlsx_path: Path) -> list[Role]:
    # Load workbook; use row 2 as headers (row 1 is title)
    # Sheet: "Open Roles"
    # Parse required_skills: split by ";", strip, extract "(proficiency)" if present
    # Parse start_date from "Start" column (ISO date string)
    # co_located: "Yes" → True, else False
    ...

def ingest_consultants_from_workbook(xlsx_path: Path) -> list[Consultant]:
    # Load all three supply tabs; set supply_state from tab name
    # Beach: available_from = None
    # Rolling Off: available_from = "Roll-off Date"; rolloff_confidence = "Confidence" column
    # New Joiners: available_from = "Join Date"; rolloff_confidence defaults to "high"
    # Skills: comma-split, strip; Skill(name=..., proficiency=3 default, years_experience=0.0)
    # Notes → raw_profile_text
    ...
```

`ingest_consultants(profiles_dir)` and `ingest_feedback(feedback_dir, consultants)` remain `raise NotImplementedError` stubs.

---

### Step 4 — Hard filters
**File:** `tests/unit/test_filters.py` (replace placeholder)

Tests per PLAN.md (verified against SCORING_SPEC.md §2):
- Beach: always passes availability
- Rolling-off high/medium: pass if `days_late ≤ 5`, fail beyond
- New joiner: pass if `days_late ≤ 7`
- Low-confidence rolloff: **always passes** (FR-16); `data_gaps` gets an "availability uncertain" warning
- Co-located role: strictly local only; non-local consultants do not pass
- Non-co-located: all consultants pass location filter

**Implement:** `apply_hard_filters(consultants, role) -> list[Consultant]` in `src/matcher/scoring/filters.py`.

`days_late` calculation:
- Beach → `days_late = 0` (always ≤ 0)
- Others → `(consultant.available_from - role.start_date).days`; if `role.start_date is None`, skip availability filter

Location match: `normalise(consultant.location) == normalise(role.locations[0])` when `role.co_located is True`.

---

### Step 5 — Skill scoring
**File:** `tests/unit/test_scoring_skill.py` (create)

Tests per PLAN.md (verified against SCORING_SPEC.md §3.1):
- Exact match, proficiency met → 100
- Exact match, proficiency below → 70 (e.g. role wants 5/expert, consultant is 3)
- Adjacent skill (via static map) → 60
- No match → 0
- Nice-to-have adds bonus up to 10; absence never penalises
- Mean over required skills; missing required = 0 in mean

**Implement:** `score_skill_match(consultant, role, adjacency_map, config) -> DimensionScore` in `src/matcher/scoring/dimensions.py`.

Algorithm:
```
for each required_skill in role.required_skills:
    find best_credit:
        check exact name match (case-insensitive):
            if required_proficiency is None or consultant_proficiency >= required_proficiency:
                credit = c_exact
            else:
                credit = c_prof
        else check adjacency_map[consultant_skill] contains required_skill (or vice versa):
            credit = c_adjacent
        else if consultant.supply_state == "new_joiner":
            credit = c_newjoiner (skill present on CV)
        else:
            credit = 0

skill_required = mean(best_credits)
skill_bonus = min(nth_bonus_per * nice_to_have_matched_count, nth_bonus_cap)
skill_score = min(100, skill_required + skill_bonus)
```

---

### Step 6 — Availability scoring
**File:** `tests/unit/test_scoring_availability.py` (create)

Tests per PLAN.md (verified against SCORING_SPEC.md §3.3):
- `days_late = 0` → 100; `days_late ≥ 30` → 0
- Low-confidence rolloff applies 30% penalty only to this dimension
- `days_late < 0` (available before start) → base_avail = 100

**Implement:** `score_availability(consultant, role, config) -> DimensionScore`.

```
if role.start_date is None:
    return neutral 50 with evidence=["no start date"]
days_late = max(0, (available_date - role.start_date).days)   # beach → 0
k = 100 / config.avail_horizon_days
base_avail = max(0.0, min(100.0, 100.0 - k * days_late))
penalty = getattr(config, f"rolloff_penalty_{consultant.rolloff_confidence}")
availability_score = base_avail * (1.0 - penalty)
```

---

### Step 7 — Supply state scoring
**File:** `tests/unit/test_scoring_supply.py` (create)

Tests: beach → 100, rolling_off → 70, new_joiner → 40.

**Implement:** `score_supply_state(consultant, config) -> DimensionScore` — pure lookup.

---

### Step 8 — Placeholder dimensions
No tests needed. Change `score_feedback_quality`, `score_adaptability`, `score_performance_trend` from `raise NotImplementedError` to:
```python
DimensionScore(
    name="feedback_quality",  # or "adaptability" / "performance_trend"
    raw_score=config.neutral_baseline,
    weight=0.25,  # from AppConfig.weights
    weighted_score=config.neutral_baseline * 0.25,
    evidence=["no data"],
)
```

---

### Step 9 — Bands and ranking
**Files:** `tests/unit/test_bands.py` (create), `tests/unit/test_rank.py` (create)

Tests per PLAN.md (verified against SCORING_SPEC.md §4.2–4.3):
- `raw_score ≥ 75` → Strong, `40–74` → Partial, `< 40` → Gap
- Signals-met count = number of Strong dimensions
- Tiebreak order: availability `raw_score` (higher = sooner) → `data_confidence` (higher = more data) → supply_state `raw_score` (100 > 70 > 40)
- Genuine ties share the same rank

**Implement:** `rank_candidates(candidates, config) -> list[ScoredCandidate]` in `src/matcher/scoring/ranker.py`.

Band helper (used by ranker and renderer):
```python
def band(score: float, config: ScoringConfig) -> str:
    if score >= config.band_strong:
        return "Strong"
    if score >= config.band_partial:
        return "Partial"
    return "Gap"
```

---

### Step 10 — Guardrails
**File:** `tests/unit/test_guardrails.py` (create)

Tests per PLAN.md:
- A consultant failing a hard filter is absent from the ranked list
- No consultant is silently dropped (FR-43) — filtered-out consultants present in output with `supply_gap_flags`
- All `DimensionScore.raw_score` values are within 0–100

**Implement:** assertions in `match_role()`.

---

### Step 11 — Match orchestration
**Implement:** `match_role(role, consultants, adjacency_map, config, top_n=5)` in `src/matcher/pipeline/match.py`:

```python
def match_role(role, consultants, adjacency_map, config, top_n=5):
    passing = apply_hard_filters(consultants, role)
    passing_emails = {c.email.lower() for c in passing}
    filtered_out = [c for c in consultants if c.email.lower() not in passing_emails]

    scored = []
    for consultant in passing:
        dims = [
            score_skill_match(consultant, role, adjacency_map, config),
            score_feedback_quality(consultant, config),   # returns neutral 50
            score_availability(consultant, role, config),
            score_adaptability(consultant, config),        # returns neutral 50
            score_supply_state(consultant, config),
            score_performance_trend(consultant, config),   # returns neutral 50
        ]
        total = sum(d.weight * d.raw_score for d in dims) / sum(d.weight for d in dims)
        assert 0.0 <= total <= 100.0
        scored.append(ScoredCandidate(
            consultant_email=consultant.email,
            consultant_name=consultant.name,
            total_score=round(total, 2),
            rank=0,  # set by rank_candidates
            dimensions=dims,
            data_confidence=consultant.data_confidence,
        ))

    ranked = rank_candidates(scored, config)[:top_n]

    # FR-43: surface filtered-out consultants in output
    gap_candidates = [
        ScoredCandidate(
            consultant_email=c.email,
            consultant_name=c.name,
            total_score=0.0,
            rank=-1,
            supply_gap_flags=c.data_gaps,  # hard filter reason appended here
        )
        for c in filtered_out
    ]
    return ranked, gap_candidates
```

---

### Step 12 — Terminal render + CLI wiring

**Create `src/matcher/render/__init__.py`** (empty)

**Create `src/matcher/render/text.py`:**
```python
def print_results(candidates, gap_candidates, config) -> None:
    # For each candidate: rank, name, per-dimension bands, signals-met summary
    # "N of 6 strong; M gap(s): (dim names)"
    # Never print a raw score or percentage
    # Gap candidates printed separately as "Filtered out (hard filter): ..."
```

**Wire `src/matcher/cli.py` `match` command:**
```python
config = AppConfig.from_yaml(Path("config/default.yaml"))
adjacency_map = load_adjacency(Path("config/skill_adjacency.yaml"))
roles = ingest_roles(config.data_dir / "demand-supply.xlsx")
role = next((r for r in roles if r.id == role_id), None)
if role is None:
    typer.echo(f"Role {role_id!r} not found.", err=True); raise typer.Exit(1)
consultants = ingest_consultants_from_workbook(config.data_dir / "demand-supply.xlsx")
consultants = dedup_by_email(canonicalise_locations(consultants))
ranked, gaps = match_role(role, consultants, adjacency_map, config.scoring_config, top_n=top_n)
print_results(ranked, gaps, config.scoring_config)
```

---

## Complete file list

| File | Action | Evidence |
|---|---|---|
| `src/matcher/models/consultant.py` | Add `supply_state`, `rolloff_confidence` | File read — fields absent |
| `src/matcher/models/role.py` | Add `co_located`, `start_date`; add `required_proficiency` to `RequiredSkill` | File read — fields absent |
| `src/matcher/models/score.py` | Add `data_confidence` to `ScoredCandidate` | File read — field absent |
| `src/matcher/config.py` | Add `ScoringConfig`, `load_adjacency()`; extend `from_yaml()` | File read — only `ScoringWeights` exists |
| `config/default.yaml` | Add `scoring.config` section | File read — section absent |
| `config/skill_adjacency.yaml` | Replace empty `adjacency: {}` with seed entries | File read — empty confirmed |
| `src/matcher/pipeline/ingest.py` | Implement `ingest_roles()`, add `ingest_consultants_from_workbook()` | File read — stubs confirmed; workbook schema read |
| `src/matcher/pipeline/normalise.py` | Implement `dedup_by_email()`, `canonicalise_locations()` | File read — stubs confirmed |
| `src/matcher/pipeline/match.py` | Implement `match_role()` with updated signature | File read — stub confirmed |
| `src/matcher/scoring/filters.py` | Implement `apply_hard_filters()` | File read — stub confirmed |
| `src/matcher/scoring/dimensions.py` | Implement 3 scorers; neutral-50 stubs for other 3 | File read — all stubs confirmed |
| `src/matcher/scoring/ranker.py` | Implement `rank_candidates()` | File read — stub confirmed |
| `src/matcher/render/__init__.py` | Create empty | Directory absent — confirmed |
| `src/matcher/render/text.py` | Create terminal renderer | Directory absent — confirmed |
| `src/matcher/cli.py` | Wire `match` command | File read — echo-only stub confirmed |
| `tests/unit/test_config.py` | Create | |
| `tests/unit/test_normalize.py` | Replace placeholder | File read — confirmed placeholder |
| `tests/unit/test_ingest.py` | Replace placeholder | File read — confirmed placeholder |
| `tests/unit/test_filters.py` | Replace placeholder | File read — confirmed placeholder |
| `tests/unit/test_scoring_skill.py` | Create | |
| `tests/unit/test_scoring_availability.py` | Create | |
| `tests/unit/test_scoring_supply.py` | Create | |
| `tests/unit/test_bands.py` | Create | |
| `tests/unit/test_rank.py` | Create | |
| `tests/unit/test_guardrails.py` | Create | |

---

## Verification

```bash
make typecheck          # mypy strict must pass (no new type errors)
make test-unit          # all 9 new test files green
make lint               # ruff clean

# Manual CLI (PLAN.md §Slice 1 manual checks)
uv run dsm match ROLE-01
uv run dsm match ROLE-01 > a.txt && uv run dsm match ROLE-01 > b.txt && diff a.txt b.txt
```

Expected from SCORING_SPEC.md §7 worked example:
- Aarav Krishnan (ROLE-01): Skill=Strong, Feedback=Partial (neutral-50 in Slice 1), Availability=**Gap** (57 days late, low-confidence), Supply=Partial, Trend=Partial (neutral-50)
- Beach consultants with matching Kotlin skills should rank above rolling-off with availability gaps
