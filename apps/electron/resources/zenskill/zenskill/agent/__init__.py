"""
ZenSkill - Agent 模块

包含：
- SkillAgent: 单体智能代理（原有）
- 代理通信协议: 多 Agent 协作基础设施
- 任务分解器: 复杂任务自动分解
- 专业角色代理: 7 种角色的 AI 代理
"""

from .skill_agent import (
    AgentConfig,
    InteractionResult,
    SkillAgent,
)

from .protocol import (
    AgentRole,
    MessageType,
    MessagePriority,
    AgentMessage,
    AgentCapability,
    AgentHandler,
    TaskContract,
    MessageBus,
    create_message_bus,
)

from .decomposer import (
    ComplexityLevel,
    DecompositionStrategy,
    SubTask,
    DecompositionResult,
    TaskDecomposer,
)

from .role_agents import (
    RoleAgent,
    create_role_agents,
    ROLE_CAPABILITIES,
)

from .negotiator import (
    NegotiationStage, VotingMethod,
    StructuredOpinion, CrossQuestion, Vote,
    NegotiationResult, NegotiationSession,
    NegotiationCoordinator,
)

from .shared_memory import (
    MemoryEntry,
    SharedMemory,
)

from .orchestrator import (
    WorkflowStatus, StepType,
    WorkflowStep, WorkflowResult, WorkflowDefinition,
    WorkflowOrchestrator,
)

from .evaluator import (
    EvaluationMetric, PerformanceRecord, AgentScore,
    AgentEvaluator, ABTestConfig, ABTestResult,
    ABTestManager,
)

from .capability_matcher import (
    TaskSpecification, AgentMatchResult, CapabilityMatcher,
    format_match_result, find_agents_for_task,
)

__all__ = [
    # 原有
    "AgentConfig",
    "InteractionResult",
    "SkillAgent",
    # 协议
    "AgentRole",
    "MessageType",
    "MessagePriority",
    "AgentMessage",
    "AgentCapability",
    "AgentHandler",
    "TaskContract",
    "MessageBus",
    "create_message_bus",
    # 分解
    "ComplexityLevel",
    "DecompositionStrategy",
    "SubTask",
    "DecompositionResult",
    "TaskDecomposer",
    # 角色
    "RoleAgent",
    "create_role_agents",
    "ROLE_CAPABILITIES",
    # 协商
    "NegotiationStage",
    "VotingMethod",
    "StructuredOpinion",
    "CrossQuestion",
    "Vote",
    "NegotiationResult",
    "NegotiationSession",
    "NegotiationCoordinator",
    # 共享记忆
    "MemoryEntry",
    "SharedMemory",
    # 编排
    "WorkflowStatus",
    "StepType",
    "WorkflowStep",
    "WorkflowResult",
    "WorkflowDefinition",
    "WorkflowOrchestrator",
    # 评估
    "EvaluationMetric",
    "PerformanceRecord",
    "AgentScore",
    "AgentEvaluator",
    "ABTestConfig",
    "ABTestResult",
    "ABTestManager",
    # 9P: 能力发现与路由
    "TaskSpecification",
    "AgentMatchResult",
    "CapabilityMatcher",
    "format_match_result",
    "find_agents_for_task",
]
