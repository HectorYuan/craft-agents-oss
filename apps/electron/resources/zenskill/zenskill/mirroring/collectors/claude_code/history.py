"""
Claude Code 消息历史采集器

解析 ~/.claude/history.jsonl，提取用户行为模式。
"""

import json
import os
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ClaudeHistoryCollector(BaseCollector):
    """Claude Code 消息历史采集器"""

    meta = CollectorMeta(
        name="claude-history",
        version="0.1.0",
        description="解析 Claude Code 消息历史，提取用户交互模式",
        sensitivity=DataSensitivity.HIGH,
        data_source="~/.claude/history.jsonl",
    )

    def __init__(self):
        self._history_path = Path.home() / ".claude" / "history.jsonl"

    def is_available(self) -> bool:
        return self._history_path.exists()

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        entries = self._load_history()
        if not entries:
            return []

        now = time.time()

        # 信号提取
        project_counts: Counter = Counter()
        session_counts: Counter = Counter()
        hour_counts: Counter = Counter()
        display_lengths: List[int] = []
        timestamps: List[float] = []

        for e in entries:
            proj = e.get("project", "unknown")
            proj_name = Path(proj).name if proj else "unknown"
            project_counts[proj_name] += 1

            sid = e.get("sessionId", "")
            if sid:
                session_counts[sid] += 1

            ts = e.get("timestamp", 0)
            if ts:
                t = float(ts) / 1000  # ms → s
                timestamps.append(t)
                try:
                    from datetime import datetime
                    hour = datetime.fromtimestamp(t).hour
                    hour_counts[hour] += 1
                except Exception:
                    pass

            display = e.get("display", "")
            if display:
                display_lengths.append(len(display))

        total = len(entries)
        avg_length = sum(display_lengths) / len(display_lengths) if display_lengths else 0
        sessions = len(session_counts)

        # 用户表达风格
        if avg_length < 20:
            style = "terse"       # 极简
        elif avg_length < 100:
            style = "concise"     # 简洁
        elif avg_length < 300:
            style = "detailed"    # 详细
        else:
            style = "verbose"     # 冗长

        # 活跃时段
        peak_hour = max(hour_counts, key=hour_counts.get) if hour_counts else -1

        return [{
            "source": "claude_code_history",
            "timestamp": now,
            "signal": {
                "total_messages": total,
                "sessions": sessions,
                "projects": len(project_counts),
                "top_projects": dict(project_counts.most_common(5)),
                "avg_message_length": round(avg_length, 1),
                "expression_style": style,
                "peak_hour": peak_hour,
                "hour_distribution": dict(hour_counts),
                "msg_per_session": round(total / sessions, 1) if sessions else 0,
            },
            "sensitivity": "high",
        }]

    def _load_history(self) -> List[Dict]:
        entries = []
        try:
            for line in open(self._history_path, encoding="utf-8"):
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        except Exception:
            pass
        return entries
