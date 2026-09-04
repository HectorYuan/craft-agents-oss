"""AgentChatSession — TUI 用的 agent 会话封装。

桥接 AgentLoop + SessionManager + CapabilityHost，为 TUI 提供：
- 持久化会话（JSONL）
- 完整工具/能力/重试
- TUI chunk 格式输出（与 stream_from_llm 兼容）

用法：
    session = AgentChatSession(model="deepseek-v4-flash")
    async for chunk in session.chat("hello"):
        # chunk = {"type": "content"|"reasoning"|"tool_start"|"tool_end"|"error"|"done", "content": ...}
"""
from __future__ import annotations

import asyncio
import os
import logging
from pathlib import Path
from collections.abc import AsyncIterator
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)




def _tui_session_id_file() -> Path:
    return Path.home() / ".zenskill" / "tui_agent_session_id"


def _load_last_session_id() -> Optional[str]:
    f = _tui_session_id_file()
    if f.exists():
        try:
            sid = f.read_text(encoding="utf-8").strip()
            if sid:
                return sid
        except Exception:
            pass
    return None


def _save_session_id(sid: str) -> None:
    try:
        f = _tui_session_id_file()
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(sid, encoding="utf-8")
    except Exception:
        pass


def _clear_session_id() -> None:
    try:
        _tui_session_id_file().unlink(missing_ok=True)
    except Exception:
        pass

