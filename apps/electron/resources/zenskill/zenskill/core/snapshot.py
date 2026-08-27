"""Lightweight data snapshots for recovery points."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .diagnostics import log_diagnostic
from .paths import get_user_data_dir


SNAPSHOTS_DIR_NAME = "snapshots"
MAX_SNAPSHOTS = 10

# Directories under ~/.zenskill/ to include in a snapshot.
# Keys are relative paths; values are globs to include (or None for all files).
SNAPSHOT_SOURCES: dict[str, str | None] = {
    "states": "*.json",
    "mirroring": "*.jsonl",
    "metrics": "*.jsonl",
    "goals": "*.jsonl",
    "insights": "*.jsonl",
    "graph": "*.jsonl",
    "cultivation": "*",
    "zenloop": "*.md",
}


@dataclass
class SnapshotInfo:
    id: str
    timestamp: str
    file_count: int
    path: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _snapshots_dir() -> Path:
    return get_user_data_dir() / SNAPSHOTS_DIR_NAME


def create_snapshot() -> SnapshotInfo:
    ts = datetime.now()
    snap_id = f"{ts.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    snap_dir = _snapshots_dir() / snap_id
    user_dir = get_user_data_dir()
    file_count = 0

    for rel_dir, pattern in SNAPSHOT_SOURCES.items():
        src_dir = user_dir / rel_dir
        if not src_dir.exists():
            continue
        dst_dir = snap_dir / rel_dir
        dst_dir.mkdir(parents=True, exist_ok=True)
        glob = pattern if pattern else "*"
        for f in src_dir.glob(glob):
            if not f.is_file():
                continue
            if ".corrupted." in f.name or ".badlines." in f.name or f.name.endswith(".lock"):
                continue
            shutil.copy2(f, dst_dir / f.name)
            file_count += 1

    manifest = {
        "id": snap_id,
        "created": ts.isoformat(),
        "file_count": file_count,
        "sources": list(SNAPSHOT_SOURCES.keys()),
    }
    (snap_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    _prune_old_snapshots()
    log_diagnostic("snapshot_create", id=snap_id, file_count=file_count)
    return SnapshotInfo(id=snap_id, timestamp=ts.isoformat(), file_count=file_count, path=str(snap_dir))


def list_snapshots() -> list[SnapshotInfo]:
    base = _snapshots_dir()
    if not base.exists():
        return []
    result: list[SnapshotInfo] = []
    for d in sorted(base.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        manifest = d / "manifest.json"
        if manifest.exists():
            try:
                m = json.loads(manifest.read_text(encoding="utf-8"))
                result.append(SnapshotInfo(
                    id=m["id"],
                    timestamp=m["created"],
                    file_count=m.get("file_count", 0),
                    path=str(d),
                ))
            except (json.JSONDecodeError, KeyError, UnicodeDecodeError):
                continue
    return result


def restore_snapshot(snap_id: str, dry_run: bool = False) -> dict[str, Any]:
    snap_dir = _snapshots_dir() / snap_id
    if not snap_dir.exists():
        raise FileNotFoundError(f"Snapshot {snap_id} 不存在")

    user_dir = get_user_data_dir()
    restored: list[str] = []

    for item in snap_dir.iterdir():
        if item.is_dir():
            dst = user_dir / item.name
            dst.mkdir(parents=True, exist_ok=True)
            for f in item.iterdir():
                if f.is_file() and f.name != "manifest.json":
                    target = dst / f.name
                    if not dry_run:
                        shutil.copy2(f, target)
                    restored.append(str(target.relative_to(user_dir)))
        elif item.is_file() and item.name == "manifest.json":
            continue

    if not dry_run:
        log_diagnostic("snapshot_restore", id=snap_id, files=len(restored))
    return {"snapshot_id": snap_id, "dry_run": dry_run, "restored_files": len(restored)}


def _prune_old_snapshots() -> None:
    snapshots = list_snapshots()
    if len(snapshots) <= MAX_SNAPSHOTS:
        return
    for info in snapshots[MAX_SNAPSHOTS:]:
        snap_dir = Path(info.path)
        if snap_dir.exists():
            shutil.rmtree(snap_dir)
