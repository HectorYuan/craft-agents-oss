"""
ZenSkill - 主动洞察推送系统

不需要用户手动触发，系统在检测到重要模式或问题时主动推送洞察：
- 成长瓶颈检测
- 里程碑达成提醒
- 模式突变检测
- 异常检测（成功率下降等）
- 黄金时刻的深度洞察
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from zenskill.core.paths import get_user_data_dir
from zenskill.systems.visualization.metrics_store import MetricsStore, MetricSnapshot
from zenskill.systems.visualization.ability_calculator import AbilityCalculator


@dataclass
class ProactiveInsight:
    """主动洞察"""
    insight_id: str
    type: str  # celebration / warning / info / bottleneck
    level: str  # low / medium / high / critical
    title: str
    content: str
    data_evidence: Dict[str, Any]
    created_at: str
    is_read: bool = False

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProactiveInsight":
        """从字典创建洞察"""
        return cls(
            insight_id=data.get("insight_id", ""),
            type=data.get("type", "info"),
            level=data.get("level", "low"),
            title=data.get("title", ""),
            content=data.get("content", ""),
            data_evidence=data.get("data_evidence", {}),
            created_at=data.get("created_at", ""),
            is_read=data.get("is_read", False),
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return asdict(self)


class ProactiveInsightEngine:
    """主动洞察引擎

    在每次交互后检测并生成洞察，在用户下次访问时主动推送。
    """

    # 洞察类型图标
    TYPE_ICONS = {
        "celebration": "🎉",
        "warning": "⚠️",
        "info": "ℹ️",
        "bottleneck": "🔧",
        "anomaly": "🚨",
        "milestone": "🏆",
    }

    # 境界阈值（用于里程碑检测）
    LEVEL_THRESHOLDS = {
        10: "APPRENTICE",
        50: "ADEPT",
        200: "EXPERT",
        500: "MASTER",
    }

    def __init__(self, skill_id: str = "zenskill-core"):
        self.skill_id = skill_id
        self.metrics_store = MetricsStore(skill_id)
        self.ability_calculator = AbilityCalculator()
        self.insights_dir = self._get_insights_dir()
        self.insights_file = self.insights_dir / f"{skill_id}_insights.jsonl"

    def _get_insights_dir(self) -> Path:
        """获取洞察存储目录"""
        user_dir = get_user_data_dir()
        insights_dir = user_dir / "insights"
        insights_dir.mkdir(parents=True, exist_ok=True)
        return insights_dir

    def _generate_insight_id(self) -> str:
        """生成唯一的洞察ID"""
        timestamp = int(time.time() * 1000)
        return f"insight_{timestamp}_{self.skill_id}"

    def _save_insight(self, insight: ProactiveInsight) -> None:
        """保存洞察到文件"""
        with open(self.insights_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(insight.to_dict(), ensure_ascii=False) + "\n")

    def check_and_generate_insights(self, state: Optional[Dict[str, Any]] = None) -> List[ProactiveInsight]:
        """
        检查当前状态并生成新的洞察

        Args:
            state: 当前技能状态（可选，自动加载）

        Returns:
            新生成的洞察列表
        """
        snapshots = self.metrics_store.get_all_snapshots()

        # 数据不足时不生成洞察
        if len(snapshots) < 2:
            return []

        new_insights = []

        # 1. 检查里程碑达成
        milestone_insights = self._check_milestones(snapshots)
        new_insights.extend(milestone_insights)

        # 2. 检查成长瓶颈
        bottleneck_insights = self._check_bottlenecks(snapshots)
        new_insights.extend(bottleneck_insights)

        # 3. 检查异常
        anomaly_insights = self._check_anomalies(snapshots)
        new_insights.extend(anomaly_insights)

        # 4. 检查快速成长（正面洞察）
        growth_insights = self._check_rapid_growth(snapshots)
        new_insights.extend(growth_insights)

        # 去重：检查是否已经有相同类型的未读洞察
        existing_unread = self.get_unread_insights()
        existing_types = set(i.type for i in existing_unread)
        new_insights = [i for i in new_insights if i.type not in existing_types]

        # 保存新洞察
        for insight in new_insights:
            self._save_insight(insight)

        return new_insights

    def _check_milestones(self, snapshots: List[MetricSnapshot]) -> List[ProactiveInsight]:
        """检查里程碑达成"""
        insights = []
        latest = snapshots[-1]
        previous = snapshots[-2] if len(snapshots) >= 2 else None

        if not previous:
            return insights

        # 检查境界突破
        prev_level = previous.level
        curr_level = latest.level
        if prev_level != curr_level:
            insights.append(ProactiveInsight(
                insight_id=self._generate_insight_id(),
                type="milestone",
                level="high",
                title=f"🏆 恭喜达到【{curr_level}】境界！",
                content=f"你的技能已经从 {prev_level} 提升到 {curr_level}！这是一个重要的里程碑，继续加油！",
                data_evidence={
                    "previous_level": prev_level,
                    "current_level": curr_level,
                    "interaction_count": latest.interaction_count,
                },
                created_at=datetime.now().isoformat(),
                is_read=False,
            ))

        # 检查 10 分的整数倍分数达成
        for dim, score in latest.ability_scores.items():
            if dim == "composite":
                continue
            prev_score = previous.ability_scores.get(dim, 0)
            # 如果跨越了 10 的倍数
            if prev_score // 10 < score // 10 and score >= 10:
                milestone = (score // 10) * 10
                dim_name = {
                    "proficiency": "熟练度",
                    "stability": "稳定性",
                    "satisfaction": "满意度",
                    "responsiveness": "响应力",
                    "memory": "记忆力",
                }.get(dim, dim)
                insights.append(ProactiveInsight(
                    insight_id=self._generate_insight_id(),
                    type="celebration",
                    level="low",
                    title=f"🎊 {dim_name}达到 {milestone} 分！",
                    content=f"你的 {dim_name} 从 {prev_score} 提升到了 {score} 分，达到 {milestone} 分里程碑！",
                    data_evidence={
                        "dimension": dim,
                        "previous_score": prev_score,
                        "current_score": score,
                        "milestone": milestone,
                    },
                    created_at=datetime.now().isoformat(),
                    is_read=False,
                ))

        return insights

    def _check_bottlenecks(self, snapshots: List[MetricSnapshot]) -> List[ProactiveInsight]:
        """检查成长瓶颈（连续多个采样点无提升）"""
        insights = []

        if len(snapshots) < 4:
            return insights

        # 检查最近 3 个采样点，每个维度是否停滞
        for dim in ["proficiency", "stability", "satisfaction", "responsiveness", "memory"]:
            recent_scores = [s.ability_scores.get(dim, 0) for s in snapshots[-4:]]

            # 如果最近 3 个采样点分数相同（停滞）
            if len(set(recent_scores)) == 1 and recent_scores[0] < 90:
                dim_name = {
                    "proficiency": "熟练度",
                    "stability": "稳定性",
                    "satisfaction": "满意度",
                    "responsiveness": "响应力",
                    "memory": "记忆力",
                }.get(dim, dim)

                # 给出瓶颈提醒
                suggestions = {
                    "proficiency": "建议增加使用频次，每天固定时间练习",
                    "stability": "建议将复杂任务拆分为小步骤，提高成功率",
                    "satisfaction": "建议每次交互后反思输出质量，思考如何改进",
                    "responsiveness": "建议使用更简洁明确的指令，减少歧义",
                    "memory": "建议多使用记忆功能，记录重要信息",
                }

                insights.append(ProactiveInsight(
                    insight_id=self._generate_insight_id(),
                    type="bottleneck",
                    level="medium",
                    title=f"🔧 检测到 {dim_name} 成长瓶颈",
                    content=f"你的 {dim_name} 在最近 {len(recent_scores)} 个采样周期内保持在 {recent_scores[0]} 分，没有明显提升。{suggestions.get(dim, '')}",
                    data_evidence={
                        "dimension": dim,
                        "recent_scores": recent_scores,
                        "current_score": recent_scores[-1],
                        "stagnant_count": len(recent_scores),
                    },
                    created_at=datetime.now().isoformat(),
                    is_read=False,
                ))

        return insights

    def _check_anomalies(self, snapshots: List[MetricSnapshot]) -> List[ProactiveInsight]:
        """检测异常情况（如成功率大幅下降）"""
        insights = []

        if len(snapshots) < 3:
            return insights

        # 检查成功率变化
        recent_success_rates = [s.success_rate for s in snapshots[-5:]]
        avg_early = sum(recent_success_rates[:-2]) / max(1, len(recent_success_rates[:-2]))
        avg_late = sum(recent_success_rates[-2:]) / 2 if len(recent_success_rates) >= 2 else 0

        if avg_late < avg_early * 0.7 and avg_early > 0.5:
            # 成功率下降超过 30%
            insights.append(ProactiveInsight(
                insight_id=self._generate_insight_id(),
                type="anomaly",
                level="high",
                title="🚨 检测到成功率下降",
                content=f"最近的任务成功率从前 {len(recent_success_rates[:-2])} 个采样点的平均 {avg_early:.1%} 下降到最近 2 个采样点的 {avg_late:.1%}。建议回顾最近的任务，找出问题所在。",
                data_evidence={
                    "previous_success_rate": avg_early,
                    "recent_success_rate": avg_late,
                    "drop_percent": (avg_early - avg_late) / max(0.01, avg_early),
                },
                created_at=datetime.now().isoformat(),
                is_read=False,
            ))

        return insights

    def _check_rapid_growth(self, snapshots: List[MetricSnapshot]) -> List[ProactiveInsight]:
        """检测快速成长，给予正面鼓励"""
        insights = []

        if len(snapshots) < 5:
            return insights

        # 检查综合能力增长
        recent = snapshots[-5:]
        start_composite = recent[0].ability_scores.get("composite", 0)
        end_composite = recent[-1].ability_scores.get("composite", 0)
        growth = end_composite - start_composite

        if growth >= 10:
            insights.append(ProactiveInsight(
                insight_id=self._generate_insight_id(),
                type="celebration",
                level="medium",
                title="🌟 成长非常迅速！",
                content=f"在最近 5 个采样周期内，你的综合能力从 {start_composite} 分提升到 {end_composite} 分，增长了 {growth} 分！继续保持这个势头！",
                data_evidence={
                    "start_composite": start_composite,
                    "end_composite": end_composite,
                    "growth": growth,
                    "period_samples": 5,
                },
                created_at=datetime.now().isoformat(),
                is_read=False,
            ))

        return insights

    def get_all_insights(self, limit: Optional[int] = None) -> List[ProactiveInsight]:
        """
        获取所有洞察

        Args:
            limit: 限制返回数量（最近 N 条）

        Returns:
            洞察列表
        """
        # 边界检查
        if limit is not None and (not isinstance(limit, int) or limit < 1):
            limit = None

        if not self.insights_file.exists():
            return []

        insights = []
        with open(self.insights_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        insights.append(ProactiveInsight.from_dict(data))
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

        if limit:
            insights = insights[-limit:]

        return insights

    def get_unread_insights(self) -> List[ProactiveInsight]:
        """获取所有未读洞察"""
        return [i for i in self.get_all_insights() if not i.is_read]

    def mark_as_read(self, insight_id: str) -> bool:
        """
        标记洞察为已读

        Args:
            insight_id: 洞察ID

        Returns:
            是否成功标记
        """
        insights = self.get_all_insights()
        found = False

        temp_file = self.insights_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for insight in insights:
                if insight.insight_id == insight_id:
                    insight.is_read = True
                    found = True
                f.write(json.dumps(insight.to_dict(), ensure_ascii=False) + "\n")

        if found:
            temp_file.rename(self.insights_file)
        else:
            temp_file.unlink(missing_ok=True)

        return found

    def mark_all_as_read(self) -> int:
        """
        标记所有洞察为已读

        Returns:
            标记的洞察数量
        """
        insights = self.get_all_insights()
        count = 0

        temp_file = self.insights_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            for insight in insights:
                if not insight.is_read:
                    insight.is_read = True
                    count += 1
                f.write(json.dumps(insight.to_dict(), ensure_ascii=False) + "\n")

        temp_file.rename(self.insights_file)
        return count

    def get_insights_by_type(self, insight_type: str) -> List[ProactiveInsight]:
        """
        按类型筛选洞察

        Args:
            insight_type: 洞察类型

        Returns:
            该类型的所有洞察
        """
        all_insights = self.get_all_insights()
        return [i for i in all_insights if i.type == insight_type]

    def generate_summary_report(self, include_read: bool = False) -> str:
        """
        生成洞察摘要报告

        Args:
            include_read: 是否包含已读洞察

        Returns:
            格式化的报告字符串
        """
        insights = self.get_unread_insights() if not include_read else self.get_all_insights()

        lines = []
        lines.append("💡 主动洞察摘要")
        lines.append("═" * 60)
        lines.append("")

        if not insights:
            lines.append("   暂无新洞察，继续使用会自动生成！")
            lines.append("")
            return "\n".join(lines)

        # 按类型分组
        by_type: Dict[str, List[ProactiveInsight]] = {}
        for insight in insights:
            if insight.type not in by_type:
                by_type[insight.type] = []
            by_type[insight.type].append(insight)

        # 显示各类型统计
        type_names = {
            "milestone": "里程碑",
            "celebration": "成就庆祝",
            "bottleneck": "瓶颈提醒",
            "anomaly": "异常警告",
            "info": "信息通知",
        }

        lines.append("📊 洞察统计:")
        for t, items in by_type.items():
            icon = self.TYPE_ICONS.get(t, "•")
            name = type_names.get(t, t)
            lines.append(f"   {icon} {name}: {len(items)} 条")
        lines.append("")

        # 显示详细内容（按重要程度排序）
        priority_order = ["anomaly", "milestone", "bottleneck", "celebration", "info"]
        insights_sorted = sorted(
            insights,
            key=lambda x: priority_order.index(x.type) if x.type in priority_order else 99
        )

        lines.append("🎯 详细洞察:")
        lines.append("")
        for insight in insights_sorted[:10]:  # 最多显示 10 条
            icon = self.TYPE_ICONS.get(insight.type, "•")
            lines.append(f"   {icon} {insight.title}")
            lines.append(f"      {insight.content}")
            lines.append(f"      ID: {insight.insight_id}")
            lines.append("")

        if len(insights) > 10:
            lines.append(f"   ... 还有 {len(insights) - 10} 条未显示")
            lines.append("")

        lines.append("💡 使用 'python -m zenskill insight read <ID>' 标记为已读")

        return "\n".join(lines)
