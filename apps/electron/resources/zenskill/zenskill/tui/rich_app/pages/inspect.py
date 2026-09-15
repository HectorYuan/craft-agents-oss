"""技能详情页面 -- /inspect <skill_id> 或 /skills inspect。

展示五维雷达 + 境界 + 统计。不需要独立路由注册——/inspect 命令
直接在 _handle_command 中调用此 render。
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ...data import TuiDataAdapter

_LEVEL_ICONS = {
    "NOVICE": ("🌱", "新手"),
    "APPRENTICE": ("🌿", "学徒"),
    "JOURNEYMAN": ("🌳", "匠人"),
    "EXPERT": ("⭐", "专家"),
    "MASTER": ("👑", "大师"),
}

_DIMS = [
    ("proficiency", "熟练度"),
    ("stability", "稳定性"),
    ("satisfaction", "满意度"),
    ("responsiveness", "响应力"),
    ("memory", "记忆力"),
]


class InspectPage:
    """技能详情页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, skill_id: str = "", **kwargs) -> None:
        """渲染技能详情。"""
        if not skill_id:
            skill_id = "zenskill-core"

        state = self.data.get_skill_state(skill_id)
        scores = self.data.get_ability_scores(skill_id)
        name = state.get("skill_name", skill_id)
        level = state.get("level", "NOVICE")
        icon = _LEVEL_ICONS.get(level, (".", level))
        usage = state.get("usage_count", 0)
        success_rate = state.get("metrics", {}).get("success_rate", 0)

        # 标题
        self.console.print(Panel(
            f"{icon[0]} {name}  [{level}]  {icon[1]}",
            title=f"📖 技能详情 -- {skill_id}",
            border_style="cyan",
        ))

        # 五维雷达
        if scores:
            self.console.print("[bold]五维能力[/bold]")
            for attr, label in _DIMS:
                val = getattr(scores, attr, 0)
                bar = "█" * (val // 10) + "░" * (10 - val // 10)
                self.console.print(f"  {label:6s} {bar} {val}")
            self.console.print(f"  综合: [bold]{scores.composite}[/bold]")
        else:
            self.console.print("[dim]无能力数据[/dim]")

        # 统计
        self.console.print()
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="bold")
        table.add_column("Value")
        table.add_row("使用次数", str(usage))
        table.add_row("成功率", f"{success_rate:.0%}" if success_rate else "-")
        self.console.print(table)
