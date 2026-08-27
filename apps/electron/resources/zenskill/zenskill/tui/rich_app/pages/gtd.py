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
            from zenskill.core.database import db
        except Exception:
            self.console.print("[yellow]数据库不可用[/yellow]")
            return

        # Inbox
        inbox_count = 0
        try:
            rows = db.execute("SELECT count(*) as c FROM gtd_inbox")
            inbox_count = rows[0]["c"] if rows else 0
        except Exception:
            pass

        # Actions
        actions = []
        try:
            rows = db.execute(
                "SELECT * FROM gtd_actions WHERE status != 'done' ORDER BY created_at DESC LIMIT 15"
            )
            for r in rows:
                actions.append({
                    "id": r.get("id", ""),
                    "title": r.get("title", "?"),
                    "status": r.get("status", "todo"),
                    "priority": r.get("priority", "medium"),
                    "energy": r.get("energy", "medium"),
                })
        except Exception:
            pass

        # Projects
        projects = []
        try:
            rows = db.execute(
                "SELECT * FROM gtd_projects WHERE status = 'active' ORDER BY created_at DESC LIMIT 5"
            )
            for r in rows:
                projects.append({
                    "id": r.get("id", ""),
                    "name": r.get("name", "?"),
                    "progress": r.get("progress", 0),
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
                icon = {"todo": "⏳", "in_progress": "🔄", "blocked": "🚫"}.get(a["status"], "·")
                priority_style = {
                    "high": "bold red", "medium": "yellow", "low": "dim"
                }.get(a["priority"], "")
                table.add_row(
                    icon,
                    a["title"][:40],
                    f"[{priority_style}]{a['priority']}[/{priority_style}]" if priority_style else a["priority"],
                    a["energy"],
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
