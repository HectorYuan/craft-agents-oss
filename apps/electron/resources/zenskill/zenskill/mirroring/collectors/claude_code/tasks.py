"""
Claude Code 任务记录采集器

解析 ~/.claude/tasks/*/*.json，分析任务执行模式。
"""

import json
import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ClaudeTasksCollector(BaseCollector):
    """Claude Code 任务记录采集器"""

    meta = CollectorMeta(
        name="claude-tasks",
        version="0.1.0",
        description="解析 Task 执行记录，分析任务粒度和执行模式",
        sensitivity=DataSensitivity.MEDIUM,
        data_source="~/.claude/tasks/",
    )

    def __init__(self):
        self._tasks_dir = Path.home() / ".claude" / "tasks"

    def is_available(self) -> bool:
        return self._tasks_dir.exists() and any(self._tasks_dir.iterdir())

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        now = time.time()

        all_tasks: List[Dict] = []
        for session_dir in self._tasks_dir.iterdir():
            if not session_dir.is_dir():
                continue
            for task_file in session_dir.glob("*.json"):
                try:
                    content = task_file.read_text(encoding="utf-8")
                    task = json.loads(content)
                    task["_session_id"] = session_dir.name
                    all_tasks.append(task)
                except Exception:
                    pass

        if not all_tasks:
            return []

        # 按状态分类
        status_counts: Counter = Counter()
        for t in all_tasks:
            status_counts[t.get("status", "unknown")] += 1

        done = status_counts.get("completed", 0) + status_counts.get("done", 0)
        total = len(all_tasks)
        completion_rate = round(done / total * 100, 1) if total > 0 else 0

        # 按项目统计（通过 task IDs）
        sessions = len(set(t.get("_session_id", "") for t in all_tasks))
        tasks_per_session = round(total / sessions, 1) if sessions else 0

        # 阻塞分析
        blocked_count = sum(1 for t in all_tasks if t.get("blockedBy"))

        # 任务粒度（通过描述长度）
        desc_lengths = [len(t.get("description", "")) for t in all_tasks]
        avg_desc_length = round(sum(desc_lengths) / len(desc_lengths), 1) if desc_lengths else 0

        if avg_desc_length < 50:
            granularity = "fine"      # 细粒度
        elif avg_desc_length < 150:
            granularity = "medium"    # 中等
        else:
            granularity = "coarse"    # 粗粒度

        return [{
            "source": "claude_code_tasks",
            "timestamp": now,
            "signal": {
                "total_tasks": total,
                "status_distribution": dict(status_counts),
                "completion_rate": completion_rate,
                "sessions": sessions,
                "tasks_per_session": tasks_per_session,
                "blocked_count": blocked_count,
                "task_granularity": granularity,
                "avg_description_length": avg_desc_length,
            },
            "sensitivity": "medium",
        }]
