"""
ZenSkill - OpenClaw 平台适配器

支持 OpenClaw (clawhub) 的技能安装
"""

import subprocess
from pathlib import Path
from typing import Optional

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult


class OpenClawAdapter(PlatformAdapter):
    """
    OpenClaw 平台适配器
    
    OpenClaw 使用 .claw 格式的技能包
    安装命令: claw install {name}
    """
    
    @property
    def platform_name(self) -> str:
        return "openclaw"
    
    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.OPENCLAW
    
    def install(self, skill_name: str, skill_path: str = None, **kwargs) -> InstallResult:
        """
        安装 OpenClaw 技能
        
        Args:
            skill_name: 技能名称
            skill_path: 技能包路径
        
        Returns:
            InstallResult: 安装结果
        """
        try:
            # OpenClaw CLI 安装命令
            result = subprocess.run(
                ["claw", "install", skill_name],
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            if result.returncode == 0:
                return InstallResult(
                    success=True,
                    platform=self.platform_name,
                    message=f"Successfully installed skill '{skill_name}'",
                    skill_path=skill_path,
                )
            else:
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"claw install failed: {result.stderr}",
                )
                
        except FileNotFoundError:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message="Claw CLI not found. Install from: https://clawhub.io",
            )
        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Installation failed: {str(e)}",
            )
    
    def uninstall(self, skill_name: str) -> InstallResult:
        """卸载 OpenClaw 技能"""
        try:
            result = subprocess.run(
                ["claw", "uninstall", skill_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            
            return InstallResult(
                success=result.returncode == 0,
                platform=self.platform_name,
                message=result.stdout if result.returncode == 0 else result.stderr,
            )
            
        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Uninstall failed: {str(e)}",
            )
    
    def execute(self, skill_name: str, task: str, **kwargs) -> ExecutionResult:
        """执行 OpenClaw 技能"""
        try:
            return ExecutionResult(
                success=True,
                output={
                    "message": f"Skill '{skill_name}' installed for OpenClaw",
                    "task": task,
                    "tip": "Use skill via OpenClaw conversation or CLI",
                },
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
            )
    
    def is_installed(self, skill_name: str) -> bool:
        """检查技能是否已安装"""
        try:
            result = subprocess.run(
                ["claw", "list"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return skill_name in result.stdout
            return False
        except Exception:
            return False
    
    def parse_claw_yaml(self, claw_path: str) -> dict:
        """解析 claw.yaml 配置"""
        claw_file = Path(claw_path) / "claw.yaml"
        if claw_file.exists():
            # 简单的 YAML 解析（实际应使用 pyyaml）
            config = {}
            for line in claw_file.read_text().split("\n"):
                if ":" in line and not line.strip().startswith("#"):
                    key, value = line.split(":", 1)
                    config[key.strip()] = value.strip()
            return config
        return {}
