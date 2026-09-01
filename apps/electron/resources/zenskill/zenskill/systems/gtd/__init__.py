"""
GTD 生产力系统 — ZenSkill 深度融合 (Phase 8.7)

引擎:
- InboxEngine:    零摩擦捕获, 多源输入, 自动意图分类
- ActionEngine:   原子化下一步行动, context/priority/energy/repeat
- ProjectEngine:  项目化编排, 子项目, 技能关联, 模板库
- EnergyEngine:   能量池, 境界决定上限, 稳定性影响恢复
- CalendarEngine: 时间盒管理, 重复规则, 智能排期
- IncubatingEngine: 四通道孵化, ZenLoop 联动, 成熟度追踪
"""

from .inbox import InboxEngine, InboxItem
from .action import ActionEngine, GTDAction
from .project import ProjectEngine, GTDProject, PROJECT_TEMPLATES
from .energy import EnergyEngine, EnergyPool, ACTION_ENERGY_COST, LEVEL_MAX_ENERGY
from .calendar import CalendarEngine, CalendarEvent
from .incubating import IncubatingEngine, IncubatingItem
from .migrate import GTDMigrator
from .report import GTDReportEngine
from .health import GTDHealthEngine

__all__ = [
    "InboxEngine", "InboxItem",
    "ActionEngine", "GTDAction",
    "ProjectEngine", "GTDProject", "PROJECT_TEMPLATES",
    "EnergyEngine", "EnergyPool", "ACTION_ENERGY_COST", "LEVEL_MAX_ENERGY",
    "CalendarEngine", "CalendarEvent",
    "IncubatingEngine", "IncubatingItem",
    "GTDMigrator", "GTDReportEngine", "GTDHealthEngine",
]
