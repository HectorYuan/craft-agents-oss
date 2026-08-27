"""
ZenSkill Runtime

MCP 客户端 + Agent 引擎（runtime/agent/）+ 记忆/反思/权限/技能链/升级子系统。
旧关键词引擎（ExecutionLoop/Controller/ToolRouter 等）已于 v3.1 退役，
由 LLM 驱动的 runtime/agent 取代（`zenskill run --engine agent`）。
"""

from .mcp_client import MCPClient, MCPTool, ToolResult
from .skill_exposure import SkillExposure, SkillTool, ExposureResult
from .config import ExecutionConfig
from .permission import (
    PermissionMode,
    ToolCategory as PermissionToolCategory,
    PermissionChecker,
    PermissionResult,
    Sandbox,
    SandboxConfig,
)
from .memory import (
    MemoryStore,
    MemoryEntry,
    MemoryType,
    ShortTermMemory,
    LongTermMemory,
    ContextManager,
)
from .reflection import (
    SelfEvaluator,
    Evaluation,
    ErrorType,
    RetryStrategy,
    Strategy,
    ReflectionLoop,
    ReflectionResult,
)
from .chain import (
    SkillChain,
    ChainStep,
    ChainConfig,
    ChainExecutor,
    ChainResult,
    StepResult,
)
from .upgrade import (
    VersionTracker,
    VersionInfo,
    UpgradeManager,
    UpgradeResult,
    RollbackManager,
    RollbackPoint,
)

__all__ = [
    "MCPClient",
    "MCPTool",
    "ToolResult",
    "SkillExposure",
    "SkillTool",
    "ExposureResult",
    "ExecutionConfig",
    "PermissionMode",
    "PermissionToolCategory",
    "PermissionChecker",
    "PermissionResult",
    "Sandbox",
    "SandboxConfig",
    "MemoryStore",
    "MemoryEntry",
    "MemoryType",
    "ShortTermMemory",
    "LongTermMemory",
    "ContextManager",
    "SelfEvaluator",
    "Evaluation",
    "ErrorType",
    "RetryStrategy",
    "Strategy",
    "ReflectionLoop",
    "ReflectionResult",
    "SkillChain",
    "ChainStep",
    "ChainConfig",
    "ChainExecutor",
    "ChainResult",
    "StepResult",
    "VersionTracker",
    "VersionInfo",
    "UpgradeManager",
    "UpgradeResult",
    "RollbackManager",
    "RollbackPoint",
]
