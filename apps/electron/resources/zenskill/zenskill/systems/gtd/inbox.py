"""
8.7A: Inbox 捕获引擎

零摩擦捕获 — 任何念头都能 <3 秒落入 Inbox。
多源: CLI/TUI/Hook/stdin, 自动意图解析, MetaMemory 桥接。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class InboxItem:
    id: str
    raw_text: str
    source: str = "cli"
    profile: str = ""  # 所属 profile（空=当前激活）
    created_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S"))
    status: str = "unprocessed"  # unprocessed / clarified / archived
    clarify_result: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "raw_text": self.raw_text, "source": self.source,
            "profile": self.profile,
            "created_at": self.created_at, "status": self.status,
            "clarify_result": self.clarify_result,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "InboxItem":
        return cls(
            id=data.get("id", ""), raw_text=data.get("raw_text", ""),
            source=data.get("source", "cli"),
            profile=data.get("profile", ""),
            created_at=data.get("created_at", ""),
            status=data.get("status", "unprocessed"),
            clarify_result=data.get("clarify_result", {}),
        )


class InboxEngine:
    """Inbox 捕获引擎"""
    _id_counter: int = 0

    @classmethod
    def _next_id(cls) -> str:
        cls._id_counter += 1
        return f"inbox_{int(time.time() * 1000)}_{cls._id_counter}"

    # 快速意图分类关键词
    INTENT_PATTERNS = {
        "action": ["做", "完成", "修复", "实现", "写", "提交", "部署", "测试",
                   "do", "fix", "implement", "write", "commit", "deploy", "test", "todo"],
        "project": ["项目", "计划", "重构", "学习", "掌握", "升级",
                    "project", "plan", "refactor", "learn", "master", "upgrade"],
        "reference": ["参考", "笔记", "文档", "链接", "记录",
                      "reference", "note", "doc", "link", "log"],
        "calendar": ["明天", "下周", "约会", "会议", "提醒", "截止",
                     "tomorrow", "meeting", "appointment", "reminder", "deadline", "due"],
    }

    def __init__(self, data_dir: str = ""):
        if data_dir:
            self._data_dir = Path(data_dir)
        else:
            from ...core.paths import get_user_data_dir
            self._data_dir = get_user_data_dir() / "gtd"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self._data_dir / "inbox.jsonl"

    @staticmethod
    def _current_profile() -> str:
        """获取当前激活的 profile 名称"""
        try:
            from ...core.paths import get_active_profile
            return get_active_profile()
        except Exception:
            return "default"

    def add(self, raw_text: str, source: str = "cli") -> InboxItem:
        item = InboxItem(
            id=InboxEngine._next_id(),
            raw_text=raw_text, source=source,
            profile=self._current_profile(),
        )
        self._append(item)
        self._bridge_to_memory(item)
        return item

    def list(self, status: str = "unprocessed", limit: int = 50) -> list[InboxItem]:
        items = self._read_all()
        if status != "all":
            items = [i for i in items if i.status == status]
        return items[:limit]

    def get(self, item_id: str) -> Optional[InboxItem]:
        for item in self._read_all():
            if item.id == item_id:
                return item
        return None

    def clarify(self, item_id: str, result_type: str, target_id: str = "") -> bool:
        items = self._read_all()
        for item in items:
            if item.id == item_id:
                item.status = "clarified"
                item.clarify_result = {"type": result_type, "target_id": target_id}
                self._rewrite(items)
                return True
        return False

    def archive(self, item_id: str) -> bool:
        items = self._read_all()
        for item in items:
            if item.id == item_id:
                item.status = "archived"
                self._rewrite(items)
                return True
        return False

    def count(self) -> int:
        return len([i for i in self._read_all() if i.status == "unprocessed"])

    def auto_classify(self, text: str) -> str:
        """自动意图归类"""
        text_lower = text.lower()
        scores = {}
        for intent, keywords in self.INTENT_PATTERNS.items():
            scores[intent] = sum(1 for kw in keywords if kw in text_lower)
        best = max(scores, key=scores.get) if scores else "action"
        return best if scores[best] > 0 else "action"

    def check_backlog(self) -> dict:
        """积压检查"""
        count = self.count()
        return {
            "unprocessed": count,
            "alert": count > 20,
            "message": f"Inbox 有 {count} 条未处理，建议执行 clarify" if count > 10 else "",
        }

    # ── 内部 ──

    def _read_all(self) -> list[InboxItem]:
        if not self._file.exists():
            return []
        items = []
        for line in self._file.read_text(encoding="utf-8").strip().split("\n"):
            if not line.strip():
                continue
            try:
                items.append(InboxItem.from_dict(json.loads(line)))
            except Exception:
                continue
        return items

    def _append(self, item: InboxItem) -> None:
        with open(self._file, "a", encoding="utf-8") as f:
            f.write(json.dumps(item.to_dict(), ensure_ascii=False) + "\n")

    def _rewrite(self, items: list[InboxItem]) -> None:
        lines = [json.dumps(i.to_dict(), ensure_ascii=False) for i in items]
        self._file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _bridge_to_memory(self, item: InboxItem) -> None:
        """自动将 Inbox 导入 EpisodicMemory"""
        try:
            from ...systems.memory.meta_memory import MetaMemory
            from ...systems.memory.memory_base import MemoryItem
            import asyncio, hashlib
            item_id = hashlib.md5(item.raw_text.encode()).hexdigest()[:12]
            mem_item = MemoryItem(id=item_id, content=item.raw_text,
                                  importance=0.3, tags={"inbox", item.source})
            mem = MetaMemory(skill_id="zenskill-core")
            asyncio.get_event_loop().run_until_complete(mem.episodic.store(mem_item))
        except Exception:
            pass
