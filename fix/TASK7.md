# TASK7 — Vector Index & Skill Matching (Embedding Tier)

## Context

**Files**: `src/matcher/pipeline/index.py`, `src/matcher/scoring/dimensions.py`,
`src/matcher/config.py`, `config/default.yaml`

Three verified gaps:

**Gap 1 — Stubs**: `index.py:10-17` — both `build_index()` and `load_index()` raise
`NotImplementedError`.

**Gap 2 — Third scoring tier missing**: `dimensions.py:9-27` `_best_credit()` chain:
exact → adjacency → `c_newjoiner` (if new joiner) → 0.0. The config key
`skill_vector_similarity: 0.65` exists in `config/default.yaml:13` but the code never reads
it. A required skill that is neither exact nor adjacent to any consultant skill always returns
0.0 — even if the consultant has a semantically close skill.

**Gap 3 — Config model gap (plan missed this)**: `skill_vector_similarity` lives under
YAML path `scoring.thresholds` (`default.yaml:13`), but `AppConfig.from_yaml()` only reads
`scoring.config` into `ScoringConfig` (`config.py:240-242`). `ScoringConfig` (`config.py:36`)
has no `skill_vector_similarity` field. Implementing the vector tier requires adding the field
to `ScoringConfig` AND updating `from_yaml()` to read from `scoring.thresholds` — not just
implementing the index.

**Dependencies**: This task is independent of TASK5/TASK6 but benefits from TASK4's
`dspy.context` pattern being in place (embedding runs offline, no LLM, but structural
consistency matters). Can be implemented in parallel with TASK4–TASK6.

**Stack**: `pymilvus[model]>=2.4` and `sentence-transformers>=2.7` are already in
`pyproject.toml:17-18`. The embedding model `all-MiniLM-L6-v2` is documented in
`config/default.yaml:73`. No new dependencies required.

---

## Implementation

### Step 1 — Fix the config model gap

**In `src/matcher/config.py`**, add `skill_vector_similarity` to `ScoringConfig`:

```python
class ScoringConfig(BaseModel):
    ...
    skill_vector_similarity: float = 0.65
```

Add a validator alongside other credit validators:
```python
@field_validator("skill_vector_similarity", mode="before")
@classmethod
def _clamp_vector_sim(cls, v: object, info: Any) -> float:
    return _clamp(v, 0.0, 1.0, info.field_name)
```

Also add `c_vector: float = 65.0` to `ScoringConfig` — this is the credit value awarded
when a skill match is found via vector similarity. The existing `c_adjacent = 60.0` provides
the reference: vector similarity should award slightly more than adjacency (65.0) but less
than exact (100.0), reflecting that semantic proximity is less reliable than declared
adjacency.

```python
c_vector: float = 65.0
```

**In `AppConfig.from_yaml()`**, extend the `scoring` section reading to include thresholds:

```python
thresholds_data = scoring.get("thresholds", {})
return cls(
    ...
    scoring_config=ScoringConfig(
        **config_data,
        skill_vector_similarity=thresholds_data.get("skill_vector_similarity", 0.65),
    ) if (config_data or thresholds_data) else ScoringConfig(),
)
```

**In `config/default.yaml`**, move `skill_vector_similarity` from `scoring.thresholds` into
`scoring.config` to unify the config section (thresholds section becomes unused):

```yaml
scoring:
  config:
    ...
    skill_vector_similarity: 0.65
    c_vector: 65
```

### Step 2 — Implement `build_index()` in `pipeline/index.py`

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

from pymilvus import MilvusClient
from sentence_transformers import SentenceTransformer

from matcher.models.consultant import Consultant
from matcher.models.role import Role

_MODEL_NAME = "all-MiniLM-L6-v2"
_COLLECTION = "skill_embeddings"
_DIM = 384  # all-MiniLM-L6-v2 output dimension


def build_index(consultants: list[Consultant], roles: list[Role], index_dir: Path) -> None:
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(index_dir / "skills.db")

    model = SentenceTransformer(_MODEL_NAME)
    client = MilvusClient(db_path)

    if client.has_collection(_COLLECTION):
        client.drop_collection(_COLLECTION)

    client.create_collection(
        collection_name=_COLLECTION,
        dimension=_DIM,
    )

    rows: list[dict[str, Any]] = []
    for consultant in consultants:
        for skill in consultant.skills:
            rows.append({
                "id": len(rows),
                "consultant_email": consultant.email,
                "skill_name": skill.name,
                "vector": model.encode(skill.name.lower()).tolist(),
            })

    if rows:
        client.insert(collection_name=_COLLECTION, data=rows)


