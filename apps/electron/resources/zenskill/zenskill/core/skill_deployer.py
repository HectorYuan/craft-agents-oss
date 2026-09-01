"""技能部署器（原 skill_executor.py，ZSR11 → P1-1 重构更名）

SkillExecutor 名不副实 — 它只做 manifest 自检与部署复制，
真实执行在 zenskill/runtime/（ExecutionLoop + BuiltinExecutor）。

本模块职责:
- test_skill: 清单自检
- deploy/undeploy/list: 委托 platforms 的 DeployAdapter 体系
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

from ..platforms.deploy import (
    DEPLOY_ADAPTERS,
    discover_skill,
    get_deploy_adapter,
    get_skills_dir,
    load_skill_manifest,
)


@dataclass
class SkillExecutionResult:
    """技能执行结果"""
    success: bool = False
    output: str = ""
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "output": self.output,
            "error": self.error,
            "metadata": self.metadata,
        }


class SkillDeployer:
    """技能部署器 — 委托 DeployAdapter 完成实际部署"""

    def __init__(
        self,
        mcp_server_path: Optional[str] = None,
        config: Optional[Any] = None,
        skills_dir: Optional[Path] = None,
    ):
        self.mcp_server_path = mcp_server_path
        self.config = config
        self._skills_dir = Path(skills_dir) if skills_dir else get_skills_dir()

    async def test_skill(self, skill_id: str) -> SkillExecutionResult:
        """测试技能: 验证清单可加载"""
        skill_path = discover_skill(skill_id, self._skills_dir)
        if not skill_path:
            return SkillExecutionResult(
                success=False,
                error=f"Skill not found: {skill_id}",
            )

        manifest = load_skill_manifest(skill_path)
        if not manifest:
            return SkillExecutionResult(
                success=False,
                error=f"Failed to load skill manifest: {skill_id}",
            )

        return SkillExecutionResult(
            success=True,
            output=f"Skill {skill_id} test passed",
            metadata={"manifest": manifest, "path": str(skill_path)},
        )

    def _adapter_kwargs(self) -> Dict[str, Any]:
        return {"skills_dir": self._skills_dir}

    async def deploy_skill(self, skill_id: str, platform: str) -> SkillExecutionResult:
        """部署技能到指定平台 (local/codex/cursor/opencode)"""
        try:
            adapter = get_deploy_adapter(platform, **self._adapter_kwargs())
        except KeyError as e:
            return SkillExecutionResult(success=False, error=str(e).strip("'"))

        result = adapter.install(skill_id)
        if not result.success:
            return SkillExecutionResult(success=False, error=result.message)

        return SkillExecutionResult(
            success=True,
            output=result.message,
            metadata={
                "platform": platform,
                "skill_path": result.skill_path,
                "manifest": adapter.get_installed_manifest(skill_id),
            },
        )

    async def undeploy_skill(self, skill_id: str, platform: str) -> SkillExecutionResult:
        """卸载技能"""
        if platform not in DEPLOY_ADAPTERS:
            return SkillExecutionResult(
                success=False,
                error=f"Unsupported platform: {platform}. "
                      f"Supported: {sorted(DEPLOY_ADAPTERS.keys())}",
            )

        adapter = get_deploy_adapter(platform, **self._adapter_kwargs())
        result = adapter.uninstall(skill_id)
        return SkillExecutionResult(
            success=result.success,
            output=result.message,
            error="" if result.success else result.message,
        )

    async def list_deployments(self, skill_id: str) -> SkillExecutionResult:
        """列出技能的所有部署"""
        platforms = []
        for platform in DEPLOY_ADAPTERS:
            adapter = get_deploy_adapter(platform, **self._adapter_kwargs())
            if adapter.is_installed(skill_id):
                platforms.append(platform)

        if not platforms:
            return SkillExecutionResult(
                success=True,
                output=f"No deployments for {skill_id}",
                metadata={"platforms": []},
            )

        return SkillExecutionResult(
            success=True,
            output=f"Deployments for {skill_id}: {', '.join(platforms)}",
            metadata={"platforms": platforms},
        )
