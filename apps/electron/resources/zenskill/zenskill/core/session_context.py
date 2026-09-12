"""活跃 session 注册表 — TUI/GUI 注册当前 session，companion 从中读取会话主题。

用法：
    # TUI chat 启动时
    from zenskill.core.session_context import register_active_session
    register_active_session("zenskill-core", server.session)

    # companion_summary 读取
    from zenskill.core.session_context import get_session_topic_context
    topic_ctx = get_session_topic_context("zenskill-core")
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# source_id → Session（同进程单例，无锁——TUI/GUI 均为单线程 asyncio）
_active_sessions: Dict[str, Any] = {}


def register_active_session(source_id: str, session: Any) -> None:
    """注册当前活跃 session（chat 开始时调用）。"""
    _active_sessions[source_id] = session


def unregister_active_session(source_id: str) -> None:
    """注销（/clear 时调用）。"""
    _active_sessions.pop(source_id, None)


def get_active_session(source_id: str = "zenskill-core") -> Any:
    """获取当前活跃 session。"""
    return _active_sessions.get(source_id)


def get_session_topic_context(source_id: str = "zenskill-core") -> Dict[str, Any]:
    """从最近 assistant 消息提取会话主题关键词。"""
    session = _active_sessions.get(source_id)
    if session is None:
        return {}
    try:
        built = session.build_context()
        messages = built.get("messages", [])
    except Exception:
        return {}

    topics: List[str] = []
    turn_count = 0
    action_count = 0
    for m in messages:
        mtype = type(m).__name__
        if mtype == "AssistantMessage":
            text = m.text() if hasattr(m, "text") else str(m)
            if text and text.strip():
                topics.append(text[:80].replace("\n", " "))
            turn_count += 1
        elif mtype == "UserMessage":
            turn_count += 1
    # 反转取最新
    recent = list(reversed(topics))[:3]

    return {"recent_topics": recent, "turn_count": turn_count}


def get_user_profile_context() -> Dict[str, Any]:
    """从 SkillStateManager 取用户画像。"""
    try:
        from ..core.paths import SkillStateManager
        state = SkillStateManager("zenskill-core").load()
        metrics = state.get("metrics", {})
        return {
            "level": state.get("level", "NOVICE"),
            "usage_count": state.get("usage_count", 0),
            "success_rate": metrics.get("success_rate", 0.0),
        }
    except Exception:
        return {"level": "NOVICE", "usage_count": 0, "success_rate": 0.0}