def load_index(index_dir: Path) -> MilvusClient | None:
    db_path = index_dir / "skills.db"
    if not db_path.exists():
        return None
    client = MilvusClient(str(db_path))
    if not client.has_collection(_COLLECTION):
        return None
    return client
```

**Rationale for MilvusClient (Lite) over full Milvus**: `MilvusClient` with a file path
uses Milvus Lite, which stores the index as a local SQLite-backed file. No separate Milvus
server process. Already in `pyproject.toml:17` as `pymilvus[model]>=2.4`. The index is
built once during `dsm ingest` and loaded read-only during `dsm match`.

**Rationale for dropping and rebuilding the collection**: Incremental vector updates to
Milvus Lite require explicit ID management. For a corpus of 50 consultants with potentially
hundreds of skills, a full rebuild takes <1 second. Simpler, no partial-update bugs.

### Step 3 — Extend `_best_credit()` in `dimensions.py` with vector tier

```python
def _best_credit(
    req: RequiredSkill,
    consultant: Consultant,
    adjacency_map: dict[str, list[str]],
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
) -> float:
    req_name = req.name.casefold()

    # Tier 1: exact match
    for skill in consultant.skills:
        s_name = skill.name.casefold()
        if s_name == req_name:
            if req.required_proficiency is None or skill.proficiency >= req.required_proficiency:
                return config.c_exact
            return config.c_prof

    # Tier 2: adjacency map match
    for skill in consultant.skills:
        s_name = skill.name.casefold()
        adjacents = adjacency_map.get(s_name, []) + adjacency_map.get(req_name, [])
        if req_name in adjacents or s_name in adjacents:
            return config.c_adjacent

    # Tier 3: vector similarity (only if index is available)
    if index_client is not None and embedding_model is not None:
        req_vec = embedding_model.encode(req_name).tolist()
        results = index_client.search(
            collection_name="skill_embeddings",
            data=[req_vec],
            limit=1,
            filter=f'consultant_email == "{consultant.email}"',
            output_fields=["skill_name"],
        )
        if results and results[0]:
            hit = results[0][0]
            distance = hit.get("distance", 0.0)
            if distance >= config.skill_vector_similarity:
                return config.c_vector

    if consultant.supply_state == "new_joiner":
        return config.c_newjoiner
    return 0.0
```

**Rationale for keeping `index_client=None` default**: `_best_credit()` and
`score_skill_match()` are called in unit tests without an index. The `None` default
preserves the existing two-tier behaviour and keeps all existing unit tests passing without
requiring a live Milvus instance.

### Step 4 — Thread `index_client` and `embedding_model` through `score_skill_match()`

```python
def score_skill_match(
    consultant: Consultant,
    role: Role,
    adjacency_map: dict[str, list[str]],
    weights: ScoringWeights,
    config: ScoringConfig,
    index_client: Any | None = None,
    embedding_model: Any | None = None,
) -> DimensionScore:
    ...
    credits = [
        _best_credit(rs, consultant, adjacency_map, config, index_client, embedding_model)
        for rs in mandatory
    ]
```

Update `pipeline/match.py` to pass `index_client` and `embedding_model` from whatever
calls `score_skill_match`. Verify how match is called from `pipeline/match.py`.

### Step 5 — Wire `build_index` into `dsm ingest`

After TASK5 lands, add to the `ingest` command in `cli.py`:

```python
from matcher.pipeline.index import build_index, load_index

# At end of ingest, after save_store():
build_index(all_consultants, roles, config.cache_dir / "milvus")
```

### Step 6 — Wire `load_index` into `dsm match`

In `cli.py` `match` command, after loading the store (TASK5):

```python
from matcher.pipeline.index import load_index
from sentence_transformers import SentenceTransformer

index_client = load_index(config.cache_dir / "milvus")
embedding_model = SentenceTransformer("all-MiniLM-L6-v2") if index_client is not None else None
```

Pass `index_client` and `embedding_model` through to `match_role()` → `score_skill_match()`.

---

## Files Changed

| File | Lines | Change |
|------|-------|--------|
| `src/matcher/config.py` | ScoringConfig | Add `skill_vector_similarity: float = 0.65`, `c_vector: float = 65.0`, validators |
| `src/matcher/config.py` | `from_yaml()` | Read `scoring.thresholds.skill_vector_similarity` |
| `config/default.yaml` | `scoring.config` | Add `skill_vector_similarity: 0.65`, `c_vector: 65` |
| `config/default.yaml` | `scoring.thresholds` | Keep for backwards compat or remove (document decision) |
| `src/matcher/pipeline/index.py` | full file | Implement `build_index()` and `load_index()` |
| `src/matcher/scoring/dimensions.py` | `_best_credit`, `score_skill_match` | Add vector tier; add `index_client`, `embedding_model` params |
| `src/matcher/pipeline/match.py` | `match_role` | Thread `index_client`, `embedding_model` params |
| `src/matcher/cli.py` | ingest command | Call `build_index()` at end |
| `src/matcher/cli.py` | match command | Call `load_index()`, create `SentenceTransformer` |

---

## Validation & Verification

### V1 — Unit test: `_best_credit` with no index still works (backwards compat)

```python
from matcher.scoring.dimensions import _best_credit
from matcher.models.consultant import Consultant, Skill
from matcher.models.role import RequiredSkill
from matcher.config import ScoringConfig

