# ZenSkill - 有生命的技能系统

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

__version__ = "0.9.14"
__author__ = "ZenSkill Team"

__all__ = [
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
    "ExecutionConfig",
    "SkillExecutor",
    "SkillExecutionResult",
]
