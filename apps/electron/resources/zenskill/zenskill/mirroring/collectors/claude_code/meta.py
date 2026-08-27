"""
Claude Code 元数据采集器

采集 sessions / file-history / shell-snapshots 三类基础设施信号。
"""

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ClaudeSessionCollector(BaseCollector):
    """Claude Code 会话元数据采集器

    数据源: ~/.claude/sessions/*.json
    """

    meta = CollectorMeta(
        name="claude-sessions",
        version="0.1.0",
        description="采集 Claude Code 会话元数据（cwd/版本/入口/时长分布）",
        sensitivity=DataSensitivity.MEDIUM,
        data_source="~/.claude/sessions/",
    )

    def __init__(self):
        self._dir = Path.home() / ".claude" / "sessions"

    def is_available(self) -> bool:
        return self._dir.exists() and any(self._dir.glob("*.json"))

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        now = time.time()

        sessions = []
        for f in self._dir.glob("*.json"):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
                sessions.append(d)
            except Exception:
                pass
        if not sessions:
            return []

        # 分析信号
        cwd_counts: Counter = Counter()
        version_counts: Counter = Counter()
        kind_counts: Counter = Counter()
        entry_counts: Counter = Counter()

        for s in sessions:
            cwd = s.get("cwd", "")
            if cwd:
                cwd_counts[Path(cwd).name] += 1
            ver = s.get("version", "")
            if ver:
                version_counts[ver] += 1
            kind = s.get("kind", "")
            if kind:
                kind_counts[kind] += 1
            entry = s.get("entrypoint", "")
            if entry:
                entry_counts[entry] += 1

        return [{
            "source": "claude_code_sessions",
            "timestamp": now,
            "signal": {
                "total_sessions": len(sessions),
                "projects": dict(cwd_counts),
                "versions": dict(version_counts),
                "session_kinds": dict(kind_counts),
                "entrypoints": dict(entry_counts),
                "latest_version": sessions[-1].get("version", "") if sessions else "",
            },
            "sensitivity": "medium",
        }]


class ClaudeFileHistoryCollector(BaseCollector):
    """Claude Code 文件操作历史采集器

    数据源: ~/.claude/file-history/*/  (134 个 session 目录)
    """

    meta = CollectorMeta(
        name="claude-file-history",
        version="0.1.0",
        description="统计文件操作历史目录分布，评估文件交互频率",
        sensitivity=DataSensitivity.MEDIUM,
        data_source="~/.claude/file-history/",
    )

    def __init__(self):
        self._dir = Path.home() / ".claude" / "file-history"

    def is_available(self) -> bool:
        return self._dir.exists() and any(self._dir.iterdir())

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        now = time.time()

        session_dirs = [d for d in self._dir.iterdir() if d.is_dir()]
        if not session_dirs:
            return []

        file_counts: List[int] = []
        for d in session_dirs:
            try:
                file_counts.append(len(list(d.iterdir())))
            except Exception:
                file_counts.append(0)

        total_files = sum(file_counts)
        avg_files = round(total_files / len(file_counts), 1) if file_counts else 0

        return [{
            "source": "claude_code_file_history",
            "timestamp": now,
            "signal": {
                "total_sessions": len(session_dirs),
                "total_file_ops": total_files,
                "avg_files_per_session": avg_files,
                "high_activity_sessions": sum(1 for c in file_counts if c > 10),
            },
            "sensitivity": "medium",
        }]


class ClaudeShellSnapshotCollector(BaseCollector):
    """Claude Code Shell 快照采集器

    数据源: ~/.claude/shell-snapshots/
    """

    meta = CollectorMeta(
        name="claude-shell-snapshots",
        version="0.1.0",
        description="采集 Shell 快照统计，评估 shell 环境复杂度",
        sensitivity=DataSensitivity.LOW,
        data_source="~/.claude/shell-snapshots/",
    )

    def __init__(self):
        self._dir = Path.home() / ".claude" / "shell-snapshots"

    def is_available(self) -> bool:
        return self._dir.exists() and any(self._dir.glob("*.sh"))

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        now = time.time()

        files = list(self._dir.glob("*.sh"))
        sizes: List[int] = []
        shells: Counter = Counter()
        for f in files:
            try:
                size = f.stat().st_size
                sizes.append(size)
                # 从文件名检测 shell 类型
                name = f.name.lower()
                if "bash" in name:
                    shells["bash"] += 1
                elif "zsh" in name:
                    shells["zsh"] += 1
                else:
                    shells["unknown"] += 1
            except Exception:
                pass

        total_size = sum(sizes)
        avg_size = round(total_size / len(sizes), 0) if sizes else 0

        return [{
            "source": "claude_code_shell_snapshots",
            "timestamp": now,
            "signal": {
                "total_snapshots": len(files),
                "total_size_bytes": total_size,
                "avg_size_bytes": avg_size,
                "shell_types": dict(shells),
            },
            "sensitivity": "low",
        }]
