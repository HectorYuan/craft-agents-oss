"""对话会话管理 -- 纯数据层，零 UI 依赖。

从 views/chat.py 提取，去除所有 UI 相关代码。
职责:
- 消息存储和检索
- SQLite 持久化
- LLM 上下文组装 (system + skill + history)
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# 数据类
# ═══════════════════════════════════════════════════════════════


@dataclass
class Message:
    """对话消息数据类。"""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp", 0),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════
# 会话管理
# ═══════════════════════════════════════════════════════════════


class ChatSession:
    """对话会话管理 -- 纯数据层，零 UI 依赖。

    职责:
    - 消息存储和检索
    - DB 持久化 (SQLite chat_messages 表)
    - LLM 上下文组装 (system + skill profiles + history)
    """

    def __init__(
        self,
        skill_id: str = "zenskill-core",
        model: Optional[str] = None,
    ):
        self.messages: List[Message] = []
        self.current_skill_id: str = skill_id
        self._model: Optional[str] = model
        self._provider = None
        self._provider_checked = False
        self._db = None
        self._db_checked = False

    # ── 属性 ──────────────────────────────────────────────────

    @property
    def model(self) -> str:
        if self._model:
            return self._display_model(self._model)
        provider = self._get_provider()
        if provider:
            try:
                name = provider.get_model_name()
                if name and name.lower() != "unknown":
                    return self._display_model(name)
            except Exception:
                pass
            # fallback: 从 LLMConfig 读取
            try:
                from zenskill.core.llm_config import LLMConfig
                cfg = LLMConfig()
                if cfg.model:
                    return self._display_model(cfg.model)
            except Exception:
                pass
        return "未配置"

    @staticmethod
    def _display_model(name: str) -> str:
        """provider 拼接的 'DeepSeek/xxx' 前缀对 TUI 显示是冗余的，只保留模型名。"""
        return name.split("/", 1)[1] if "/" in name else name

    @model.setter
    def model(self, value: str):
        self._model = value

    @property
    def provider_name(self) -> str:
        provider = self._get_provider()
        if provider:
            return type(provider).__name__.replace("LLMProvider", "")
        return "none"

    @property
    def llm_available(self) -> bool:
        return self._get_provider() is not None

    @property
    def turn_count(self) -> int:
        return len([m for m in self.messages if m.role == "user"])

    # ── Provider 懒加载 ────────────────────────────────────────

    def _get_provider(self):
        if not self._provider_checked:
            self._provider_checked = True
            try:
                from zenskill.core.llm_provider import get_llm_provider
                self._provider = get_llm_provider()
            except Exception as e:
                logger.debug("LLM provider 不可用: %s", e)
                self._provider = None
        return self._provider

    # ── DB 懒加载 ──────────────────────────────────────────────

    def _get_db(self):
        if not self._db_checked:
            self._db_checked = True
            try:
                db_path = Path.home() / ".zenskill" / "chat.db"
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS chat_messages (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT,
                        role TEXT,
                        content TEXT,
                        timestamp REAL,
                        metadata TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.commit()
                self._db = conn
            except Exception as e:
                logger.debug("SQLite 不可用: %s", e)
                self._db = None
        return self._db

    # ── 消息操作 ────────────────────────────────────────────────

    def send(self, content: str) -> Message:
        """发送用户消息。"""
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        self._save_message(msg)
        return msg

    def receive(self, role: str, content: str, **metadata) -> Message:
        """接收回复 (assistant/system)。"""
        msg = Message(role=role, content=content, metadata=metadata)
        self.messages.append(msg)
        self._save_message(msg)
        return msg

    def clear(self):
        """清空当前会话历史。"""
        self.messages.clear()

    def get_history(self, n: Optional[int] = None) -> List[Message]:
        """获取消息历史。n=None 返回全部。"""
        if n is None:
            return list(self.messages)
        return self.messages[-n:]

    def get_context_messages(self, n: int = 20) -> List[Dict[str, str]]:
        """获取用于 LLM 的上下文消息列表。"""
        return [{"role": m.role, "content": m.content} for m in self.messages[-n:]]

    # ── DB 持久化 ───────────────────────────────────────────────

    def _save_message(self, msg: Message, session_id: str = "default"):
        db = self._get_db()
        if not db:
            return
        try:
            db.execute(
                "INSERT INTO chat_messages (session_id, role, content, timestamp, metadata) "
                "VALUES (?, ?, ?, ?, ?)",
                (session_id, msg.role, msg.content, msg.timestamp,
                 json.dumps(msg.metadata, ensure_ascii=False)),
            )
            db.commit()
        except Exception as e:
            logger.debug("保存消息失败: %s", e)

    def load_history(self, session_id: str = "default", limit: int = 50) -> List[Message]:
        """从数据库加载历史消息。"""
        db = self._get_db()
        if not db:
            return []
        try:
            rows = db.execute(
                "SELECT role, content, timestamp, metadata FROM chat_messages "
                "WHERE session_id = ? ORDER BY created_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
            messages = []
            for row in reversed(rows):
                meta = json.loads(row[3]) if row[3] else {}
                messages.append(Message(
                    role=row[0], content=row[1],
                    timestamp=row[2], metadata=meta,
                ))
            return messages
        except Exception:
            return []

    # ── 上下文组装 ──────────────────────────────────────────────

    def build_system_prompt(self) -> str:
        """构建系统提示词 -- 注入技能信息 + GTD 状态。"""
        ctx = "你是 ZenSkill AI 助手，帮助用户管理技能、成长和知识。回答简洁、实用，用中文。\n\n"

        # 注入技能信息
        try:
            from zenskill.core.skill_profile import SkillProfile
            profiles = SkillProfile.list_all(limit=10)
            if profiles:
                ctx += "## 当前已安装技能\n"
                for p in profiles[:8]:
                    icon = {"NOVICE": "🌱", "APPRENTICE": "🌿", "JOURNEYMAN": "🌳",
                            "EXPERT": "⭐", "MASTER": "👑"}.get(p.level, "")
                    ctx += f"- {icon} {p.name} [{p.category}] Lv.{p.level} 调用{p.total_interactions}次\n"
        except Exception:
            pass

        # 注入 GTD 状态
        try:
            from zenskill.core.database import db
            rows = db.execute("SELECT count(*) as c FROM gtd_actions WHERE status != 'done'")
            pending = rows[0]["c"] if rows else 0
            if pending:
                ctx += f"\n## GTD 状态\n- 待处理 Actions: {pending} 个\n"
        except Exception:
            pass

        ctx += "\n用户可以:\n"
        ctx += "- 查看技能: CLI `zenskill spec inspect <id>` 或 TUI 按 3\n"
        ctx += "- 安装技能: CLI `zenskill install npx://<pkg>`\n"
        ctx += "- 管理 GTD: CLI `zenskill gtd dashboard` 或 TUI 按 5\n"
        ctx += "- 搜索技能: CLI `zenskill search <关键词>` 或 TUI 按 /\n"

        return ctx

    def assemble_llm_messages(self, user_input: str) -> List[Dict[str, str]]:
        """组装完整的 LLM 消息列表: system + history + current。"""
        messages = [{"role": "system", "content": self.build_system_prompt()}]
        # 最近 10 条历史
        for msg in self.messages[-10:]:
            messages.append({"role": msg.role, "content": msg.content})
        # 当前输入
        messages.append({"role": "user", "content": user_input})
        return messages

    # ── LLM 调用 ────────────────────────────────────────────────

    async def call_llm(self, user_input: str) -> str:
        """调用 LLM 获取完整回复。"""
        provider = self._get_provider()
        if not provider:
            return "(AI 不可用，请设置 API Key)"

        try:
            from zenskill.core.llm_provider import ChatMessage
            llm_messages = [
                ChatMessage(role=m["role"], content=m["content"])
                for m in self.assemble_llm_messages(user_input)
            ]
            response = await provider.chat(llm_messages)
            return response.content
        except Exception as e:
            return f"(LLM 调用失败: {e})"

    def has_stream(self) -> bool:
        """检查 provider 是否支持流式输出。"""
        provider = self._get_provider()
        return provider is not None and hasattr(provider, "stream_chat")
