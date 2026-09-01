"""短期记忆 — 会话内内存缓存 + JSONL 桥接 (ZSR2)

v3.0: 新增 JSONL 桥接，recall() miss 时从文件加载
新增: cleanup_expired() 清理过期条目
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Optional

from .memory_store import MemoryEntry, MemoryStore, MemoryType


class ShortTermMemory(MemoryStore):
    """短期记忆

    会话内内存存储，保留最近 N 条记忆。
    超过容量时自动淘汰最旧的记忆。
    JSONL 桥接: recall() miss 时从文件加载。

    使用方式：
        memory = ShortTermMemory(max_size=10)
        await memory.remember(MemoryEntry(content="test", source="user"))
        results = await memory.recall("test")
    """

    def __init__(self, max_size: int = 10, memory_dir=None) -> None:
        """初始化短期记忆

        Args:
            max_size: 最大容量
            memory_dir: 自定义存储目录
        """
        super().__init__(memory_dir=memory_dir)
        self._max_size = max_size
        self._entries: deque[MemoryEntry] = deque(maxlen=max_size)
        self._index: dict[str, MemoryEntry] = {}
        self._lock = __import__("threading").Lock()

    async def remember(self, entry: MemoryEntry) -> None:
        """存储记忆（内存 + JSONL 双写）

        超过容量时自动淘汰最旧的记忆。
        """
        with self._lock:
            if entry.id in self._index:
                self._entries = deque(
                    [e for e in self._entries if e.id != entry.id],
                    maxlen=self._max_size,
                )
            self._entries.append(entry)
            self._index[entry.id] = entry
        await super().remember(entry)

    async def recall(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """检索相关记忆

        优先查内存缓存，miss 时从 JSONL 文件加载。
        """
        results = []
        query_lower = query.lower()

        with self._lock:
            for entry in reversed(self._entries):
                if len(results) >= limit:
                    break
                if memory_type and entry.memory_type != memory_type:
                    continue
                if query_lower in entry.content.lower():
                    entry.access()
                    results.append(entry)
                elif any(query_lower in tag.lower() for tag in entry.tags):
                    entry.access()
                    results.append(entry)

        # 内存 miss 时从 JSONL 加载
        if len(results) < limit:
            file_results = await super().recall(
                query, limit=limit - len(results), memory_type=memory_type
            )
            # 去重
            existing_ids = {r.id for r in results}
            for entry in file_results:
                if entry.id not in existing_ids:
                    results.append(entry)
                    if len(results) >= limit:
                        break

        return results

    async def forget(self, entry_id: str) -> bool:
        """遗忘记忆（内存 + JSONL 双删）"""
        found = False
        if entry_id in self._index:
            self._index.pop(entry_id)
            self._entries = deque(
                [e for e in self._entries if e.id != entry_id],
                maxlen=self._max_size,
            )
            found = True
        # 也从 JSONL 删除
        file_found = await super().forget(entry_id)
        return found or file_found

    async def consolidate(self) -> None:
        """记忆整合

        短期记忆不做整合，但清理过期条目。
        """
        self.cleanup_expired()

    def cleanup_expired(self, max_age_seconds: float = 3600) -> int:
        """清理过期条目

        Args:
            max_age_seconds: 最大存活时间（秒），默认 1 小时

        Returns:
            清理的条目数
        """
        now = time.time()
        before = len(self._entries)
        self._entries = deque(
            [e for e in self._entries if now - e.created_at < max_age_seconds],
            maxlen=self._max_size,
        )
        # 同步更新索引
        self._index = {e.id: e for e in self._entries}
        return before - len(self._entries)

    async def get_context(self, task: str) -> dict[str, Any]:
        """获取任务相关上下文"""
        recent = list(self._entries)[-5:]  # 最近 5 条
        return {
            "recent_memories": [e.to_dict() for e in recent],
            "total_memories": len(self._entries),
        }

    async def clear(self) -> None:
        """清空所有记忆（内存 + JSONL）"""
        self._entries.clear()
        self._index.clear()
        await super().clear()

    async def count(self) -> int:
        """获取记忆总数（内存数）"""
        return len(self._entries)

    def get_all(self) -> list[MemoryEntry]:
        """获取所有内存记忆"""
        return list(self._entries)
