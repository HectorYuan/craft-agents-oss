"""
ZenSkill 多技能协同系统

包含:
- SkillDependencyGraph: 技能依赖图谱 - 自动发现技能间的关系
- CrossSkillInsight: 跨技能洞察整合 - 全局视角分析
- SkillEcosystemDashboard: 技能生态仪表盘 - 统一管理界面
"""

from .dependency_graph import (
    SkillDependencyGraph,
    SkillNode,
    SkillRelation,
    SkillCategory,
)
from .cross_insight import CrossSkillInsightEngine, CrossSkillInsight
from .dashboard import SkillEcosystemDashboard

__all__ = [
    "SkillDependencyGraph",
    "SkillNode",
    "SkillRelation",
    "SkillCategory",
    "CrossSkillInsightEngine",
    "CrossSkillInsight",
    "SkillEcosystemDashboard",
]
