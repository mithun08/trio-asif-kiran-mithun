from __future__ import annotations

from pathlib import Path

from matcher.models.output import RunOutput


def save_snapshot(output: RunOutput, snapshot_dir: Path) -> Path:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{output.timestamp:%Y%m%dT%H%M%S}_{output.run_id}.json"
    path = snapshot_dir / filename
    path.write_text(output.model_dump_json(indent=2))
    return path


def prune_snapshots(snapshot_dir: Path, retention: int) -> list[Path]:
    if retention <= 0 or not snapshot_dir.exists():
        return []

    files = sorted(snapshot_dir.glob("*.json"))
    excess = files[:-retention] if retention < len(files) else []
    for path in excess:
        path.unlink()
    return excess
