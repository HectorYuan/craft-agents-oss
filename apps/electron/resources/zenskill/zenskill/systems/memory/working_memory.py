"""
ZenSkill - L1 工作记忆

特性：
- 容量极小（默认 20 条）
- LRU 淘汰策略
- 访问即激活到顶部
- 纯内存，零依赖
"""
from __future__ import annotations

import logging
from collections import OrderedDict
from typing import List, Optional

from .memory_base import MemoryItem, BaseMemory

logger = logging.getLogger(__name__)


class WorkingMemory(BaseMemory):
    """
    L1 工作记忆 - 短时记忆缓存
    
    类似人类的工作记忆：
    - 容量很小，只能记住最近的几件事
    - 被访问就会被"激活"，移到顶部
    - 溢出时自动淘汰最久没被访问的
    """
    
    def __init__(self, max_items: int = 20) -> None:
        self._max_items = max_items
        self._items: OrderedDict[str, MemoryItem] = OrderedDict()
        logger.debug(f"WorkingMemory initialized, capacity={max_items}")
    
    async def store(self, item: MemoryItem) -> str:
        """
        存入工作记忆
        
        如果已存在，移到顶部；如果容量满，淘汰最旧的
        """
        item_id = item.id
        
        if item_id in self._items:
            # 已存在，移到顶部
            self._items.move_to_end(item_id)
            return item_id
        
        # 容量检查：溢出则淘汰最旧的（最左边）
        if len(self._items) >= self._max_items:
            oldest_id, oldest_item = self._items.popitem(last=False)
            logger.debug(f"WorkingMemory overflow, evicted: {oldest_id}")
        
        self._items[item_id] = item
        return item_id
    
    async def retrieve(self, query: str, top_k: int = 3) -> List[MemoryItem]:
        """
        检索工作记忆
        
        逻辑：
        1. 关键词匹配筛选
        2. 匹配度 × 记忆强度 排序
        3. 被命中的记忆会被激活，移到顶部
        """
        query_lower = query.lower()
        results: list[tuple[MemoryItem, float]] = []
        
        for item in self._items.values():
            # 计算匹配度
            match_score = item.matches_query(query)
            if match_score > 0:
                # 综合得分 = 匹配度 × 记忆强度
                total_score = match_score * item.get_strength()
                results.append((item, total_score))
                item.touch()  # 激活
        
        # 按得分降序排序
        results.sort(key=lambda x: x[1], reverse=True)
        
        # 所有命中的都移到顶部（保持顺序）
        for item, _ in results:
            self._items.move_to_end(item.id)
        
        return [item for item, _ in results[:top_k]]
    
    async def forget(self, item_id: str) -> bool:
        """主动遗忘某条记忆"""
        if item_id in self._items:
            del self._items[item_id]
            logger.debug(f"WorkingMemory forgot: {item_id}")
            return True
        return False
    
    def get(self, item_id: str) -> Optional[MemoryItem]:
        """直接获取某条记忆（不触发激活）"""
        return self._items.get(item_id)
    
    def get_and_touch(self, item_id: str) -> Optional[MemoryItem]:
        """获取并激活"""
        item = self._items.get(item_id)
        if item:
            item.touch()
            self._items.move_to_end(item_id)
        return item
    
    def get_recent(self, n: int = 5) -> List[MemoryItem]:
        """获取最近的 n 条记忆"""
        items = list(self._items.values())
        return items[-n:] if items else []
    
    def __len__(self) -> int:
        return len(self._items)
    
    def clear(self) -> None:
        """清空所有记忆"""
        self._items.clear()
    
    def __repr__(self) -> str:
        return f"WorkingMemory(size={len(self._items)}/{self._max_items})"