def test_exact_match_no_index():
    c = Consultant(email="a@b.com", name="A", skills=[Skill(name="Python")])
    req = RequiredSkill(name="Python", mandatory=True)
    assert _best_credit(req, c, {}, ScoringConfig()) == 100.0

def test_no_match_no_index_returns_zero():
    c = Consultant(email="a@b.com", name="A", skills=[Skill(name="Java")])
    req = RequiredSkill(name="Python", mandatory=True)
    assert _best_credit(req, c, {}, ScoringConfig()) == 0.0
```

### V2 — Unit test: vector tier awards `c_vector` on cosine match above threshold

```python
from unittest.mock import MagicMock

def test_vector_tier_awards_c_vector():
    mock_client = MagicMock()
    mock_client.search.return_value = [[{"distance": 0.80, "skill_name": "TypeScript"}]]
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 384

    c = Consultant(email="a@b.com", name="A", skills=[Skill(name="TypeScript")])
    req = RequiredSkill(name="JavaScript", mandatory=True)
    config = ScoringConfig()
    result = _best_credit(req, c, {}, config, mock_client, mock_model)
    assert result == config.c_vector

def test_vector_tier_skipped_below_threshold():
    mock_client = MagicMock()
    mock_client.search.return_value = [[{"distance": 0.40, "skill_name": "TypeScript"}]]
    mock_model = MagicMock()
    mock_model.encode.return_value = [0.1] * 384

    c = Consultant(email="a@b.com", name="A", skills=[Skill(name="TypeScript")])
    req = RequiredSkill(name="JavaScript", mandatory=True)
    result = _best_credit(req, c, {}, ScoringConfig(), mock_client, mock_model)
    assert result == 0.0
```

### V3 — Unit test: `ScoringConfig` loads `skill_vector_similarity` from `from_yaml()`

```python
def test_scoring_config_has_vector_similarity():
    config = AppConfig.from_yaml(Path("config/default.yaml"))
    assert config.scoring_config.skill_vector_similarity == 0.65
    assert config.scoring_config.c_vector == 65.0
```

### V4 — Integration: `build_index` creates `.cache/milvus/skills.db`

```
uv run dsm ingest --no-llm
ls .cache/milvus/skills.db
```
Expected: file exists.

### V5 — Integration: `load_index` returns non-None after `build_index`

```python
from matcher.pipeline.index import build_index, load_index
from pathlib import Path
# With test fixtures or minimal consultant data
```

### V6 — Integration: `dsm match` runs end-to-end with index loaded

```
uv run dsm ingest --no-llm
uv run dsm match ROLE-01 --no-llm --top 3
```
Expected: completes without error. Results should be identical or better than without index
(since no-LLM means no LLM extraction, but the index contains skills from ingest).

### V7 — mypy
```
uv run mypy src/matcher/pipeline/index.py src/matcher/scoring/dimensions.py src/matcher/config.py
```
Note: `sentence_transformers` and `pymilvus` have `ignore_missing_imports = true` in
`pyproject.toml:78-80`. Add similar override for `pymilvus` if not already present.

### V8 — Full unit suite
```
uv run pytest tests/unit/ -v
```
Expected: all green. New params are `None`-defaulted; existing tests pass unchanged.

---

## Acceptance Criteria

- [ ] `ScoringConfig` has `skill_vector_similarity: float = 0.65` and `c_vector: float = 65.0`
- [ ] `from_yaml()` reads `skill_vector_similarity` from YAML into `ScoringConfig`
- [ ] `build_index()` creates `skills.db` at specified path with consultant skill vectors
- [ ] `load_index()` returns `MilvusClient` when db exists, `None` otherwise
- [ ] `_best_credit()` has three tiers: exact → adjacency → vector (only when client provided)
- [ ] Vector tier awards `c_vector` when cosine distance ≥ `skill_vector_similarity`
- [ ] Existing two-tier behaviour preserved when `index_client=None`
- [ ] V1–V3 unit tests pass
- [ ] `uv run mypy src/` passes
- [ ] `uv run pytest tests/unit/ -v` all green
