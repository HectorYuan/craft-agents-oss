"""
ZenSkill - 记忆系统基础数据结构

三层记忆体系：
- L1 Working Memory: 工作记忆，LRU，秒级响应
- L2 Episodic Memory: 情景记忆，倒排索引，联想检索
- L3 Semantic Memory: 语义记忆，三元组，知识推理
"""
from __future__ import annotations

import hashlib
import time
import math
from dataclasses import dataclass, field
from collections import OrderedDict
from typing import Any, Optional, Set, List, Tuple

from abc import ABC, abstractmethod


@dataclass
class MemoryItem:
    """
    通用记忆单元
    
    三层记忆共用的基础数据结构
    """
    id: str
    content: str  # 记忆内容
    importance: float = 0.5  # 重要性 0-1
    tags: Set[str] = field(default_factory=set)  # 标签（用于联想检索）
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    
    def touch(self) -> None:
        """标记被访问，更新访问时间和计数"""
        self.last_accessed = time.time()
        self.access_count += 1
    
    def get_strength(self) -> float:
        """
        计算记忆强度（综合评分）
        
        公式：重要性 × 时间衰减 × 访问频率因子
        
        Returns:
            0-1 的记忆强度值
        """
        # 时间衰减: Ebbinghaus 遗忘曲线模拟
        # 越新的记忆越强，半衰期约 7 天
        hours_passed = (time.time() - self.last_accessed) / 3600
        decay_factor = math.exp(-hours_passed * 0.1)  # 7 小时半衰期
        
        # 频率因子: 被访问越多次越强（边际递减）
        freq_factor = 1.0 + math.log(self.access_count + 1, 10) * 0.3
        
        return self.importance * decay_factor * freq_factor
    
    def matches_query(self, query: str) -> float:
        """
        计算与查询的匹配度
        
        Returns:
            0-1 的匹配分数
        """
        query_lower = query.lower()
        content_lower = self.content.lower()
        
        # 精确匹配加分
        if query_lower in content_lower:
            return 1.0
        
        # 标签匹配
        query_tags = set(query_lower.split())
        if self.tags:
            overlap = len(self.tags & query_tags)
            if overlap > 0:
                return min(1.0, overlap / max(len(query_tags), 1))
        
        return 0.0


@dataclass
class SemanticFact:
    """
    语义事实 - 三元组 (主体, 谓词, 客体)
    
    用于 L3 语义记忆，存储结构化知识
    """
    subject: str
    predicate: str
    object: str
    confidence: float = 1.0  # 置信度 0-1
    created_at: float = field(default_factory=time.time)
    
    def get_id(self) -> str:
        """生成三元组唯一 ID"""
        content = f"{self.subject}|{self.predicate}|{self.object}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def matches(
        self,
        subject: Optional[str] = None,
        predicate: Optional[str] = None,
        object: Optional[str] = None,
    ) -> bool:
        """
        检查是否匹配模式
        
        Args:
            subject: 主体（None 表示任意匹配）
            predicate: 谓词（None 表示任意匹配）
            object: 客体（None 表示任意匹配）
        
        Returns:
            是否匹配
        """
        if subject and self.subject != subject:
            return False
        if predicate and self.predicate != predicate:
            return False
        if object and self.object != object:
            return False
        return True


class BaseMemory(ABC):
    """记忆层基类"""
    
    @abstractmethod
    async def store(self, item: MemoryItem) -> str:
        """存储记忆"""
        pass
    
    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """检索记忆"""
        pass
    
    @abstractmethod
    async def forget(self, item_id: str) -> bool:
        """主动遗忘"""
        pass
    
    @abstractmethod
    def __len__(self) -> int:
        """记忆数量"""
        pass
