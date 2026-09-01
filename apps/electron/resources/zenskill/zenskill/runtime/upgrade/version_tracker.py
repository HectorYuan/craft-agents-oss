"""版本跟踪器"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from packaging import version


@dataclass
class VersionInfo:
    """版本信息

    Attributes:
        skill_id: 技能ID
        current_version: 当前版本
        latest_version: 最新版本
        upgrade_available: 是否有更新
        last_checked: 最后检查时间
        dependencies: 依赖的技能版本
    """
    skill_id: str
    current_version: str
    latest_version: str = ""
    upgrade_available: bool = False
    last_checked: float = 0.0
    dependencies: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "current_version": self.current_version,
            "latest_version": self.latest_version,
            "upgrade_available": self.upgrade_available,
            "last_checked": self.last_checked,
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VersionInfo:
        """从字典创建"""
        return cls(
            skill_id=data["skill_id"],
            current_version=data["current_version"],
            latest_version=data.get("latest_version", ""),
            upgrade_available=data.get("upgrade_available", False),
            last_checked=data.get("last_checked", 0.0),
            dependencies=data.get("dependencies", {}),
        )

    def check_upgrade(self, remote_version: str) -> bool:
        """检查是否有更新

        Args:
            remote_version: 远程版本

        Returns:
            是否有更新
        """
        try:
            current = version.parse(self.current_version)
            remote = version.parse(remote_version)

            self.latest_version = remote_version
            self.upgrade_available = remote > current
            self.last_checked = time.time()

            return self.upgrade_available
        except Exception:
            return False


class VersionTracker:
    """版本跟踪器

    跟踪技能的版本信息，支持版本检查和升级记录。

    使用方式：
        tracker = VersionTracker("/path/to/versions.json")
        tracker.register("skill-1", "1.0.0")
        info = tracker.get_version_info("skill-1")
        if info.check_upgrade("1.1.0"):
            print(f"有新版本: {info.latest_version}")
    """

    def __init__(self, storage_path: str | Path | None = None):
        """初始化版本跟踪器

        Args:
            storage_path: 版本信息存储路径
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._versions: dict[str, VersionInfo] = {}
        self._upgrade_history: list[dict[str, Any]] = []

        if self._storage_path and self._storage_path.exists():
            self._load()

    @property
    def versions(self) -> dict[str, VersionInfo]:
        return self._versions.copy()

    @property
    def upgrade_history(self) -> list[dict[str, Any]]:
        return self._upgrade_history.copy()

    def register(self, skill_id: str, version_str: str, dependencies: dict[str, str] | None = None) -> VersionInfo:
        """注册技能版本

        Args:
            skill_id: 技能ID
            version_str: 版本号
            dependencies: 依赖版本

        Returns:
            版本信息
        """
        info = VersionInfo(
            skill_id=skill_id,
            current_version=version_str,
            dependencies=dependencies or {},
        )
        self._versions[skill_id] = info
        self._save()
        return info

    def update_version(self, skill_id: str, new_version: str) -> VersionInfo | None:
        """更新技能版本

        Args:
            skill_id: 技能ID
            new_version: 新版本号

        Returns:
            更新后的版本信息
        """
        if skill_id not in self._versions:
            return None

        info = self._versions[skill_id]
        old_version = info.current_version

        info.current_version = new_version
        info.upgrade_available = False
        info.last_checked = time.time()

        # 记录升级历史
        self._upgrade_history.append({
            "skill_id": skill_id,
            "old_version": old_version,
            "new_version": new_version,
            "timestamp": time.time(),
        })

        self._save()
        return info

    def get_version_info(self, skill_id: str) -> VersionInfo | None:
        """获取技能版本信息"""
        return self._versions.get(skill_id)

    def get_all_versions(self) -> dict[str, str]:
        """获取所有技能版本"""
        return {
            skill_id: info.current_version
            for skill_id, info in self._versions.items()
        }

    def get_upgradable(self) -> list[VersionInfo]:
        """获取可升级的技能列表"""
        return [
            info for info in self._versions.values()
            if info.upgrade_available
        ]

    def check_compatibility(
        self,
        skill_id: str,
        target_version: str,
        available_versions: dict[str, str],
    ) -> tuple[bool, list[str]]:
        """检查版本兼容性

        Args:
            skill_id: 技能ID
            target_version: 目标版本
            available_versions: 可用版本映射

        Returns:
            (是否兼容, 不兼容的原因列表)
        """
        if skill_id not in self._versions:
            return False, [f"Skill {skill_id} not registered"]

        info = self._versions[skill_id]
        reasons = []

        # 检查依赖版本
        for dep_id, dep_version in info.dependencies.items():
            if dep_id not in available_versions:
                reasons.append(f"Dependency {dep_id} not available")
            else:
                available = version.parse(available_versions[dep_id])
                required = version.parse(dep_version)
                if available < required:
                    reasons.append(
                        f"Dependency {dep_id} version {available_versions[dep_id]} "
                        f"is less than required {dep_version}"
                    )

        return len(reasons) == 0, reasons

    def _load(self) -> None:
        """从文件加载"""
        if not self._storage_path:
            return

        try:
            with open(self._storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self._versions = {
                skill_id: VersionInfo.from_dict(info)
                for skill_id, info in data.get("versions", {}).items()
            }
            self._upgrade_history = data.get("upgrade_history", [])
        except Exception:
            pass

    def _save(self) -> None:
        """保存到文件"""
        if not self._storage_path:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "versions": {
                skill_id: info.to_dict()
                for skill_id, info in self._versions.items()
            },
            "upgrade_history": self._upgrade_history,
        }

        with open(self._storage_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
