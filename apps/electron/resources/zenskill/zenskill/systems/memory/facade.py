"""MemoryStore / MemoryEntry：AgentSwarm zenskill_adapter 的稳定契约门面。

AgentSwarm 的 ZenSkillCapability 动态导入 `from zenskill.systems.memory
import MemoryStore, MemoryEntry` 并调用 recall/remember——本模块把该导入面
固定下来（内部组合 EpisodicMemory），签名漂移由 tests/test_swarm_contract.py
契约测试锁定。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from .episodic_memory import EpisodicMemory
from .memory_base import MemoryItem


@dataclass
class MemoryEntry:
    content: str
    tags: List[str] = field(default_factory=list)
    importance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


class MemoryStore:
    def __init__(self, skill_id: str = "zenskill-core",
                 episodic: Optional[EpisodicMemory] = None) -> None:
        self._episodic = episodic or EpisodicMemory(skill_id=skill_id)

    async def remember(self, entry: MemoryEntry) -> str:
        item = MemoryItem(
            id=uuid.uuid4().hex[:16],
            content=entry.content,
            importance=entry.importance,
            tags=set(entry.tags or []),
            metadata=dict(entry.metadata or {}),
        )
        return await self._episodic.store(item)

    async def recall(self, query: str, limit: int = 3) -> List[MemoryEntry]:
        items = await self._episodic.retrieve(query, top_k=limit)
        return [
            MemoryEntry(
                content=item.content,
                tags=sorted(item.tags),
                importance=item.importance,
                metadata=dict(item.metadata),
            )
            for item in items
        ]

    def __len__(self) -> int:
        return len(self._episodic)
