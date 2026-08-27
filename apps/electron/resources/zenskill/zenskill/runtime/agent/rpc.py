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
    ) -> None:
        self.model = model
        self.stream_fn = stream_fn
        self.session_manager = SessionManager(root=session_root, stateless=stateless)
        self.permission = permission
        self.cwd = cwd or "."
        self._stateless = stateless
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

        config = AgentLoopConfig(
            stream=self.stream_fn,
            model=self.model,
            abort_event=self.abort_event,
            before_tool_call=PermissionGate(self.permission, cwd=self.cwd) if self.permission != "full" else None,
            get_steering_messages=take_steering,
            get_follow_up_messages=take_follow_up,
            on_entry=on_entry,
            tool_executor=self._build_proxy_executor() if self._proxy_tools else None,
        )
        # 注入 Craft system prompt（合并到 Context.system_prompt）
        if self._host_system_prompt:
            config._host_system_prompt = self._host_system_prompt
        return AgentLoop(config)

    def _build_proxy_executor(self):
        """构建工具代理执行器：发 tool_execute_request，等 tool_execute_response"""
        proxy_tools = self._proxy_tools
        proxy_pending = self._proxy_pending
        pre_tool_pending = self._pre_tool_pending
        send = self._send

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

            # tool_execute 请求
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
        try:
            loop = self._build_loop(context)
            async for ev in loop.run(context):
                payload = serialize_event(ev)
                if payload is not None:
                    await self._send_await(payload)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._send({
                "type": "agent_end",
                "error": f"{type(e).__name__}: {e}",
            })
        finally:
            self.abort_event.clear()
            if self._auto_compaction and self.session is not None and self.stream_fn is not None:
                try:
                    result = await compact_session(self.session, self.stream_fn, self.model)
                    if result is not None:
                        self._send({
                            "type": "compaction_end",
                            "tokensBefore": result.tokens_before,
                            "tokensAfter": result.tokens_after,
                        })
                except Exception:
                    pass
            self._send({"type": "agent_settled"})

    def start_prompt(self, message: str) -> None:
        session = self._ensure_session()
        tools = create_default_tools(self.cwd)
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
            # run 不会被调用（代理模式走 tool_executor），但保留兜底
            async def _fallback_run(tc_id, params, **kw):
                return AgentToolResult(content=[TC("proxy tool: execution delegated to host")], is_error=True)
            pt.run = _fallback_run
            tools.append(pt)
        # 合并 system prompt：Craft 注入的 + ZenSkill 默认的
        final_system_prompt = DEFAULT_SYSTEM_PROMPT
        if self._host_system_prompt:
            final_system_prompt = self._host_system_prompt + "\n\n" + DEFAULT_SYSTEM_PROMPT
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
                respond({
                    "running": self.running,
                    "model": f"{self.model.provider}/{self.model.id}" if self.model else None,
                    "sessionId": session.id if session else None,
                    "leaf": session.leaf_id if session else None,
                    "messageCount": len(built.get("messages", [])),
                    "steering": len(self.steering),
                    "followUp": len(self.follow_up),
                    "usage": total_usage(built.get("messages", [])).to_dict(),
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
                self.session.branch_from(entry_id)
                respond({"leaf": self.session.leaf_id})

            elif ctype == "mini_completion":
                prompt = cmd.get("prompt", "")
                if not prompt:
                    respond(None, success=False, error="prompt is required")
                    return
                try:
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
    )
    try:
        _asyncio.run(server.serve(_stdin_lines(), _stdout_write))
        return 0
    except KeyboardInterrupt:
        return 0
