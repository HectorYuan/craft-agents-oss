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
        elif action == "achievements":
            self._render_achievements(skill_id)
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
            # 与 AbilityCalculator.DIMENSIONS 对齐（此前字段名错位恒显示 0）
            dims = [
                ("熟练度", getattr(scores, "proficiency", 0)),
                ("稳定性", getattr(scores, "stability", 0)),
                ("满意度", getattr(scores, "satisfaction", 0)),
                ("响应力", getattr(scores, "responsiveness", 0)),
                ("记忆力", getattr(scores, "memory", 0)),
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

    def _render_achievements(self, skill_id: str):
        """成就墙：已解锁徽章 + 接近解锁进度条。"""
        from ....systems.active.achievement_system import AchievementSystem

        data = AchievementSystem(skill_id).evaluate()
        unlocked = data["unlocked"]
        locked = data["locked"]

        lines = [f"🏅 解锁进度: {data['unlocked_count']}/{data['total']} ({data['completion_rate']:.0%})", ""]
        if unlocked:
            lines.append("[bold green]已解锁[/bold green]")
            for b in unlocked:
                lines.append(f"  {b.icon} [{b.tier}] {b.title} — [dim]{b.detail}[/dim]")
        if locked:
            lines.append("")
            lines.append("[bold]接近解锁[/bold]")
            for b in locked[:5]:
                filled = int(b.progress * 10)
                bar = "█" * filled + "░" * (10 - filled)
                lines.append(f"  {b.icon} {b.title} [{bar}] {b.progress:.0%}")
        self.console.print(Panel(
            "\n".join(lines),
            title=f"🏅 成就墙 -- {skill_id}",
            border_style="yellow",
        ))
