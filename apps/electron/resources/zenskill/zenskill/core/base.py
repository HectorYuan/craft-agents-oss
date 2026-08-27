"""
ZenSkill - 核心基础模块
定义系统类型、系统基类、配置类等核心抽象
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SystemType(Enum):
    """系统类型枚举"""
    PERCEPTION = "perception"
    REASONING = "reasoning"
    PLANNING = "planning"
    EXECUTION = "execution"
    MEMORY = "memory"
    COLLABORATION = "collaboration"
    
    # === ZenSkill 独创系统 ===
    ZENLOOP = "zenloop"          # 禅思循环系统
    CULTIVATING = "cultivating"  # 修炼体系系统
    METALEARNING = "metalearning" # 元学习诊断系统


@dataclass
class SystemMetadata:
    """系统元数据"""
    name: str
    version: str
    description: str = ""
    priority: int = 100  # 优先级，越小越先初始化
    dependencies: list[SystemType] = field(default_factory=list)


@dataclass
class SystemConfig:
    """系统配置"""
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)


class BaseSystem(ABC):
    """
    系统基类
    
    所有 ZenSkill 系统都需要继承这个基类
    """
    
    @property
    @abstractmethod
    def system_type(self) -> SystemType:
        """返回系统类型"""
        pass
    
    @property
    @abstractmethod
    def metadata(self) -> SystemMetadata:
        """返回系统元数据"""
        pass
    
    async def initialize(self, config: SystemConfig) -> None:
        """
        初始化系统
        
        子类可以重写此方法来执行初始化逻辑
        """
        logger.info(f"Initializing system: {self.metadata.name} v{self.metadata.version}")
    
    async def shutdown(self) -> None:
        """
        关闭系统
        
        子类可以重写此方法来执行清理逻辑
        """
        logger.info(f"Shutting down system: {self.metadata.name}")
