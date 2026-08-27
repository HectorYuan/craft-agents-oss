"""
ZenSkill - 系统注册中心
管理所有系统的生命周期、依赖关系
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import TypeVar, Type, Optional

from .base import SystemType, BaseSystem, SystemConfig, SystemMetadata

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseSystem)


@dataclass
class SystemRegistration:
    """系统注册信息"""
    system_type: SystemType
    system_class: Type[BaseSystem]
    config: SystemConfig = field(default_factory=SystemConfig)
    instance: Optional[BaseSystem] = None


class SystemRegistry:
    """
    系统注册中心 - 单例模式
    
    功能：
    1. 注册系统类型
    2. 按拓扑顺序初始化系统（处理依赖）
    3. 获取系统实例
    4. 关闭所有系统
    """
    
    _instance: Optional['SystemRegistry'] = None
    
    def __new__(cls) -> 'SystemRegistry':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self) -> None:
        if self._initialized:
            return
        
        self._registrations: dict[SystemType, SystemRegistration] = {}
        self._initialized = True
    
    def register(
        self,
        system_class: Type[BaseSystem] | BaseSystem,
        config: Optional[SystemConfig] = None,
    ) -> None:
        """注册一个系统

        支持两种调用方式：
        - 传入类：registry.register(MetaMemory, config)
        - 传入实例：registry.register(memory_instance, config)
        """
        # 兼容：如果是实例，直接使用；如果是类，先实例化
        if isinstance(system_class, BaseSystem):
            instance = system_class
            cls = type(instance)
        else:
            instance = system_class()
            cls = system_class

        system_type = instance.system_type
        metadata = instance.metadata

        if system_type in self._registrations:
            logger.warning(f"System {system_type.value} already registered, overriding")

        self._registrations[system_type] = SystemRegistration(
            system_type=system_type,
            system_class=cls,
            config=config or SystemConfig(),
        )

        logger.info(
            f"Registered system: {metadata.name} v{metadata.version} "
            f"(priority: {metadata.priority}, type: {system_type.value})"
        )
    
    async def initialize_all(self) -> None:
        """
        初始化所有已注册的系统
        
        按优先级顺序初始化，自动处理依赖关系
        """
        # 按优先级排序
        sorted_registrations = sorted(
            self._registrations.values(),
            key=lambda r: r.system_class().metadata.priority,
        )
        
        for registration in sorted_registrations:
            if not registration.config.enabled:
                logger.info(f"Skipping disabled system: {registration.system_type.value}")
                continue
            
            # 创建实例
            system_instance = registration.system_class()
            registration.instance = system_instance
            
            # 初始化
            await system_instance.initialize(registration.config)
        
        logger.info(f"Initialized {len([r for r in self._registrations.values() if r.instance])} systems")
    
    def get(self, system_type: SystemType | str) -> Optional[BaseSystem]:
        """获取系统实例"""
        if isinstance(system_type, str):
            try:
                system_type = SystemType(system_type)
            except ValueError:
                logger.warning(f"Unknown system type: {system_type}")
                return None
        
        registration = self._registrations.get(system_type)
        if not registration:
            return None
        
        return registration.instance
    
    def get_typed(self, system_type: SystemType, expected_type: Type[T]) -> Optional[T]:
        """获取指定类型的系统实例"""
        instance = self.get(system_type)
        if instance and isinstance(instance, expected_type):
            return instance
        return None
    
    async def shutdown_all(self) -> None:
        """关闭所有系统"""
        # 按逆优先级顺序关闭
        sorted_registrations = sorted(
            self._registrations.values(),
            key=lambda r: r.system_class().metadata.priority,
            reverse=True
        )
        
        for registration in sorted_registrations:
            if registration.instance:
                await registration.instance.shutdown()
                registration.instance = None
        
        logger.info("All systems shutdown")
    
    def reset(self) -> None:
        """
        重置注册中心（测试用）
        
        注意：不会调用 shutdown，仅清空状态
        """
        self._registrations.clear()
        logger.debug("System registry reset")


# 全局单例
registry = SystemRegistry()
