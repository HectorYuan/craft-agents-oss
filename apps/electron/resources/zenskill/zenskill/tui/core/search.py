"""SessionSearcher — 在 JSONL 会话文件中搜索匹配的消息。"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 默认会话存储根目录
_DEFAULT_SESSION_ROOT = Path.home() / ".zenskill" / "agent" / "sessions"

# 防抖时间窗口（秒）
_DEBOUNCE_SECONDS = 0.3


class SessionSearcher:
    """在 JSONL 会话文件中搜索匹配的消息。"""

    def __init__(self, session_root: Optional[Path] = None):
        self._session_root = session_root or _DEFAULT_SESSION_ROOT
        self._last_search_time: float = 0.0

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """搜索会话历史，返回匹配结果列表。

        300ms 防抖：连续快速调用时跳过过于频繁的请求。
        """
        now = time.monotonic()
        if now - self._last_search_time < _DEBOUNCE_SECONDS and query:
            return []
        self._last_search_time = now

        if not query or not query.strip():
            return self.get_recent_sessions(limit)

        results: List[Dict[str, Any]] = []
        if not self._session_root.is_dir():
            return results

        query_lower = query.lower()
        for session_file in self._session_root.glob("*.jsonl"):
            try:
                results.extend(self._search_file(session_file, query_lower))
            except Exception:
                continue

        results.sort(key=lambda r: r.get("timestamp", 0), reverse=True)
        return results[:limit]

    def _search_file(self, path: Path, query_lower: str) -> List[Dict[str, Any]]:
        """在单个会话 JSONL 中搜索匹配的消息。"""
        results: List[Dict[str, Any]] = []
        session_id = path.stem

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # 只搜索 message 类型的 entry
                    if entry.get("type") != "message":
                        continue

                    # 消息内容嵌套在 data.message.content 中
                    msg_data = entry.get("data", {})
                    message = msg_data.get("message", {})
                    content = message.get("content", "")

                    if not content or query_lower not in content.lower():
                        continue

                    role = message.get("role", "unknown")
                    timestamp = entry.get("timestamp", 0)

                    results.append({
                        "session_id": session_id,
                        "role": role,
                        "content": content[:200],
                        "timestamp": timestamp,
                        "tool_count": self._count_tools_in_session(path),
                        "entry_id": entry.get("id", ""),
                    })
        except OSError:
            pass

        return results

    def _count_tools_in_session(self, path: Path) -> int:
        """统计会话中的工具调用总数（惰性计算，仅匹配结果需要时调用）。"""
        count = 0
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if entry.get("type") == "custom":
                        data = entry.get("data", {})
                        if data.get("tool_name"):
                            count += 1
        except OSError:
            pass
        return count

    def get_recent_sessions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取最近的会话列表（无搜索词时）。"""
        results: List[Dict[str, Any]] = []
        if not self._session_root.is_dir():
            return results

        for session_file in self._session_root.glob("*.jsonl"):
            try:
                stat = session_file.stat()
                # 从 header 读取 session id 和创建时间
                header = self._read_header(session_file)
                results.append({
                    "session_id": session_file.stem,
                    "created": header.get("created", 0),
                    "last_active": stat.st_mtime,
                    "size": stat.st_size,
                })
            except Exception:
                continue

        results.sort(key=lambda r: r["last_active"], reverse=True)
        return results[:limit]

    def _read_header(self, path: Path) -> Dict[str, Any]:
        """读取 JSONL 文件的首行 header。"""
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                first_line = f.readline().strip()
                if first_line:
                    return json.loads(first_line)
        except Exception:
            pass
        return {}
