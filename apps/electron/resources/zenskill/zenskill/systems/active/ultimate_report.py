"""Ultimate growth report generator (7Z)."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ...core.paths import SkillStateManager, get_user_data_dir


class UltimateReportEngine:
    """终极成长报告引擎"""

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id

    def generate(self, period: str = "year", output_path: Optional[str] = None) -> str:
        """生成年度/季度/月度总结报告"""
        state = self._safe_get(self._get_state, {})
        scores = self._safe_get(self._get_scores, {})
        goals = self._safe_get(self._get_goals_summary, {})
        insights = self._safe_get(self._get_insights_summary, {})
        achievements = self._safe_get(self._get_achievements, [])
        habits = self._safe_get(self._get_habits, [])
        events = self._safe_get(self._get_event_count, 0)
        trends = self._safe_get(self._get_trends, "")

        now = datetime.now()
        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)
        period_label = {"year": "年度", "quarter": "季度", "month": "月度"}.get(period, "综合")

        dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        dim_names = {"proficiency": "熟练度", "stability": "稳定性", "satisfaction": "满意度",
                     "responsiveness": "响应力", "memory": "记忆度"}
        dim_icons = {"proficiency": "🎯", "stability": "🪨", "satisfaction": "😊",
                     "responsiveness": "⚡", "memory": "🧠"}

        lines = [
            f"# ZenSkill {period_label}成长报告",
            f"",
            f"> {now:%Y-%m-%d} | 技能: {self.skill_id} | 境界: **{level}**",
            f"",
            f"---",
            f"",
            f"## 📊 {period_label}概览",
            f"",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 当前境界 | {level} |",
            f"| 累计使用 | {usage} 次 |",
            f"| 记录事件 | {events} 条 |",
            f"| 获得成就 | {len(achievements)} 项 |",
            f"| 追踪习惯 | {len(habits)} 个 |",
        ]

        if goals:
            lines.append(f"| 达成目标 | {goals.get('completed', 0)} 个 |")
        lines.append("")

        # 五维雷达
        score_map = scores if isinstance(scores, dict) else {}
        if score_map:
            lines.append("## 五维能力")
            lines.append("")
            for dim in dims:
                val = score_map.get(dim, 0) if score_map else 0
                bar_w = 20
                filled = int(min(val, 100) / 100 * bar_w)
                bar = "█" * filled + "░" * (bar_w - filled)
                icon = dim_icons.get(dim, "  ")
                lines.append(f"- {icon} {dim_names.get(dim, dim):6s} [{bar}] {val}%")
            lines.append("")

        # 趋势
        if trends:
            lines.append("## 📈 成长趋势")
            lines.append("")
            lines.append(trends)
            lines.append("")

        # 成就墙
        if achievements:
            lines.append("## 🏆 成就墙")
            lines.append("")
            for a in achievements:
                name = a.get("name", "?") if isinstance(a, dict) else getattr(a, "name", "?")
                desc = a.get("description", "") if isinstance(a, dict) else getattr(a, "description", "")
                lines.append(f"- 🏅 **{name}**: {desc}")
            lines.append("")

        # 洞察摘要
        if insights and insights.get("total", 0) > 0:
            lines.append("## 💡 洞察摘要")
            lines.append("")
            lines.append(f"- 总洞察: {insights.get('total', 0)} 条")
            lines.append(f"- 未读: {insights.get('unread', 0)} 条")
            lines.append("")

        # 预测
        lines.append("## 🔮 下一阶段预测")
        lines.append("")
        if level in ("NOVICE", "APPRENTICE"):
            lines.append("- 预计 2-4 周内晋升至下一境界")
        elif level == "ADEPT":
            lines.append("- 预计 1-2 月内晋升至 EXPERT")
        elif level == "EXPERT":
            lines.append("- 预计 3-6 月内晋升至 MASTER")
        else:
            lines.append("- 已达最高境界，建议拓宽新技能领域")
        lines.append("")

        # 建议
        lines.append("## 🎯 建议行动")
        lines.append("")
        low_dims = sorted(
            [(dim, score_map.get(dim, 0)) for dim in dims if score_map.get(dim, 0) < 50],
            key=lambda x: x[1]
        ) if score_map else []
        if low_dims:
            d = low_dims[0]
            lines.append(f"1. 加强 **{dim_names.get(d[0], d[0])}** (当前 {d[1]}%) — 这是最弱维度")
        lines.append(f"2. 查看完整状态: `zenskill skill info`")
        lines.append(f"3. 生成新目标: `zenskill goal suggest`")
        lines.append(f"4. 导出此报告: `zenskill growth export`")
        lines.append("")

        lines.append("---")
        lines.append(f"_由 ZenSkill UltimateReport 自动生成_")

        report = "\n".join(lines)

        if output_path:
            Path(output_path).write_text(report, encoding="utf-8")
            return output_path
        return report

    @staticmethod
    def _safe_get(func, default):
        try:
            return func()
        except Exception:
            return default

    def _get_state(self) -> dict:
        return SkillStateManager(self.skill_id).load()

    def _get_scores(self) -> dict:
        from zenskill.systems.visualization.metrics_store import MetricsStore
        store = MetricsStore(self.skill_id)
        snap = store.get_latest_snapshot()
        return snap.ability_scores if snap and hasattr(snap, "ability_scores") else {}

    def _get_goals_summary(self) -> dict:
        from zenskill.systems.active.goal_engine import ActiveGoalEngine
        goals = ActiveGoalEngine(self.skill_id).get_active_goals()
        return {"active": len(goals), "completed": sum(1 for g in goals if g.status == "completed")}

    def _get_insights_summary(self) -> dict:
        from zenskill.systems.active.proactive_insight import ProactiveInsightEngine
        engine = ProactiveInsightEngine(self.skill_id)
        return {"total": len(engine.get_all_insights()), "unread": len(engine.get_unread_insights())}

    def _get_achievements(self) -> list:
        try:
            from zenskill.systems.active.achievement_system import AchievementSystem
            return AchievementSystem(self.skill_id).get_all_achievements()
        except Exception:
            return []

    def _get_habits(self) -> list:
        try:
            from zenskill.systems.active.habit_tracker import HabitTracker
            return HabitTracker(self.skill_id).get_all_habits()
        except Exception:
            return []

    def _get_event_count(self) -> int:
        try:
            from zenskill.mirroring.event_collector import EventCollector
            return EventCollector().get_event_count()
        except Exception:
            return 0

    def _get_trends(self) -> str:
        try:
            from zenskill.systems.active.growth_analyzer import GrowthAnalyzer
            return GrowthAnalyzer(self.skill_id).format_compare()
        except Exception:
            return ""
