"""
MU2-F: 协作记忆共享 (Collaborative Shared Memory)

多 Agent 间的共享记忆系统：
1. 全局公共记忆 — 所有 Agent 可访问
2. 任务上下文 — 当前任务的共享上下文
3. 角色专用记忆 — 特定角色的知识
4. 协作历史 — Agent 间的交互历史
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .protocol import AgentRole

logger = logging.getLogger(__name__)


@dataclass
class MemoryEntry:
    """共享记忆条目"""
    id: str
    content: str
    source: str                    # 来源 Agent ID
    entry_type: str = "general"    # general / task / role / collaboration
    tags: list[str] = field(default_factory=list)
    scope: str = "global"          # global / task / role
    target_role: str = ""          # scope=role 时指定角色
    task_id: str = ""              # scope=task 时指定任务
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5        # 0-1 重要性
    ttl_hours: float = 0           # 0=永不过期

    def is_expired(self) -> bool:
        if self.ttl_hours <= 0:
            return False
        return time.time() - self.timestamp > self.ttl_hours * 3600

    def to_dict(self) -> dict:
        return {
            "id": self.id, "content": self.content[:200],
            "source": self.source, "type": self.entry_type,
            "tags": self.tags, "scope": self.scope,
            "target_role": self.target_role,
            "task_id": self.task_id,
            "timestamp": datetime.fromtimestamp(self.timestamp).isoformat(),
            "importance": self.importance,
        }


class SharedMemory:
    """
    协作共享记忆

    五层记忆模型：
    L0: 全局公共 — 所有 Agent 可读写
    L1: 任务上下文 — 当前任务的共享上下文
    L2: 角色专用 — 特定角色的知识库
    L3: 代理私有 — 单个 Agent 的经验（不存储于此）
    L4: 协作历史 — Agent 间交互历史
    """

    def __init__(self, max_entries: int = 10000):
        self._entries: list[MemoryEntry] = []
        self._max_entries = max_entries
        self._task_contexts: dict[str, dict] = {}  # task_id → context
        self._collaboration_graph: dict[str, set[str]] = {}  # agent_id → {collaborators}

    # ── 写入 ──

    def store(self, content: str, source: str,
              entry_type: str = "general",
              scope: str = "global",
              tags: Optional[list[str]] = None,
              target_role: str = "",
              task_id: str = "",
              importance: float = 0.5,
              ttl_hours: float = 0) -> str:
        """
        存储记忆

        Args:
            content: 内容
            source: 来源
            entry_type: 类型
            scope: 范围
            tags: 标签
            target_role: 目标角色
            task_id: 任务 ID
            importance: 重要性
            ttl_hours: 过期时间

        Returns:
            记忆条目 ID
        """
        entry = MemoryEntry(
            id=f"mem_{uuid.uuid4().hex[:12]}",
            content=content,
            source=source,
            entry_type=entry_type,
            tags=tags or [],
            scope=scope,
            target_role=target_role,
            task_id=task_id,
            importance=importance,
            ttl_hours=ttl_hours,
        )
        self._entries.append(entry)
        self._trim()

        # 记录协作关系
        if source:
            self._collaboration_graph.setdefault(source, set())

        return entry.id

    def update_task_context(self, task_id: str, key: str, value: Any) -> None:
        """更新任务上下文"""
        if task_id not in self._task_contexts:
            self._task_contexts[task_id] = {}
        self._task_contexts[task_id][key] = value

    def record_collaboration(self, agent_a: str, agent_b: str) -> None:
        """记录协作关系"""
        self._collaboration_graph.setdefault(agent_a, set()).add(agent_b)
        self._collaboration_graph.setdefault(agent_b, set()).add(agent_a)

    # ── 读取 ──

    def query(self, query: str = "",
              scope: str = "",
              role: str = "",
              task_id: str = "",
              entry_type: str = "",
              tags: Optional[list[str]] = None,
              limit: int = 20) -> list[MemoryEntry]:
        """
        查询记忆

        Args:
            query: 关键词搜索
            scope: 过滤范围
            role: 过滤角色
            task_id: 过滤任务
            entry_type: 过滤类型
            tags: 过滤标签
            limit: 返回条数

        Returns:
            匹配的记忆条目
        """
        results = [e for e in self._entries if not e.is_expired()]

        if scope:
            results = [e for e in results if e.scope == scope]
        if role:
            results = [e for e in results if e.target_role == role or e.scope == "global"]
        if task_id:
            results = [e for e in results if e.task_id == task_id or e.scope == "global"]
        if entry_type:
            results = [e for e in results if e.entry_type == entry_type]
        if tags:
            results = [e for e in results if any(t in e.tags for t in tags)]
        if query:
            q = query.lower()
            results = [e for e in results if q in e.content.lower()]

        # 按重要性降序
        results.sort(key=lambda e: (-e.importance, -e.timestamp))
        return results[:limit]

    def get_task_context(self, task_id: str) -> dict:
        """获取任务上下文"""
        return self._task_contexts.get(task_id, {})

    def get_collaborators(self, agent_id: str) -> list[str]:
        """获取 Agent 的历史协作者"""
        return list(self._collaboration_graph.get(agent_id, set()))

    def get_collaboration_network(self) -> dict[str, list[str]]:
        """获取完整协作网络"""
        return {
            aid: list(collabs)
            for aid, collabs in self._collaboration_graph.items()
        }

    def get_role_knowledge(self, role: AgentRole, limit: int = 50) -> list[MemoryEntry]:
        """获取角色专用知识"""
        return self.query(
            scope="global",
            role=role.value,
            entry_type="role",
            limit=limit,
        )

    def get_task_memory(self, task_id: str, limit: int = 50) -> list[MemoryEntry]:
        """获取任务相关记忆"""
        return self.query(
            task_id=task_id,
            limit=limit,
        )

    # ── 统计 ──

    def stats(self) -> dict:
        """记忆统计"""
        return {
            "total_entries": len(self._entries),
            "global": len([e for e in self._entries if e.scope == "global"]),
            "task": len([e for e in self._entries if e.scope == "task"]),
            "role": len([e for e in self._entries if e.scope == "role"]),
            "collaboration_edges": sum(
                len(v) for v in self._collaboration_graph.values()
            ) // 2,
            "active_tasks": len(self._task_contexts),
        }

    def list_tasks(self) -> list[str]:
        """列出有上下文的活跃任务"""
        return list(self._task_contexts.keys())

    # ── 内部方法 ──

    def _trim(self) -> None:
        """限制条目数量"""
        if len(self._entries) > self._max_entries:
            self._entries.sort(key=lambda e: (-e.importance, -e.timestamp))
            self._entries = self._entries[:self._max_entries]
