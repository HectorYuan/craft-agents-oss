"""
MU2-C: 7 个专业角色代理 (Specialized Agent Roles)

每种角色有独特的专业能力和视角，通过 MessageBus 通信协作。

使用方式：
    agent = RoleAgent.create(AgentRole.DEVELOPER, "dev-1")
    bus.register(agent)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from .protocol import (
    AgentRole, AgentCapability, AgentHandler,
    AgentMessage, MessageType, MessageBus,
)

logger = logging.getLogger(__name__)


# ============================================================
# 角色默认能力定义
# ============================================================

ROLE_CAPABILITIES = {
    AgentRole.ARCHITECT: AgentCapability(
        role=AgentRole.ARCHITECT,
        skills=["system_design", "architecture", "technology_selection",
                "tradeoff_analysis", "scalability"],
        domains=["architecture", "design", "infrastructure", "security"],
        max_concurrent_tasks=2,
        confidence_factors={
            "architecture": 0.95, "design": 0.85, "security": 0.70,
        },
    ),
    AgentRole.DEVELOPER: AgentCapability(
        role=AgentRole.DEVELOPER,
        skills=["coding", "refactoring", "debugging", "code_review",
                "performance_optimization"],
        domains=["python", "backend", "api", "database"],
        max_concurrent_tasks=3,
        confidence_factors={
            "coding": 0.95, "debugging": 0.85, "refactoring": 0.80,
        },
    ),
    AgentRole.TESTER: AgentCapability(
        role=AgentRole.TESTER,
        skills=["testing", "qa", "boundary_analysis", "test_design",
                "regression_testing"],
        domains=["testing", "qa", "quality"],
        max_concurrent_tasks=3,
        confidence_factors={
            "testing": 0.95, "qa": 0.90, "quality": 0.85,
        },
    ),
    AgentRole.WRITER: AgentCapability(
        role=AgentRole.WRITER,
        skills=["technical_writing", "documentation", "api_docs",
                "tutorial_creation", "changelog"],
        domains=["documentation", "writing", "communication"],
        max_concurrent_tasks=2,
        confidence_factors={
            "writing": 0.95, "documentation": 0.90, "communication": 0.80,
        },
    ),
    AgentRole.ANALYST: AgentCapability(
        role=AgentRole.ANALYST,
        skills=["data_analysis", "diagnostics", "insight_generation",
                "reporting", "visualization"],
        domains=["analysis", "data", "metrics", "optimization"],
        max_concurrent_tasks=2,
        confidence_factors={
            "analysis": 0.95, "data": 0.85, "optimization": 0.75,
        },
    ),
    AgentRole.CRITIC: AgentCapability(
        role=AgentRole.CRITIC,
        skills=["code_review", "design_review", "risk_assessment",
                "quality_audit", "improvement_suggestion"],
        domains=["review", "quality", "risk", "best_practices"],
        max_concurrent_tasks=2,
        confidence_factors={
            "review": 0.95, "quality": 0.85, "risk": 0.80,
        },
    ),
    AgentRole.COORDINATOR: AgentCapability(
        role=AgentRole.COORDINATOR,
        skills=["task_orchestration", "conflict_resolution", "result_integration",
                "progress_tracking", "communication"],
        domains=["coordination", "integration", "management"],
        max_concurrent_tasks=5,
        confidence_factors={
            "coordination": 0.95, "integration": 0.85, "management": 0.80,
        },
    ),
}


# ============================================================
# 角色 Agent 实现
# ============================================================

class RoleAgent(AgentHandler):
    """
    专业角色代理

    每个角色代理拥有：
    - 独特的技能组合和领域知识
    - 标准化消息处理能力
    - 任务执行接口
    - 自我状态追踪
    """

    def __init__(self, role: AgentRole, agent_id: str,
                 custom_capability: Optional[AgentCapability] = None):
        self._role = role
        self._agent_id = agent_id
        self._capability = custom_capability or ROLE_CAPABILITIES[role]
        self._bus: Optional[MessageBus] = None
        self._active_tasks: dict[str, dict] = {}  # task_id → task_info
        self._completed_tasks: list[str] = []
        self._message_count = 0

    # ── AgentHandler 接口 ──

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @property
    def capability(self) -> AgentCapability:
        return self._capability

    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        处理收到的消息

        自动路由到对应的消息处理器
        """
        self._message_count += 1

        handlers = {
            MessageType.CAPABILITY_QUERY: self._handle_capability_query,
            MessageType.TASK_ASSIGNMENT: self._handle_task_assignment,
            MessageType.FEEDBACK_REQUEST: self._handle_feedback_request,
            MessageType.CLARIFICATION_QUESTION: self._handle_clarification,
            MessageType.KNOWLEDGE_SHARE: self._handle_knowledge_share,
            MessageType.TERMINATION_REQUEST: self._handle_termination,
            MessageType.HEARTBEAT: self._handle_heartbeat,
        }

        handler = handlers.get(message.msg_type, self._handle_default)
        return await handler(message)

    async def on_registered(self, bus: MessageBus) -> None:
        """注册到总线后的回调"""
        self._bus = bus
        logger.info(f"{self._role.emoji} {self._agent_id} 已连接到总线")

    async def on_unregistered(self) -> None:
        """从总线注销后的回调"""
        self._bus = None
        logger.info(f"{self._role.emoji} {self._agent_id} 已断开连接")

    # ── 消息处理器 ──

    async def _handle_capability_query(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理能力查询"""
        task_type = msg.payload.get("task_type", "")
        domain = msg.payload.get("domain", "")
        score = self._capability.can_handle(task_type, domain)

        return AgentMessage.new(
            sender=self._agent_id,
            msg_type=MessageType.CAPABILITY_RESPONSE,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "agent_id": self._agent_id,
                "role": self._role.value,
                "score": score,
                "capability": self._capability.to_dict(),
                "active_tasks": len(self._active_tasks),
                "max_concurrent": self._capability.max_concurrent_tasks,
            },
        )

    async def _handle_task_assignment(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理任务分配"""
        task_info = msg.payload.get("task", {})
        task_id = task_info.get("task_id", "")

        # 检查并发限制
        if len(self._active_tasks) >= self._capability.max_concurrent_tasks:
            return AgentMessage.new(
                sender=self._agent_id,
                msg_type=MessageType.TASK_REJECTION,
                receiver=msg.sender,
                correlation_id=msg.msg_id,
                payload={
                    "reason": "max_concurrent_reached",
                    "active_tasks": len(self._active_tasks),
                },
            )

        self._active_tasks[task_id] = {
            "task_info": task_info,
            "status": "accepted",
            "assigned_at": msg.timestamp,
            "assigner": msg.sender,
        }

        return AgentMessage.new(
            sender=self._agent_id,
            msg_type=MessageType.TASK_ACCEPTANCE,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "task_id": task_id,
                "role": self._role.value,
                "estimated_completion": "pending",
            },
        )

    async def _handle_feedback_request(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理反馈请求"""
        return AgentMessage.new(
            sender=self._agent_id,
            msg_type=MessageType.FEEDBACK_RESPONSE,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "agent_id": self._agent_id,
                "role": self._role.value,
                "status": "available",
                "active_tasks": len(self._active_tasks),
                "completed_tasks": len(self._completed_tasks),
                "message_count": self._message_count,
            },
        )

    async def _handle_clarification(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理澄清请求"""
        return AgentMessage.new(
            sender=self._agent_id,
            msg_type=MessageType.CLARIFICATION_ANSWER,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={
                "question": msg.payload.get("question", ""),
                "answer": f"[{self._role.emoji} {self._role.value}] "
                          f"需要更多上下文才能回答该问题",
            },
        )

    async def _handle_knowledge_share(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理知识共享"""
        logger.info(f"{self._agent_id} 收到知识: {str(msg.payload)[:100]}")
        return None

    async def _handle_termination(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理终止请求"""
        task_id = msg.payload.get("task_id", "")
        if task_id in self._active_tasks:
            del self._active_tasks[task_id]

        return AgentMessage.new(
            sender=self._agent_id,
            msg_type=MessageType.TERMINATION_ACK,
            receiver=msg.sender,
            correlation_id=msg.msg_id,
            payload={"task_id": task_id, "status": "terminated"},
        )

    async def _handle_heartbeat(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """处理心跳"""
        return None

    async def _handle_default(self, msg: AgentMessage) -> Optional[AgentMessage]:
        """默认处理器 — 未知消息类型"""
        logger.debug(f"{self._agent_id} 收到未知消息类型: {msg.msg_type}")
        return None

    # ── 任务状态管理 ──

    def complete_task(self, task_id: str, result: dict = None) -> None:
        """
        标记任务已完成

        Args:
            task_id: 任务 ID
            result: 执行结果
        """
        if task_id in self._active_tasks:
            self._active_tasks[task_id]["status"] = "completed"
            self._active_tasks[task_id]["result"] = result or {}
            self._completed_tasks.append(task_id)
            # 从活跃中移除
            del self._active_tasks[task_id]

    def get_status_summary(self) -> dict:
        """获取状态摘要"""
        return {
            "agent_id": self._agent_id,
            "role": self._role.value,
            "role_emoji": self._role.emoji,
            "active_tasks": len(self._active_tasks),
            "completed_tasks": len(self._completed_tasks),
            "message_count": self._message_count,
            "current_load": f"{len(self._active_tasks)}/{self._capability.max_concurrent_tasks}",
        }


def create_role_agents(bus: MessageBus, roles: Optional[list[AgentRole]] = None) -> list[RoleAgent]:
    """
    便捷方法：创建并注册一组角色代理

    Args:
        bus: 消息总线
        roles: 要创建的角色列表（默认全部 7 个）

    Returns:
        创建的代理列表
    """
    if roles is None:
        roles = list(AgentRole)

    agents = []
    for role in roles:
        agent_id = f"{role.value}-{len(agents) + 1}"
        agent = RoleAgent(role=role, agent_id=agent_id)
        bus.register(agent)
        agents.append(agent)

    return agents
