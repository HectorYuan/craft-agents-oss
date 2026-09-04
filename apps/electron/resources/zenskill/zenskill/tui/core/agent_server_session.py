"""AgentServerSession — 用 AgentServer 驱动 TUI chat 的会话封装。

替换原 AgentChatSession 的 AgentLoop 直连路径，改用 AgentServer（含完整
steering/follow_up/compaction/steering/event_collector 能力）。

用法（与 AgentChatSession 接口兼容）：
    session = AgentServerSession(model="deepseek-v4-flash")
    async for chunk in session.chat("hello"):
        # chunk = {"type": "content"|"reasoning"|"tool_start"|"tool_end"|"error"|"done", "content": ...}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# 从 agent_session.py 复用的持久化 helper
from .agent_session import (
    _load_last_session_id,
    _save_session_id,
    _clear_session_id,
    _format_args,
)


class AgentServerSession:
    """AgentServer 驱动的 TUI chat 会话。"""

    def __init__(
        self,
        model: Optional[str] = None,
        cwd: str = ".",
        with_memory: bool = True,
        with_skills: bool = True,
        max_steps: int = 10,
    ) -> None:
        self._model_name = model
        self._cwd = cwd
        self._with_memory = with_memory
        self._with_skills = with_skills
        self._max_steps = max_steps

        self._server = None
        self._initialized = False
        self._init_error = None

        # G3: 崩溃重启追踪
        self._consecutive_crashes = 0
        self._crash_warning_sent = False

    async def _do_init(self) -> bool:
        """初始化 AgentServer（含能力/工具/技能）。"""
        if self._initialized:
            return True

        try:
            from zenskill.runtime.agent.rpc import AgentServer
            from zenskill.runtime.agent.providers import resolve_model, create_stream
        except ImportError as e:
            self._init_error = f"Agent engine 模块未安装: {e}"
            logger.warning(self._init_error)
            return False

        # 模型解析（复用 AgentChatSession 的占位名消毒 + model-switcher 注入）
        model_name = self._model_name
        if model_name:
            leaf = (model_name.split("/", 1)[1] if "/" in model_name else model_name)
            if leaf.strip().lower() in ("test-model", "mock-gpt", "mock", "unknown", "未配置"):
                model_name = None
        model_name = model_name or os.environ.get("ZENSKILL_AGENT_MODEL")
        if model_name is None and not os.environ.get("DEEPSEEK_API_KEY"):
            try:
                import sqlite3
                db = Path.home() / ".model-switch" / "modelswitcher.db"
                if db.exists():
                    conn = sqlite3.connect(str(db))
                    rows = conn.execute(
                        "SELECT es.var_value FROM key_accounts ka "
                        "JOIN env_vars es ON ka.key_env = es.var_name "
                        "WHERE ka.pool_name = 'deepseek'"
                    ).fetchall()
                    conn.close()
                    if rows:
                        os.environ.setdefault("DEEPSEEK_API_KEY", rows[0][0])
            except Exception:
                pass

        try:
            model_config = resolve_model(model_name)
            stream_fn = create_stream(model_config)
        except Exception as e:
            self._init_error = f"模型解析失败: {e}"
            logger.warning(self._init_error)
            return False

        try:
            # AgentServer 会自动初始化 CapabilityHost（with_memory/with_skills）
            self._server = AgentServer(
                model=model_config,
                stream_fn=stream_fn,
                cwd=self._cwd,
                stateless=False,
                max_steps=self._max_steps,
                with_memory=self._with_memory,
                with_skills=self._with_skills,
            )
        except Exception as e:
            self._init_error = f"AgentServer 创建失败: {e}"
            logger.warning(self._init_error)
            return False

        self._model_config = model_config
        # 尝试加载上次 session（跨启动续聊）
        last_sid = _load_last_session_id()
        if last_sid:
            try:
                import asyncio as _aio
                await self._server.handle_command({
                    "type": "switch_session", "sessionId": last_sid,
                })
            except Exception:
                pass

        # 懒初始化能力（与 AgentServer._init_capabilities 同步）
        try:
            self._server._init_capabilities()
        except Exception:
            pass
        self._initialized = True
        logger.info("AgentServerSession 初始化完成")
        return True

    async def chat(self, user_input: str) -> "AsyncIterator[Dict[str, str]]":
        """发送消息，yield TUI chunk 格式（通过 outbox 映射）。"""
        if not self._initialized:
            ok = await self._do_init()
            if not ok:
                yield {"type": "error", "content": self._init_error or "Agent 初始化失败"}
                yield {"type": "done", "content": ""}
                return

        if self._server is None:
            yield {"type": "error", "content": self._init_error or "AgentServer 不可用"}
            yield {"type": "done", "content": ""}
            return

        # 通过 handle_command 启动 prompt（会触发 _run_agent 后台任务）
        self._server.abort_event.clear()
        await self._server.handle_command({"type": "prompt", "message": user_input})

        # G3: 工具执行计数（用于区分空闲崩溃 vs 会话中崩溃）
        tool_exec_count = 0

        # 保存 session ID
        if self._server.session:
            _save_session_id(self._server.session.id)

        # 消费 outbox 事件，映射为 TUI chunk
        try:
            while self._server.running or not self._server.outbox.empty():
                try:
                    event_json = await asyncio.wait_for(
                        self._server.outbox.get(), timeout=0.05,
                    )
                except asyncio.TimeoutError:
                    continue

                if event_json is None:
                    break

                try:
                    event = json.loads(event_json)
                except json.JSONDecodeError:
                    continue

                chunk = self._map_event(event)
                if chunk is not None:
                    # G3: 追踪工具执行次数
                    if event.get("type") == "tool_execution_start":
                        tool_exec_count += 1
                    yield chunk
                    if chunk["type"] == "done":
                        # G3: 正常结束，重置崩溃计数
                        self._consecutive_crashes = 0
                        self._crash_warning_sent = False
                        return

            # outbox 空且不 running —— 正常结束
            yield {"type": "done", "content": ""}

        except asyncio.CancelledError:
            self._server.abort_event.set()
            yield {"type": "done", "content": ""}
        except Exception as e:
            # G3: 崩溃重启区分 — 记录崩溃次数，区分空闲/会话崩溃
            self._consecutive_crashes += 1
            crash_type = "idle" if tool_exec_count == 0 else "session"
            crash_detail = f"Agent 崩溃 ({crash_type}, 工具执行 {tool_exec_count} 次): {e}"

            logger.warning("AgentServerSession crash #%d: %s", self._consecutive_crashes, crash_detail)

            # 连续崩溃 3 次警告
            if self._consecutive_crashes >= 3 and not self._crash_warning_sent:
                yield {
                    "type": "error",
                    "content": f"连续崩溃 {self._consecutive_crashes} 次，建议检查系统状态（API 连通性、模型服务状态）",
                }
                self._crash_warning_sent = True

            yield {"type": "error", "content": crash_detail}
            yield {"type": "done", "content": ""}

    def _map_event(self, event: dict) -> Optional[Dict[str, str]]:
        """AgentServer 事件 → TUI chunk 映射。"""
        etype = event.get("type", "")

        if etype == "message_update":
            delta = event.get("delta", {})
            kind = delta.get("kind", "")
            if kind == "text":
                return {"type": "content", "content": delta.get("text", "")}
            elif kind == "thinking":
                return {"type": "reasoning", "content": delta.get("thinking", "")}
            return None

        elif etype == "tool_execution_start":
            name = event.get("toolName", "")
            args = event.get("args", {})
            from .agent_session import _format_args
            return {"type": "tool_start", "content": f"[{name}] {_format_args(args)}"}

        elif etype == "tool_execution_update":
            name = event.get("toolName", "")
            partial = str(event.get("partialResult", ""))[:200]
            return {"type": "tool_progress", "content": f"[{name}] {partial}"} if partial else None

        elif etype == "tool_execution_end":
            name = event.get("toolName", "")
            is_error = event.get("isError", False)
            text = str(event.get("text", ""))[:120]
            status = "✗" if is_error else "✓"
            return {"type": "tool_end", "content": f"[{name}] {status} {text}"}

        elif etype == "message_end":
            if event.get("stopReason") in ("error", "aborted"):
                return {"type": "error", "content": event.get("errorMessage") or event.get("stopReason", "")}
            return None

        elif etype == "agent_end":
            # G3: 检查是否包含 error 字段（崩溃结束）
            if event.get("error"):
                error_msg = event.get("error")
                # 从 session entry 数量变化判断是否有工具执行中
                entry_count = 0
                if self._server and self._server.session:
                    entry_count = len(self._server.session.entries)
                # entry_count > 1 说明有对话历史 = 会话中崩溃；否则空闲崩溃
                crash_type = "session" if entry_count > 1 else "idle"
                logger.warning(
                    "agent_end with error (type=%s, entries=%d): %s",
                    crash_type, entry_count, error_msg,
                )

            # P3-1: Token 校准 — 真实 input tokens 回报
            usage = event.get("usage", {})
            if usage and usage.get("input", 0) > 0:
                try:
                    from zenskill.runtime.agent.types import record_usage_sample
                    # 从 session 收集 messages 构建估算基准
                    if self._server and self._server.session:
                        built = self._server.session.build_context()
                        msgs = built.get("messages", [])
                        record_usage_sample(msgs, usage["input"])
                except Exception:
                    pass
            return None

        elif etype == "compaction_end":
            before = event.get("tokensBefore", 0)
            after = event.get("tokensAfter", 0)
            return {"type": "tool_end", "content": f"[compaction] ✓ {before} → {after} tokens"}

        elif etype == "compaction_error":
            return {"type": "tool_end", "content": f"[compaction] ✗ {event.get('error', '?')}"}

        # agent_start, turn_start/end, message_start, entry_appended, queue_update, agent_settled
        # → 不直接映射为 TUI chunk（agent_settled 由外层循环检测）
        return None

    def clear(self) -> str:
        """新建 session，返回新 session ID。"""
        _clear_session_id()
        if self._server:
            import asyncio as _aio
            _aio.get_event_loop().run_until_complete(
                self._server.handle_command({"type": "new_session"})
            )
            if self._server.session:
                return self._server.session.id
        return ""

    def session_info(self) -> Dict[str, Any]:
        """返回 session 状态信息。"""
        if not self._server:
            return {"initialized": self._initialized, "error": self._init_error}
        # 确保 session 存在（首次 chat 后才会创建）
        session = self._server.session
        if session is None:
            try:
                session = self._server._ensure_session()
            except Exception:
                pass
        if session is None:
            return {"initialized": self._initialized, "error": self._init_error or "session 未创建"}
        built = session.build_context()
        return {
            "initialized": self._initialized,
            "session_id": session.id,
            "message_count": len(built.get("messages", [])),
            "model": self._model_config.id if self._model_config else "unknown",
            "provider": self._model_config.provider if self._model_config else "unknown",
            "tool_count": len(self._server.start_prompt.__code__.co_consts) if hasattr(self._server.start_prompt, "__code__") else 0,
            "capabilities": [c.name for c in self._server._capability_host.capabilities] if self._server._capability_host else [],
        }

    def abort(self) -> None:
        """中止当前运行。"""
        if self._server:
            self._server.abort_event.set()

    def switch_model(self, model_name: str) -> str:
        """切换模型。"""
        try:
            from zenskill.runtime.agent.providers import resolve_model, create_stream
            self._model_config = resolve_model(model_name)
            self._model_name = model_name
            if self._server:
                self._server.model = self._model_config
                self._server.stream_fn = create_stream(self._model_config)
            return self._model_config.id
        except Exception as e:
            return f"切换失败: {e}"
