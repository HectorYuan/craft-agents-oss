"""
ZenSkill - 智能成长洞察引擎

基于历史数据分析，提供有价值的洞察和建议：
- 成长速度分析
- 瓶颈识别
- 里程碑预测
- 个性化建议
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from zenskill.systems.visualization.metrics_store import MetricsStore, MetricSnapshot
from zenskill.systems.visualization.charts import ASCIICharts


@dataclass
class Insight:
    """单个洞察"""
    type: str  # "positive" | "warning" | "info" | "suggestion"
    title: str
    content: str
    evidence: str  # 数据依据


class GrowthInsightEngine:
    """成长洞察引擎"""

    # 维度显示名称
    DIMENSION_NAMES = {
        "proficiency": "熟练度",
        "stability": "稳定性",
        "satisfaction": "满意度",
        "responsiveness": "响应力",
        "memory": "记忆力",
        "composite": "综合能力",
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.metrics_store = MetricsStore(skill_id)
        self.skill_id = skill_id

    def generate_insight_report(
        self,
        brief: bool = False,
    ) -> str:
        """
        生成完整的洞察报告

        Args:
            brief: 是否生成精简版

        Returns:
            洞察报告字符串
        """
        # 边界检查
        if not isinstance(brief, bool):
            brief = bool(brief)

        snapshots = self.metrics_store.get_all_snapshots()

        if len(snapshots) < 2:
            return self._generate_insufficient_data_msg()

        insights = []

        # 1. 成长速度分析
        insights.extend(self._analyze_growth_speed(snapshots))

        # 2. 最快/最慢增长维度
        insights.extend(self._analyze_dimension_growth(snapshots))

        # 3. 瓶颈识别
        insights.extend(self._identify_bottlenecks(snapshots))

        # 4. 里程碑预测
        insights.extend(self._predict_milestones(snapshots))

        # 5. 个性化建议
        if not brief:
            insights.extend(self._generate_suggestions(snapshots))

        # 格式化输出
        return self._format_report(insights, snapshots, brief)

    def _generate_insufficient_data_msg(self) -> str:
        """数据不足时的提示消息"""
        lines = []
        lines.append("🔍 成长洞察")
        lines.append("═" * 50)
        lines.append("")
        lines.append("📊 数据正在积累中，继续使用 ZenSkill:")
        lines.append("")
        lines.append("   • 每 5 次交互记录一次成长数据")
        lines.append("   • 至少需要 2 个采样点才能生成洞察")
        lines.append("   • 当前已有: {} 个采样点".format(self.metrics_store.get_snapshot_count()))
        lines.append("")
        lines.append("💡 建议：继续使用，积累更多成长数据！")

        return "\n".join(lines)

    def _analyze_growth_speed(self, snapshots: List[MetricSnapshot]) -> List[Insight]:
        """分析成长速度"""
        insights = []

        # 边界检查
        if not isinstance(snapshots, list) or len(snapshots) < 3:
            return insights

        # 对比最近几次采样的综合得分
        recent = snapshots[-5:]
        composite_scores = []
        for s in recent:
            try:
                score = s.ability_scores.get("composite", 0)
                if isinstance(score, (int, float)):
                    composite_scores.append(int(score))
                else:
                    composite_scores.append(0)
            except Exception:
                composite_scores.append(0)

        if len(composite_scores) >= 3:
            # 计算增长速度
            first = composite_scores[0]
            last = composite_scores[-1]
            total_growth = last - first
            growth_rate = total_growth / len(recent)

            if growth_rate > 2:
                insights.append(Insight(
                    type="positive",
                    title="🚀 成长非常迅速",
                    content=f"综合能力在最近 {len(recent)} 次采样中提升了 {total_growth} 分，平均每次增长 {growth_rate:.1f} 分",
                    evidence=f"综合得分从 {first} → {last}",
                ))
            elif growth_rate > 0.5:
                insights.append(Insight(
                    type="positive",
                    title="📈 稳步成长中",
                    content=f"综合能力保持稳定增长，趋势良好",
                    evidence=f"综合得分从 {first} → {last}，平均每次 +{growth_rate:.1f}",
                ))
            elif growth_rate > -1:
                insights.append(Insight(
                    type="info",
                    title="➡️ 成长进入平台期",
                    content=f"综合能力变化不大，可能进入技能巩固阶段",
                    evidence=f"综合得分波动在 {first} 分上下",
                ))
            else:
                insights.append(Insight(
                    type="warning",
                    title="⚠️ 成长出现停滞",
                    content=f"综合能力近期有所下降，建议回顾使用方式",
                    evidence=f"综合得分从 {first} → {last}，变化 {total_growth}",
                ))

        return insights

    def _analyze_dimension_growth(self, snapshots: List[MetricSnapshot]) -> List[Insight]:
        """分析各维度的增长情况"""
        insights = []

        # 边界检查
        if not isinstance(snapshots, list) or len(snapshots) < 2:
            return insights

        first = snapshots[0]
        last = snapshots[-1]

        dim_changes = []
        for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
            f_score = first.ability_scores.get(dim, 0)
            l_score = last.ability_scores.get(dim, 0)
            change = l_score - f_score
            dim_changes.append((dim, change, f_score, l_score))

        # 按变化量排序
        dim_changes.sort(key=lambda x: x[1], reverse=True)

        # 增长最快的维度
        best_dim, best_change, best_before, best_after = dim_changes[0]
        if best_change > 3:
            insights.append(Insight(
                type="positive",
                title=f"⭐ {self.DIMENSION_NAMES[best_dim]}是最大亮点",
                content=f"{self.DIMENSION_NAMES[best_dim]}是成长最快的维度",
                evidence=f"从 {best_before} 分提升到 {best_after} 分，+{best_change} 分",
            ))

        # 增长最慢的维度
        worst_dim, worst_change, worst_before, worst_after = dim_changes[-1]
        if worst_change < 0:
            insights.append(Insight(
                type="warning",
                title=f"📉 {self.DIMENSION_NAMES[worst_dim]}需要关注",
                content=f"{self.DIMENSION_NAMES[worst_dim]}出现了下降趋势",
                evidence=f"从 {worst_before} 分下降到 {worst_after} 分，{worst_change} 分",
            ))

        return insights

    def _identify_bottlenecks(self, snapshots: List[MetricSnapshot]) -> List[Insight]:
        """识别成长瓶颈"""
        insights = []

        # 边界检查
        if not isinstance(snapshots, list) or not snapshots:
            return insights

        latest = snapshots[-1]
        scores = latest.ability_scores if hasattr(latest, 'ability_scores') else {}

        # 找出得分最低的维度
        dim_scores = [
            (dim, scores.get(dim, 0))
            for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]
        ]
        dim_scores.sort(key=lambda x: x[1])

        lowest_dim, lowest_score = dim_scores[0]

        if lowest_score < 30:
            insights.append(Insight(
                type="warning",
                title=f"🔧 {self.DIMENSION_NAMES[lowest_dim]}是主要瓶颈",
                content=f"{self.DIMENSION_NAMES[lowest_dim]}得分偏低（{lowest_score}/100），建议重点加强",
                evidence=f"当前得分: {lowest_score}，低于其他维度平均水平",
            ))
        elif lowest_score < 50:
            insights.append(Insight(
                type="info",
                title=f"💡 {self.DIMENSION_NAMES[lowest_dim]}有提升空间",
                content=f"{self.DIMENSION_NAMES[lowest_dim]}是相对较弱的维度，可以通过使用提升",
                evidence=f"当前得分: {lowest_score}/100",
            ))

        return insights

    def _predict_milestones(self, snapshots: List[MetricSnapshot]) -> List[Insight]:
        """预测里程碑达成时间"""
        insights = []

        # 边界检查
        if not isinstance(snapshots, list) or len(snapshots) < 3:
            return insights

        latest = snapshots[-1]
        current_level = getattr(latest, 'level', 'NOVICE')

        # 境界阈值
        level_thresholds = {
            "NOVICE": ("APPRENTICE", 10),
            "APPRENTICE": ("ADEPT", 50),
            "ADEPT": ("EXPERT", 200),
            "EXPERT": ("MASTER", 500),
        }

        if current_level in level_thresholds:
            next_level, threshold = level_thresholds[current_level]
            current_count = latest.interaction_count

            # 计算还需要多少次
            remaining = max(0, threshold - current_count)

            # 计算最近的增长速度
            if len(snapshots) >= 2:
                period_start = snapshots[-min(5, len(snapshots))]
                period_interactions = current_count - period_start.interaction_count
                period_samples = len(snapshots) - snapshots.index(period_start)

                if period_interactions > 0 and period_samples > 0:
                    avg_per_sample = period_interactions / period_samples
                    estimated_samples = remaining / max(avg_per_sample, 1)

                    insights.append(Insight(
                        type="info",
                        title=f"🎯 距离【{next_level}】还有约 {remaining} 次交互",
                        content=f"按当前使用速度估算，还需 {int(estimated_samples)} 个采样周期",
                        evidence=f"当前 {current_count} 次，目标 {threshold} 次",
                    ))

        return insights

    def _generate_suggestions(self, snapshots: List[MetricSnapshot]) -> List[Insight]:
        """生成个性化建议"""
        insights = []

        # 边界检查
        if not isinstance(snapshots, list) or not snapshots:
            return insights

        latest = snapshots[-1]
        scores = getattr(latest, 'ability_scores', {})

        # 基于各维度得分给出具体建议
        suggestions = {
            "proficiency": (
                30,
                "💡 多使用积累经验",
                "熟练度主要来自使用频次，继续保持稳定的使用节奏即可快速提升"
            ),
            "stability": (
                50,
                "💡 提高任务成功率",
                "稳定性由任务成功率决定，建议将复杂任务拆分为小步骤执行"
            ),
            "satisfaction": (
                60,
                "💡 关注反馈质量",
                "满意度反映了输出质量，建议在每次交互后反思如何提升回答质量"
            ),
            "responsiveness": (
                70,
                "💡 优化响应速度",
                "响应力与平均响应时间相关，简洁明确的指令有助于更快获得响应"
            ),
            "memory": (
                40,
                "💡 多使用记忆功能",
                "记忆力通过记忆相关操作提升，建议多记录重要信息到情景记忆"
            ),
        }

        for dim, (threshold, title, content) in suggestions.items():
            score = scores.get(dim, 0)
            if score < threshold:
                insights.append(Insight(
                    type="suggestion",
                    title=title,
                    content=content,
                    evidence=f"当前 {self.DIMENSION_NAMES[dim]}得分: {score}/100，建议提升到 {threshold}+",
                ))

        return insights[:2]  # 最多显示 2 条建议

    def _format_report(
        self,
        insights: List[Insight],
        snapshots: List[MetricSnapshot],
        brief: bool,
    ) -> str:
        """格式化报告输出"""
        lines = []

        lines.append("🔍 成长洞察报告")
        lines.append("═" * 50)
        lines.append("")

        # 边界检查
        if not isinstance(snapshots, list) or not snapshots:
            lines.append("   暂无数据")
            return "\n".join(lines)

        # 摘要信息
        lines.append(f"📊 数据概况")
        lines.append(f"   • 采样点数: {len(snapshots)}")
        first_count = getattr(snapshots[0], 'interaction_count', 0)
        last_count = getattr(snapshots[-1], 'interaction_count', 0)
        first_level = getattr(snapshots[0], 'level', 'UNKNOWN')
        last_level = getattr(snapshots[-1], 'level', 'UNKNOWN')
        lines.append(f"   • 覆盖交互: {first_count} → {last_count}")
        lines.append(f"   • 境界变化: {first_level} → {last_level}")
        lines.append("")

        # 显示趋势火花线
        composite_scores = []
        for s in snapshots[-10:]:
            try:
                score = s.ability_scores.get("composite", 0)
                composite_scores.append(int(score) if isinstance(score, (int, float)) else 0)
            except Exception:
                composite_scores.append(0)
        sparkline = ASCIICharts.sparkline(composite_scores)
        lines.append(f"📈 成长趋势: {sparkline}")
        lines.append("")

        # 洞察分类
        type_icons = {
            "positive": "✅",
            "warning": "⚠️",
            "info": "ℹ️",
            "suggestion": "💡",
        }

        lines.append("🎯 核心洞察")
        lines.append("")

        for insight in insights:
            lines.append(f"{type_icons.get(insight.type, '•')} {insight.title}")
            lines.append(f"   {insight.content}")
            if not brief:
                lines.append(f"   数据依据: {insight.evidence}")
            lines.append("")

        # 总结
        if brief:
            lines.append("💡 使用 'zenskill growth insight' 查看完整报告")

        return "\n".join(lines)
