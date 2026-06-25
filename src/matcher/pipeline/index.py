from __future__ import annotations

from pathlib import Path
from typing import Any

from matcher.models.consultant import Consultant
from matcher.models.role import Role

_MODEL_NAME = "all-MiniLM-L6-v2"
_COLLECTION = "skill_embeddings"
_DIM = 384


def build_index(
    consultants: list[Consultant],
    roles: list[Role],
    index_dir: Path,
    model_name: str = _MODEL_NAME,
) -> None:
    from pymilvus import MilvusClient
    from sentence_transformers import SentenceTransformer

    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(index_dir / "skills.db")

    model: Any = SentenceTransformer(model_name)
    client: Any = MilvusClient(db_path)

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


def load_index(index_dir: Path) -> Any:
    from pymilvus import MilvusClient

    db_path = index_dir / "skills.db"
    if not db_path.exists():
        return None
    client: Any = MilvusClient(str(db_path))
    if not client.has_collection(_COLLECTION):
        return None
    return client
