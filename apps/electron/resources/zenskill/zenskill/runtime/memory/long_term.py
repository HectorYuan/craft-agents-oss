"""长期记忆 — SQLite 持久化 + JSONL 桥接 (ZSR3)

v3.0: 新增 JSONL 桥接，consolidate() 触发时写入 JSONL
保持 SQLite 为主要存储，JSONL 作为备份/迁移路径
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from typing import Any, Optional

from .memory_store import MemoryEntry, MemoryStore, MemoryType


class LongTermMemory(MemoryStore):
    """长期记忆

    SQLite 持久化存储，跨会话保留记忆。
    JSONL 桥接: consolidate() 触发时同步写入 JSONL。

    使用方式：
        memory = LongTermMemory(db_path="~/.zenskill/memory.db")
        await memory.remember(MemoryEntry(content="important fact", importance=0.9))
        results = await memory.recall("important")
    """

    def __init__(self, db_path: str | None = None, memory_dir=None) -> None:
        """初始化长期记忆

        Args:
            db_path: SQLite 数据库路径
            memory_dir: JSONL 存储目录
        """
        super().__init__(memory_dir=memory_dir)

        if db_path is None:
            db_path = os.path.expanduser("~/.zenskill/memory.db")

        self._db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _init_db(self) -> None:
        """初始化数据库"""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                memory_type TEXT NOT NULL,
                source TEXT DEFAULT '',
                context TEXT DEFAULT '{}',
                importance REAL DEFAULT 0.5,
                created_at REAL NOT NULL,
                accessed_at REAL NOT NULL,
                access_count INTEGER DEFAULT 0,
                tags TEXT DEFAULT '[]'
            )
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_memory_type ON memories(memory_type)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_importance ON memories(importance DESC)
        """)
        self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_accessed_at ON memories(accessed_at DESC)
        """)
        self._conn.commit()

    def _row_to_entry(self, row: sqlite3.Row) -> MemoryEntry:
        """将数据库行转换为 MemoryEntry"""
        return MemoryEntry(
            id=row["id"],
            content=row["content"],
            memory_type=MemoryType(row["memory_type"]),
            source=row["source"],
            context=json.loads(row["context"]),
            importance=row["importance"],
            created_at=row["created_at"],
            accessed_at=row["accessed_at"],
            access_count=row["access_count"],
            tags=json.loads(row["tags"]),
        )

    async def remember(self, entry: MemoryEntry) -> None:
        """存储记忆（SQLite）"""
        if self._conn is None:
            return

        self._conn.execute(
            """
            INSERT OR REPLACE INTO memories
            (id, content, memory_type, source, context, importance, created_at, accessed_at, access_count, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.id,
                entry.content,
                entry.memory_type.value,
                entry.source,
                json.dumps(entry.context),
                entry.importance,
                entry.created_at,
                entry.accessed_at,
                entry.access_count,
                json.dumps(entry.tags),
            ),
        )
        self._conn.commit()

    async def recall(
        self,
        query: str,
        limit: int = 10,
        memory_type: MemoryType | None = None,
    ) -> list[MemoryEntry]:
        """检索相关记忆（基于关键词匹配和重要性排序）"""
        if self._conn is None:
            return []

        query_lower = query.lower()
        results = []

        sql = "SELECT * FROM memories"
        params: list[Any] = []

        if memory_type:
            sql += " WHERE memory_type = ?"
            params.append(memory_type.value)

        sql += " ORDER BY importance DESC, accessed_at DESC"

        cursor = self._conn.execute(sql, params)
        rows = cursor.fetchall()

        for row in rows:
            entry = self._row_to_entry(row)
            if query_lower in entry.content.lower():
                entry.access()
                results.append(entry)
                if len(results) >= limit:
                    break
            elif any(query_lower in tag.lower() for tag in entry.tags):
                entry.access()
                results.append(entry)
                if len(results) >= limit:
                    break

        return results

    async def forget(self, entry_id: str) -> bool:
        """遗忘记忆"""
        if self._conn is None:
            return False

        cursor = self._conn.execute(
            "DELETE FROM memories WHERE id = ?", (entry_id,)
        )
        self._conn.commit()
        return cursor.rowcount > 0

    async def consolidate(self) -> None:
        """记忆整合（SQLite + JSONL 桥接）

        1. 衰减不常用记忆的重要性
        2. 删除过期记忆（access_count=0 且超过 30 天）
        3. 同步写入 JSONL 文件
        """
        if self._conn is None:
            return

        now = time.time()
        thirty_days = 30 * 24 * 3600

        # 衰减不常用记忆
        self._conn.execute("""
            UPDATE memories
            SET importance = importance * 0.9
            WHERE access_count < 3 AND created_at < ?
        """, (now - thirty_days,))

        # 删除过期记忆（重要性低于 0.1）
        self._conn.execute("""
            DELETE FROM memories
            WHERE importance < 0.1 AND access_count = 0
        """)

        self._conn.commit()

        # JSONL 桥接: 将当前所有记忆同步到 JSONL
        await self._sync_to_jsonl()

    async def _sync_to_jsonl(self) -> None:
        """将 SQLite 数据同步到 JSONL 文件"""
        if self._conn is None:
            return

        from .memory_store import _save_jsonl
        cursor = self._conn.execute("SELECT * FROM memories ORDER BY created_at DESC")
        rows = cursor.fetchall()
        entries = [self._row_to_entry(row) for row in rows]

        # 按类型分组写入
        from collections import defaultdict
        by_type: dict[MemoryType, list[MemoryEntry]] = defaultdict(list)
        for entry in entries:
            by_type[entry.memory_type].append(entry)

        for mt, mt_entries in by_type.items():
            path = self._memory_dir / f"{mt.value}s.jsonl"
            _save_jsonl(path, mt_entries)

    async def get_context(self, task: str) -> dict[str, Any]:
        """获取任务相关上下文"""
        memories = await self.recall(task, limit=5)
        return {
            "related_memories": [m.to_dict() for m in memories],
            "total_memories": await self.count(),
        }

    async def clear(self) -> None:
        """清空所有记忆"""
        if self._conn is None:
            return
        self._conn.execute("DELETE FROM memories")
        self._conn.commit()

    async def count(self) -> int:
        """获取记忆总数"""
        if self._conn is None:
            return 0
        cursor = self._conn.execute("SELECT COUNT(*) FROM memories")
        return cursor.fetchone()[0]

    def close(self) -> None:
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self) -> None:
        self.close()
