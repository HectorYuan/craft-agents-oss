# ZenSkill - 有生命的技能系统
# 扣子技能版本 v1.0.0

import warnings

try:
    from .zenomni import (
        omni_skill,
        SkillType,
        ZenOmniSkill,
        GlobalSkillRegistry,
        TaskPlanner,
        StepExecutor,
        ErrorRecoverer,
        ResultIntegrator,
    )
except ImportError:
    omni_skill = None
    SkillType = None
    ZenOmniSkill = None
    GlobalSkillRegistry = None
    TaskPlanner = None
    StepExecutor = None
    ErrorRecoverer = None
    ResultIntegrator = None

warnings.warn(
    "zenskill.zenomni exports (omni_skill, ZenOmniSkill, GlobalSkillRegistry, "
    "TaskPlanner, StepExecutor, ErrorRecoverer, ResultIntegrator) are deprecated. "
    "Migrate to zenskill.db.skill_dao (SkillDAO) and "
    "zenskill.core.skill_profile (SkillProfile).",
    DeprecationWarning,
    stacklevel=2,
)

from .wrapper.skill_wrapper import wrap_skill
from .agent.skill_agent import SkillAgent, AgentConfig, InteractionResult

# Runtime 模块
from .runtime import (
    MCPClient,
    MCPTool,
    ToolResult,
    ExecutionConfig,
)
from .core.skill_deployer import SkillDeployer, SkillExecutionResult
from .core.skill_executor import SkillExecutor
from .mirroring import (
    EventType,
    InteractionEvent,
    FeatureVector,
    UserPrivacyPrefs,
    EventCollector,
    FeatureStore,
    PrivacyLayer,
)

__version__ = "2.6.7"
__author__ = "ZenSkill Team"

__all__ = [
    # ZenOmni 核心
    "omni_skill",
    "SkillType",
    "ZenOmniSkill",
    "GlobalSkillRegistry",
    "TaskPlanner",
    "StepExecutor",
    "ErrorRecoverer",
    "ResultIntegrator",
    # Wrapper
    "wrap_skill",
    # Agent
    "SkillAgent",
    "AgentConfig",
    "InteractionResult",
    # 用户镜像
    "EventType",
    "InteractionEvent",
    "FeatureVector",
    "UserPrivacyPrefs",
    "EventCollector",
    "FeatureStore",
    "PrivacyLayer",
    # Runtime
    "MCPClient",
    "MCPTool",
    "ToolResult",
    
    
    
    "ExecutionResult",
    
    
    
    
    "SkillExecutor",
    "SkillExecutionResult",
]
