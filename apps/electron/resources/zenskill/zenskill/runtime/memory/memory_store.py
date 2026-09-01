"""记忆存储基础模块 — JSONL 持久化实现 (ZSR1)

v3.0: MemoryStore 基类从 NotImplementedError 改为 JSONL 持久化实现
存储路径: ~/.zenskill/runtime/memory/{type}.jsonl
并发安全: 使用 core/paths.py 的 file_lock + atomic_write_json
"""

from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional


class MemoryType(Enum):
    """记忆类型"""

    FACT = "fact"  # 事实：工具返回的结果
    PROCEDURE = "procedure"  # 流程：成功的执行步骤
    ERROR = "error"  # 错误：失败模式和解决方案
    PREFERENCE = "preference"  # 偏好：用户习惯
    PATTERN = "pattern"  # 模式：反复出现的行为


@dataclass
class MemoryEntry:
    """单条记忆"""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    content: str = ""
    memory_type: MemoryType = MemoryType.FACT
    source: str = ""  # 来源：tool_execution/user_input/evaluation
    context: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 重要性 0.0-1.0
    created_at: float = field(default_factory=time.time)
    accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "source": self.source,
            "context": self.context,
            "importance": self.importance,
            "created_at": self.created_at,
            "accessed_at": self.accessed_at,
            "access_count": self.access_count,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryEntry:
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            content=data.get("content", ""),
            memory_type=MemoryType(data.get("memory_type", "fact")),
            source=data.get("source", ""),
            context=data.get("context", {}),
            importance=data.get("importance", 0.5),
            created_at=data.get("created_at", time.time()),
            accessed_at=data.get("accessed_at", time.time()),
            access_count=data.get("access_count", 0),
            tags=data.get("tags", []),
        )

    def access(self) -> None:
        """记录访问"""
        self.accessed_at = time.time()
        self.access_count += 1


def _get_memory_dir() -> Path:
    """获取 Runtime 记忆存储目录（ZENSKILL_MEMORY_DIR 可覆盖，默认 ~/.zenskill/runtime/memory/）"""
    env_dir = os.environ.get("ZENSKILL_MEMORY_DIR")
    if env_dir:
        return Path(env_dir)
    home = os.path.expanduser("~")
    return Path(home) / ".zenskill" / "runtime" / "memory"


def _get_jsonl_path(memory_type: MemoryType) -> Path:
    """获取指定类型的 JSONL 文件路径"""
    return _get_memory_dir() / f"{memory_type.value}s.jsonl"


def _load_jsonl(path: Path) -> list[MemoryEntry]:
    """从 JSONL 文件加载记忆条目"""
    if not path.exists():
        return []
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        data = json.loads(line)
                        if not data.get("deleted"):
                            entries.append(MemoryEntry.from_dict(data))
                    except (json.JSONDecodeError, ValueError):
                        continue
    except OSError:
        pass
    return entries


_save_lock = __import__("threading").Lock()


