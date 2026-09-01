"""
ZenSkill - 技能修炼档案
记录技能的成长历程、境界、统计数据和修炼状态
"""
from __future__ import annotations

import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from zenskill.systems.visualization.level_up_ceremony import LevelUpCeremony
    from zenskill.systems.visualization.ability_calculator import AbilityCalculator, AbilityScores
    from zenskill.systems.visualization.metrics_store import MetricPoint

logger = logging.getLogger(__name__)

# 延迟导入避免循环依赖
_ceremony = None
_calculator = None


def _get_ceremony() -> "LevelUpCeremony":
    """获取境界突破仪式实例（延迟导入）"""
    global _ceremony
    if _ceremony is None:
        from zenskill.systems.visualization.level_up_ceremony import LevelUpCeremony
        _ceremony = LevelUpCeremony()
    return _ceremony


def _get_calculator() -> "AbilityCalculator":
    """获取能力计算器实例（延迟导入）"""
    global _calculator
    if _calculator is None:
        from zenskill.systems.visualization.ability_calculator import AbilityCalculator
        _calculator = AbilityCalculator()
    return _calculator


class SkillLevel(Enum):
    """技能境界等级"""
    NOVICE = 1      # 新手 - 刚安装
    APPRENTICE = 2  # 学徒 - 积累10+交互，开始了解偏好
    ADEPT = 3       # 熟手 - 理解用户工作模式，犯错减少
    EXPERT = 4      # 专家 - 深度适配习惯，预判需求
    MASTER = 5      # 大师 - 高度契合，真正伙伴


@dataclass
class SkillStat:
    """技能统计数据"""
    total_interactions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    user_feedback_score: float = 0.0  # 0-1 移动平均分
    average_response_time_ms: float = 0.0
    memory_usage_count: int = 0
    upgrade_proposals_submitted: int = 0


@dataclass
class SkillMilestone:
    """成长里程碑"""
    level: SkillLevel
    achieved_at: float
    achievement_description: str
    unlocked_abilities: list[str]


