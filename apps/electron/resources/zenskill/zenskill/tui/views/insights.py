"""
InsightsVM — 洞察视图 (Phase T+)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("insights")
@dataclass
class InsightsVM(ViewModel):
    """洞察与反思"""

    title: str = "洞察"
    icon: str = "💡"

    insights: List[Dict] = field(default_factory=list)
    skill_id: str = "zenskill-core"

    @classmethod
    def load(cls, skill_id: str = "zenskill-core") -> "InsightsVM":
        vm = cls(skill_id=skill_id)
        try:
            from zenskill.core.skill_dao import SkillDAO
            vm.insights = SkillDAO.get_insights(skill_id, limit=20)
            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ {self.error}"
        if not self.insights:
            return "  📭 暂无洞察 — 继续使用后会自动生成"

        lines = [f"  💡 洞察列表 (共 {len(self.insights)} 条)"]
        for ins in self.insights[:20]:
            title = str(ins.get("title", ins.get("description", "?")))[:70]
            level = str(ins.get("level", ""))[:8]
            read = "✓" if ins.get("is_read") else "新"
            lines.append(f"  [{read}] {title}")
        return "\n".join(lines)

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ {self.error}[/red]"
        if not self.insights:
            return "  [dim]📭 暂无洞察 — 继续使用后会自动生成[/dim]"

        lines = [f"[bold #9B59B6]💡 洞察列表[/bold #9B59B6] [dim](共 {len(self.insights)} 条)[/dim]"]
        for ins in self.insights[:20]:
            title = str(ins.get("title", ins.get("description", "?")))[:70]
            read_tag = "[dim]✓[/dim]" if ins.get("is_read") else "[bold]新[/bold]"
            lines.append(f"  [{read_tag}] {title}")
        return "\n".join(lines)
