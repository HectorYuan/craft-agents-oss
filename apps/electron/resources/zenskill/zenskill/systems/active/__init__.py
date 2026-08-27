"""
ZenSkill 主动成长系统

包含:
- ActiveGoalEngine: 目标设定与追踪
- ProactiveInsightEngine: 主动洞察推送
- TaskRecommendationEngine: 智能任务推荐
- MetaReflectionEngine: 元反思系统（反思反思过程本身）
"""

from .goal_engine import ActiveGoalEngine, GrowthGoal, GoalProgress
from .proactive_insight import ProactiveInsightEngine, ProactiveInsight
from .task_recommender import TaskRecommendationEngine, RecommendedTask, UserBehaviorPattern
from .meta_reflection import MetaReflectionEngine, ReflectionQuality, ReflectionOptimization, OptimizationImpact

__all__ = [
    "ActiveGoalEngine",
    "GrowthGoal",
    "GoalProgress",
    "ProactiveInsightEngine",
    "ProactiveInsight",
    "TaskRecommendationEngine",
    "RecommendedTask",
    "UserBehaviorPattern",
    "MetaReflectionEngine",
    "ReflectionQuality",
    "ReflectionOptimization",
    "OptimizationImpact",
]