@dataclass
class SkillManifest:
    """
    技能修炼档案
    
    每个技能都有独立的修炼档案，记录：
    - 当前境界和进度
    - 交互统计数据
    - 成长里程碑
    - 解锁的能力
    - 升级阈值配置
    """
    
    skill_id: str
    skill_name: str
    
    # 境界状态
    current_level: SkillLevel = SkillLevel.NOVICE
    level_progress: float = 0.0  # 0-1 当前境界进度
    
    # 修炼统计
    stats: SkillStat = field(default_factory=SkillStat)
    milestones: list[SkillMilestone] = field(default_factory=list)
    
    # 修炼配置 - 各境界升级所需交互次数
    upgrade_thresholds: dict[SkillLevel, int] = field(default_factory=lambda: {
        SkillLevel.APPRENTICE: 10,    # 10 次交互升学徒
        SkillLevel.ADEPT: 50,          # 50 次交互升熟手
        SkillLevel.EXPERT: 200,        # 200 次交互升专家
        SkillLevel.MASTER: 500,        # 500 次交互升大师
    })
    
    # 能力树
    unlocked_abilities: list[str] = field(default_factory=list)
    locked_abilities: list[str] = field(default_factory=list)
    
    # ====================================================================
    # 核心修炼方法
    # ====================================================================
    
    def record_interaction(self, success: bool, feedback_score: float = 0.5) -> None:
        """
        记录一次交互，推进修炼进度

        Args:
            success: 是否执行成功
            feedback_score: 用户反馈评分 0-1
        """
        # 边界检查
        if not isinstance(success, bool):
            success = bool(success)

        if not isinstance(feedback_score, (int, float)):
            feedback_score = 0.5

        # 限制在 0-1 范围
        feedback_score = max(0.0, min(1.0, feedback_score))

        self.stats.total_interactions += 1

        if success:
            self.stats.successful_executions += 1
        else:
            self.stats.failed_executions += 1

        # 更新反馈评分（移动平均）
        n = self.stats.total_interactions
        if n == 1:
            self.stats.user_feedback_score = feedback_score
        else:
            old = self.stats.user_feedback_score
            self.stats.user_feedback_score = (old * (n-1) + feedback_score) / n

        # 计算境界进度，检查是否升级
        self._update_level_progress()
    
    def _update_level_progress(self) -> None:
        """更新境界进度，检查是否升级"""
        n = self.stats.total_interactions
        
        # 检查是否可以进入下一境界
        next_level_value = self.current_level.value + 1
        if next_level_value <= SkillLevel.MASTER.value:
            next_level = SkillLevel(next_level_value)
            if next_level in self.upgrade_thresholds:
                threshold = self.upgrade_thresholds[next_level]
                if n >= threshold:
                    self._level_up(next_level)
                    return
        
        # 计算当前境界进度
        if self.current_level == SkillLevel.NOVICE:
            threshold = self.upgrade_thresholds[SkillLevel.APPRENTICE]
            self.level_progress = min(1.0, n / threshold)
        else:
            # 当前境界的阈值
            current_threshold = self.upgrade_thresholds.get(self.current_level, 0)
            
            # 下一境界的阈值
            next_level_value = self.current_level.value + 1
            if next_level_value <= SkillLevel.MASTER.value:
                next_level = SkillLevel(next_level_value)
                next_threshold = self.upgrade_thresholds.get(next_level, current_threshold * 2)
            else:
                next_threshold = current_threshold * 2  # 大师之后，继续成长但不升级
            
            if next_threshold > current_threshold:
                progress = (n - current_threshold) / (next_threshold - current_threshold)
                self.level_progress = min(1.0, max(0.0, progress))
    
    def _level_up(self, new_level: SkillLevel) -> None:
        """
        境界提升！解锁新能力
        
        Args:
            new_level: 新的境界
        """
        old_level = self.current_level
        self.current_level = new_level
        self.level_progress = 0.0
        
        # 获取新能力
        new_abilities = self._get_abilities_for_level(new_level)
        
        # 记录里程碑
        milestone = SkillMilestone(
            level=new_level,
            achieved_at=time.time(),
            achievement_description=f"从 {old_level.name} 晋升到 {new_level.name}",
            unlocked_abilities=new_abilities,
        )
        self.milestones.append(milestone)
        
        # 解锁新能力
        self.unlocked_abilities.extend(new_abilities)
        
        # 生成境界突破仪式文案
        ceremony = _get_ceremony()
        ceremony_text = ceremony.generate_ceremony(self, old_level, new_level)
        logger.info(f"\n{ceremony_text}\n")

        # 保存仪式到文件持久化
        try:
            ceremony.save_ceremony(ceremony_text, old_level.name, new_level.name)
        except Exception as e:
            logger.debug(f"Failed to save ceremony: {e}")

        # 记录仪式结果，供外部获取
        self._last_level_up_ceremony = ceremony_text

        logger.info(
            f"🎉 Skill '{self.skill_name}' level up! "
            f"{old_level.name} → {new_level.name}. "
            f"Unlocked: {len(new_abilities)} abilities"
        )
    
    def _get_abilities_for_level(self, level: SkillLevel) -> list[str]:
        """获取对应境界解锁的能力"""
        ability_map = {
            SkillLevel.APPRENTICE: [
                "基础用户偏好识别",
                "简单反思摘要生成",
            ],
            SkillLevel.ADEPT: [
                "主动记忆整合",
                "性能瓶颈自我诊断",
                "基础升级提案生成",
            ],
            SkillLevel.EXPERT: [
                "跨领域洞见生成",
                "复杂模式识别",
                "高级升级提案生成",
            ],
            SkillLevel.MASTER: [
                "自主进化策略规划",
                "用户需求预判",
                "多技能协同优化",
            ],
        }
        return ability_map.get(level, [])
    
    def get_growth_report(self) -> dict[str, Any]:
        """
        生成成长报告（用于展示给用户）
        
        Returns:
            成长报告字典
        """
        success_rate = self.stats.successful_executions / max(1, self.stats.total_interactions)
        
        return {
            "skill_name": self.skill_name,
            "current_level": self.current_level.name,
            "level_progress": f"{self.level_progress * 100:.1f}%",
            "stats": {
                "total_interactions": self.stats.total_interactions,
                "success_rate": f"{success_rate * 100:.1f}%",
                "user_satisfaction": f"{self.stats.user_feedback_score * 100:.1f}%",
            },
            "next_milestone": self._get_next_milestone(),
            "recent_abilities": self.unlocked_abilities[-3:] if self.unlocked_abilities else [],
        }
    
    def _get_next_milestone(self) -> str:
        """获取下一个里程碑的描述"""
        next_level_value = self.current_level.value + 1
        
        if next_level_value > SkillLevel.MASTER.value:
            return "已达到最高境界，继续精进中 🌟"
        
        next_level = SkillLevel(next_level_value)
        if next_level not in self.upgrade_thresholds:
            return "已达到最高境界"
        
        threshold = self.upgrade_thresholds[next_level]
        remaining = threshold - self.stats.total_interactions
        
        if remaining > 0:
            return f"还需 {remaining} 次交互晋升 {next_level.name}"
        return f"即将晋升 {next_level.name}！"

    # ====================================================================
    # 可视化相关方法
    # ====================================================================

    def get_ability_scores(self) -> "AbilityScores":
        """
        获取五维能力得分

        Returns:
            AbilityScores 五维能力得分
        """
        calc = _get_calculator()
        return calc.calculate_from_skill_manifest(self)

    def get_radar_chart(self, width: int = 30) -> str:
        """
        获取 ASCII 雷达图

        Args:
            width: 进度条宽度

        Returns:
            ASCII 雷达图字符串
        """
        calc = _get_calculator()
        scores = self.get_ability_scores()
        return calc.generate_radar_ascii(scores, self.skill_name, width)

    def get_full_status_summary(self) -> str:
        """
        获取完整的状态摘要（雷达图 + 境界 + 统计）

        Returns:
            完整状态摘要字符串
        """
        calc = _get_calculator()
        scores = self.get_ability_scores()
        return calc.generate_status_summary(scores, self)

    def get_last_level_up_ceremony(self) -> str:
        """
        获取上次境界突破的仪式文案

        Returns:
            仪式文案，如果没有过升级则返回提示
        """
        if hasattr(self, '_last_level_up_ceremony'):
            return self._last_level_up_ceremony
        return "尚未达成过境界突破，继续加油！"

    # ====================================================================
    # 历史趋势相关方法
    # ====================================================================

    def create_metric_point(self) -> "MetricPoint":
        """
        从当前状态创建一个指标采样点

        Returns:
            MetricPoint 指标采样点
        """
        from zenskill.systems.visualization.trend_chart import MetricPoint
        return MetricPoint.from_manifest(self)

    def __repr__(self) -> str:
        return (
            f"SkillManifest(skill_id='{self.skill_id}', "
            f"skill_name='{self.skill_name}', "
            f"level={self.current_level.name}, "
            f"progress={self.level_progress*100:.1f}%)"
        )