class AgentChatSession:
    """TUI 用的 agent 会话封装。"""

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
        self._thinking_level = "medium"

        # Lazy init — 首次 chat() 时创建
        self._loop = None
        self._context = None
        self._session = None
        self._session_manager = None
        self._host = None
        self._tools = None
        self._model_config = None
        self._abort_event = asyncio.Event()
        self._initialized = False
        self._init_error = None

    def _ensure_init(self) -> bool:
        """同步初始化检查（首次调用时触发 async init）。"""
        return self._initialized

    async def _do_init(self) -> bool:
        """异步初始化 agent engine 组件。

        分两阶段：先初始化 tools/caps/session（不依赖模型），
        再尝试解析模型并创建 AgentLoop。模型不可用时仍可报告工具信息。
        """
        if self._initialized:
            return True

        try:
            from zenskill.runtime.agent.tools import create_default_tools, DEFAULT_SYSTEM_PROMPT
            from zenskill.runtime.agent.builtin_capabilities import (
                MemoryCapability, SummaryCapability, ReflectionCapability, TaskTypeCapability,
            )
            from zenskill.runtime.agent.capability import CapabilityHost
            from zenskill.runtime.agent.session import SessionManager
        except ImportError as e:
            self._init_error = f"Agent engine 模块未安装: {e}"
            logger.warning(self._init_error)
            return False

        # Phase 1: tools + caps + session（不依赖模型）
        self._session_manager = SessionManager()
        # X1: 尝试加载上次 TUI session（跨启动续聊）
        last_sid = _load_last_session_id()
        if last_sid:
            try:
                self._session = self._session_manager.load(last_sid)
            except Exception:
                self._session = self._session_manager.create(cwd=self._cwd)
        else:
            self._session = self._session_manager.create(cwd=self._cwd)
        # X1: session 创建/加载后立即保存 ID（无论后续 chat 是否成功）
        _save_session_id(self._session.id)

        caps = [TaskTypeCapability()]
        if self._with_memory:
            caps.append(MemoryCapability())
        caps.append(ReflectionCapability())
        caps.append(SummaryCapability())
        self._host = CapabilityHost(caps)

        self._tools = create_default_tools(self._cwd) + self._host.extra_tools
        try:
            from zenskill.runtime.agent.skill_tools import load_skill_tools
            self._tools.extend(load_skill_tools())
        except Exception:
            pass

        prompt = DEFAULT_SYSTEM_PROMPT
        if self._with_skills:
            try:
                from zenskill.runtime.agent.mcp_capability import format_skills_prompt
                section = format_skills_prompt()
                if section:
                    prompt = self._host.build_system_prompt(prompt) + "\n\n" + section
                else:
                    prompt = self._host.build_system_prompt(prompt)
            except Exception:
                prompt = self._host.build_system_prompt(prompt)
        else:
            prompt = self._host.build_system_prompt(prompt)
        self._base_prompt = prompt

        # Phase 2: 模型 + AgentLoop（可能失败）
        try:
            from zenskill.runtime.agent.providers import resolve_model, create_stream
            from zenskill.runtime.agent.agent_loop import AgentLoop, AgentLoopConfig
            from zenskill.runtime.agent.delegate_tool import DelegateTool

            # 占位模型名消毒：旧托管 provider 会返回 "DeepSeek/test-model" 这类
            # 字符串，形似 provider/model 但 leaf 是占位符——当作未指定，
            # 让 resolve_model 走环境变量/配置自动探测
            model_name = self._model_name
            if model_name:
                leaf = (model_name.split("/", 1)[1] if "/" in model_name else model_name)
                if leaf.strip().lower() in ("test-model", "mock-gpt", "mock",
                                            "unknown", "未配置"):
                    model_name = None
            # DeepSeek key 注入（与 TUI streaming.py 同源：model-switcher DB）
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

            self._model_config = resolve_model(model_name)
            stream_fn = create_stream(self._model_config)
            host_hooks = self._host.hooks()

            # SubAgent delegate：子任务隔离子上下文执行，进度经 on_update 流出
            self._tools.append(DelegateTool(
                stream_fn, self._model_config, cwd=self._cwd,
                system_prompt=self._base_prompt,
            ))

            config = AgentLoopConfig(
                stream=stream_fn,
                model=self._model_config,
                max_steps=self._max_steps,
                abort_event=self._abort_event,
                on_entry=self._session.append_message,
                **host_hooks,
            )
            self._loop = AgentLoop(config)
        except Exception as e:
            self._init_error = f"模型解析失败: {e}（工具和能力已加载）"
            logger.warning(self._init_error)
            # 不 return False — tools/caps 已就绪，chat 时再报错

        self._initialized = True
        logger.info("AgentChatSession 初始化完成: tools=%d", len(self._tools))
        return True

    async def chat(self, user_input: str) -> AsyncIterator[Dict[str, str]]:
        """发送消息，yield TUI chunk 格式。"""
        if not await self._do_init():
            yield {"type": "error", "content": self._init_error or "Agent 初始化失败"}
            yield {"type": "done", "content": ""}
            return

        if self._loop is None:
            yield {"type": "error", "content": self._init_error or "模型不可用，请设置 API Key"}
            yield {"type": "done", "content": ""}
            return

        from zenskill.runtime.agent.types import (
            Context, UserMessage, AssistantMessage, TextContent,
        )

        # 从 session 构建上下文
        built = self._session.build_context()
        messages = list(built.get("messages", []))
        messages.append(UserMessage(content=user_input))

        context = Context(
            messages=messages,
            system_prompt=self._base_prompt,
            tools=self._tools,
        )

        self._abort_event.clear()

        try:
            async for ev in self._loop.run(context):
                etype = type(ev).__name__

                if etype == "MessageUpdate":
                    delta = ev.delta
                    dtype = type(delta).__name__
                    if dtype == "TextDelta":
                        yield {"type": "content", "content": delta.text}
                    elif dtype == "ThinkingDelta":
                        yield {"type": "reasoning", "content": delta.thinking}

                elif etype == "ToolExecutionStart":
                    args_str = _format_args(ev.args)
                    yield {"type": "tool_start", "content": f"[{ev.tool_name}] {args_str}"}

                elif etype == "ToolExecutionUpdate":
                    partial = str(ev.partial_result)[:200] if ev.partial_result else ""
                    if partial:
                        yield {"type": "tool_progress", "content": f"[{ev.tool_name}] {partial}"}

                elif etype == "ToolExecutionEnd":
                    status = "✗" if ev.is_error else "✓"
                    text = ""
                    if hasattr(ev.result, "content") and ev.result.content:
                        first = ev.result.content[0]
                        text = first.text[:120] if hasattr(first, "text") else str(first)[:120]
                    yield {"type": "tool_end", "content": f"[{ev.tool_name}] {status} {text}"}

                elif etype == "MessageEnd":
                    msg = ev.message
                    if hasattr(msg, "stop_reason") and str(msg.stop_reason) in ("error", "aborted"):
                        yield {"type": "error", "content": msg.error_message or str(msg.stop_reason)}

            yield {"type": "done", "content": ""}

            # X4: daily_review 兜底——run 结束时如有 2+ 行动完成，自动触发一次
            self._maybe_auto_daily_review()

        except asyncio.CancelledError:
            self._abort_event.set()
            yield {"type": "done", "content": ""}
        except Exception as e:
            yield {"type": "error", "content": f"Agent 错误: {e}"}
            yield {"type": "done", "content": ""}

    def clear(self) -> str:
        """新建 session，返回新 session ID。"""
        _clear_session_id()
        if self._session_manager:
            self._session = self._session_manager.create(cwd=self._cwd)
            return self._session.id
        return ""

    def session_info(self) -> Dict[str, Any]:
        """返回 session 状态信息。"""
        if not self._session:
            return {"initialized": False, "error": self._init_error}
        built = self._session.build_context()
        return {
            "initialized": self._initialized,
            "session_id": self._session.id,
            "message_count": len(built.get("messages", [])),
            "model": self._model_config.id if self._model_config else "unknown",
            "provider": self._model_config.provider if self._model_config else "unknown",
            "tool_count": len(self._tools) if self._tools else 0,
            "capabilities": [c.name for c in self._host.capabilities] if self._host else [],
            "thinking_level": getattr(self, "_thinking_level", "medium"),
        }

    def _maybe_auto_daily_review(self) -> None:
        """X4: run 结束后如有 2+ 行动完成，自动记一条 daily_review episode。"""
        try:
            from zenskill.core.paths import SkillStateManager
            state = SkillStateManager("zenskill-core").load()
            episodes = state.get("episodes", [])
            today = __import__("datetime").datetime.now().strftime("%Y-%m-%d")
            today_actions = [e for e in episodes
                             if e.get("date") == today and e.get("action") in ("action_done", "agent_session")]
            if len(today_actions) >= 2:
                # 生成简短复盘并记为 episode
                actions_summary = ", ".join(
                    (e.get("content") or "")[:30] for e in today_actions[:5]
                )
                SkillStateManager("zenskill-core").record_episode(
                    action="daily_review",
                    content=f"今日完成 {len(today_actions)} 项：{actions_summary[:120]}",
                    success=True,
                )
        except Exception:
            pass  # 自动复盘失败不影响主流程

    def abort(self) -> None:
        """中止当前运行。"""
        self._abort_event.set()

    def switch_model(self, model_name: str) -> str:
        """切换模型，返回新模型 ID。"""
        try:
            from zenskill.runtime.agent.providers import resolve_model, create_stream
            self._model_config = resolve_model(model_name)
            self._model_name = model_name
            # 重建 loop 以使用新 stream_fn
            if self._loop and self._host:
                stream_fn = create_stream(self._model_config)
                host_hooks = self._host.hooks()
                from zenskill.runtime.agent.agent_loop import AgentLoop, AgentLoopConfig
                config = AgentLoopConfig(
                    stream=stream_fn,
                    model=self._model_config,
                    max_steps=self._max_steps,
                    abort_event=self._abort_event,
                    on_entry=self._session.append_message,
                    **host_hooks,
                )
                self._loop = AgentLoop(config)
            return self._model_config.id
        except Exception as e:
            return f"切换失败: {e}"

    def switch_thinking(self, level: str) -> str:
        """切换 thinking level，返回生效值。"""
        if level not in ("low", "medium", "high"):
            return f"无效 level: {level}"
        self._thinking_level = level
        return level

    async def compact(self) -> str:
        """手动压缩上下文，返回结果摘要。"""
        if not self._session:
            return "无活动会话"
        try:
            from zenskill.runtime.agent.compaction import (
                compact_session,
            )
            result = await compact_session(
                self._session, self._stream_fn, self._model_config,
            )
            if result is None:
                return "未达压缩阈值"
            return (
                f"压缩完成: {result.tokens_before} → {result.tokens_after} tokens "
                f"(裁剪 {result.cut_index} 条)"
            )
        except Exception as e:
            return f"压缩失败: {e}"


def _format_args(args: Any) -> str:
    """格式化工具参数为简短摘要。"""
    if not args or not isinstance(args, dict):
        return ""
    parts = []
    for k, v in args.items():
        if k in ("path", "pattern", "command", "name", "content"):
            s = str(v)
            if len(s) > 60:
                s = s[:57] + "..."
            parts.append(f"{k}={s}")
        elif k == "edits":
            parts.append(f"edits={len(v)}处")
        elif k == "files":
            parts.append(f"files={len(v)}个")
    return " ".join(parts) if parts else ""
