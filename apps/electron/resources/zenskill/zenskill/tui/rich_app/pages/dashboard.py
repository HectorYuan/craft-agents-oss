"""仪表盘页面 -- /dashboard 命令。

从 screens/dashboard.py (348 行) 精简到 ~80 行。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter


class DashboardPage:
    """仪表盘页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, **kwargs) -> None:
        """渲染仪表盘。"""
        summary = self.data.get_dashboard_summary()

        # 核心指标卡片
        stats_text = (
            f"📊 今日使用: [bold]{summary['today_usage']}[/bold] 次  │  "
            f"🎯 活跃技能: [bold]{summary['active_skills']}[/bold] 个  │  "
            f"⏱ 会话时长: [bold]{summary['avg_session_min']}[/bold] 分钟  │  "
            f"📝 事件数: [bold]{summary['event_count']}[/bold]"
        )
        self.console.print(Panel(stats_text, title="📊 仪表盘", border_style="cyan"))

        # 感知告警
        alerts = summary.get("perception_alerts", [])
        if alerts:
            for alert in alerts[:3]:
                self.console.print(f"  [yellow]⚠ {alert}[/yellow]")

        # 技能表格
        skills = self.data.list_skills()
        if skills:
            table = Table(title="技能列表", show_lines=False)
            table.add_column("技能", style="cyan", width=20)
            table.add_column("等级", width=10)
            table.add_column("使用次数", width=10)
            table.add_column("成功率", width=10)

            for s in skills[:10]:
                level = s.get("level", "NOVICE")
                icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                        "EXPERT": "⭐", "MASTER": "👑"}.get(level, "")
                rate = s.get("success_rate", 0)
                table.add_row(
                    s.get("skill_id", ""),
                    f"{icon} {level}",
                    str(s.get("usage_count", 0)),
                    f"{rate:.0%}" if rate else "-",
                )

            self.console.print(table)
        else:
            self.console.print("[dim]暂无技能数据[/dim]")

        # 最近工具
        recent = summary.get("recent_tools", [])
        if recent:
            self.console.print(f"  [dim]最近工具: {', '.join(recent[-5:])}[/dim]")
