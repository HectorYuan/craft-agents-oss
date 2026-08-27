"""
ZenSkill 内部记忆采集器

扫描 ~/.zenskill/memory/ 目录，统计记忆分布。
"""

import time
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from ..base import BaseCollector, CollectorMeta, DataSensitivity


class ZenskillMemoryCollector(BaseCollector):
    """ZenSkill 记忆系统采集器"""

    meta = CollectorMeta(
        name="zenskill-memory",
        version="0.1.0",
        description="扫描 ZenSkill 三层记忆目录，统计记忆数量和类型分布",
        sensitivity=DataSensitivity.LOW,
        data_source="~/.zenskill/memory/",
    )

    def __init__(self):
        self._dir = Path.home() / ".zenskill" / "memory"

    def is_available(self) -> bool:
        return self._dir.exists()

    def collect_full(self) -> List[Dict[str, Any]]:
        now = time.time()

        stats: Dict[str, dict] = {}
        total_files = 0
        total_size = 0

        for layer in ["working", "episodic", "semantic"]:
            layer_dir = self._dir / layer
            if layer_dir.exists():
                files = list(layer_dir.rglob("*"))
                md_files = [f for f in files if f.suffix in (".md", ".json")]
                layer_total = sum(
                    f.stat().st_size for f in md_files if f.is_file()
                )
                stats[layer] = {
                    "count": len(md_files),
                    "total_size_bytes": layer_total,
                }
                total_files += len(md_files)
                total_size += layer_total

        return [{
            "source": "zenskill_memory",
            "timestamp": now,
            "signal": {
                "total_files": total_files,
                "total_size_bytes": total_size,
                "layers": stats,
            },
            "sensitivity": "low",
        }]


class ZenskillZenloopCollector(BaseCollector):
    """ZenSkill 禅思报告采集器"""

    meta = CollectorMeta(
        name="zenskill-zenloop",
        version="0.1.0",
        description="分析禅思反思报告，提取反思频率和关注主题",
        sensitivity=DataSensitivity.MEDIUM,
        data_source="~/.zenskill/zenloop/",
    )

    def __init__(self):
        self._dir = Path.home() / ".zenskill" / "zenloop"

    def is_available(self) -> bool:
        return self._dir.exists() and any(self._dir.glob("*.md"))

    def collect_full(self) -> List[Dict[str, Any]]:
        if not self.is_available():
            return []
        now = time.time()

        reflections = list(self._dir.glob("reflection_*.md"))
        if not reflections:
            return []

        sizes = []
        keywords = Counter()
        kw_list = ["记忆", "记忆系统", "禅思", "反思", "成长", "修炼",
                   "bug", "修复", "优化", "架构", "测试", "TUI",
                   "Memory", "ZenLoop", "cultivating", "Phase",
                   "LLM", "API", "CLI", "streaming"]

        for rf in reflections:
            try:
                content = rf.read_text(encoding="utf-8")
                sizes.append(len(content))
                for kw in kw_list:
                    if kw.lower() in content.lower():
                        keywords[kw] += 1
            except Exception:
                pass

        avg_size = round(sum(sizes) / len(sizes), 0) if sizes else 0

        return [{
            "source": "zenskill_zenloop",
            "timestamp": now,
            "signal": {
                "total_reflections": len(reflections),
                "avg_size_bytes": avg_size,
                "has_latest": (self._dir / "latest_reflection.md").exists(),
                "top_keywords": dict(keywords.most_common(10)),
                "dominant_theme": keywords.most_common(1)[0][0] if keywords else "none",
            },
            "sensitivity": "medium",
        }]
