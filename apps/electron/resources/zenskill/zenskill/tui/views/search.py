"""
SearchVM — 搜索视图 (Phase T+)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("search")
@dataclass
class SearchVM(ViewModel):
    """技能搜索"""

    title: str = "搜索"
    icon: str = "🔍"

    results: List[Dict] = field(default_factory=list)
    query: str = ""
    top_k: int = 10

    @classmethod
    def load(cls, query: str = "", top_k: int = 10) -> "SearchVM":
        vm = cls(query=query, top_k=top_k)
        if not query:
            return vm
        try:
            from zenskill.skills.search_engine import SkillSearchEngine
            engine = SkillSearchEngine()
            engine.build_index()
            results = engine.search(query, top_k=top_k)
            for r in results:
                vm.results.append({
                    "name": r.name,
                    "category": r.category,
                    "rating": r.rating,
                    "description": r.description[:80] if r.description else "",
                })
            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ {self.error}"
        if not self.query:
            return "  🔍 输入 /search <关键词> 搜索技能"
        if not self.results:
            return f"  📭 未找到: {self.query}"

        lines = [f"  🔍 搜索: {self.query} ({len(self.results)} 个结果)"]
        for i, r in enumerate(self.results, 1):
            star = f"⭐{r['rating']:.1f}" if r["rating"] > 0 else "-"
            lines.append(f"  {i:2d}. {r['name']:25s} [{r['category']}] {star}")
        return "\n".join(lines)

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ {self.error}[/red]"
        if not self.query:
            return "  [dim]🔍 输入 /search <关键词> 或按 / 搜索技能[/dim]"
        if not self.results:
            return f"  [dim]📭 未找到: {self.query}[/dim]"

        lines = [f"[bold blue]🔍 搜索: {self.query}[/bold blue] [dim]({len(self.results)} 个结果)[/dim]"]
        for i, r in enumerate(self.results, 1):
            star = f"⭐{r['rating']:.1f}" if r["rating"] > 0 else "-"
            lines.append(f"  {i:2d}. {r['name']:25s} [{r['category']}] {star}")
        return "\n".join(lines)
