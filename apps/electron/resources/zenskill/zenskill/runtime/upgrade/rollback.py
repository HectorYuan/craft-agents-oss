"""回滚管理器"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class RollbackPoint:
    """回滚点

    Attributes:
        point_id: 回滚点ID
        skill_id: 技能ID
        version: 版本号
        snapshot: 快照数据
        created_at: 创建时间
        description: 描述
    """
    point_id: str
    skill_id: str
    version: str
    snapshot: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "point_id": self.point_id,
            "skill_id": self.skill_id,
            "version": self.version,
            "snapshot": self.snapshot,
            "created_at": self.created_at,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RollbackPoint:
        """从字典创建"""
        return cls(
            point_id=data["point_id"],
            skill_id=data["skill_id"],
            version=data["version"],
            snapshot=data.get("snapshot", {}),
            created_at=data.get("created_at", 0.0),
            description=data.get("description", ""),
        )


class RollbackManager:
    """回滚管理器

    管理回滚点，支持创建快照和回滚操作。

    使用方式：
        manager = RollbackManager("/path/to/rollback")
        point = manager.create_point("skill-1", "1.0.0", {"config": "..."})
        # ... 执行升级 ...
        if need_rollback:
            snapshot = manager.rollback(point.point_id)
    """

    def __init__(self, storage_path: str | Path | None = None):
        """初始化回滚管理器

        Args:
            storage_path: 回滚点存储路径
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._points: dict[str, RollbackPoint] = {}
        self._max_points: int = 10  # 每个技能最多保留10个回滚点

        if self._storage_path and self._storage_path.exists():
            self._load()

    @property
    def points(self) -> dict[str, RollbackPoint]:
        return self._points.copy()

    def create_point(
        self,
        skill_id: str,
        version: str,
        snapshot: dict[str, Any],
        description: str = "",
    ) -> RollbackPoint:
        """创建回滚点

        Args:
            skill_id: 技能ID
            version: 版本号
            snapshot: 快照数据
            description: 描述

        Returns:
            回滚点
        """
        import uuid

        point = RollbackPoint(
            point_id=str(uuid.uuid4())[:8],
            skill_id=skill_id,
            version=version,
            snapshot=snapshot,
            created_at=time.time(),
            description=description,
        )

        self._points[point.point_id] = point

        # 清理旧的回滚点
        self._cleanup_old_points(skill_id)

        self._save()
        return point

    def get_point(self, point_id: str) -> RollbackPoint | None:
        """获取回滚点"""
        return self._points.get(point_id)

    def get_points_for_skill(self, skill_id: str) -> list[RollbackPoint]:
        """获取技能的所有回滚点"""
        return [
            point for point in self._points.values()
            if point.skill_id == skill_id
        ]

    def get_latest_point(self, skill_id: str) -> RollbackPoint | None:
        """获取技能的最新回滚点"""
        points = self.get_points_for_skill(skill_id)
        if not points:
            return None
        return max(points, key=lambda p: p.created_at)

    def rollback(self, point_id: str) -> dict[str, Any] | None:
        """执行回滚

        Args:
            point_id: 回滚点ID

        Returns:
            快照数据，如果回滚点不存在返回None
        """
        point = self._points.get(point_id)
        if not point:
            return None

        return point.snapshot

    def delete_point(self, point_id: str) -> bool:
        """删除回滚点

        Args:
            point_id: 回滚点ID

        Returns:
            是否删除成功
        """
        if point_id in self._points:
            del self._points[point_id]
            self._save()
            return True
        return False

    def _cleanup_old_points(self, skill_id: str) -> None:
        """清理旧的回滚点"""
        points = self.get_points_for_skill(skill_id)
        if len(points) <= self._max_points:
            return

        # 按创建时间排序，删除最旧的
        points.sort(key=lambda p: p.created_at)
        for point in points[: len(points) - self._max_points]:
            del self._points[point.point_id]

    def _load(self) -> None:
        """从文件加载"""
        if not self._storage_path:
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._points = {
                point_id: RollbackPoint.from_dict(point)
                for point_id, point in data.get("points", {}).items()
            }
            self._max_points = data.get("max_points", 10)
        except Exception:
            pass

    def _save(self) -> None:
        """保存到文件"""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "points": {
                point_id: point.to_dict()
                for point_id, point in self._points.items()
            },
            "max_points": self._max_points,
        }

        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
