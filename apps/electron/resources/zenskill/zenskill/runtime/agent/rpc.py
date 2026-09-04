"""JSONL RPC headless 模式（参照 pi coding-agent --mode rpc 的协议形态）。

传输：stdin 每行一个 JSON 命令；stdout 每行一个 JSON（响应 + 事件混流）。
命令集 v1：prompt / steer / follow_up / abort / get_state / set_model /
get_available_models / compact / get_entries / get_messages / new_session /
switch_session / fork。prompt/steer/abort 立即返回，进度走事件流。

事件序列化：AgentEvent + 会话事件（entry_appended）；线上 message_update
丢弃累计快照只传 delta（快照体积大且消费方可由 message_end 重建）。
背压：出站队列有界（默认 512），agent 事件产出在队列满时自然反压。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .agent_loop import AgentLoop, AgentLoopConfig
from .compaction import compact_session
from .permission_gate import PermissionGate
from .providers import ModelConfig, _REGISTRY, build_model_config, create_stream, resolve_model
from .session import Session, SessionManager
from .tools import DEFAULT_SYSTEM_PROMPT, create_default_tools
from .types import (
    AgentEnd,
    AssistantMessage,
    Context,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    StopReason,
    StreamDone,
    StreamError,
    TextContent,
    TextDelta,
    ThinkingDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    TurnEnd,
    TurnStart,
    UserMessage,
    message_to_dict,
    total_usage,
)

PROTOCOL_VERSION = 1
OUTBOX_MAX = 512


class EchoFauxStream:
    """离线冒烟用：每次调用回显最近的 user 消息（无工具调用，立即 done）。"""

    async def __call__(self, model, context, abort_event=None):
        from .types import StreamStart
        query = ""
        for m in reversed(context.messages):
            if isinstance(m, UserMessage):
                query = m.text()
                break
        full_text = f"FAUX: {query}".strip()
        yield StreamStart(AssistantMessage(model="faux"))
        for word in full_text.split(" "):
            yield TextDelta(word + " ")
        yield StreamDone(
            StopReason.STOP,
            AssistantMessage(model="faux", content=[TextContent(full_text)]),
        )


def serialize_event(ev: Any) -> Optional[Dict[str, Any]]:
    """AgentEvent -> 线上 dict；返回 None 表示不发送"""
    etype = type(ev).__name__
    if etype == "AgentStart":
        return {"type": "agent_start"}
    if etype == "AgentEnd":
        return {
            "type": "agent_end",
            "messageCount": len(ev.messages),
            "usage": total_usage(list(ev.messages)).to_dict() if ev.messages else None,
            "truncatedHistory": bool(getattr(ev, "truncated_history", False)),
        }
    if etype == "TurnStart":
        return {"type": "turn_start"}
    if etype == "TurnEnd":
        return {
            "type": "turn_end",
            "stopReason": ev.message.stop_reason,
            "toolResultCount": len(ev.tool_results),
        }
    if etype == "MessageStart":
        return {"type": "message_start"}
    if etype == "MessageUpdate":
        d = ev.delta
        dtype = type(d).__name__
        if dtype == "TextDelta":
            return {"type": "message_update", "delta": {"kind": "text", "text": d.text}}
        if dtype == "ThinkingDelta":
            return {"type": "message_update", "delta": {"kind": "thinking", "thinking": d.thinking}}
        if dtype == "ToolCallStart":
            return {"type": "message_update", "delta": {"kind": "toolCallStart", "index": d.index, "name": d.tool_call.name, "id": d.tool_call.id}}
        if dtype == "ToolCallDelta":
            return {"type": "message_update", "delta": {"kind": "toolCallDelta", "index": d.index, "fragment": d.delta}}
        if dtype == "ToolCallEnd":
            return {"type": "message_update", "delta": {"kind": "toolCallEnd", "index": d.index, "name": d.tool_call.name, "arguments": d.tool_call.arguments}}
        return None  # StreamStart/StreamDone/Error 不在 update 层外发
    if etype == "MessageEnd":
        m = ev.message
        payload: Dict[str, Any] = {
            "type": "message_end",
            "role": "assistant",
            "text": m.text(),
            "stopReason": m.stop_reason,
            "usage": m.usage.to_dict(),
        }
        if m.error_message:
            payload["errorMessage"] = m.error_message
        tool_calls = m.tool_calls()
        if tool_calls:
            payload["toolCalls"] = [
                {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                for tc in tool_calls
            ]
        return payload
    if etype == "ToolExecutionStart":
        return {
            "type": "tool_execution_start",
            "toolCallId": ev.tool_call_id,
            "toolName": ev.tool_name,
            "args": ev.args,
        }
    if etype == "ToolExecutionUpdate":
        return {
            "type": "tool_execution_update",
            "toolCallId": ev.tool_call_id,
            "toolName": ev.tool_name,
            "partialResult": str(ev.partial_result)[:2000],
        }
    if etype == "ToolExecutionEnd":
        return {
            "type": "tool_execution_end",
            "toolCallId": ev.tool_call_id,
            "toolName": ev.tool_name,
            "isError": ev.is_error,
            "text": ev.result.text()[:8000],
        }
    return None


class AgentServer:
    def __init__(
        self,
        model: Optional[ModelConfig] = None,
        stream_fn: Optional[Callable] = None,
        session_root: Optional[str] = None,
        permission: str = "full",
        cwd: Optional[str] = None,
        stateless: bool = False,
        max_steps: Optional[int] = None,
        max_total_tokens: Optional[int] = None,
        with_memory: bool = False,
        with_skills: bool = True,
    ) -> None:
        self.model = model
        self.stream_fn = stream_fn
        self.session_manager = SessionManager(root=session_root, stateless=stateless)
        self.permission = permission
        self.cwd = cwd or "."
        self._stateless = stateless
        self.max_steps = max_steps
        self.max_total_tokens = max_total_tokens
        self.session: Optional[Session] = None
        self.steering: List[UserMessage] = []
        self.follow_up: List[UserMessage] = []
        self.abort_event = asyncio.Event()
        self.run_task: Optional[asyncio.Task] = None
        self.outbox: "asyncio.Queue[Optional[str]]" = asyncio.Queue(maxsize=OUTBOX_MAX)
        self._usage_lock = asyncio.Lock()
        # 工具代理状态
        self._proxy_tools: Dict[str, Any] = {}  # name -> tool spec
        self._proxy_pending: Dict[str, asyncio.Future] = {}  # requestId -> Future
        self._pre_tool_pending: Dict[str, asyncio.Future] = {}  # requestId -> Future
        self._host_system_prompt: str = ""  # Craft 注入的 system prompt
        self._thinking_level: str = "medium"  # 思考深度
        self._auto_compaction: bool = True  # 自动压缩开关
        self._config: Dict[str, Any] = {}  # 运行时配置
        self._with_memory = with_memory
        self._with_skills = with_skills
        # CapabilityHost（能力注入 + 系统提示词增强）
        self._capability_host = None
        # 记忆桥接（统一模式方案：brain 层公共能力，craft/python 两种运行
        # 模式共享；上移自 ws_server 的 Mode C 专用实现）
        self._event_collector = None
        try:
            from ...mirroring.event_collector import EventCollector
            self._event_collector = EventCollector()
        except Exception:
            self._event_collector = None

    def _mirror_event(self, ev: Any) -> None:
        """AgentEvent → ZenSkill mirroring 记录（宿主/GUI 会话进记忆生态）。"""
        if self._event_collector is None:
            return
        try:
            etype = type(ev).__name__
            if etype == "ToolExecutionStart":
                self._event_collector.record_skill_execution(
                    skill_id="agent-engine",
                    task=f"{ev.tool_name}: {json.dumps(ev.args or {}, ensure_ascii=False)[:200]}",
                    success=True,
                    duration_ms=0,
                    context={"tool_name": ev.tool_name, "tool_call_id": ev.tool_call_id},
                )
            elif etype == "ToolExecutionEnd" and ev.is_error:
                text = ev.result.text() if hasattr(ev.result, "text") else str(ev.result)
                self._event_collector.record_error(
                    skill_id="agent-engine",
                    error_msg=f"{ev.tool_name}: {text[:200]}",
                )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # 出站
    # ------------------------------------------------------------------

    def _send(self, payload: Dict[str, Any]) -> None:
        try:
            self.outbox.put_nowait(json.dumps(payload, ensure_ascii=False, default=str))
        except asyncio.QueueFull:
            # 背压兜底：丢最旧事件保响应通道
            try:
                self.outbox.get_nowait()
            except asyncio.QueueEmpty:
                pass
            self.outbox.put_nowait(json.dumps(payload, ensure_ascii=False, default=str))

    async def _send_await(self, payload: Dict[str, Any]) -> None:
        await self.outbox.put(json.dumps(payload, ensure_ascii=False, default=str))

    # ------------------------------------------------------------------
    # 运行
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.run_task is not None and not self.run_task.done()

    def _ensure_session(self) -> Session:
        if self.session is None:
            self.session = self.session_manager.create(cwd=self.cwd)
        return self.session

    def _build_loop(self, context: Context) -> AgentLoop:
        session = self._ensure_session()

        def on_entry(message) -> None:
            entry = session.append_message(message)
            self._send({
                "type": "entry_appended",
                "entryId": entry.id,
                "entryType": entry.type,
                "role": type(message).__name__.replace("Message", ""),
            })

        def take_steering() -> List[UserMessage]:
            taken, self.steering = self.steering, []
            if taken or self.steering or self.follow_up:
                self._send({"type": "queue_update", "steering": len(self.steering), "followUp": len(self.follow_up)})
            return taken

        def take_follow_up() -> List[UserMessage]:
            taken, self.follow_up = self.follow_up, []
            if taken or self.steering or self.follow_up:
                self._send({"type": "queue_update", "steering": len(self.steering), "followUp": len(self.follow_up)})
            return taken

        # CapabilityHost hooks（transform_context / before_tool_call / after_tool_call / prepare_next_turn）
        cap_hooks = {}
        if self._capability_host is not None:
            try:
                cap_hooks = self._capability_host.hooks()
            except Exception:
                pass

        # PermissionGate 与 capability before_tool_call 合并
        perm_gate = PermissionGate(self.permission, cwd=self.cwd) if self.permission != "full" else None
        cap_before = cap_hooks.get("before_tool_call")
        def merged_before_tool(tc, params):
            if perm_gate is not None:
                veto = perm_gate(tc, params)
                if isinstance(veto, dict) and veto.get("block"):
                    return veto
            if cap_before is not None:
                return cap_before(tc, params)
            return None

        config = AgentLoopConfig(
            stream=self.stream_fn,
            model=self.model,
            abort_event=self.abort_event,
            before_tool_call=merged_before_tool if (perm_gate or cap_before) else None,
            transform_context=cap_hooks.get("transform_context"),
            after_tool_call=cap_hooks.get("after_tool_call"),
            prepare_next_turn=cap_hooks.get("prepare_next_turn"),
            get_steering_messages=take_steering,
            get_follow_up_messages=take_follow_up,
            on_entry=on_entry,
            tool_executor=self._build_proxy_executor(context) if self._proxy_tools else None,
            max_steps=self.max_steps,
            max_total_tokens=self.max_total_tokens,
        )
        # 注入 Craft system prompt（合并到 Context.system_prompt）
        if self._host_system_prompt:
            config._host_system_prompt = self._host_system_prompt
        return AgentLoop(config)

    def _build_proxy_executor(self, context: "Context"):
        """构建工具代理执行器：代理表内工具发 tool_execute_request 委托宿主；
        表外工具（builtin：ls/bash/read...）走进程内执行。

        此前无条件转发所有工具——宿主 routeToolCall 只认 MCP 代理工具，
        导致 builtin 工具全部返回 Unknown tool（craft 模式基础工具断裂根因）。
        """
        proxy_tools = self._proxy_tools
        proxy_pending = self._proxy_pending
        pre_tool_pending = self._pre_tool_pending
        send = self._send
        local_tools = {t.name: t for t in context.tools}

        async def executor(tc, params):
            from uuid import uuid4
            from .types import ToolResultMessage, TextContent

            # pre_tool_use 请求（可选）
            if pre_tool_pending is not None:
                pre_id = f"ptu-{uuid4().hex[:8]}"
                pre_future = asyncio.get_running_loop().create_future()
                pre_tool_pending[pre_id] = pre_future
                send({"type": "pre_tool_use_request", "requestId": pre_id,
                      "toolName": tc.name, "input": params})
                try:
                    pre_result = await asyncio.wait_for(pre_future, timeout=120.0)
                    if pre_result.get("action") == "block":
                        return ToolResultMessage(
                            tool_call_id=tc.id, tool_name=tc.name,
                            content=[TextContent(f"Tool blocked: {pre_result.get('reason', 'denied')}")],
                            is_error=True,
                        )
                    if pre_result.get("action") == "modify" and pre_result.get("input"):
                        params = pre_result["input"]
                except asyncio.TimeoutError:
                    pass  # 超时不阻塞，继续执行

            # 非代理工具（builtin）走进程内执行
            if tc.name not in proxy_tools:
                tool = local_tools.get(tc.name)
                if tool is None:
                    return ToolResultMessage(
                        tool_call_id=tc.id, tool_name=tc.name,
                        content=[TextContent(f"Unknown tool: {tc.name}")],
                        is_error=True,
                    )
                try:
                    result = await tool.run(tc.id, params)
                    return ToolResultMessage(
                        tool_call_id=tc.id, tool_name=tc.name,
                        content=result.content,
                        is_error=result.is_error,
                    )
                except Exception as e:
                    return ToolResultMessage(
                        tool_call_id=tc.id, tool_name=tc.name,
                        content=[TextContent(f"{type(e).__name__}: {e}")],
                        is_error=True,
                    )

            # 代理工具：tool_execute 请求委托宿主
            req_id = f"proxy-{uuid4().hex[:8]}"
            future = asyncio.get_running_loop().create_future()
            proxy_pending[req_id] = future
            send({"type": "tool_execute_request", "requestId": req_id,
                  "toolName": tc.name, "args": params})
            try:
                result = await asyncio.wait_for(future, timeout=120.0)
            except asyncio.TimeoutError:
                return ToolResultMessage(
                    tool_call_id=tc.id, tool_name=tc.name,
                    content=[TextContent(f"Tool proxy timeout after 120s: {tc.name}")],
                    is_error=True,
                )

            return ToolResultMessage(
                tool_call_id=tc.id, tool_name=tc.name,
                content=[TextContent(result.get("content", ""))],
                is_error=result.get("isError", False),
            )

        return executor

    async def _run_agent(self, context: Context) -> None:
        # P4.1 会话元数据：run 结束后回流一条 episode（系统记得你做过什么）
        run_meta: Dict[str, Any] = {"turns": 0, "tools": [], "error": None,
                                    "started": time.time()}
        try:
            loop = self._build_loop(context)
            async for ev in loop.run(context):
                payload = serialize_event(ev)
                if payload is not None:
                    await self._send_await(payload)
                self._mirror_event(ev)
                etype = type(ev).__name__
                if etype == "TurnEnd":
                    run_meta["turns"] += 1
                elif etype == "ToolExecutionStart" and ev.tool_name not in run_meta["tools"]:
                    run_meta["tools"].append(ev.tool_name)
        except asyncio.CancelledError:
            run_meta["error"] = "aborted"
            raise
        except Exception as e:
            run_meta["error"] = f"{type(e).__name__}: {e}"
            self._send({
                "type": "agent_end",
                "error": run_meta["error"],
            })
        finally:
            self.abort_event.clear()
            self._record_session_episode(context, run_meta)
            if self._auto_compaction and self.session is not None and self.stream_fn is not None:
                try:
                    result = await compact_session(self.session, self.stream_fn, self.model)
                    if result is not None:
                        self._send({
                            "type": "compaction_end",
                            "tokensBefore": result.tokens_before,
                            "tokensAfter": result.tokens_after,
                        })
                except Exception as e:
                    # 压缩失败不应静默：向宿主暴露错误但继续正常收尾
                    self._send({
                        "type": "compaction_error",
                        "error": f"{type(e).__name__}: {e}",
                    })
            self._send({"type": "agent_settled"})

    def _record_session_episode(self, context: "Context", meta: Dict[str, Any]) -> None:
        """P4.1 会话回流：一次 agent run 完成后记一条 episode（尽力而为）。"""
        try:
            if meta.get("turns", 0) <= 0:
                return  # 空转（无 LLM 输出）不记录
            first_user = ""
            for m in context.messages:
                if type(m).__name__ == "UserMessage":
                    first_user = getattr(m, "text", lambda: str(m))()[:120].replace("\n", " ")
                    break
            tools = meta.get("tools") or []
            tool_part = f"，工具 {','.join(tools[:6])}" + ("…" if len(tools) > 6 else "")
            err = meta.get("error")
            content = (f"会话：{first_user or '(无文本任务)'}"
                       f"（{meta['turns']} 轮{tool_part}"
                       f"{('，异常退出: ' + str(err)[:60]) if err else ''}）")
            from ...core.paths import SkillStateManager
            duration_ms = int((time.time() - meta.get("started", time.time())) * 1000)
            SkillStateManager("zenskill-core").record_episode(
                action="agent_session",
                content=content,
                success=err is None,
                duration_ms=duration_ms,
            )
        except Exception:
            pass  # 回流失败绝不影响 agent 主流程

    def _init_capabilities(self) -> None:
        """初始化 CapabilityHost（一次性，幂等）。"""
        if self._capability_host is not None:
            return
        from .builtin_capabilities import (
            MemoryCapability, SummaryCapability, ReflectionCapability, TaskTypeCapability,
        )
        from .capability import CapabilityHost

        caps = [TaskTypeCapability()]
        if self._with_memory:
            caps.append(MemoryCapability())
        caps.append(ReflectionCapability())
        caps.append(SummaryCapability())
        self._capability_host = CapabilityHost(caps)
        self._capability_host.initialize()

    def start_prompt(self, message: str) -> None:
        session = self._ensure_session()
        # 记忆桥接：宿主/GUI 用户输入进 mirroring 生态（模式无关）
        if self._event_collector is not None:
            try:
                self._event_collector.record_user_input(
                    skill_id="agent-engine", input_text=message,
                )
            except Exception:
                pass
        # 初始化能力（幂等）
        self._init_capabilities()
        tools = create_default_tools(self.cwd)
        # skill_tools
        try:
            from .skill_tools import load_skill_tools
            tools.extend(load_skill_tools())
        except Exception:
            pass
        # capability extra tools（memory_remember/memory_recall 等）
        if self._capability_host is not None:
            tools.extend(self._capability_host.extra_tools)
        # delegate（子 agent）
        try:
            from .delegate_tool import DelegateTool
            if self.stream_fn and self.model:
                tools.append(DelegateTool(
                    self.stream_fn, self.model, cwd=self.cwd,
                    system_prompt=self._host_system_prompt or DEFAULT_SYSTEM_PROMPT,
                ))
        except Exception:
            pass
        # 把代理工具追加到 context 的 tool 列表
        for name, spec in self._proxy_tools.items():
            from .types import AgentTool, AgentToolResult, TextContent as TC
            proxy_spec = spec
            class _ProxyTool(AgentTool):
                pass
            pt = _ProxyTool()
            pt.name = name
            pt.description = proxy_spec.get("description", "")
            pt.parameters = proxy_spec.get("inputSchema", {"type": "object"})
            async def _fallback_run(tc_id, params, **kw):
                return AgentToolResult(content=[TC("proxy tool: execution delegated to host")], is_error=True)
            pt.run = _fallback_run
            tools.append(pt)
        # 合并 system prompt：Craft 注入的 + 能力提示词 + 技能提示词 + 默认
        final_system_prompt = DEFAULT_SYSTEM_PROMPT
        if self._capability_host is not None:
            final_system_prompt = self._capability_host.build_system_prompt(final_system_prompt)
        if self._with_skills:
            try:
                from .mcp_capability import format_skills_prompt
                section = format_skills_prompt()
                if section:
                    final_system_prompt += "\n\n" + section
            except Exception:
                pass
        if self._host_system_prompt:
            final_system_prompt = self._host_system_prompt + "\n\n" + final_system_prompt
        context = Context(
            messages=session.build_context()["messages"] + [UserMessage(content=message)],
            system_prompt=final_system_prompt,
            tools=tools,
        )
        session.append_message(context.messages[-1])
        self.run_task = asyncio.ensure_future(self._run_agent(context))

    # ------------------------------------------------------------------
    # 命令分发
    # ------------------------------------------------------------------

    async def handle_command(self, cmd: Dict[str, Any]) -> None:
        ctype = cmd.get("type", "")
        cid = cmd.get("id")
        response_id = cid

        def respond(data: Dict[str, Any], success: bool = True, error: Optional[str] = None) -> None:
            payload: Dict[str, Any] = {
                "id": response_id,
                "type": "response",
                "command": ctype,
                "success": success,
            }
            if data is not None:
                payload["data"] = data
            if error is not None:
                payload["error"] = error
            self._send(payload)

        try:
            if ctype == "prompt":
                message = cmd.get("message", "")
                host_system_prompt = cmd.get("systemPrompt", "")
                behavior = cmd.get("streamingBehavior") or "steer"
                if self.running:
                    target = self.steering if behavior == "steer" else self.follow_up
                    target.append(UserMessage(content=message))
                    respond({"queued": True, "behavior": behavior})
                else:
                    self._host_system_prompt = host_system_prompt
                    self.start_prompt(message)
                    respond({"started": True, "sessionId": self._ensure_session().id})

            elif ctype == "steer":
                self.steering.append(UserMessage(content=cmd.get("message", "")))
                respond({"queued": True, "queue": "steering"})

            elif ctype == "follow_up":
                self.follow_up.append(UserMessage(content=cmd.get("message", "")))
                respond({"queued": True, "queue": "followUp"})

            elif ctype == "abort":
                if self.running:
                    self.abort_event.set()
                    respond({"aborting": True})
                else:
                    respond({"aborting": False, "idle": True})

            elif ctype == "get_state":
                session = self.session
                built = session.build_context() if session else {"messages": []}
                from .compaction import context_pressure
                context_window = int(self._config.get("contextWindow", 128_000))
                respond({
                    "running": self.running,
                    "model": f"{self.model.provider}/{self.model.id}" if self.model else None,
                    "sessionId": session.id if session else None,
                    "leaf": session.leaf_id if session else None,
                    "messageCount": len(built.get("messages", [])),
                    "steering": len(self.steering),
                    "followUp": len(self.follow_up),
                    "usage": total_usage(built.get("messages", [])).to_dict(),
                    "contextPressure": context_pressure(
                        total_usage(built.get("messages", [])).total_tokens,
                        context_window,
                    ) if built.get("messages") else "normal",
                })

            elif ctype == "set_model":
                provider = cmd.get("provider") or ""
                model_id = cmd.get("model") or ""
                if provider not in _REGISTRY:
                    respond(None, success=False, error=f"unknown provider: {provider}")
                    return
                self.model = build_model_config(provider, model_id)
                self.stream_fn = create_stream(self.model)
                if self.session is not None:
                    self.session.append("model_change", {"model": f"{provider}/{self.model.id}"})
                respond({"model": f"{provider}/{self.model.id}"})

            elif ctype == "get_available_models":
                respond({
                    "providers": [
                        {"provider": p, "defaultModel": e["default_model"], "api": e["api"]}
                        for p, e in _REGISTRY.items()
                    ]
                })

            elif ctype == "compact":
                if self.running:
                    respond(None, success=False, error="cannot compact while running")
                    return
                session = self._ensure_session()
                result = await compact_session(session, self.stream_fn, self.model)
                respond({
                    "compacted": result is not None,
                    "tokensBefore": result.tokens_before if result else None,
                    "tokensAfter": result.tokens_after if result else None,
                })

            elif ctype == "get_entries":
                session = self.session
                since = cmd.get("since")
                entries = session.entries if session else []
                respond({
                    "entries": [
                        {"id": e.id, "type": e.type, "parentId": e.parent_id, "timestamp": e.timestamp}
                        for e in entries if since is None or e.timestamp > since
                    ]
                })

            elif ctype == "get_messages":
                session = self.session
                messages = session.build_context()["messages"] if session else []
                respond({
                    "messages": [message_to_dict(m, truncate_images=True) for m in messages]
                })

            elif ctype == "new_session":
                parent = cmd.get("parent")
                self.session = self.session_manager.create(cwd=self.cwd)
                if parent:
                    self.session.header["parentSession"] = parent
                respond({"sessionId": self.session.id})

            elif ctype == "switch_session":
                sid = cmd.get("sessionId", "")
                if self.running:
                    respond(None, success=False, error="cannot switch session while running")
                    return
                self.session = self.session_manager.load(sid)
                respond({"sessionId": self.session.id, "entries": len(self.session.entries)})

            elif ctype == "fork":
                entry_id = cmd.get("entryId", "")
                if self.session is None:
                    respond(None, success=False, error="no active session")
                    return
                label = cmd.get("label")
                if label:
                    self.session.set_branch_label(entry_id, str(label))
                else:
                    self.session.branch_from(entry_id)
                respond({"leaf": self.session.leaf_id})

            elif ctype == "mini_completion":
                prompt = cmd.get("prompt", "")
                if not prompt:
                    respond(None, success=False, error="prompt is required")
                    return
                try:
                    mc = getattr(self, "model", None)
                    if mc is not None and getattr(mc, "provider", "") == "deepseek":
                        # Honor the serve-time --model (provider-prefixed) so GUI
                        # connections exercise the exact endpoint+credential they
                        # configured, not the ambient llm_config.
                        from ...core.llm_provider import DeepSeekLLMProvider
                        provider = DeepSeekLLMProvider(
                            api_key=mc.api_key, model=mc.id, base_url=mc.base_url
                        )
                    else:
                        from ...core.llm_provider import get_llm_provider
                        provider = get_llm_provider()
                    result = await provider.simple_chat(prompt)
                    respond({"text": result})
                except Exception as e:
                    respond(None, success=False, error=f"mini_completion failed: {e}")

            elif ctype == "llm_query":
                request = cmd.get("request", {})
                prompt = request.get("prompt", "")
                system_prompt = request.get("systemPrompt")
                model_id = request.get("model")
                if not prompt:
                    respond(None, success=False, error="prompt is required")
                    return
                try:
                    from ...core.llm_provider import get_llm_provider
                    provider = get_llm_provider()
                    result = await provider.simple_chat(prompt, system_prompt=system_prompt)
                    respond({"text": result, "model": model_id or provider.get_model_name()})
                except Exception as e:
                    respond(None, success=False, error=f"llm_query failed: {e}")

            elif ctype == "register_tools":
                tools = cmd.get("tools", [])
                for t in tools:
                    self._proxy_tools[t["name"]] = t
                self._send({"type": "register_tools_result", "id": cid,
                            "count": len(tools), "total": len(self._proxy_tools)})

            elif ctype == "tool_execute_response":
                req_id = cmd.get("requestId", "")
                future = self._proxy_pending.pop(req_id, None)
                if future and not future.done():
                    future.set_result(cmd.get("result", {"content": "", "isError": True}))
                else:
                    self._send({"type": "debug", "message": f"no pending tool_execute for {req_id}"})

            elif ctype == "pre_tool_use_response":
                req_id = cmd.get("requestId", "")
                future = self._pre_tool_pending.pop(req_id, None)
                if future and not future.done():
                    future.set_result({
                        "action": cmd.get("action", "allow"),
                        "input": cmd.get("input"),
                        "reason": cmd.get("reason"),
                    })

            elif ctype == "set_thinking_level":
                level = cmd.get("level", "medium")
                self._thinking_level = level
                respond({"level": level})

            elif ctype == "set_auto_compaction":
                enabled = cmd.get("enabled", True)
                self._auto_compaction = enabled
                respond({"enabled": enabled})

            elif ctype == "update_runtime_config":
                model = cmd.get("model", "")
                if model:
                    try:
                        self.model = build_model_config(model)
                        self.stream_fn = create_stream(self.model)
                        self._config.update({
                            "model": model,
                            "providerType": cmd.get("providerType"),
                            "baseUrl": cmd.get("baseUrl"),
                        })
                        respond({"success": True, "updated": True, "model": model})
                    except Exception as e:
                        respond({"success": False, "updated": False, "error": str(e)})
                else:
                    respond({"success": False, "updated": False, "error": "model is required"})

            elif ctype == "token_update":
                # 热刷新 LLM 凭据
                try:
                    from ...core.llm_provider import get_llm_provider
                    provider = get_llm_provider()
                    if hasattr(provider, 'reload'):
                        provider.reload()
                    respond({"success": True})
                except Exception as e:
                    respond({"success": False, "error": str(e)})

            elif ctype == "ensure_session_ready":
                session = self._ensure_session()
                respond({"sessionId": session.id})

            else:
                respond(None, success=False, error=f"unknown command: {ctype}")

        except FileNotFoundError as e:
            respond(None, success=False, error=str(e))
        except ValueError as e:
            respond(None, success=False, error=str(e))

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def serve(self, input_lines: AsyncIterator[str],
                    write_line: Callable[[str], None]) -> None:
        async def pump_outbox() -> None:
            while True:
                line = await self.outbox.get()
                if line is None:
                    break
                write_line(line)
            write_line(None)  # 结束信号

        writer = asyncio.ensure_future(pump_outbox())
        self._send({"type": "server_hello", "protocolVersion": PROTOCOL_VERSION})
        try:
            async for raw in input_lines:
                line = raw.strip()
                if not line:
                    continue
                try:
                    cmd = json.loads(line)
                except ValueError:
                    self._send({
                        "id": None, "type": "response", "command": "?",
                        "success": False, "error": f"invalid JSON: {line[:120]}",
                    })
                    continue
                if cmd.get("type") == "shutdown":
                    self._send({"id": cmd.get("id"), "type": "response", "command": "shutdown", "success": True})
                    break
                await self.handle_command(cmd)
        finally:
            if self.running:
                # 优雅关闭：先等运行自然结束，超时才中止（避免刚启动即被 abort）
                try:
                    await asyncio.wait_for(asyncio.shield(self.run_task), timeout=3)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    self.abort_event.set()
                    try:
                        await asyncio.wait_for(self.run_task, timeout=5)
                    except (asyncio.TimeoutError, asyncio.CancelledError):
                        self.run_task.cancel()
            await self.outbox.put(None)
            await writer


async def _stdin_lines() -> AsyncIterator[str]:
    if sys.platform == "win32":
        # Windows ProactorEventLoop stdin pipe transport crashes on read
        # (_ProactorReadPipeTransport._empty_waiter AttributeError, CPython
        # proactor quirk) — the JSONL protocol goes silent right after
        # server_hello. Read the line protocol on a worker thread instead.
        import concurrent.futures
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            while True:
                line = await loop.run_in_executor(pool, sys.stdin.readline)
                if not line:
                    return
                yield line
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    async for line in reader:
        yield line.decode("utf-8", errors="replace")


def _stdout_write(line: Optional[str]) -> None:
    if line is None:
        sys.stdout.flush()
        return
    sys.stdout.write(line + "\n")
    sys.stdout.flush()


def serve_main(args: Any) -> int:
    """`zenskill agent-engine serve` 入口"""
    import asyncio as _asyncio

    faux = bool(getattr(args, "faux", False))
    if faux:
        model = ModelConfig(id="faux", api="faux", provider="faux", base_url="")
        stream_fn = EchoFauxStream()
    else:
        model = resolve_model(getattr(args, "model", None))
        stream_fn = create_stream(model)

    server = AgentServer(
        model=model,
        stream_fn=stream_fn,
        session_root=getattr(args, "session_root", None),
        permission=getattr(args, "permission", "full") or "full",
        cwd=getattr(args, "cwd", None) or ".",
        stateless=bool(getattr(args, "stateless", False)),
        max_steps=getattr(args, "max_steps", None),
        max_total_tokens=getattr(args, "max_total_tokens", None),
    )
    try:
        _asyncio.run(server.serve(_stdin_lines(), _stdout_write))
        return 0
    except KeyboardInterrupt:
        return 0
