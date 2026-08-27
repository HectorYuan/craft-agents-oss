"""
成长数据导出 (7N)

生成 Markdown/JSON 格式的成长报告，支持周报、月报和自定义时间范围。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


class GrowthExporter:
    """成长数据导出器"""

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id

    def export_markdown(self, period: str = "week", output_dir: Optional[str] = None) -> str:
        """导出 Markdown 成长报告

        Args:
            period: week/month/all
            output_dir: 输出目录（None 则返回字符串）

        Returns:
            Markdown 内容或文件路径
        """
        report = self._build_markdown_report(period)
        if output_dir:
            out = Path(output_dir) / f"zenskill_report_{period}_{datetime.now():%Y%m%d}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(report)
            return str(out)
        return report

    def export_json(self, output_dir: Optional[str] = None) -> str:
        """导出 JSON 结构化数据"""
        data = self._collect_all_data()
        if output_dir:
            out = Path(output_dir) / f"zenskill_data_{datetime.now():%Y%m%d}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            return str(out)
        return json.dumps(data, ensure_ascii=False, indent=2)

    # ═══════════════════════════════════════════════
    # Internal
    # ═══════════════════════════════════════════════

    def _build_markdown_report(self, period: str) -> str:
        state = self._get_skill_state()
        scores = self._get_ability_scores()
        goals = self._get_active_goals()
        insights = self._get_insights()
        mem = self._get_memory_stats()

        level = state.get("level", "NOVICE")
        usage = state.get("usage_count", 0)
        now = datetime.now()

        lines = [
            f"# ZenSkill 成长报告",
            f"",
            f"> {now:%Y-%m-%d %H:%M} | 技能: {self.skill_id} | 境界: {level}",
            f"",
            f"---",
            f"",
            f"## 五维能力",
            f"",
        ]

        # 五维雷达数据
        if scores:
            dims = ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
            names = {"proficiency": "熟练度", "stability": "稳定性", "satisfaction": "满意度",
                     "responsiveness": "响应力", "memory": "记忆度"}
            for dim in dims:
                score = scores.get(dim, 0) if isinstance(scores, dict) else getattr(scores, dim, 0)
                bar_w = 20
                filled = int(score / 100 * bar_w)
                bar = "█" * filled + "░" * (bar_w - filled)
                lines.append(f"- {names.get(dim, dim):6s} [{bar}] {score}")
            lines.append("")

        # 活跃目标
        lines.append("## 活跃目标")
        lines.append("")
        if goals:
            for g in goals:
                lines.append(f"- **{g.dimension}**: {g.current_score}→{g.target_score} ({g.status})")
        else:
            lines.append("_暂无活跃目标_")
        lines.append("")

        # 洞察
        lines.append("## 最近洞察")
        lines.append("")
        if insights:
            for ins in insights[:3]:
                icon = {"celebration": "🎉", "warning": "⚠️", "bottleneck": "🔍"}.get(
                    getattr(ins, "type", ""), "💡")
                lines.append(f"- {icon} [{getattr(ins, 'level', '?')}] {ins.title}")
        else:
            lines.append("_暂无新洞察_")
        lines.append("")

        # 记忆
        lines.append("## 记忆统计")
        lines.append("")
        lines.append(f"- 总记忆: {mem.get('total', 0)} 条")
        lines.append(f"- 使用次数: {usage}")
        lines.append(f"- 境界: {level}")
        lines.append("")

        # 下一步建议
        lines.append("## 下一步建议")
        lines.append("")
        lines.append(f"1. 查看完整状态: `zenskill skill info`")
        lines.append(f"2. 生成新目标: `zenskill goal suggest`")
        lines.append(f"3. 查看洞察: `zenskill insight unread`")
        lines.append(f"4. 运行诊断: `zenskill doctor`")
        lines.append("")

        lines.append("---")
        lines.append(f"_由 ZenSkill v{self._get_version()} 自动生成_")

        return "\n".join(lines)

    def _collect_all_data(self) -> Dict[str, Any]:
        state = self._get_skill_state()
        return {
            "skill_id": self.skill_id,
            "level": state.get("level", "NOVICE"),
            "usage_count": state.get("usage_count", 0),
            "ability_scores": self._get_ability_scores_raw(),
            "active_goals": len(self._get_active_goals()),
            "insights": self._get_insights_count(),
            "memory": self._get_memory_stats(),
            "exported_at": datetime.now().isoformat(),
        }

    def _get_skill_state(self) -> Dict:
        try:
            from zenskill.core.paths import SkillStateManager
            return SkillStateManager(self.skill_id).load()
        except Exception:
            return {}

    def _get_ability_scores(self) -> Any:
        try:
            from zenskill.systems.visualization.ability_calculator import AbilityCalculator
            from zenskill.systems.visualization.metrics_store import MetricsStore
            from zenskill.core.paths import SkillStateManager
            state = self._get_skill_state()
            store = MetricsStore(self.skill_id)
            snapshots = store.get_all_snapshots()
            calculator = AbilityCalculator()
            if snapshots:
                return snapshots[-1].ability_scores
        except Exception:
            pass
        return {}

    def _get_ability_scores_raw(self) -> Dict:
        scores = self._get_ability_scores()
        if hasattr(scores, '__dict__'):
            return {k: v for k, v in scores.__dict__.items() if not k.startswith('_')}
        return scores if isinstance(scores, dict) else {}

    def _get_active_goals(self) -> List:
        try:
            from zenskill.systems.active.goal_engine import ActiveGoalEngine
            return ActiveGoalEngine(self.skill_id).get_active_goals()
        except Exception:
            return []

    def _get_insights(self) -> List:
        try:
            from zenskill.systems.active.proactive_insight import ProactiveInsightEngine
            return ProactiveInsightEngine(self.skill_id).get_unread_insights()
        except Exception:
            return []

    def _get_insights_count(self) -> int:
        return len(self._get_insights())

    def _get_memory_stats(self) -> Dict:
        state = self._get_skill_state()
        return {"total": len(state.get("episodes", []))}

    def _get_version(self) -> str:
        try:
            from zenskill import __version__
            return __version__
        except Exception:
            return "?"