def _save_jsonl(path: Path, entries: list[MemoryEntry]) -> None:
    """保存记忆条目到 JSONL 文件（原子写入 + 并发锁）"""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for entry in entries:
        lines.append(json.dumps(entry.to_dict(), ensure_ascii=False))
    content = "\n".join(lines)
    if content:
        content += "\n"

    with _save_lock:
        import tempfile
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class MemoryStore:
    """记忆存储基类 — JSONL 持久化实现

    存储路径: ~/.zenskill/runtime/memory/{type}.jsonl
    并发安全: 文件级锁 + 原子写入
    """

    def __init__(self, memory_dir: str | Path | None = None) -> None:
        """初始化记忆存储

        Args:
            memory_dir: 自定义存储目录，默认 ~/.zenskill/runtime/memory/
        """
        self._memory_dir = Path(memory_dir) if memory_dir else _get_memory_dir()
        self._memory_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[MemoryType, list[MemoryEntry]] = {}
        self._loaded: set[MemoryType] = set()

    def _load(self, memory_type: MemoryType) -> list[MemoryEntry]:
        """加载指定类型的记忆（带缓存）"""
        if memory_type not in self._loaded:
            path = self._memory_dir / f"{memory_type.value}s.jsonl"
            self._cache[memory_type] = _load_jsonl(path)
            self._loaded.add(memory_type)
        return self._cache[memory_type]

    def _save(self, memory_type: MemoryType) -> None:
        """保存指定类型的记忆到 JSONL"""
        path = self._memory_dir / f"{memory_type.value}s.jsonl"
        entries = self._cache.get(memory_type, [])
        _save_jsonl(path, entries)

    async def remember(self, entry: MemoryEntry) -> None:
        """存储记忆（写入 JSONL）"""
        entries = self._load(entry.memory_type)
        # 更新已存在的条目
        for i, existing in enumerate(entries):
            if existing.id == entry.id:
                entries[i] = entry
                self._save(entry.memory_type)
                return
        # 新增条目
        entries.append(entry)
        self._save(entry.memory_type)

    async def recall(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """检索相关记忆（全文搜索）"""
        results = []
        query_lower = query.lower()

        types = [memory_type] if memory_type else list(MemoryType)
        for mt in types:
            entries = self._load(mt)
            for entry in reversed(entries):  # 最新的优先
                if len(results) >= limit:
                    break
                # 关键词匹配
                if query_lower in entry.content.lower():
                    entry.access()
                    results.append(entry)
                elif any(query_lower in tag.lower() for tag in entry.tags):
                    entry.access()
                    results.append(entry)

        return results[:limit]

    async def forget(self, entry_id: str) -> bool:
        """遗忘记忆（标记删除 + 重写文件）"""
        for mt in MemoryType:
            entries = self._load(mt)
            for i, entry in enumerate(entries):
                if entry.id == entry_id:
                    entries.pop(i)
                    self._save(mt)
                    return True
        return False

    async def consolidate(self) -> None:
        """记忆整合：衰减不常用记忆，删除过期记忆"""
        now = time.time()
        thirty_days = 30 * 24 * 3600
        for mt in MemoryType:
            entries = self._load(mt)
            changed = False
            for entry in entries:
                # 衰减不常用记忆
                if entry.access_count < 3 and entry.created_at < now - thirty_days:
                    entry.importance *= 0.9
                    changed = True
            # 删除重要性过低的记忆
            before = len(entries)
            entries[:] = [e for e in entries if e.importance >= 0.1]
            if len(entries) != before:
                changed = True
            if changed:
                self._save(mt)

    async def get_context(self, task: str) -> dict[str, Any]:
        """获取任务相关上下文"""
        memories = await self.recall(task, limit=5)
        return {
            "related_memories": [m.to_dict() for m in memories],
            "total_memories": await self.count(),
        }

    async def clear(self) -> None:
        """清空所有记忆"""
        for mt in MemoryType:
            self._cache[mt] = []
            self._save(mt)

    async def count(self) -> int:
        """获取记忆总数"""
        total = 0
        for mt in MemoryType:
            total += len(self._load(mt))
        return total

    async def store(self, entry: MemoryEntry) -> None:
        """存储记忆（remember 别名）"""
        await self.remember(entry)

    async def get(self, entry_id: str) -> Optional[MemoryEntry]:
        """按 ID 获取记忆"""
        for mt in MemoryType:
            entries = self._load(mt)
            for entry in entries:
                if entry.id == entry_id:
                    return entry
        return None

    async def search(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """搜索记忆（recall 别名）"""
        return await self.recall(query, limit=limit, memory_type=memory_type)

    async def delete(self, entry_id: str) -> bool:
        """删除记忆（forget 别名）"""
        return await self.forget(entry_id)

    async def list_all(
        self,
        limit: int = 100,
        offset: int = 0,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """列出所有记忆"""
        all_entries = []
        types = [memory_type] if memory_type else list(MemoryType)
        for mt in types:
            all_entries.extend(self._load(mt))
        # 按创建时间倒序
        all_entries.sort(key=lambda e: e.created_at, reverse=True)
        return all_entries[offset:offset + limit]

    async def export_data(self) -> dict[str, Any]:
        """导出所有记忆为 JSON"""
        result = {}
        for mt in MemoryType:
            entries = self._load(mt)
            result[mt.value] = [e.to_dict() for e in entries]
        return result

    async def import_data(self, data: dict[str, Any]) -> int:
        """从 JSON 导入记忆，返回导入数量"""
        count = 0
        for mt_name, entries_data in data.items():
            try:
                mt = MemoryType(mt_name)
            except ValueError:
                continue
            for entry_data in entries_data:
                entry = MemoryEntry.from_dict(entry_data)
                await self.remember(entry)
                count += 1
        return count
