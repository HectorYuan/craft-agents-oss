"""
用户镜像系统数据模型

Phase 9A: 用户画像数据层
定义事件采集、特征向量、隐私偏好等核心数据结构
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List


class EventType(str, Enum):
    """事件类型枚举"""
    SKILL_EXEC = "skill_exec"           # 技能执行
    USER_INPUT = "user_input"           # 用户输入
    MEMORY_OP = "memory_op"             # 记忆操作
    REFLECTION = "reflection"           # 禅思反思
    GOAL_ACTION = "goal_action"         # 目标操作
    SESSION_START = "session_start"     # 会话开始
    SESSION_END = "session_end"         # 会话结束
    LEVEL_UP = "level_up"               # 境界突破
    ERROR = "error"                     # 错误事件


@dataclass
class InteractionEvent:
    """交互事件记录"""
    event_id: str
    event_type: EventType
    timestamp: float
    skill_id: str
    action: str
    success: bool
    duration_ms: float
    context: Dict[str, Any]
    session_id: str
    user_id: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "skill_id": self.skill_id,
            "action": self.action,
            "success": self.success,
            "duration_ms": self.duration_ms,
            "context": self.context,
            "session_id": self.session_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "InteractionEvent":
        """从字典反序列化"""
        return cls(
            event_id=data["event_id"],
            event_type=EventType(data["event_type"]),
            timestamp=data["timestamp"],
            skill_id=data["skill_id"],
            action=data["action"],
            success=data["success"],
            duration_ms=data["duration_ms"],
            context=data.get("context", {}),
            session_id=data["session_id"],
            user_id=data.get("user_id", "default"),
        )

    @classmethod
    def create(
        cls,
        event_type: EventType,
        skill_id: str,
        action: str,
        success: bool = True,
        duration_ms: float = 0,
        context: Dict[str, Any] | None = None,
        session_id: str = "",
        user_id: str = "default",
    ) -> "InteractionEvent":
        """工厂方法，自动生成 event_id 和 timestamp"""
        return cls(
            event_id=uuid.uuid4().hex[:16],
            event_type=event_type,
            timestamp=datetime.now().timestamp(),
            skill_id=skill_id,
            action=action,
            success=success,
            duration_ms=duration_ms,
            context=context or {},
            session_id=session_id or uuid.uuid4().hex[:12],
            user_id=user_id,
        )


@dataclass
class FeatureVector:
    """用户行为特征向量"""
    computed_at: float
    window_days: int
    total_events: int
    session_count: int
    avg_session_duration_min: float
    active_hours: Dict[int, float]          # hour(0-23) -> fraction
    weekday_distribution: Dict[int, float]  # day(0-6, Mon=0) -> fraction
    skill_preferences: Dict[str, float]     # skill_id -> fraction
    avg_task_complexity: float
    success_rate: float
    memory_usage_rate: float
    reflection_frequency: float
    goal_completion_rate: float
    engagement_trend: str                   # "increasing" / "stable" / "decreasing"
    success_trend: str
    avg_response_time_ms: float

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "computed_at": self.computed_at,
            "window_days": self.window_days,
            "total_events": self.total_events,
            "session_count": self.session_count,
            "avg_session_duration_min": self.avg_session_duration_min,
            "active_hours": {str(k): v for k, v in self.active_hours.items()},
            "weekday_distribution": {str(k): v for k, v in self.weekday_distribution.items()},
            "skill_preferences": self.skill_preferences,
            "avg_task_complexity": self.avg_task_complexity,
            "success_rate": self.success_rate,
            "memory_usage_rate": self.memory_usage_rate,
            "reflection_frequency": self.reflection_frequency,
            "goal_completion_rate": self.goal_completion_rate,
            "engagement_trend": self.engagement_trend,
            "success_trend": self.success_trend,
            "avg_response_time_ms": self.avg_response_time_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeatureVector":
        """从字典反序列化"""
        return cls(
            computed_at=data["computed_at"],
            window_days=data["window_days"],
            total_events=data["total_events"],
            session_count=data["session_count"],
            avg_session_duration_min=data["avg_session_duration_min"],
            active_hours={int(k): v for k, v in data.get("active_hours", {}).items()},
            weekday_distribution={int(k): v for k, v in data.get("weekday_distribution", {}).items()},
            skill_preferences=data.get("skill_preferences", {}),
            avg_task_complexity=data.get("avg_task_complexity", 0.0),
            success_rate=data.get("success_rate", 0.0),
            memory_usage_rate=data.get("memory_usage_rate", 0.0),
            reflection_frequency=data.get("reflection_frequency", 0.0),
            goal_completion_rate=data.get("goal_completion_rate", 0.0),
            engagement_trend=data.get("engagement_trend", "stable"),
            success_trend=data.get("success_trend", "stable"),
            avg_response_time_ms=data.get("avg_response_time_ms", 0.0),
        )

    @classmethod
    def empty(cls) -> "FeatureVector":
        """返回空特征向量（数据不足时使用）"""
        return cls(
            computed_at=datetime.now().timestamp(),
            window_days=0,
            total_events=0,
            session_count=0,
            avg_session_duration_min=0.0,
            active_hours={h: 0.0 for h in range(24)},
            weekday_distribution={d: 0.0 for d in range(7)},
            skill_preferences={},
            avg_task_complexity=0.0,
            success_rate=0.0,
            memory_usage_rate=0.0,
            reflection_frequency=0.0,
            goal_completion_rate=0.0,
            engagement_trend="stable",
            success_trend="stable",
            avg_response_time_ms=0.0,
        )


@dataclass
class UserPrivacyPrefs:
    """用户隐私偏好"""
    consent_given: bool = True
    encryption_enabled: bool = False
    retention_days: int = 90
    anonymize_after_days: int = 30
    excluded_event_types: List[str] = field(default_factory=list)
    last_modified: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """序列化为字典"""
        return {
            "consent_given": self.consent_given,
            "encryption_enabled": self.encryption_enabled,
            "retention_days": self.retention_days,
            "anonymize_after_days": self.anonymize_after_days,
            "excluded_event_types": self.excluded_event_types,
            "last_modified": self.last_modified,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "UserPrivacyPrefs":
        """从字典反序列化"""
        return cls(
            consent_given=data.get("consent_given", True),
            encryption_enabled=data.get("encryption_enabled", False),
            retention_days=data.get("retention_days", 90),
            anonymize_after_days=data.get("anonymize_after_days", 30),
            excluded_event_types=data.get("excluded_event_types", []),
            last_modified=data.get("last_modified", ""),
        )
