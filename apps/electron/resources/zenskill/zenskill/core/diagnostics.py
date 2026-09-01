"""Lightweight diagnostic event logging."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .paths import append_jsonl_locked, atomic_write_text, file_lock, get_user_data_dir

MAX_DIAG_ENTRIES = 500


def _diag_file() -> Path:
    return get_user_data_dir() / "diagnostics.jsonl"


def log_diagnostic(event: str, **kwargs: Any) -> None:
    """写入诊断事件。静默失败，不抛异常。"""
    try:
        record = {
            "ts": datetime.now().isoformat(),
            "event": event,
            **kwargs,
        }
        diag = _diag_file()
        append_jsonl_locked(diag, record)
        _trim_if_needed(diag)
    except Exception:
        pass


def _trim_if_needed(path: Path) -> None:
    """保留最近 MAX_DIAG_ENTRIES 条，超出部分裁剪。"""
    try:
        if not path.exists():
            return
        lines = path.read_text(encoding="utf-8").splitlines()
        good = [l for l in lines if l.strip()]
        if len(good) <= MAX_DIAG_ENTRIES:
            return
        with file_lock(path):
            kept = good[-MAX_DIAG_ENTRIES:]
            content = "\n".join(kept) + "\n"
            atomic_write_text(path, content)
    except Exception:
        pass


def read_diagnostics(n: int = 50) -> list[dict[str, Any]]:
    """读取最近 n 条诊断记录。"""
    diag = _diag_file()
    if not diag.exists():
        return []
    records: list[dict[str, Any]] = []
    try:
        with open(diag, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except (UnicodeDecodeError, OSError):
        return []
    return records[-n:]
