"""
GTDVM — 任务管理视图 (Phase T1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from . import ViewModel, register_viewmodel


@register_viewmodel("gtd")
@dataclass
class GTDVM(ViewModel):
    """GTD 任务视图"""

    title: str = "GTD 任务"
    icon: str = "✅"

    actions: List[Dict] = field(default_factory=list)
    projects: List[Dict] = field(default_factory=list)
    inbox_count: int = 0

    @classmethod
    def load(cls) -> "GTDVM":
        vm = cls()
        try:
            from zenskill.systems.gtd.action import ActionEngine
            from zenskill.systems.gtd.inbox import InboxEngine
            from zenskill.systems.gtd.project import ProjectEngine

            # Actions（未完成，按创建时间倒序）
            try:
                for a in ActionEngine().list_pending(limit=15):
                    vm.actions.append({
                        "id": a.id,
                        "title": a.title or "?",
                        "status": a.status or "pending",
                        "priority": a.priority or "P2",
                    })
            except Exception:
                pass

            # Projects（活跃）
            try:
                for p in ProjectEngine().list_active(limit=5):
                    vm.projects.append({
                        "id": p.id,
                        "name": p.name or "?",
                        "progress": 0,
                    })
            except Exception:
                pass

            # Inbox（未处理条目）
            try:
                vm.inbox_count = InboxEngine().count_pending()
            except Exception:
                pass

            vm.data_level = 2
        except Exception as e:
            vm.error = str(e)
        return vm

    def render_l1(self) -> str:
        if self.error:
            return f"  ⚠️ 加载失败: {self.error}"

        lines = []
        # 概览
        from zenskill.render import PlainRenderer
        r = PlainRenderer()

        lines.append(r.card(
            type('s', (), {'title': 'GTD 概览', 'icon': 'gtd',
                           'fields': [("待处理", str(self.inbox_count)),
                                      ("进行中 Actions", str(len(self.actions))),
                                      ("活跃项目", str(len(self.projects)))],
                           'footer': '', 'color': 'primary'})()
        ))

        # Actions
        if self.actions:
            lines.append(r._color_ansi("#4A90D9", "  📋 Actions"))
            for a in self.actions[:10]:
                icon = {"todo": "⏳", "in_progress": "🔄", "done": "✅"}.get(a["status"], "·")
                lines.append(f"  {icon} {a['title'][:60]}")

        # Projects
        if self.projects:
            lines.append(r._color_ansi("#9B59B6", "  📁 Projects"))
            for p in self.projects:
                bar = "█" * (p["progress"] // 10) + "·" * (10 - p["progress"] // 10)
                lines.append(f"  · {p['name'][:40]} [{bar}]")

        return "\n".join(lines) if lines else "  📭 GTD 数据暂无"

    def render_l2(self) -> str:
        if self.error:
            return f"[red]⚠️ 加载失败: {self.error}[/red]"

        from zenskill.render import RichRenderer
        r = RichRenderer()
        lines = []

        lines.append(r.card(
            type('s', (), {'title': 'GTD 概览', 'icon': 'gtd',
                           'fields': [("待处理", str(self.inbox_count)),
                                      ("进行中 Actions", str(len(self.actions))),
                                      ("活跃项目", str(len(self.projects)))],
                           'footer': '', 'color': 'primary'})()
        ))

        if self.actions:
            lines.append("[bold blue]📋 Actions[/bold blue]")
            for a in self.actions[:10]:
                icon = {"todo": "⏳", "in_progress": "🔄", "done": "✅"}.get(a["status"], "·")
                lines.append(f"  {icon} {a['title'][:60]}")

        if self.projects:
            lines.append("[bold #9B59B6]📁 Projects[/bold #9B59B6]")
            for p in self.projects:
                bar = "█" * (p["progress"] // 10) + "░" * (10 - p["progress"] // 10)
                lines.append(f"  · {p['name'][:40]} [{bar}]")

        return "\n".join(lines) if lines else "  [dim]📭 GTD 数据暂无[/dim]"
