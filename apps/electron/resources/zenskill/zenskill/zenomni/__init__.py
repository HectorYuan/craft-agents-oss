"""
ZenOmni — 遗留模块 (Phase Z: marked deprecated)

Coze/OmniAgent 平台时代的技能基类系统。
已由 Phase D (SkillProfile + SkillDAO + SkillSearchEngine) 替代。

迁移指南: docs/PHASE_Z_ROADMAP.md
用法:
    旧: class MySkill(ZenOmniSkill): ...
    新: from zenskill.core.skill_profile import SkillProfile
"""

import warnings

warnings.warn(
    "ZenOmni is deprecated. Use SkillProfile + SkillDAO from zenskill.core instead.",
    DeprecationWarning, stacklevel=2,
)

from .core import (
    ZenOmniSkill,
    SkillType,
    SkillCapability,
    omni_skill,
    _DefaultTaskPlanner as TaskPlanner,
    _DefaultStepExecutor as StepExecutor,
    _DefaultErrorRecoverer as ErrorRecoverer,
    _DefaultResultIntegrator as ResultIntegrator
)
from .registry import GlobalSkillRegistry, SkillRoute

global_skill_registry = GlobalSkillRegistry()

__all__ = [
    "ZenOmniSkill",
    "SkillType",
    "SkillCapability",
    "omni_skill",
    "GlobalSkillRegistry",
    "global_skill_registry",
    "SkillRoute",
    "TaskPlanner",
    "StepExecutor",
    "ErrorRecoverer",
    "ResultIntegrator",
]
