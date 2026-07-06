from __future__ import annotations

from datetime import datetime
from pathlib import Path

from matcher.models.output import RunOutput
from matcher.observability.snapshot_archive import prune_snapshots, save_snapshot


def _output(run_id: str, timestamp: datetime) -> RunOutput:
    return RunOutput(
        snapshot_id="snap-abc",
        run_id=run_id,
        timestamp=timestamp,
        role_id="ROLE-01",
    )


def test_save_snapshot_roundtrips(tmp_path: Path) -> None:
    output = _output("run1", datetime(2026, 7, 6, 9, 0, 0))
    path = save_snapshot(output, tmp_path)

    assert path.exists()
    loaded = RunOutput.model_validate_json(path.read_text())
    assert loaded.run_id == "run1"
    assert loaded.snapshot_id == "snap-abc"
    assert loaded.role_id == "ROLE-01"


def test_save_snapshot_same_second_different_run_ids_no_collision(tmp_path: Path) -> None:
    ts = datetime(2026, 7, 6, 9, 0, 0)
    path1 = save_snapshot(_output("run1", ts), tmp_path)
    path2 = save_snapshot(_output("run2", ts), tmp_path)

    assert path1 != path2
    assert path1.exists() and path2.exists()


def test_prune_snapshots_keeps_newest_n(tmp_path: Path) -> None:
    for i in range(5):
        save_snapshot(_output(f"run{i}", datetime(2026, 7, 6, 9, i, 0)), tmp_path)

    deleted = prune_snapshots(tmp_path, retention=2)

    remaining = sorted(p.name for p in tmp_path.glob("*.json"))
    assert len(remaining) == 2
    assert remaining == sorted(
        p.name
        for p in [
            tmp_path / "20260706T090300_run3.json",
            tmp_path / "20260706T090400_run4.json",
        ]
    )
    assert len(deleted) == 3
    for path in deleted:
        assert not path.exists()


def test_prune_snapshots_zero_retention_is_unlimited(tmp_path: Path) -> None:
    for i in range(5):
        save_snapshot(_output(f"run{i}", datetime(2026, 7, 6, 9, i, 0)), tmp_path)

    deleted = prune_snapshots(tmp_path, retention=0)

    assert deleted == []
    assert len(list(tmp_path.glob("*.json"))) == 5


def test_prune_snapshots_fewer_files_than_retention_is_noop(tmp_path: Path) -> None:
    save_snapshot(_output("run0", datetime(2026, 7, 6, 9, 0, 0)), tmp_path)

    deleted = prune_snapshots(tmp_path, retention=50)

    assert deleted == []
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_prune_snapshots_missing_dir_is_noop(tmp_path: Path) -> None:
    deleted = prune_snapshots(tmp_path / "nonexistent", retention=5)
    assert deleted == []
