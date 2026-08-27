"""
Claude Code 项目记忆采集器

扫描 ~/.claude/projects/*/memory/*.md，提取决策模式和经验总结。
"""

import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ClaudeMemoryCollector(BaseCollector):
    """Claude Code 项目记忆采集器"""

    meta = CollectorMeta(
        name="claude-memory",
        version="0.1.0",
        description="扫描所有项目的 memory/*.md，提取决策记录和经验模式",
        sensitivity=DataSensitivity.HIGH,
        data_source="~/.claude/projects/*/memory/",
    )

    def __init__(self):
        self._projects_dir = Path.home() / ".claude" / "projects"

    def is_available(self) -> bool:
        return self._projects_dir.exists() and any(self._projects_dir.iterdir())

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        now = time.time()

        project_memories: Dict[str, List[str]] = {}
        all_tags: Counter = Counter()
        keyword_counts: Counter = Counter()
        total_files = 0
        total_size = 0

        keywords = [
            "bug", "fix", "refactor", "feature", "design", "决策",
            "经验", "教训", "完成", "修复", "优化", "实现",
            "architecture", "测试", "test", "deploy", "部署",
        ]

        for project_dir in self._projects_dir.iterdir():
            if not project_dir.is_dir():
                continue
            memory_dir = project_dir / "memory"
            if not memory_dir.exists():
                continue

            proj_name = project_dir.name
            files = list(memory_dir.glob("*.md"))
            project_memories[proj_name] = [f.stem for f in files]
            total_files += len(files)

            for mf in files:
                try:
                    content = mf.read_text(encoding="utf-8")
                    total_size += len(content)

                    # 关键词匹配
                    for kw in keywords:
                        if kw.lower() in content.lower():
                            keyword_counts[kw] += 1
                except Exception:
                    pass

        return [{
            "source": "claude_code_memory",
            "timestamp": now,
            "signal": {
                "total_projects": len(project_memories),
                "total_files": total_files,
                "total_size_bytes": total_size,
                "projects_summary": {k: len(v) for k, v in project_memories.items()},
                "avg_files_per_project": round(total_files / len(project_memories), 1) if project_memories else 0,
                "top_keywords": dict(keyword_counts.most_common(10)),
                "dominant_theme": keyword_counts.most_common(1)[0][0] if keyword_counts else "none",
            },
            "sensitivity": "high",
        }]
