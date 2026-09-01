"""技能路由协议定义 (Phase Z1B + PROP-20260712-088)

定义 SkillHandler Protocol 和 RoutingContext，为能力路由提供统一接口。

用法:
    from zenskill.core.protocols import SkillHandler, RoutingContext

    class MySkill:
        def can_handle(self, task: str, context: RoutingContext | None = None) -> float:
            return 0.8 if "分析" in task else 0.2
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


class SkillType(str, Enum):
    """技能类型（对齐 core/skill_types.py）"""
    EXECUTION = "execution"
    ANALYSIS = "analysis"
    CREATION = "creation"
    COORDINATION = "coordination"
    KNOWLEDGE = "knowledge"
    GENERAL = "general"


@dataclass
class RoutingContext:
    """路由上下文 — 让 can_handle 感知执行环境

    Attributes:
        user_role: 用户角色（developer/coach/architect 等）
        env: 运行环境（dev/staging/prod）
        load_level: 系统负载（0.0-1.0）
        deadline: 截止时间（None 表示无限制）
        history: 最近执行记录（task_hash, skill_id, success）
        skill_type: 期望的技能类型（None 表示不限）
        extra: 扩展字段（各信号源可存放自定义数据）
    """
    user_role: str = "developer"
    env: str = "dev"
    load_level: float = 0.0
    deadline: Optional[datetime] = None
    history: List[Dict[str, Any]] = field(default_factory=list)
    skill_type: Optional[SkillType] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "user_role": self.user_role,
            "env": self.env,
            "load_level": self.load_level,
            "deadline": self.deadline.isoformat() if self.deadline else None,
            "history": self.history,
            "skill_type": self.skill_type.value if self.skill_type else None,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingContext":
        """从字典反序列化"""
        deadline = None
        if data.get("deadline"):
            deadline = datetime.fromisoformat(data["deadline"])
        skill_type = None
        if data.get("skill_type"):
            skill_type = SkillType(data["skill_type"])
        return cls(
            user_role=data.get("user_role", "developer"),
            env=data.get("env", "dev"),
            load_level=data.get("load_level", 0.0),
            deadline=deadline,
            history=data.get("history", []),
            skill_type=skill_type,
            extra=data.get("extra", {}),
        )


@runtime_checkable
class SkillHandler(Protocol):
    """技能处理器协议 — 能力路由的基础接口

    所有参与能力路由的技能必须实现此协议。
    can_handle() 返回 0.0-1.0 的置信度分数，表示该技能处理给定任务的能力。

    用法:
        class DataAnalysisSkill:
            def can_handle(self, task: str, context: RoutingContext | None = None) -> float:
                if "分析" in task or "数据" in task:
                    return 0.9
                return 0.1
    """

    def can_handle(self, task: str, context: Optional[RoutingContext] = None) -> float:
        """判断能否处理此任务

        Args:
            task: 任务描述（自然语言）
            context: 路由上下文（可选，None 表示无上下文）

        Returns:
            置信度分数 0.0-1.0（0.0 表示完全不能处理，1.0 表示完美匹配）
        """
        ...


class ChainableSkillHandler(SkillHandler, Protocol):
    """可链式组合的技能处理器协议 (PROP-20260712-091)

    在 SkillHandler 基础上扩展 suggest_chain()，支持多技能协作路由。
    """

    def suggest_chain(
        self, task: str, context: Optional[RoutingContext] = None
    ) -> List["RoutingCandidate"]:
        """建议技能链（多技能协作）

        Args:
            task: 任务描述
            context: 路由上下文

        Returns:
            候选技能列表，按执行顺序排列
        """
        ...


@dataclass
class RoutingCandidate:
    """路由候选 — 技能链中的一个节点

    Attributes:
        skill_id: 技能标识
        confidence: 置信度 0.0-1.0
        role: 在链中的角色
            - primary: 主要执行者
            - fallback: 备选方案
            - preprocessor: 前置处理
            - postprocessor: 后置处理
    """
    skill_id: str
    confidence: float
    role: str = "primary"  # primary / fallback / preprocessor / postprocessor

    def to_dict(self) -> Dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "role": self.role,
        }


@dataclass
class RoutingDecision:
    """路由决策记录 — 可追溯路由原因

    Attributes:
        task: 原始任务
        context: 路由上下文
        skill_id: 选中的技能
        confidence: 最终置信度
        rule_id: 命中的规则 ID（None 表示走 Protocol 兜底）
        signal_scores: 各信号源评分（Phase 2 扩展）
        timestamp: 决策时间
    """
    task: str
    context: Optional[RoutingContext]
    skill_id: str
    confidence: float
    rule_id: Optional[str] = None
    signal_scores: Dict[str, float] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task": self.task,
            "context": self.context.to_dict() if self.context else None,
            "skill_id": self.skill_id,
            "confidence": self.confidence,
            "rule_id": self.rule_id,
            "signal_scores": self.signal_scores,
            "timestamp": self.timestamp.isoformat(),
        }
