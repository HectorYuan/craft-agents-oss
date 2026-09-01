"""升级管理器"""


from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .version_tracker import VersionTracker, VersionInfo
from .rollback import RollbackManager, RollbackPoint

__stable_api__ = "1.0"  # UpgradeManager 公开方法 为外部消费方稳定面（docs/agentswarm_integration_plan.md I2）


@dataclass
class UpgradeResult:
    """升级结果

    Attributes:
        skill_id: 技能ID
        success: 是否成功
        old_version: 旧版本
        new_version: 新版本
        rollback_point: 回滚点（如果创建了）
        error: 错误信息
        duration_seconds: 耗时
    """
    skill_id: str
    success: bool = False
    old_version: str = ""
    new_version: str = ""
    rollback_point: RollbackPoint | None = None
    error: str = ""
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        return {
            "skill_id": self.skill_id,
            "success": self.success,
            "old_version": self.old_version,
            "new_version": self.new_version,
            "rollback_point": self.rollback_point.to_dict() if self.rollback_point else None,
            "error": self.error,
            "duration_seconds": self.duration_seconds,
        }


class UpgradeManager:
    """升级管理器

    管理技能的升级过程，包括版本检查、升级执行和回滚。

    使用方式：
        manager = UpgradeManager(
            version_tracker=tracker,
            rollback_manager=rollback_mgr,
        )

        # 检查更新
        updates = await manager.check_updates(["skill-1", "skill-2"])

        # 执行升级
        result = await manager.upgrade("skill-1", "1.1.0", apply_func)

        # 如果失败，回滚
        if not result.success and result.rollback_point:
            await manager.rollback(result.rollback_point.point_id)
    """

    def __init__(
        self,
        version_tracker: VersionTracker,
        rollback_manager: RollbackManager,
        on_upgrade_start: Callable[[str], None] | None = None,
        on_upgrade_complete: Callable[[str, UpgradeResult], None] | None = None,
    ):
        """初始化升级管理器

        Args:
            version_tracker: 版本跟踪器
            rollback_manager: 回滚管理器
            on_upgrade_start: 升级开始回调
            on_upgrade_complete: 升级完成回调
        """
        self._version_tracker = version_tracker
        self._rollback_manager = rollback_manager
        self._on_upgrade_start = on_upgrade_start
        self._on_upgrade_complete = on_upgrade_complete

    async def check_updates(
        self,
        skill_ids: list[str],
        remote_versions: dict[str, str] | None = None,
    ) -> list[VersionInfo]:
        """检查更新

        Args:
            skill_ids: 技能ID列表
            remote_versions: 远程版本映射（模拟）

        Returns:
            有更新的技能列表
        """
        upgradable = []

        for skill_id in skill_ids:
            info = self._version_tracker.get_version_info(skill_id)
            if not info:
                continue

            # 如果提供了远程版本，使用它
            if remote_versions and skill_id in remote_versions:
                remote_version = remote_versions[skill_id]
            else:
                # 真实更新源（GitHub Releases 等），失败回退本地模拟
                remote_version = self._fetch_remote_version(skill_id, info)

            if info.check_upgrade(remote_version):
                upgradable.append(info)

        return upgradable

    async def upgrade(
        self,
        skill_id: str,
        target_version: str,
        apply_func: Callable[[str, str, dict[str, Any]], Any] | None = None,
        snapshot_data: dict[str, Any] | None = None,
    ) -> UpgradeResult:
        """执行升级

        Args:
            skill_id: 技能ID
            target_version: 目标版本
            apply_func: 应用升级的函数 (skill_id, new_version, snapshot) -> result
            snapshot_data: 升级前的快照数据

        Returns:
            升级结果
        """
        start_time = time.time()
        result = UpgradeResult(skill_id=skill_id)

        # 获取当前版本信息
        info = self._version_tracker.get_version_info(skill_id)
        if not info:
            result.error = f"Skill {skill_id} not registered"
            result.duration_seconds = time.time() - start_time
            return result

        result.old_version = info.current_version
        result.new_version = target_version

        # 回调
        if self._on_upgrade_start:
            self._on_upgrade_start(skill_id)

        try:
            # 创建回滚点
            if snapshot_data:
                rollback_point = self._rollback_manager.create_point(
                    skill_id=skill_id,
                    version=info.current_version,
                    snapshot=snapshot_data,
                    description=f"Before upgrade to {target_version}"
                )
                result.rollback_point = rollback_point

            # 执行升级
            if apply_func:
                await apply_func(skill_id, target_version, snapshot_data or {})
            else:
                # 默认升级逻辑（仅更新版本号）
                pass

            # 更新版本号
            self._version_tracker.update_version(skill_id, target_version)

            result.success = True

        except Exception as e:
            result.error = str(e)

        result.duration_seconds = time.time() - start_time

        # 回调
        if self._on_upgrade_complete:
            self._on_upgrade_complete(skill_id, result)

        return result

    async def rollback(self, point_id: str) -> dict[str, Any] | None:
        """执行回滚

        Args:
            point_id: 回滚点ID

        Returns:
            回滚的快照数据
        """
        return self._rollback_manager.rollback(point_id)

    async def batch_upgrade(
        self,
        upgrades: list[dict[str, Any]],
        apply_func: Callable[[str, str, dict[str, Any]], Any] | None = None,
    ) -> list[UpgradeResult]:
        """批量升级

        Args:
            upgrades: 升级列表 [{"skill_id": "...", "version": "...", "snapshot": {...}}]
            apply_func: 应用升级的函数

        Returns:
            升级结果列表
        """
        results = []

        for upgrade_info in upgrades:
            skill_id = upgrade_info["skill_id"]
            version = upgrade_info["version"]
            snapshot = upgrade_info.get("snapshot")

            result = await self.upgrade(
                skill_id=skill_id,
                target_version=version,
                apply_func=apply_func,
                snapshot_data=snapshot,
            )
            results.append(result)

        return results

    def get_upgrade_history(self) -> list[dict[str, Any]]:
        """获取升级历史"""
        return self._version_tracker.upgrade_history

    def _fetch_remote_version(self, skill_id: str, info: Any) -> str:
        """查询真实远程版本 (P2-3)

        GitHub 来源走 Releases API；无来源或查询失败时回退本地模拟
        （模拟结果仅用于演示，避免误判真实更新）。
        """
        source_url = ""
        try:
            from ...core.skill_dao import SkillDAO

            row = SkillDAO.get(skill_id)
            source_url = (row or {}).get("source_url", "")
        except Exception:
            source_url = getattr(info, "source_url", "")

        m = re.match(r"https?://github\.com/([^/]+)/([^/@#\s]+)/?", source_url or "")
        if m:
            try:
                import requests

                resp = requests.get(
                    f"https://api.github.com/repos/{m.group(1)}/{m.group(2)}/releases/latest",
                    timeout=5,
                    headers={"Accept": "application/vnd.github+json"},
                )
                if resp.status_code == 200:
                    tag = (resp.json() or {}).get("tag_name", "")
                    version = tag.lstrip("vV")
                    if version:
                        return version
            except Exception:
                pass

        return self._simulate_remote_version(info.current_version)

    def _simulate_remote_version(self, current_version: str) -> str:
        """模拟远程版本（实际应从注册中心获取）

        Args:
            current_version: 当前版本

        Returns:
            模拟的远程版本
        """
        # 简单模拟：将最后一位+1
        parts = current_version.split(".")
        if len(parts) >= 3:
            try:
                parts[-1] = str(int(parts[-1]) + 1)
                return ".".join(parts)
            except ValueError:
                pass
        return current_version
