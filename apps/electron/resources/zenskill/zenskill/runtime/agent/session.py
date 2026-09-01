"""JSONL 树会话（参照 pi coding-agent v3 session 格式）。

文件布局：每会话一个 append-only JSONL，首行 header，其后每行一个 entry；
entry 的 parentId 链构成树，分支 = 换一个 parentId 继续追加；当前分支 =
根到 leaf 的路径。resume = 重放 entries 沿 parentId 链走到 leaf。
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .types import (
    AssistantMessage,
    Message,
    UserMessage,
    message_from_dict,
    message_to_dict,
    new_id,
    now_ms,
)

SESSION_VERSION = 1


def _uuid7_like() -> str:
    # 时间有序 id（毫秒前缀 + 随机后缀），树遍历与调试友好
    return f"{now_ms():013d}-{uuid.uuid4().hex[:8]}"


@dataclass
class SessionEntry:
    type: str                 # message | model_change | compaction | custom
    id: str
    parent_id: Optional[str]
    timestamp: int
    data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "id": self.id,
            "parentId": self.parent_id,
            "timestamp": self.timestamp,
            **({"data": self.data} if self.data else {}),
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "SessionEntry":
        return cls(
            type=d.get("type", "custom"),
            id=d.get("id", ""),
            parent_id=d.get("parentId"),
            timestamp=d.get("timestamp", 0),
            data=d.get("data") or {},
        )


class Session:
    def __init__(self, path: Path, header: Dict[str, Any],
                 entries: Optional[List[SessionEntry]] = None) -> None:
        self.path = path
        self.header = header
        self.entries: List[SessionEntry] = entries or []
        self._leaf_override: Optional[str] = None
        self._write_lock = __import__("threading").Lock()

    @property
    def id(self) -> str:
        return str(self.header.get("id", ""))

    @property
    def cwd(self) -> str:
        return str(self.header.get("cwd", ""))

    def _leaf_id(self) -> Optional[str]:
        if self._leaf_override is not None:
            return self._leaf_override
        if not self.entries:
            return None
        parent_ids = {e.parent_id for e in self.entries if e.parent_id}
        # 叶子 = 不被任何 entry 引用为 parent 的最末 entry
        for e in reversed(self.entries):
            if e.id not in parent_ids:
                return e.id
        return self.entries[-1].id

    @property
    def leaf_id(self) -> Optional[str]:
        return self._leaf_id()

    # ------------------------------------------------------------------
    # 追加
    # ------------------------------------------------------------------

    def append(self, type_: str, data: Optional[Dict[str, Any]] = None,
               parent_id: Optional[str] = None) -> SessionEntry:
        entry = SessionEntry(
            type=type_,
            id=_uuid7_like(),
            parent_id=parent_id if parent_id is not None else self._leaf_id(),
            timestamp=now_ms(),
            data=data or {},
        )
        with self._write_lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            self.entries.append(entry)
        self._leaf_override = None
        return entry

    def append_message(self, message: Message, parent_id: Optional[str] = None) -> SessionEntry:
        return self.append(
            "message",
            {"message": message_to_dict(message)},
            parent_id=parent_id,
        )

    def branch_from(self, entry_id: str) -> None:
        """把当前分支切到任意历史 entry，之后 append 从该点分叉"""
        if not any(e.id == entry_id for e in self.entries):
            raise ValueError(f"entry not found: {entry_id}")
        self._leaf_override = entry_id

    # ------------------------------------------------------------------
    # 重建上下文
    # ------------------------------------------------------------------

    def walk(self, leaf_id: Optional[str] = None) -> List[SessionEntry]:
        """沿 parentId 链从根走到 leaf（含 leaf）"""
        target = leaf_id or self._leaf_id()
        if target is None:
            return []
        by_id = {e.id: e for e in self.entries}
        chain: List[SessionEntry] = []
        cur = by_id.get(target)
        while cur is not None:
            chain.append(cur)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        chain.reverse()
        return chain

    def build_context(self, leaf_id: Optional[str] = None) -> Dict[str, Any]:
        """产出 {messages, model}；分支上的 compaction entry 把被压缩前缀替换为摘要"""
        collected: List[Any] = []  # [entry_id, Message] 对
        model: Optional[str] = None
        for entry in self.walk(leaf_id):
            if entry.type == "message":
                collected.append([entry.id, message_from_dict(entry.data.get("message") or {})])
            elif entry.type == "model_change":
                model = entry.data.get("model") or model
            elif entry.type == "compaction":
                first_kept = entry.data.get("firstKeptEntryId")
                if first_kept:
                    idx = next(
                        (i for i, (eid, _) in enumerate(collected) if eid == first_kept),
                        0,
                    )
                    collected = collected[idx:]
                else:
                    collected = []
                summary = entry.data.get("summary") or ""
                if summary:
                    collected.insert(0, [None, UserMessage(
                        content=f"[conversation summary]\n{summary}"
                    )])
        return {"messages": [m for _, m in collected], "model": model}


class SessionManager:
    def __init__(self, root: Optional[str] = None, stateless: bool = False) -> None:
        self.root = Path(root) if root else (
            Path.home() / ".zenskill" / "agent" / "sessions"
        )
        self._stateless = stateless

    def create(self, cwd: Optional[str] = None, session_id: Optional[str] = None) -> Session:
        self.root.mkdir(parents=True, exist_ok=True)
        sid = session_id or uuid.uuid4().hex[:12]
        # 外部 session_id 可能携带路径分量，构造上阻断穿越
        from ...core.paths import safe_child_path

        path = safe_child_path(self.root, f"{sid}.jsonl")
        header = {
            "type": "session",
            "version": SESSION_VERSION,
            "id": sid,
            "cwd": cwd or os.getcwd(),
            "created": now_ms(),
        }
        if not self._stateless:
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(header, ensure_ascii=False) + "\n")
        return Session(path, header)

    def load(self, session_id: str) -> Session:
        """加载会话；崩溃残留的半写行跳过并截断（log recovery）。

        append-only JSONL 在进程被杀时尾部可能留下不完整行：直接 json.loads
        会让整个会话打不开，且下次 append 会与残行拼接造成二次损坏。此处
        逐行解析跳过损坏行，并把文件截断到最后一个完整行。
        """
        path = self.root / f"{session_id}.jsonl"
        if not path.is_file():
            raise FileNotFoundError(f"session not found: {session_id}")
        parsed: List[Dict[str, Any]] = []
        corrupted = 0
        last_good_offset = 0
        with open(path, "rb") as f:
            raw = f.read()
        for line in raw.splitlines(keepends=True):
            text = line.decode("utf-8", errors="replace").strip()
            if not text:
                last_good_offset += len(line)
                continue
            try:
                d = json.loads(text)
            except json.JSONDecodeError:
                corrupted += 1
                continue
            parsed.append(d)
            last_good_offset += len(line)
        if corrupted and last_good_offset < len(raw):
            # 只截尾部残留；中间损坏行（磁盘级异常）保留原字节以便排查
            with open(path, "r+b") as f:
                f.truncate(last_good_offset)
        # header = 首个 type=="session" 的行；否则 header 行已损坏，兜底重建
        header = next(
            (d for d in parsed if isinstance(d, dict) and d.get("type") == "session"),
            None,
        )
        recovered_header = header is None
        if recovered_header:
            header = {
                "type": "session",
                "version": SESSION_VERSION,
                "id": session_id,
                "created": 0,
                "recovered": True,
            }
        entries = [SessionEntry.from_dict(d) for d in parsed if d is not header]
        if corrupted:
            header["corruptedLines"] = corrupted
        return Session(path, header, entries)

    def list_sessions(self) -> List[Dict[str, Any]]:
        if not self.root.is_dir():
            return []
        out = []
        for p in sorted(self.root.glob("*.jsonl")):
            try:
                s = self.load(p.stem)
                out.append({
                    "id": s.id,
                    "cwd": s.cwd,
                    "created": s.header.get("created"),
                    "entries": len(s.entries),
                })
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
        return out
