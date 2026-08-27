"""
ZenSkill 数据结构 Schema 验证

使用 pydantic 确保所有记忆记录和状态数据格式统一。
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum


class SkillLevel(str, Enum):
    """技能境界等级"""
    NOVICE = "NOVICE"
    APPRENTICE = "APPRENTICE"
    ADEPT = "ADEPT"
    EXPERT = "EXPERT"
    MASTER = "MASTER"


class MemoryRecord:
    """
    记忆记录 Schema

    确保所有记忆记录格式统一，字段完整。
    """

    def __init__(
        self,
        name: str,
        description: str,
        content: str,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        created_at: Optional[datetime] = None,
    ):
        # 验证 name 长度
        if len(name) < 3 or len(name) > 100:
            raise ValueError("name 长度必须在 3-100 字符之间")

        # 验证 description 长度
        if len(description) > 200:
            raise ValueError("description 长度不能超过 200 字符")

        self.name = name
        self.description = description
        self.content = content
        self.tags = tags or []
        self.metadata = metadata or {}
        self.created_at = created_at or datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "tags": self.tags,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MemoryRecord":
        """从字典创建"""
        created_at = data.get("created_at")
        if created_at:
            created_at = datetime.fromisoformat(created_at)

        return cls(
            name=data["name"],
            description=data["description"],
            content=data["content"],
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            created_at=created_at,
        )


class SkillState:
    """
    技能状态 Schema

    确保技能状态数据格式统一。
    """

    def __init__(
        self,
        skill_id: str,
        name: str,
        level: SkillLevel = SkillLevel.NOVICE,
        usage_count: int = 0,
        last_used: Optional[datetime] = None,
        level_up_at: Optional[datetime] = None,
        episodes: Optional[List[Dict[str, Any]]] = None,
        milestones: Optional[List[Dict[str, Any]]] = None,
    ):
        self.skill_id = skill_id
        self.name = name
        self.level = SkillLevel(level) if isinstance(level, str) else level
        self.usage_count = max(0, usage_count)
        self.last_used = last_used
        self.level_up_at = level_up_at
        self.episodes = episodes or []
        self.milestones = milestones or []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "name": self.name,
            "level": self.level.value,
            "usage_count": self.usage_count,
            "last_used": self.last_used.isoformat() if self.last_used else None,
            "level_up_at": self.level_up_at.isoformat() if self.level_up_at else None,
            "episodes": self.episodes,
            "milestones": self.milestones,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SkillState":
        """从字典创建"""
        last_used = data.get("last_used")
        if last_used:
            last_used = datetime.fromisoformat(last_used)

        level_up_at = data.get("level_up_at")
        if level_up_at:
            level_up_at = datetime.fromisoformat(level_up_at)

        return cls(
            skill_id=data["skill_id"],
            name=data["name"],
            level=data.get("level", SkillLevel.NOVICE),
            usage_count=data.get("usage_count", 0),
            last_used=last_used,
            level_up_at=level_up_at,
            episodes=data.get("episodes", []),
            milestones=data.get("milestones", []),
        )


class Episode:
    """
    事件记录 Schema

    记录每次技能使用的事件信息。
    """

    def __init__(
        self,
        date: str,
        action: str,
        content: str,
        tags: Optional[List[str]] = None,
    ):
        self.date = date
        self.action = action
        self.content = content
        self.tags = tags or []

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "date": self.date,
            "action": self.action,
            "content": self.content,
            "tags": self.tags,
        }


def validate_memory_record(data: Dict[str, Any]) -> bool:
    """
    验证记忆记录格式是否正确

    Args:
        data: 待验证的记忆数据

    Returns:
        是否通过验证

    Raises:
        ValueError: 格式不正确时抛出
    """
    try:
        MemoryRecord.from_dict(data)
        return True
    except Exception as e:
        raise ValueError(f"记忆记录格式错误: {e}")


def validate_skill_state(data: Dict[str, Any]) -> bool:
    """
    验证技能状态格式是否正确

    Args:
        data: 待验证的状态数据

    Returns:
        是否通过验证

    Raises:
        ValueError: 格式不正确时抛出
    """
    try:
        SkillState.from_dict(data)
        return True
    except Exception as e:
        raise ValueError(f"技能状态格式错误: {e}")
