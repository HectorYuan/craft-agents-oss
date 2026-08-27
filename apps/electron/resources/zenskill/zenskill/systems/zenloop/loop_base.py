"""
ZenSkill - ZenLoop 基础定义

四大禅思循环：
- REFLECTION: 反思循环 - 每次交互后即时反思
- CONSOLIDATION: 整合循环 - 周期性记忆整理固化
- INSIGHT: 洞见循环 - 跨领域关联，发现新模式
- PURIFICATION: 净化循环 - 错误修正，认知净化
"""
from __future__ import annotations

import time
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LoopType(Enum):
    """循环类型枚举"""
    REFLECTION = auto()     # 反思循环 - 每次交互后
    CONSOLIDATION = auto()  # 整合循环 - 周期性执行
    INSIGHT = auto()        # 洞见循环 - 积累足够记忆后触发
    PURIFICATION = auto()   # 净化循环 - 出错后修正


@dataclass
class LoopResult:
    """循环执行结果"""
    loop_type: LoopType
    success: bool
    summary: str = ""
    extracted_patterns: list[str] = field(default_factory=list)
    memory_updates: list[dict] = field(default_factory=list)
    new_insights: list[str] = field(default_factory=list)
    action_items: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0
    
    def __post_init__(self) -> None:
        """执行后自动记录时长"""
        if self.duration_ms == 0:
            self.duration_ms = (time.time() - self.metadata.get(
                "_start_time", time.time()
            )) * 1000


class ZenLoopPlugin(ABC):
    """
    ZenLoop 插件抽象基类
    
    所有循环都要实现这个接口
    """
    
    @property
    @abstractmethod
    def loop_type(self) -> LoopType:
        """循环类型"""
        pass
    
    @property
    @abstractmethod
    def trigger_condition(self) -> str:
        """触发条件描述"""
        pass
    
    @abstractmethod
    async def should_trigger(self, context: dict[str, Any]) -> bool:
        """
        判断是否应该触发此循环
        
        Args:
            context: 上下文字典
        
        Returns:
            是否应该触发
        """
        pass
    
    @abstractmethod
    async def execute(
        self,
        context: dict[str, Any],
        memory_system: Optional[Any] = None,
    ) -> LoopResult:
        """
        执行循环逻辑
        
        Args:
            context: 上下文字典
            memory_system: 记忆系统引用（可选）
        
        Returns:
            循环执行结果
        """
        pass
