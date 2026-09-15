"""GTD 任务管理页面 -- /gtd 命令。

展示 Inbox/Actions/Projects 三栏概览。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class GTDPage:
    """GTD 任务管理页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染 GTD 概览。"""
        try:
            from zenskill.systems.gtd.action import ActionEngine
            from zenskill.systems.gtd.inbox import InboxEngine
            from zenskill.systems.gtd.project import ProjectEngine
        except Exception:
            self.console.print("[yellow]GTD 引擎不可用[/yellow]")
            return

        # Inbox（未处理条目）
        inbox_count = 0
        try:
            inbox_count = InboxEngine().count_pending()
        except Exception:
            pass

        # Actions（未完成，按创建时间倒序）
        actions = []
        try:
            for a in ActionEngine().list_pending(limit=15):
                actions.append({
                    "id": a.id,
                    "title": a.title or "?",
                    "status": a.status or "pending",
                    "priority": a.priority or "P2",
                    "energy": a.energy_required,
                })
        except Exception:
            pass

        # Projects（活跃）
        projects = []
        try:
            for p in ProjectEngine().list_active(limit=5):
                projects.append({
                    "id": p.id,
                    "name": p.name or "?",
                    "progress": 0,
                })
        except Exception:
            pass

        # 概览卡片
        summary = (
            f"📥 Inbox: [bold]{inbox_count}[/bold]  │  "
            f"📋 Actions: [bold]{len(actions)}[/bold]  │  "
            f"📁 Projects: [bold]{len(projects)}[/bold]"
        )
        self.console.print(Panel(summary, title="✅ GTD 概览", border_style="green"))

        # Actions 表格
        if actions:
            table = Table(title="📋 待办 Actions", show_lines=False)
            table.add_column("状态", width=4)
            table.add_column("标题", width=40)
            table.add_column("优先级", width=8)
            table.add_column("精力", width=6)

            for a in actions:
                icon = {"pending": "⏳", "next": "🔄", "delegated": "📨",
                        "incubating": "🌱"}.get(a["status"], "·")
                priority_style = {
                    "P0": "bold red", "P1": "red", "P2": "yellow", "P3": "dim"
                }.get(a["priority"], "")
                energy_label = {3: "easy", 5: "medium", 8: "hard",
                                10: "extreme"}.get(a["energy"], str(a["energy"]))
                table.add_row(
                    icon,
                    a["title"][:40],
                    f"[{priority_style}]{a['priority']}[/{priority_style}]" if priority_style else a["priority"],
                    energy_label,
                )
            self.console.print(table)
        else:
            self.console.print("[dim]📭 Inbox 为空，无待办 Actions[/dim]")

        # Projects
        if projects:
            self.console.print()
            table = Table(title="📁 活跃项目", show_lines=False)
            table.add_column("项目", width=30)
            table.add_column("进度", width=20)
            table.add_column("%", width=5)

            for p in projects:
                progress = p.get("progress", 0) or 0
                bar = "█" * (progress // 5) + "░" * (20 - progress // 5)
                table.add_row(p["name"][:30], bar, f"{progress}%")
            self.console.print(table)

        # 快捷命令提示
        self.console.print()
        self.console.print("[dim]命令: /gtd inbox add | /gtd action add | /gtd project create | /gtd weekly-review[/dim]")
