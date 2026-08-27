"""
MU2-A: 代理通信协议 (Agent Communication Protocol)

多 Agent 协作的基础设施，提供：
- 标准化的消息类型和格式
- 总线式消息路由
- 能力声明与发现
- 任务契约管理
- 审计追踪

使用方式：
    bus = MessageBus()
    bus.register(architect_agent)
    bus.register(developer_agent)
    result = await bus.send_and_wait(AgentMessage(...))
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


# ============================================================
# Agent 角色枚举 — 7 种专业角色
# ============================================================

class AgentRole(str, Enum):
    """代理角色 — 每种角色有独特的专业能力"""
    ARCHITECT = "architect"       # 🏗️ 架构师：系统设计、技术选型、架构决策
    DEVELOPER = "developer"       # 💻 开发者：代码实现、重构、调试
    TESTER = "tester"            # 🧪 测试工程师：质量保证、测试策略、边界分析
    WRITER = "writer"            # ✍️ 技术作家：文档、注释优化、技术博客
    ANALYST = "analyst"          # 📊 分析师：数据分析、问题诊断、决策支持
    CRITIC = "critic"            # 🧠 评论家：批判性审查、潜在问题识别
    COORDINATOR = "coordinator"  # 🎯 协调者：集成、同步、冲突解决

    @property
    def emoji(self) -> str:
        return {
            AgentRole.ARCHITECT: "🏗️",
            AgentRole.DEVELOPER: "💻",
            AgentRole.TESTER: "🧪",
            AgentRole.WRITER: "✍️",
            AgentRole.ANALYST: "📊",
            AgentRole.CRITIC: "🧠",
            AgentRole.COORDINATOR: "🎯",
        }.get(self, "🤖")

    @property
    def description(self) -> str:
        return {
            AgentRole.ARCHITECT: "系统设计、技术选型、架构决策",
            AgentRole.DEVELOPER: "代码实现、重构、调试",
            AgentRole.TESTER: "质量保证、测试策略、边界分析",
            AgentRole.WRITER: "文档、注释优化、技术博客",
            AgentRole.ANALYST: "数据分析、问题诊断、决策支持",
            AgentRole.CRITIC: "批判性审查、潜在问题识别",
            AgentRole.COORDINATOR: "集成、同步、冲突解决",
        }.get(self, "")


# ============================================================
# 消息类型枚举
# ============================================================

class MessageType(str, Enum):
    """代理间通信的消息类型"""
    # 生命周期
    CAPABILITY_DECLARATION = "cap_decl"      # 能力声明 — Agent 注册时广播
    CAPABILITY_QUERY = "cap_query"            # 能力查询 — 寻找能处理某任务的 Agent
    CAPABILITY_RESPONSE = "cap_resp"          # 能力响应 — Agent 对查询的回复
    HEARTBEAT = "heartbeat"                   # 心跳 — 存活检测
    GOODBYE = "goodbye"                       # 离线通知

    # 任务
    TASK_ASSIGNMENT = "task_assign"           # 任务分配
    TASK_ACCEPTANCE = "task_accept"           # 任务接受
    TASK_REJECTION = "task_reject"            # 任务拒绝
    PROGRESS_UPDATE = "progress"              # 进度更新
    RESULT_DELIVERY = "result"                # 结果交付
    RESULT_REVIEW = "result_review"           # 结果评审

    # 协作
    FEEDBACK_REQUEST = "feedback_req"         # 反馈请求
    FEEDBACK_RESPONSE = "feedback_resp"       # 反馈回复
    CLARIFICATION_QUESTION = "clarify_q"      # 澄清问题
    CLARIFICATION_ANSWER = "clarify_a"        # 澄清答复
    NEGOTIATION_PROPOSAL = "nego_proposal"    # 协商提案
    NEGOTIATION_ACCEPT = "nego_accept"        # 协商接受
    NEGOTIATION_REJECT = "nego_reject"        # 协商拒绝

    # 错误
    ERROR_NOTIFICATION = "error"              # 错误通知
    TERMINATION_REQUEST = "terminate"         # 终止请求
    TERMINATION_ACK = "terminate_ack"         # 终止确认

    # 知识共享
    KNOWLEDGE_SHARE = "knowledge"             # 知识共享
    MEMORY_QUERY = "memory_query"             # 记忆查询
    MEMORY_RESPONSE = "memory_resp"           # 记忆回复


# ============================================================
# 消息优先级
# ============================================================

class MessagePriority(Enum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


# ============================================================
# 核心数据模型
# ============================================================

@dataclass
class AgentCapability:
    """Agent 能力描述"""
    role: AgentRole
    skills: list[str] = field(default_factory=list)       # 擅长技能列表
    domains: list[str] = field(default_factory=list)      # 擅长领域
    max_concurrent_tasks: int = 3                          # 最大并发任务数
    confidence_factors: dict[str, float] = field(default_factory=dict)  # 各领域置信度

    def can_handle(self, task_type: str, domain: str = "") -> float:
        """
        判断能否处理某类任务，返回匹配度 0-1

        Args:
            task_type: 任务类型
            domain: 任务领域

        Returns:
            匹配度（0=不能，1=完美匹配）
        """
        score = 0.0
        if task_type in self.skills:
            score += 0.6
        if domain in self.domains:
            score += 0.4
        if domain in self.confidence_factors:
            score *= self.confidence_factors.get(domain, 1.0)
        return min(score, 1.0)

    def to_dict(self) -> dict:
        return {
            "role": self.role.value,
            "skills": self.skills,
            "domains": self.domains,
            "max_concurrent_tasks": self.max_concurrent_tasks,
        }


@dataclass
class AgentMessage:
    """代理间通信的标准消息"""
    msg_id: str                                          # 消息唯一 ID
    sender: str                                          # 发送者 ID
    msg_type: MessageType                                # 消息类型
    payload: dict = field(default_factory=dict)          # 消息体
    receiver: str = ""                                   # 接收者 ID（空=广播）
    correlation_id: str = ""                             # 关联 ID（追踪消息链）
    priority: MessagePriority = MessagePriority.NORMAL   # 优先级
    ttl_seconds: int = 300                               # 生存时间（默认 5 分钟）
    timestamp: float = field(default_factory=time.time)  # 发送时间戳
    source_session: str = ""                             # 来源会话 ID

    def is_expired(self) -> bool:
        """检查消息是否过期"""
        return time.time() - self.timestamp > self.ttl_seconds

    def to_dict(self) -> dict:
        return {
            "msg_id": self.msg_id,
            "sender": self.sender,
            "receiver": self.receiver,
            "msg_type": self.msg_type.value,
            "payload": self.payload,
            "correlation_id": self.correlation_id,
            "priority": self.priority.value,
            "ttl_seconds": self.ttl_seconds,
            "timestamp": self.timestamp,
            "source_session": self.source_session,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentMessage":
        return cls(
            msg_id=data.get("msg_id", ""),
            sender=data.get("sender", ""),
            receiver=data.get("receiver", ""),
            msg_type=MessageType(data.get("msg_type", "heartbeat")),
            payload=data.get("payload", {}),
            correlation_id=data.get("correlation_id", ""),
            priority=MessagePriority(data.get("priority", 1)),
            ttl_seconds=data.get("ttl_seconds", 300),
            timestamp=data.get("timestamp", time.time()),
            source_session=data.get("source_session", ""),
        )

    @staticmethod
    def new(sender: str, msg_type: MessageType, **kwargs) -> "AgentMessage":
        """便捷创建新消息"""
        return AgentMessage(
            msg_id=f"msg_{uuid.uuid4().hex[:12]}_{int(time.time() * 1000)}",
            sender=sender,
            msg_type=msg_type,
            **kwargs,
        )


@dataclass
class TaskContract:
    """任务契约 — 定义任务的完整生命周期"""
    task_id: str
    title: str
    description: str = ""
    required_skills: list[str] = field(default_factory=list)
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    acceptance_criteria: list[str] = field(default_factory=list)
    estimated_hours: float = 1.0
    priority: MessagePriority = MessagePriority.NORMAL
    created_at: float = field(default_factory=time.time)
    assigned_to: str = ""
    parent_task_id: str = ""  # 父任务 ID（子任务用）
    dependencies: list[str] = field(default_factory=list)  # 前置任务 ID

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "required_skills": self.required_skills,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_hours": self.estimated_hours,
            "priority": self.priority.value,
            "created_at": self.created_at,
            "assigned_to": self.assigned_to,
            "parent_task_id": self.parent_task_id,
            "dependencies": self.dependencies,
        }


# ============================================================
# Agent 处理器接口
# ============================================================

class AgentHandler:
    """
    Agent 消息处理器接口

    所有 Agent 必须实现此接口才能接入 MessageBus
    """

    @property
    def agent_id(self) -> str:
        """Agent 唯一标识符"""
        raise NotImplementedError

    @property
    def capability(self) -> AgentCapability:
        """Agent 能力描述"""
        raise NotImplementedError

    async def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """
        处理收到的消息

        Args:
            message: 收到的消息

        Returns:
            可选的回复消息
        """
        raise NotImplementedError

    async def on_registered(self, bus: "MessageBus") -> None:
        """注册到总线后的回调"""
        pass

    async def on_unregistered(self) -> None:
        """从总线注销后的回调"""
        pass


# ============================================================
# MessageBus — 中央消息总线
# ============================================================

class MessageBus:
    """
    消息总线 — 多 Agent 通信中枢

    特性：
    - 总线式消息路由（发布/订阅 + 点对点）
    - 自动能力发现与匹配
    - 消息追踪与审计
    - 超时与重试
    - 优先级队列
    """

    def __init__(self, bus_id: str = "default"):
        self.bus_id = bus_id
        self._agents: dict[str, AgentHandler] = {}             # agent_id → handler
        self._capabilities: dict[str, AgentCapability] = {}    # agent_id → capability
        self._message_history: list[AgentMessage] = []          # 审计追踪
        self._pending_responses: dict[str, asyncio.Future] = {}  # 等待回复
        self._task_contracts: dict[str, TaskContract] = {}       # 活跃任务
        self._max_history: int = 10000
        self._initialized = False

    # ── Agent 生命周期 ──

    def register(self, agent: AgentHandler) -> None:
        """
        注册 Agent 到总线

        - 添加 Agent 处理器
        - 广播能力声明
        - 触发 on_registered 回调
        """
        agent_id = agent.agent_id
        if agent_id in self._agents:
            logger.warning(f"Agent 已注册，跳过: {agent_id}")
            return

        self._agents[agent_id] = agent
        self._capabilities[agent_id] = agent.capability

        # 广播能力声明
        decl_msg = AgentMessage.new(
            sender=agent_id,
            msg_type=MessageType.CAPABILITY_DECLARATION,
            payload={
                "agent_id": agent_id,
                "capability": agent.capability.to_dict(),
            },
        )
        self._record_message(decl_msg)

        logger.info(f"🤖 Agent 已注册: {agent_id} ({agent.capability.role.value})")
        self._initialized = True

    def unregister(self, agent_id: str) -> None:
        """从总线注销 Agent"""
        if agent_id in self._agents:
            # 广播离线通知
            goodbye = AgentMessage.new(
                sender=agent_id,
                msg_type=MessageType.GOODBYE,
                payload={"agent_id": agent_id},
            )
            self._record_message(goodbye)

            self._agents.pop(agent_id, None)
            self._capabilities.pop(agent_id, None)
            logger.info(f"Agent 已注销: {agent_id}")

    def list_capabilities(self) -> dict[str, AgentCapability]:
        """
        列出所有已注册 Agent 的能力描述

        Returns:
            {agent_id: AgentCapability, ...}
        """
        return dict(self._capabilities)

    def get_agent(self, agent_id: str) -> Optional[AgentHandler]:
        """获取已注册的 Agent"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        """列出所有已注册的 Agent"""
        return [
            {
                "agent_id": aid,
                "role": cap.role.value,
                "skills": cap.skills,
                "domains": cap.domains,
            }
            for aid, cap in self._capabilities.items()
        ]

    # ── 消息发送 ──

    async def send(self, message: AgentMessage) -> None:
        """
        发送消息（异步，不等待回复）

        根据 receiver 字段决定路由方式：
        - 空 → 广播给所有 Agent
        - 指定 ID → 点对点发送
        """
        if message.is_expired():
            logger.warning(f"消息已过期，丢弃: {message.msg_id}")
            return

        self._record_message(message)

        if not message.receiver:
            # 广播
            await self._broadcast(message)
        else:
            # 点对点
            await self._send_to(message, message.receiver)

    async def send_and_wait(
        self, message: AgentMessage, timeout: float = 30.0
    ) -> Optional[AgentMessage]:
        """
        发送消息并等待回复

        Args:
            message: 要发送的消息
            timeout: 超时秒数

        Returns:
            回复消息，超时返回 None
        """
        loop = asyncio.get_event_loop()
        future = loop.create_future()
        self._pending_responses[message.msg_id] = future

        try:
            await self.send(message)
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(f"等待回复超时: {message.msg_id}")
            return None
        finally:
            self._pending_responses.pop(message.msg_id, None)

    async def dispatch_response(self, response: AgentMessage) -> None:
        """
        分发回复消息到对应的等待 Future

        Args:
            response: 回复消息
        """
        corr_id = response.correlation_id
        if corr_id and corr_id in self._pending_responses:
            future = self._pending_responses[corr_id]
            if not future.done():
                future.set_result(response)

    # ── 能力发现 ──

    def find_agents_for_task(
        self, task_type: str, domain: str = "", min_score: float = 0.3
    ) -> list[tuple[str, AgentCapability, float]]:
        """
        查找能处理某任务的 Agent

        Args:
            task_type: 任务类型
            domain: 领域
            min_score: 最低匹配度

        Returns:
            [(agent_id, capability, score), ...] 按匹配度降序
        """
        results = []
        for agent_id, cap in self._capabilities.items():
            score = cap.can_handle(task_type, domain)
            if score >= min_score:
                results.append((agent_id, cap, score))

        results.sort(key=lambda x: -x[2])
        return results

    # ── 任务管理 ──

    def register_task(self, contract: TaskContract) -> None:
        """注册任务契约"""
        self._task_contracts[contract.task_id] = contract

    def get_task(self, task_id: str) -> Optional[TaskContract]:
        """获取任务契约"""
        return self._task_contracts.get(task_id)

    def list_active_tasks(self) -> list[TaskContract]:
        """列出所有活跃任务"""
        return [t for t in self._task_contracts.values() if t.assigned_to]

    # ── 审计追踪 ──

    def get_message_history(
        self, limit: int = 100, agent_id: str = ""
    ) -> list[AgentMessage]:
        """
        获取消息历史

        Args:
            limit: 返回条数
            agent_id: 按 Agent 过滤（可选）

        Returns:
            消息历史列表
        """
        history = self._message_history
        if agent_id:
            history = [
                m for m in history
                if m.sender == agent_id or m.receiver == agent_id
            ]
        return history[-limit:]

    def get_task_audit_trail(self, correlation_id: str) -> list[dict]:
        """
        获取任务审计追踪

        Args:
            correlation_id: 关联 ID

        Returns:
            与该关联 ID 相关的所有消息摘要
        """
        return [
            {
                "msg_id": m.msg_id,
                "sender": m.sender,
                "receiver": m.receiver,
                "type": m.msg_type.value,
                "timestamp": datetime.fromtimestamp(m.timestamp).isoformat(),
                "summary": str(m.payload)[:100],
            }
            for m in self._message_history
            if m.correlation_id == correlation_id
        ]

    # ── 内部方法 ──

    async def _broadcast(self, message: AgentMessage) -> None:
        """广播消息给所有 Agent"""
        for agent_id, handler in list(self._agents.items()):
            if agent_id == message.sender:
                continue
            try:
                response = await handler.handle_message(message)
                if response:
                    response.correlation_id = message.msg_id
                    await self.dispatch_response(response)
                    self._record_message(response)
            except Exception as e:
                logger.error(f"广播到 {agent_id} 失败: {e}")

    async def _send_to(self, message: AgentMessage, receiver: str) -> None:
        """发送消息到指定 Agent"""
        handler = self._agents.get(receiver)
        if not handler:
            logger.warning(f"接收者不存在: {receiver}")
            return

        try:
            response = await handler.handle_message(message)
            if response:
                response.correlation_id = message.msg_id
                await self.dispatch_response(response)
                self._record_message(response)
        except Exception as e:
            logger.error(f"发送到 {receiver} 失败: {e}")

    def _record_message(self, message: AgentMessage) -> None:
        """记录消息到审计历史"""
        self._message_history.append(message)
        # 限制历史长度
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history:]


# ============================================================
# 便捷工厂
# ============================================================

def create_message_bus(bus_id: str = "default") -> MessageBus:
    """
    创建消息总线实例

    这是推荐的创建方式，后续可以扩展为共享总线
    """
    return MessageBus(bus_id=bus_id)
