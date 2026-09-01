"""成长中心页面 -- /growth 命令。"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from ...data import TuiDataAdapter


class GrowthPage:
    """成长中心页面。"""

    def __init__(self, console: Console, data: TuiDataAdapter):
        self.console = console
        self.data = data

    def render(self, action: str = "show", skill_id: str = None, **kwargs) -> None:
        """渲染成长中心。

        action: show / report / compare / replay / errors / feedback
        """
        skill_id = skill_id or "zenskill-core"

        if action in ("show", "report"):
            self._render_report(skill_id)
        elif action == "compare":
            self._render_compare(skill_id)
        elif action == "replay":
            self._render_replay(skill_id)
        elif action == "errors":
            self._render_errors(skill_id)
        elif action == "feedback":
            self._render_feedback(skill_id)
        else:
            self._render_report(skill_id)

    def _render_report(self, skill_id: str):
        """渲染成长报告。"""
        report = self.data.get_growth_report(skill_id)
        self.console.print(Panel(
            report,
            title=f"📈 成长报告 -- {skill_id}",
            border_style="green",
        ))

        # 能力分数
        scores = self.data.get_ability_scores(skill_id)
        if scores:
            dims = [
                ("理解力", getattr(scores, "comprehension", 0)),
                ("应用力", getattr(scores, "application", 0)),
                ("创造力", getattr(scores, "creativity", 0)),
                ("协作力", getattr(scores, "collaboration", 0)),
                ("持久力", getattr(scores, "persistence", 0)),
            ]
            bars = []
            for name, val in dims:
                bar = "█" * (val // 10) + "░" * (10 - val // 10)
                bars.append(f"  {name}: {bar} {val}")
            self.console.print("\n".join(bars))

        # 活跃目标
        goals = self.data.get_active_goals(skill_id)
        if goals:
            self.console.print(f"\n[bold]活跃目标 ({len(goals)}):[/bold]")
            for g in goals[:5]:
                dim = getattr(g, "dimension", "?")
                target = getattr(g, "target_score", "?")
                self.console.print(f"  🎯 {dim} → {target}")

    def _render_compare(self, skill_id: str):
        result = self.data.get_growth_compare(skill_id)
        self.console.print(Panel(result, title="📊 成长对比", border_style="blue"))

    def _render_replay(self, skill_id: str):
        result = self.data.get_growth_replay(skill_id)
        self.console.print(Panel(result, title="⏪ 成长回放", border_style="magenta"))

    def _render_errors(self, skill_id: str):
        result = self.data.get_error_clusters(skill_id)
        self.console.print(Panel(result, title="🔍 错误聚类", border_style="red"))

    def _render_feedback(self, skill_id: str):
        result = self.data.get_instant_feedback(skill_id)
        self.console.print(Panel(result, title="⚡ 即时反馈", border_style="yellow"))
