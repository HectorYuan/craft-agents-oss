"""State integrity scanner and repair."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .diagnostics import log_diagnostic
from .paths import atomic_write_text, get_metrics_dir, get_mirroring_dir, get_user_data_dir


@dataclass
class FileCheck:
    path: str
    ok: bool
    bad_lines: int = 0
    total_lines: int = 0
    error: str = ""


@dataclass
class StateDoctorReport:
    status: str
    summary: dict[str, int]
    states: list[FileCheck]
    histories: list[FileCheck]
    events: list[FileCheck]
    metrics: list[FileCheck]
    corrupted_backups: list[str]
    suggestions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _check_json_file(path: Path) -> FileCheck:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return FileCheck(str(path), False, error="JSON 根对象不是 dict")
        return FileCheck(str(path), True)
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
        return FileCheck(str(path), False, error=str(e))


def _check_jsonl_file(path: Path) -> FileCheck:
    bad_lines = 0
    total_lines = 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                total_lines += 1
                try:
                    json.loads(line)
                except json.JSONDecodeError:
                    bad_lines += 1
    except (UnicodeDecodeError, OSError) as e:
        return FileCheck(str(path), False, error=str(e))
    return FileCheck(str(path), bad_lines == 0, bad_lines=bad_lines, total_lines=total_lines)


def scan_state_integrity() -> StateDoctorReport:
    user_dir = get_user_data_dir()
    states_dir = user_dir / "states"
    mirroring_dir = get_mirroring_dir(autocreate=False)
    metrics_dir = get_metrics_dir(autocreate=False)

    state_files = sorted(
        p for p in states_dir.glob("*.json")
        if not p.name.endswith(".history.jsonl") and ".corrupted." not in p.name
    ) if states_dir.exists() else []
    history_files = sorted(states_dir.glob("*.history.jsonl")) if states_dir.exists() else []
    corrupted_backups = sorted(str(p) for p in states_dir.glob("*.corrupted.*")) if states_dir.exists() else []
    event_files = [mirroring_dir / "events.jsonl"] if (mirroring_dir / "events.jsonl").exists() else []
    metric_files = sorted(metrics_dir.glob("*.jsonl")) if metrics_dir.exists() else []

    states = [_check_json_file(path) for path in state_files]
    histories = [_check_jsonl_file(path) for path in history_files]
    events = [_check_jsonl_file(path) for path in event_files]
    metrics = [_check_jsonl_file(path) for path in metric_files]

    all_jsonl = histories + events + metrics
    bad_states = sum(1 for item in states if not item.ok)
    bad_jsonl_files = sum(1 for item in all_jsonl if not item.ok)
    bad_jsonl_lines = sum(item.bad_lines for item in all_jsonl)

    suggestions: list[str] = []
    if bad_states:
        suggestions.append("运行 zenskill doctor repair --dry-run 查看可修复状态文件")
    if bad_jsonl_lines:
        suggestions.append("JSONL 存在坏行；后续 repair 可生成备份后移除坏行")
    if corrupted_backups:
        suggestions.append("发现 corrupted 备份，请保留用于排查，确认无用后再手动清理")
    if not suggestions:
        suggestions.append("状态数据完整性正常")

    if bad_states:
        status = "critical"
    elif bad_jsonl_files or corrupted_backups:
        status = "degraded"
    else:
        status = "healthy"

    summary = {
        "state_files": len(states),
        "bad_state_files": bad_states,
        "history_files": len(histories),
        "event_files": len(events),
        "metric_files": len(metrics),
        "bad_jsonl_files": bad_jsonl_files,
        "bad_jsonl_lines": bad_jsonl_lines,
        "corrupted_backups": len(corrupted_backups),
    }

    return StateDoctorReport(
        status=status,
        summary=summary,
        states=states,
        histories=histories,
        events=events,
        metrics=metrics,
        corrupted_backups=corrupted_backups,
        suggestions=suggestions,
    )


# ---- repair ----------------------------------------------------------------

@dataclass
class FileRepair:
    path: str
    action: str  # "recovered_json", "cleaned_jsonl", "skipped_unrecoverable", "skipped_healthy"
    backup: str = ""
    bad_lines_removed: int = 0
    error: str = ""


@dataclass
class StateRepairReport:
    dry_run: bool
    repairs: list[FileRepair] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def repaired_count(self) -> int:
        return sum(1 for r in self.repairs if r.action in ("recovered_json", "cleaned_jsonl"))

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.repairs if r.action.startswith("skipped"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "repaired": self.repaired_count,
            "skipped": self.skipped_count,
            "repairs": [asdict(r) for r in self.repairs],
            "errors": self.errors,
        }


def _make_backup_path(original: Path, tag: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    return original.with_name(f"{original.name}.{tag}.{timestamp}.{os.getpid()}")


def _repair_json_file(path: Path, dry_run: bool) -> FileRepair:
    try:
        raw = path.read_bytes()
        decoder = json.JSONDecoder()
        obj, end = decoder.raw_decode(raw.decode("utf-8", errors="ignore"))
        if not isinstance(obj, dict):
            return FileRepair(str(path), "skipped_unrecoverable", error="根对象不是 dict")
        valid = raw.decode("utf-8", errors="ignore")[:end]
        if not dry_run:
            backup = _make_backup_path(path, "corrupted")
            backup.write_bytes(raw)
            atomic_write_text(path, valid)
            log_diagnostic("repair_json", path=str(path), backup=str(backup))
            return FileRepair(str(path), "recovered_json", backup=str(backup))
        return FileRepair(str(path), "recovered_json")
    except Exception as e:
        return FileRepair(str(path), "skipped_unrecoverable", error=str(e))


def _repair_jsonl_file(path: Path, dry_run: bool) -> FileRepair:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError) as e:
        return FileRepair(str(path), "skipped_unrecoverable", error=str(e))

    good: list[str] = []
    bad_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            json.loads(stripped)
            good.append(stripped)
        except json.JSONDecodeError:
            bad_count += 1

    if bad_count == 0:
        return FileRepair(str(path), "skipped_healthy")

    if not dry_run:
        backup = _make_backup_path(path, "badlines")
        backup.write_text("\n".join(lines) + "\n", encoding="utf-8")
        content = "\n".join(good)
        atomic_write_text(path, content + "\n" if content else "")
        log_diagnostic("repair_jsonl", path=str(path), bad_lines_removed=bad_count)
        return FileRepair(str(path), "cleaned_jsonl", backup=str(backup), bad_lines_removed=bad_count)
    return FileRepair(str(path), "cleaned_jsonl", bad_lines_removed=bad_count)


def repair_state_integrity(dry_run: bool = False) -> StateRepairReport:
    report = StateRepairReport(dry_run=dry_run)
    scan = scan_state_integrity()

    for item in scan.states:
        if not item.ok:
            report.repairs.append(_repair_json_file(Path(item.path), dry_run))

    for item in scan.histories + scan.events + scan.metrics:
        if not item.ok:
            report.repairs.append(_repair_jsonl_file(Path(item.path), dry_run))

    if scan.corrupted_backups and not dry_run:
        report.errors.append(
            f"发现 {len(scan.corrupted_backups)} 个 corrupted 备份，请手动确认后清理"
        )

    return report
