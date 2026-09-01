"""
ZenSkill - 跨平台一键安装器

提供统一的技能安装接口，支持多平台一键安装
"""

from typing import Optional
from dataclasses import dataclass, field

from .base import PlatformType, InstallResult, ExecutionResult
from .coze import CozeAdapter
from .pip import PipAdapter
from .claude import ClaudeAdapter
from .openclaw import OpenClawAdapter
from .hermes import HermesAdapter
from .deploy import (
    LocalDeployAdapter,
    CodexAdapter,
    CursorDeployAdapter,
    OpencodeDeployAdapter,
)


@dataclass
class InstallConfig:
    """安装配置"""
    platforms: list[str] = field(default_factory=lambda: ["coze", "pip", "claude"])
    skill_path: Optional[str] = None
    package_name: Optional[str] = None
    skip_installed: bool = True


class SkillInstaller:
    """
    跨平台技能安装器
    
    用法:
    ```python
    from zenskill.platforms.installer import SkillInstaller
    
    installer = SkillInstaller()
    
    # 安装到所有支持的平台
    results = installer.install("zenskill")
    
    # 安装到指定平台
    results = installer.install("zenskill", platforms=["pip", "claude"])
    
    # 检查安装状态
    status = installer.check_status("zenskill")
    ```
    """
    
    # 平台适配器映射（P1-1: 部署型四平台 + hermes 全部注册，消除孤儿代码）
    ADAPTERS = {
        "coze": CozeAdapter(),
        "pip": PipAdapter(),
        "claude": ClaudeAdapter(),
        "openclaw": OpenClawAdapter(),
        "hermes": HermesAdapter(),
        "local": LocalDeployAdapter(),
        "codex": CodexAdapter(),
        "cursor": CursorDeployAdapter(),
        "opencode": OpencodeDeployAdapter(),
    }
    
    def __init__(self, config: InstallConfig = None):
        self.config = config or InstallConfig()
    
    def install(
        self,
        skill_name: str,
        platforms: list[str] = None,
        **kwargs
    ) -> dict[str, InstallResult]:
        """
        一键安装技能到指定平台
        
        Args:
            skill_name: 技能名称
            platforms: 目标平台列表，None 表示全部
            **kwargs: 额外参数
        
        Returns:
            dict: 各平台的安装结果
        """
        if platforms is None:
            platforms = self.config.platforms
        
        results = {}
        
        for platform in platforms:
            adapter = self.ADAPTERS.get(platform)
            if not adapter:
                results[platform] = InstallResult(
                    success=False,
                    platform=platform,
                    message=f"Unknown platform: {platform}",
                )
                continue
            
            # 检查是否已安装
            if self.config.skip_installed and adapter.is_installed(skill_name):
                results[platform] = InstallResult(
                    success=True,
                    platform=platform,
                    message=f"'{skill_name}' already installed",
                )
                continue
            
            # 执行安装
            install_kwargs = dict(kwargs)
            if self.config.skill_path:
                install_kwargs["skill_path"] = self.config.skill_path
            if self.config.package_name:
                install_kwargs["package_name"] = self.config.package_name
            
            results[platform] = adapter.install(skill_name, **install_kwargs)
        
        return results
    
    def uninstall(
        self,
        skill_name: str,
        platforms: list[str] = None
    ) -> dict[str, InstallResult]:
        """
        从指定平台卸载技能
        
        Args:
            skill_name: 技能名称
            platforms: 目标平台列表，None 表示全部
        
        Returns:
            dict: 各平台的卸载结果
        """
        if platforms is None:
            platforms = list(self.ADAPTERS.keys())
        
        results = {}
        
        for platform in platforms:
            adapter = self.ADAPTERS.get(platform)
            if adapter:
                results[platform] = adapter.uninstall(skill_name)
            else:
                results[platform] = InstallResult(
                    success=False,
                    platform=platform,
                    message=f"Unknown platform: {platform}",
                )
        
        return results
    
    def check_status(
        self,
        skill_name: str,
        platforms: list[str] = None
    ) -> dict[str, dict]:
        """
        检查技能在各平台的安装状态
        
        Args:
            skill_name: 技能名称
            platforms: 检查的平台列表，None 表示全部
        
        Returns:
            dict: 各平台的安装状态
        """
        if platforms is None:
            platforms = list(self.ADAPTERS.keys())
        
        status = {}
        
        for platform in platforms:
            adapter = self.ADAPTERS.get(platform)
            if adapter:
                status[platform] = adapter.get_status(skill_name)
            else:
                status[platform] = {
                    "name": skill_name,
                    "platform": platform,
                    "installed": None,
                    "error": "Unknown platform",
                }
        
        return status
    
    def execute(
        self,
        skill_name: str,
        task: str,
        platform: str = "pip",
        **kwargs
    ) -> ExecutionResult:
        """
        在指定平台执行技能
        
        Args:
            skill_name: 技能名称
            task: 任务描述
            platform: 执行平台
            **kwargs: 执行参数
        
        Returns:
            ExecutionResult: 执行结果
        """
        adapter = self.ADAPTERS.get(platform)
        if not adapter:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Unknown platform: {platform}",
            )
        
        return adapter.execute(skill_name, task, **kwargs)
    
    def list_platforms(self) -> list[str]:
        """列出支持的平台"""
        return list(self.ADAPTERS.keys())
    
    def get_platform_info(self, platform: str) -> dict:
        """获取平台信息"""
        adapter = self.ADAPTERS.get(platform)
        if not adapter:
            return {"error": f"Unknown platform: {platform}"}
        
        return {
            "name": adapter.platform_name,
            "type": adapter.platform_type.value,
            "install_command": self._get_install_command(platform),
        }
    
    def _get_install_command(self, platform: str) -> str:
        """获取平台安装命令"""
        commands = {
            "coze": "Import SKILL.md in Coze dashboard",
            "pip": f"pip install {self.config.package_name or '{skill}'}",
            "claude": "claude plugins install {skill}",
            "openclaw": "claw install {skill}",
            "hermes": "zenskill deploy-skill --platform hermes",
            "local": "zenskill deploy-skill --platform local",
            "codex": "zenskill deploy-skill --platform codex",
            "cursor": "zenskill deploy-skill --platform cursor",
            "opencode": "zenskill deploy-skill --platform opencode",
        }
        return commands.get(platform, "")


# 便捷函数
def install_skill(
    skill_name: str,
    platforms: list[str] = None,
    **kwargs
) -> dict[str, InstallResult]:
    """
    一键安装技能到指定平台
    
    Args:
        skill_name: 技能名称
        platforms: 目标平台列表，None 表示 ["coze", "pip"]
    
    Returns:
        dict: 各平台的安装结果
    """
    installer = SkillInstaller()
    return installer.install(skill_name, platforms, **kwargs)


def check_skill_status(skill_name: str) -> dict[str, dict]:
    """检查技能在所有平台的安装状态"""
    installer = SkillInstaller()
    return installer.check_status(skill_name)
