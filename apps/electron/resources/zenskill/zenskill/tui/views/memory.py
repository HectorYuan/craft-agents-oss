"""
MemoryVM — 记忆视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("memory")
@dataclass
class MemoryVM(ViewModel):
    """记忆管理视图"""

    title: str = "记忆"
    icon: str = "🧠"

    skill_id: str = "zenskill-core"
    events: List[Dict] = field(default_factory=list)
    total: int = 0

    @classmethod
    def load(cls, skill_id: str = "zenskill-core", limit: int = 20) -> "MemoryVM":
        vm = cls(skill_id=skill_id)
        try:
            from zenskill.core.skill_dao import SkillDAO
            vm.events = SkillDAO.get_events(skill_id, limit=limit)
            vm.total = SkillDAO.get_event_count(skill_id)
            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"
        if not self.events:
            return "  📭 暂无记忆"

        lines = [f"  📋 最近记忆 (共 {self.total} 条)"]
        for e in self.events[:20]:
            content = str(e.get("content", ""))[:70]
            action = str(e.get("action", ""))[:10]
            if content:
                lines.append(f"  · [{action}] {content}")
        return "\n".join(lines)

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ 加载失败: {self.error}[/red]"
        if not self.events:
            return "  [dim]📭 暂无记忆[/dim]"

        lines = [f"[bold blue]📋 最近记忆[/bold blue] [dim](共 {self.total} 条)[/dim]"]
        for e in self.events[:20]:
            content = str(e.get("content", ""))[:70]
            action = str(e.get("action", ""))[:10]
            if content:
                lines.append(f"  · [dim][{action}][/dim] {content}")
        return "\n".join(lines)
