"""
ZenSkill - 五维能力计算器和 ASCII 雷达图

从技能统计数据中计算五个核心能力维度，
并生成漂亮的纯文本可视化展示。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from zenskill.systems.cultivating.skill_manifest import SkillManifest


@dataclass
class AbilityScores:
    """五维能力得分"""
    proficiency: int  # 熟练度: 交互次数决定
    stability: int    # 稳定性: 成功率决定
    satisfaction: int  # 满意度: 用户反馈评分
    responsiveness: int  # 响应力: 响应速度决定
    memory: int       # 记忆力: 记忆使用频率

    @property
    def composite(self) -> int:
        """综合能力得分（加权平均）"""
        weighted = (
            self.proficiency * 0.3
            + self.stability * 0.25
            + self.satisfaction * 0.2
            + self.responsiveness * 0.15
            + self.memory * 0.1
        )
        return round(weighted)


class AbilityCalculator:
    """五维能力计算器

    从 SkillStat 中计算出五个核心能力维度：
    - 熟练度: min(100, total_interactions / 5)
    - 稳定性: success_rate * 100
    - 满意度: user_feedback_score * 100
    - 响应力: max(0, 100 - avg_response_time_ms / 50)
    - 记忆力: min(100, memory_usage_count / 2)
    """

    # 维度显示名称（按重要性排序）
    DIMENSIONS = [
        ("proficiency", "熟练度"),
        ("stability", "稳定性"),
        ("satisfaction", "满意度"),
        ("responsiveness", "响应力"),
        ("memory", "记忆力"),
    ]

    def calculate_from_stats(
        self,
        total_interactions: int,
        successful_executions: int,
        user_feedback_score: float,
        average_response_time_ms: float,
        memory_usage_count: int,
    ) -> AbilityScores:
        """
        从统计数据计算五维能力得分

        Args:
            total_interactions: 总交互次数
            successful_executions: 成功执行次数
            user_feedback_score: 用户反馈评分（0-1）
            average_response_time_ms: 平均响应时间（毫秒）
            memory_usage_count: 记忆使用次数

        Returns:
            AbilityScores 五维能力得分
        """
        # 熟练度: 500 次满
        proficiency = min(100, total_interactions // 5)

        # 稳定性: 成功率 × 100
        success_rate = successful_executions / max(1, total_interactions)
        stability = round(success_rate * 100)

        # 满意度: 用户评分 × 100
        satisfaction = round(user_feedback_score * 100)

        # 响应力: 5000ms (5s) 得 0 分, 0ms 得 100 分
        responsiveness = max(0, round(100 - average_response_time_ms / 50))

        # 记忆力: 200 次满
        memory = min(100, memory_usage_count // 2)

        return AbilityScores(
            proficiency=proficiency,
            stability=stability,
            satisfaction=satisfaction,
            responsiveness=responsiveness,
            memory=memory,
        )

    def calculate_from_skill_manifest(self, manifest: "SkillManifest") -> AbilityScores:
        """
        从 SkillManifest 计算能力得分

        Args:
            manifest: SkillManifest 实例

        Returns:
            AbilityScores 五维能力得分
        """
        stats = manifest.stats
        return self.calculate_from_stats(
            total_interactions=stats.total_interactions,
            successful_executions=stats.successful_executions,
            user_feedback_score=stats.user_feedback_score,
            average_response_time_ms=stats.average_response_time_ms,
            memory_usage_count=stats.memory_usage_count,
        )

    def generate_radar_ascii(
        self,
        scores: AbilityScores,
        skill_name: str = "ZenSkill",
        width: int = 30,
    ) -> str:
        """
        生成 ASCII 雷达图

        Args:
            scores: 五维能力得分
            skill_name: 技能名称
            width: 进度条宽度

        Returns:
            格式化的 ASCII 雷达图字符串
        """
        lines = []

        # 标题
        lines.append(f"🧠 {skill_name} 五维能力雷达")
        lines.append("═" * (width + 12))

        # 将分数转为字典以便遍历
        scores_dict = {
            "proficiency": scores.proficiency,
            "stability": scores.stability,
            "satisfaction": scores.satisfaction,
            "responsiveness": scores.responsiveness,
            "memory": scores.memory,
        }

        # 生成每个维度的进度条
        for dim_key, dim_name in self.DIMENSIONS:
            score = scores_dict[dim_key]
            bar = self._generate_progress_bar(score, width)
            lines.append(f"  {dim_name:4s} {bar} {score:3d}")

        lines.append("═" * (width + 12))

        # 综合能力得分
        composite = scores.composite
        grade = self._get_grade(composite)
        lines.append(f"📊 综合能力：{composite:3d} 分 | {grade}")

        # 当前境界进度
        lines.append("")

        return "\n".join(lines)

    def _generate_progress_bar(self, score: int, width: int) -> str:
        """生成进度条"""
        filled = round(score / 100 * width)
        filled = min(filled, width)
        empty = width - filled
        return "█" * filled + "░" * empty

    def _get_grade(self, composite_score: int) -> str:
        """根据综合得分获得评级"""
        if composite_score >= 90:
            return "🏆 大师级"
        elif composite_score >= 75:
            return "⭐ 专家级"
        elif composite_score >= 60:
            return "💪 熟练级"
        elif composite_score >= 40:
            return "📖 进阶中"
        else:
            return "🌱 新手期"

    def generate_status_summary(
        self,
        scores: AbilityScores,
        manifest: "SkillManifest",
    ) -> str:
        """
        生成完整的状态摘要

        Args:
            scores: 五维能力得分
            manifest: SkillManifest 实例

        Returns:
            完整的状态摘要字符串
        """
        lines = []

        # 雷达图
        lines.append(self.generate_radar_ascii(scores))
        lines.append("")

        # 当前境界信息
        level_name = manifest.current_level.name
        level_progress_pct = manifest.level_progress * 100
        next_milestone = manifest._get_next_milestone()

        lines.append(f"🏅 当前境界：【{level_name}】")
        lines.append(f"   境界进度：{level_progress_pct:.1f}%")
        lines.append(f"   {next_milestone}")
        lines.append("")

        # 统计概览
        success_rate = manifest.stats.successful_executions / max(1, manifest.stats.total_interactions)
        lines.append(f"📈 统计概览")
        lines.append(f"   总交互：{manifest.stats.total_interactions} 次")
        lines.append(f"   成功率：{success_rate * 100:.1f}%")
        lines.append(f"   满意度：{manifest.stats.user_feedback_score * 100:.1f}%")
        lines.append(f"   记忆使用：{manifest.stats.memory_usage_count} 次")

        return "\n".join(lines)
