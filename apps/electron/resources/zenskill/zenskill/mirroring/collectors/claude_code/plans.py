"""
Claude Code 计划文档采集器

扫描 ~/.claude/plans/*.md，分析用户如何做架构设计和决策。
"""

import time
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ClaudePlansCollector(BaseCollector):
    """Claude Code 计划文档采集器"""

    meta = CollectorMeta(
        name="claude-plans",
        version="0.1.0",
        description="扫描 plans/*.md，分析计划复杂度和决策模式",
        sensitivity=DataSensitivity.MEDIUM,
        data_source="~/.claude/plans/",
    )

    def __init__(self):
        self._plans_dir = Path.home() / ".claude" / "plans"

    def is_available(self) -> bool:
        return self._plans_dir.exists() and any(self._plans_dir.glob("*.md"))

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []

        now = time.time()
        plan_files = list(self._plans_dir.glob("*.md"))

        sizes: List[int] = []
        sections_list: List[int] = []
        total_size = 0
        complexity_levels: Dict[str, int] = {"simple": 0, "medium": 0, "complex": 0}

        for pf in plan_files:
            try:
                content = pf.read_text(encoding="utf-8")
                size = len(content)
                sizes.append(size)
                total_size += size

                # 统计标题行数（估算节数）
                sections = sum(1 for line in content.split("\n") if line.startswith("##"))
                sections_list.append(sections)

                # 复杂度分类
                if size < 1000:
                    complexity_levels["simple"] += 1
                elif size < 3000:
                    complexity_levels["medium"] += 1
                else:
                    complexity_levels["complex"] += 1

            except Exception:
                pass

        total = len(plan_files)
        avg_size = round(sum(sizes) / len(sizes), 0) if sizes else 0
        avg_sections = round(sum(sections_list) / len(sections_list), 1) if sections_list else 0

        # 迭代风格
        if total <= 3:
            iteration_style = "few_large_plans"
        elif total <= 8:
            iteration_style = "balanced"
        else:
            iteration_style = "many_small_plans"

        return [{
            "source": "claude_code_plans",
            "timestamp": now,
            "signal": {
                "total_plans": total,
                "avg_size_bytes": avg_size,
                "avg_sections": avg_sections,
                "complexity_distribution": complexity_levels,
                "iteration_style": iteration_style,
                "total_size_bytes": total_size,
            },
            "sensitivity": "medium",
        }]
