"""技能列表页面 -- /skills 命令。"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class SkillsPage:
    """技能列表页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染技能列表。"""
        skills = self.data.list_skills()

        if not skills:
            self.console.print(Panel(
                "[yellow]暂无技能数据[/yellow]\n"
                "使用 [bold]zenskill install npx://<pkg>[/bold] 安装技能",
                title="📚 技能列表",
                border_style="yellow",
            ))
            return

        table = Table(title=f"📚 技能列表 ({len(skills)} 个)", show_lines=False)
        table.add_column("#", style="dim", width=4)
        table.add_column("技能 ID", style="cyan", width=20)
        table.add_column("等级", width=12)
        table.add_column("使用次数", width=10)
        table.add_column("成功率", width=10)
        table.add_column("最后使用", width=12)

        for i, s in enumerate(skills, 1):
            level = s.get("level", "NOVICE")
            icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                    "EXPERT": "⭐", "MASTER": "👑"}.get(level, "")
            rate = s.get("success_rate", 0)
            last_used = s.get("last_used", "")
            if last_used and len(last_used) > 10:
                last_used = last_used[:10]

            table.add_row(
                str(i),
                s.get("skill_id", ""),
                f"{icon} {level}",
                str(s.get("usage_count", 0)),
                f"{rate:.0%}" if rate else "-",
                last_used or "-",
            )

        self.console.print(table)
