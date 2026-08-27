"""
ZenSkill - 平台适配器基类

所有平台适配器必须继承此基类并实现相应接口
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class PlatformType(Enum):
    """支持的平台类型"""
    COZE = "coze"
    PIP = "pip"
    CLAUDE = "claude"
    OPENCLAW = "openclaw"
    HERMES = "hermes"
    CODEX = "codex"
    LOCAL = "local"
    CURSOR = "cursor"
    OPENCODE = "opencode"


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    platform: str
    message: str
    skill_path: Optional[str] = None


@dataclass
class ExecutionResult:
    """执行结果"""
    success: bool
    output: Any
    error: Optional[str] = None
    metadata: dict = None


class PlatformAdapter(ABC):
    """
    平台适配器基类
    
    所有平台适配器必须实现以下接口：
    - platform_name: 平台名称
    - install: 安装技能
    - uninstall: 卸载技能
    - execute: 执行技能
    - is_installed: 检查是否已安装
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称"""
        pass
    
    @property
    def platform_type(self) -> PlatformType:
        """返回平台类型枚举"""
        raise NotImplementedError
    
    @abstractmethod
    def install(self, skill_name: str, **kwargs) -> InstallResult:
        """
        安装技能到平台
        
        Args:
            skill_name: 技能名称
            **kwargs: 平台特定参数
        
        Returns:
            InstallResult: 安装结果
        """
        pass
    
    @abstractmethod
    def uninstall(self, skill_name: str) -> InstallResult:
        """
        从平台卸载技能
        
        Args:
            skill_name: 技能名称
        
        Returns:
            InstallResult: 卸载结果
        """
        pass
    
    @abstractmethod
    def execute(self, skill_name: str, task: str, **kwargs) -> ExecutionResult:
        """
        执行技能
        
        Args:
            skill_name: 技能名称
            task: 任务描述
            **kwargs: 执行参数
        
        Returns:
            ExecutionResult: 执行结果
        """
        pass
    
    def is_installed(self, skill_name: str) -> bool:
        """
        检查技能是否已安装
        
        Args:
            skill_name: 技能名称
        
        Returns:
            bool: 是否已安装
        """
        raise NotImplementedError
    
    def get_status(self, skill_name: str) -> dict:
        """
        获取技能状态
        
        Args:
            skill_name: 技能名称
        
        Returns:
            dict: 状态信息
        """
        return {
            "name": skill_name,
            "platform": self.platform_name,
            "installed": self.is_installed(skill_name),
        }
