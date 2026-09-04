"""JSONL 树会话（参照 pi coding-agent v3 session 格式）。

文件布局：每会话一个 append-only JSONL，首行 header，其后每行一个 entry；
entry 的 parentId 链构成树，分支 = 换一个 parentId 继续追加；当前分支 =
根到 leaf 的路径。resume = 重放 entries 沿 parentId 链走到 leaf。
"""
from __future__ import annotations

import json
import logging
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

logger = logging.getLogger(__name__)


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
        line = json.dumps(entry.to_dict(), ensure_ascii=False) + "\n"
        persisted = False
        with self._write_lock:
            # WAL: 写入 .wal 临时文件，成功后原子追加到主文件
            wal_path = str(self.path) + ".wal"
            try:
                with open(wal_path, "a", encoding="utf-8") as wf:
                    wf.write(line)
                    wf.flush()
                    os.fsync(wf.fileno())
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())
                try:
                    os.unlink(wal_path)
                except OSError:
                    pass
                persisted = True
            except Exception as wal_err:
                # WAL 失败时 fallback 到直接写入
                try:
                    with open(self.path, "a", encoding="utf-8") as f:
                        f.write(line)
                        f.flush()
                    persisted = True
                except Exception as direct_err:
                    logger.error(
                        "session append NOT persisted (entry %s): wal=%s, direct=%s",
                        entry.id, wal_err, direct_err,
                    )
            if not persisted:
                # 磁盘没写进去：内存不能假装成功，否则崩溃恢复丢消息且无迹可查
                raise OSError(f"session write failed (wal + direct): {self.path}")
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

    def set_branch_label(self, entry_id: str, label: str) -> SessionEntry:
        """给历史 entry 打命名分支标签并切到该分支（持久化，reload 自动恢复）。

        落盘为 custom entry（{tag: "branch", targetEntryId, label}），
        collect_pairs/build_context 天然跳过，不影响上下文重建。
        """
        if not label or not label.strip():
            raise ValueError("branch label must be non-empty")
        if not any(e.id == entry_id for e in self.entries):
            raise ValueError(f"entry not found: {entry_id}")
        entry = self.append("custom", {
            "tag": "branch",
            "targetEntryId": entry_id,
            "label": label.strip(),
        })
        # append 会把 _leaf_override 重置回主干叶子，分支切换需在其后指向
        self._leaf_override = entry_id
        return entry

    def get_branch_labels(self) -> Dict[str, str]:
        """聚合分支标签：{targetEntryId: label}（同目标后写覆盖先写）。"""
        labels: Dict[str, str] = {}
        for e in self.entries:
            if e.type == "custom" and e.data.get("tag") == "branch":
                target = e.data.get("targetEntryId")
                label = e.data.get("label")
                if target and label:
                    labels[target] = label
        return labels

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

    def collect_pairs(self, leaf_id: Optional[str] = None) -> tuple:
        """沿分支收集 (entry_id, Message) 对，应用 compaction 折叠。

        返回 (collected, model)：collected[0] 可能是历史摘要（entry_id=None）。
        """
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
        return collected, model

    def build_context(self, leaf_id: Optional[str] = None) -> Dict[str, Any]:
        """产出 {messages, model}；分支上的 compaction entry 把被压缩前缀替换为摘要"""
        collected, model = self.collect_pairs(leaf_id)
        return {"messages": [m for _, m in collected], "model": model}


_health_hint_shown = False


def session_health_hints(manager: "SessionManager", *, force: bool = False) -> list[str]:
    """扫描 sessions 目录，返回需要打印的清理提示列表。

    触发条件：
    - 目录总大小 > 100MB
    - 有超过 30 天的会话文件

    同一进程内默认只提示一次（force=True 强制重新检查）。
    """
    global _health_hint_shown
    if _health_hint_shown and not force:
        return []
    _health_hint_shown = True

    root = manager.root
    if not root.is_dir():
        return []

    import time as _time

    hints: list[str] = []
    cutoff = _time.time() - 30 * 86400
    total_size = 0
    stale_count = 0
    stale_size = 0

    for p in root.glob("*.jsonl"):
        try:
            st = p.stat()
        except OSError:
            continue
        total_size += st.st_size
        if st.st_mtime < cutoff:
            stale_count += 1
            stale_size += st.st_size

    if total_size > 100 * 1024 * 1024:
        mb = total_size / (1024 * 1024)
        hints.append(
            f"sessions/ 占用 {mb:.0f}MB（超过 100MB），"
            "运行 zenskill agent-engine session prune 清理"
        )
    if stale_count > 0:
        mb = stale_size / (1024 * 1024)
        hints.append(
            f"有 {stale_count} 个超过 30 天的会话（{mb:.1f}MB），"
            "运行 zenskill agent-engine session prune --older-than 30 --delete 清理"
        )
    return hints


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
        session = Session(path, header, entries)
        # 恢复分支选择：最后一条 branch 标记的 target 即当前分支点
        # （branch_from/set_branch_label 的选择原本只存内存，reload 即丢失）
        for e in reversed(entries):
            if e.type == "custom" and e.data.get("tag") == "branch":
                target = e.data.get("targetEntryId")
                if target and any(x.id == target for x in entries):
                    session._leaf_override = target
                break
        return session

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
                    "branches": len(s.get_branch_labels()),
                })
            except (ValueError, KeyError, json.JSONDecodeError):
                continue
        return out
