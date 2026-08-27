"""
ZenSkill - pip 平台适配器

支持 Python pip 包的分发和安装
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from .base import PlatformAdapter, PlatformType, InstallResult, ExecutionResult


class PipAdapter(PlatformAdapter):
    """
    pip 平台适配器
    
    支持通过 pip 安装 Python 包到当前环境
    """
    
    @property
    def platform_name(self) -> str:
        return "pip"
    
    @property
    def platform_type(self) -> PlatformType:
        return PlatformType.PIP
    
    def install(self, skill_name: str, package_name: str = None, **kwargs) -> InstallResult:
        """
        安装 pip 包
        
        Args:
            skill_name: 技能名称
            package_name: PyPI 包名（可选，默认与 skill_name 相同）
        
        Returns:
            InstallResult: 安装结果
        """
        package = package_name or skill_name
        
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode == 0:
                return InstallResult(
                    success=True,
                    platform=self.platform_name,
                    message=f"Successfully installed {package}",
                    skill_path=f"site-packages/{package}",
                )
            else:
                return InstallResult(
                    success=False,
                    platform=self.platform_name,
                    message=f"pip install failed: {result.stderr}",
                )
                
        except subprocess.TimeoutExpired:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message="pip install timed out",
            )
        except Exception as e:
            return InstallResult(
                success=False,
                platform=self.platform_name,
                message=f"Installation failed: {str(e)}",
            )
    
    def uninstall(self, skill_name: str) -> InstallResult:
        """卸载 pip 包"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "uninstall", skill_name, "-y"],
                capture_output=True,
                text=True,
                timeout=120,
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
        """执行 Python 包中的技能"""
        try:
            # 尝试导入并执行
            module = __import__(skill_name, fromlist=[""])
            
            if hasattr(module, "execute"):
                output = module.execute(task)
            elif hasattr(module, "run"):
                output = module.run(task)
            else:
                output = f"Module '{skill_name}' loaded. Use it as a Python package."
            
            return ExecutionResult(
                success=True,
                output=output,
            )
            
        except ImportError:
            return ExecutionResult(
                success=False,
                output=None,
                error=f"Package '{skill_name}' not installed. Run: pip install {skill_name}",
            )
        except Exception as e:
            return ExecutionResult(
                success=False,
                output=None,
                error=str(e),
            )
    
    def is_installed(self, skill_name: str) -> bool:
        """检查包是否已安装"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "show", skill_name],
                capture_output=True,
                text=True,
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def get_installed_packages(self) -> list:
        """获取已安装的包列表"""
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "list", "--format=json"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
            return []
        except Exception:
            return []
