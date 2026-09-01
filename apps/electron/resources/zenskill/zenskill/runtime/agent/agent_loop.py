"""LLM 驱动的 agent 循环（参照 pi packages/agent/src/agent-loop.ts 的双层循环）。

内层：steering 注入 -> 流式产出一条 assistant 消息 -> 执行工具调用批
       -> ToolResultMessage 压回 context -> turn_end -> prepare_next_turn。
外层：agent 本要停止时轮询 follow_up 队列，有则继续，无则 agent_end。

关键语义（对齐 pi）：
- stop_reason == "length" 时放弃该消息全部工具调用，回填错误结果后继续
- 工具批内所有结果都置 terminate=True 才终止整个 run
- before_tool_call 返回 {block: True, reason, terminate?} 可否决工具调用
- StreamFn 永不抛异常，失败编码为 StreamError 携带的终态消息
- AgentEnd.messages 只含本次 run 新增的消息（steering/followup/assistant/
  toolResult），不含调用前已在 context 中的输入
"""
from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from .types import (
    AgentEnd,
    AgentEvent,
    AgentStart,
    AgentToolResult,
    AssistantMessage,
    AssistantMessageEvent,
    Context,
    Message,
    MessageEnd,
    MessageStart,
    MessageUpdate,
    StopReason,
    StreamDone,
    StreamError,
    StreamStart,
    TextContent,
    TextDelta,
    ThinkingContent,
    ThinkingDelta,
    ToolCall,
    ToolCallEnd,
    ToolCallStart,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
    ToolResultMessage,
    TurnEnd,
    TurnStart,
    UserMessage,
    total_usage,
    estimate_context_tokens,
    estimate_tool_result_tokens,
)
from .validation import ToolValidationError, validate_tool_arguments


async def _maybe_call(fn, *args):
    if fn is None:
        return None
    result = fn(*args)
    if asyncio.iscoroutine(result):
        result = await result
    return result


@dataclass
class AgentLoopConfig:
    stream: Callable[..., Any]  # async (model, context, abort_event) -> AsyncIterator[AssistantMessageEvent]
    model: Any = ""             # 透传给 stream 的模型标识（str 或 ModelConfig）
    transform_context: Optional[Callable] = None       # (messages) -> messages，LLM 调用前裁剪/注入
    before_tool_call: Optional[Callable] = None        # (tool_call, params) -> Optional[{block, reason, terminate?}]
    after_tool_call: Optional[Callable] = None         # (result) -> Optional[ToolResultMessage]
    prepare_next_turn: Optional[Callable] = None       # (context, last_message) -> None
    should_stop_after_turn: Optional[Callable] = None  # (message, tool_results) -> bool
    get_steering_messages: Optional[Callable] = None   # () -> list[Message]
    response_format: Optional[str] = None              # "json"：要求 LLM 输出合法 JSON（P0-3）
    get_follow_up_messages: Optional[Callable] = None  # () -> list[Message]
    max_steps: Optional[int] = None  # 安全阀：最大 turn 数；None 表示不限
    max_total_tokens: Optional[int] = None  # token 预算：超限先注入收尾提示，再超则终止
    tool_result_budget_ratio: float = 0.5  # 工具结果占总预算的最大比例（E1-3）
    parallel_tools: bool = False  # 工具批内并行执行（校验/veto 仍保序，结果消息保序）
    planning: bool = False  # E4-1：第一轮先输出步骤计划，后续轮次按计划执行
    abort_event: Optional[asyncio.Event] = None
    on_entry: Optional[Callable] = None  # (message) -> None，每个新增消息回调（会话持久化）
    tool_executor: Optional[Callable] = None  # async (tool_call, params) -> ToolResultMessage，代理模式
    max_turn_retries: int = 2  # 流式失败后 turn 级重试次数（0 = 不重试）


def _model_name(model: Any) -> str:
    return str(getattr(model, "id", model))


# ---------------------------------------------------------------------------
# 循环卫生守卫：重复工具调用提醒（advisory，never vetoes）
# ---------------------------------------------------------------------------

_REPEAT_REMIND_AT = (3, 5, 8)


def _split_by_concurrency_safety(pending: List[Any]) -> List[List[Any]]:
    """按模型顺序把工具批切为执行段：连续 concurrency_safe 成并行段，
    unsafe 工具恒单独成 barrier 段（长度 1，段间串行等待）。"""
    segments: List[List[Any]] = []
    current: List[Any] = []
    for item in pending:
        tool = item[1]
        if bool(getattr(tool, "concurrency_safe", False)):
            current.append(item)
        else:
            if current:
                segments.append(current)
                current = []
            segments.append([item])  # barrier
    if current:
        segments.append(current)
    return segments


def _tool_batch_key(tool_calls: List[ToolCall]) -> str:
    """整批工具调用的规范化签名：检测"同批重复"而非仅单工具重复。"""
    parts = []
    for tc in tool_calls:
        try:
            args = json.dumps(tc.arguments, sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            args = str(tc.arguments)
        parts.append(f"{tc.name}:{args}")
    return "|".join(parts)


def _repeat_reminder(count: int, tool_calls: List[ToolCall]) -> Optional[UserMessage]:
    """连续第 N 次相同工具调用批时产生提醒，其余返回 None。"""
    if count not in _REPEAT_REMIND_AT:
        return None
    first = tool_calls[0]
    args_preview = ""
    try:
        args_preview = json.dumps(first.arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        args_preview = str(first.arguments)
    if len(args_preview) > 200:
        args_preview = args_preview[:200] + "…"
    if count == 3:
        batch_desc = first.name
        if len(tool_calls) > 1:
            batch_desc = f"{first.name} +{len(tool_calls) - 1} more"
        text = (
            f"[system] Tool call batch ({batch_desc}) has been issued {count} "
            "times in a row with identical arguments. The result will not "
            "change. Adjust your approach, or conclude if done."
        )
    else:
        text = (
            f"[system] Repeated tool call #{count}: {first.name}({args_preview}) "
            "with identical arguments. Stop retrying the same call — change "
            "strategy, use different arguments, or give your final answer."
        )
    return UserMessage(content=text)


class AgentLoop:
    def __init__(self, config: AgentLoopConfig) -> None:
        self.config = config

    def _emit_entry(self, message: Message) -> None:
        if self.config.on_entry is not None:
            try:
                self.config.on_entry(message)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------

    async def run(self, context: Context) -> AsyncIterator[AgentEvent]:
        yield AgentStart()
        new_messages: List[Message] = []
        turns = 0
        budget_warned = False
        plan_captured = False
        plan_text = ""
        repeat_key = ""
        repeat_count = 0
        hit_length = False  # P2-8 粘滞：任一 turn 触发 LENGTH 后，后续正常完成也标记

        while True:
            if self.config.abort_event is not None and self.config.abort_event.is_set():
                break
            if self.config.max_steps is not None and turns >= self.config.max_steps:
                break

            # E4-1：Planning Phase — 第一轮注入规划提示
            if self.config.planning and turns == 0 and not plan_captured:
                plan_prompt = UserMessage(
                    content=(
                        "[system] Before executing, create a step-by-step plan. "
                        "List each step with a number. Do NOT use any tools yet — "
                        "just output your plan as numbered steps."
                    )
                )
                context.messages.append(plan_prompt)
                new_messages.append(plan_prompt)
                self._emit_entry(plan_prompt)

            steering = (await _maybe_call(self.config.get_steering_messages)) or []
            # E4-1：后续轮次注入已捕获的计划
            if plan_captured and plan_text:
                plan_steering = UserMessage(
                    content=f"[system] Your plan for this task:\n{plan_text}\n\nExecute step by step."
                )
                steering = [plan_steering] + steering
            if steering:
                context.messages.extend(steering)
                new_messages.extend(steering)
                for m in steering:
                    self._emit_entry(m)

            yield TurnStart()
            turn_start = time.monotonic()

            llm_messages = context.messages
            if self.config.transform_context is not None:
                transformed = await _maybe_call(
                    self.config.transform_context, list(context.messages)
                )
                if transformed is not None:
                    llm_messages = transformed

            # Turn-level retry: stream failures trigger retry up to max_turn_retries
            partial = AssistantMessage(model=_model_name(self.config.model))
            final_msg: Optional[AssistantMessage] = None
            turn_retries = 0
            while True:
                partial = AssistantMessage(model=_model_name(self.config.model))
                final_msg = None
                yield MessageStart(partial)
                async for ev in self._stream_once(context, llm_messages):
                    if isinstance(ev, StreamStart):
                        partial = ev.partial
                    elif isinstance(ev, (TextDelta, ThinkingDelta)):
                        _apply_delta(partial, ev)
                    elif isinstance(ev, ToolCallStart):
                        partial.content.append(ev.tool_call)
                    elif isinstance(ev, ToolCallEnd):
                        _replace_tool_call(partial, ev.index, ev.tool_call)
                    elif isinstance(ev, StreamDone):
                        final_msg = ev.message
                    elif isinstance(ev, StreamError):
                        final_msg = ev.error
                    yield MessageUpdate(partial, ev)

                if final_msg is None:
                    final_msg = partial
                    final_msg.stop_reason = StopReason.ERROR
                    final_msg.error_message = "stream ended without terminal event"

                # Retry on ERROR (not ABORTED) if retries remain
                if (final_msg.stop_reason == StopReason.ERROR
                        and turn_retries < self.config.max_turn_retries
                        and not (self.config.abort_event and self.config.abort_event.isset() if hasattr(self.config.abort_event, 'isset') else False)):
                    turn_retries += 1
                    yield MessageEnd(final_msg)
                    # Remove failed message from context before retry
                    if final_msg in context.messages:
                        context.messages.remove(final_msg)
                    if final_msg in new_messages:
                        new_messages.remove(final_msg)
                    import asyncio as _retry_asyncio
                    await _retry_asyncio.sleep(0.5 * turn_retries)
                    continue
                break

            yield MessageEnd(final_msg)
            context.messages.append(final_msg)
            new_messages.append(final_msg)
            self._emit_entry(final_msg)

            tool_calls = final_msg.tool_calls()

            if final_msg.stop_reason in (StopReason.ERROR, StopReason.ABORTED):
                turn_dur = int((time.monotonic() - turn_start) * 1000)
                yield TurnEnd(final_msg, [], turn_duration_ms=turn_dur)
                break

            results: List[ToolResultMessage] = []
            if final_msg.stop_reason == StopReason.LENGTH and tool_calls:
                hit_length = True
                results = _fail_tool_calls_from_truncated(final_msg)
                for r in results:
                    context.messages.append(r)
                    new_messages.append(r)
                    self._emit_entry(r)
            elif tool_calls:
                produced: List[ToolResultMessage] = []
                async for ev in self._invoke_tool_calls(context, tool_calls, produced):
                    yield ev
                results = produced

            turn_dur = int((time.monotonic() - turn_start) * 1000)
            turn_usage = final_msg.usage
            turn_tok = turn_usage.total_tokens if turn_usage else 0
            t_names = [tc.name for tc in tool_calls] if tool_calls else []
            yield TurnEnd(final_msg, results, turn_tokens=turn_tok, turn_duration_ms=turn_dur, tool_names=t_names)
            turns += 1

            # 循环卫生：整批 results 就位后检测重复调用批，注入 advisory 提醒。
            # 不在此刻之前的任何位置注入——UserMessage 插进 tool_calls/results
            # 之间会导致下次 LLM 请求 400。
            if tool_calls:
                batch_key = _tool_batch_key(tool_calls)
                if batch_key == repeat_key:
                    repeat_count += 1
                else:
                    repeat_key = batch_key
                    repeat_count = 1
                reminder = _repeat_reminder(repeat_count, tool_calls)
                if reminder is not None:
                    context.messages.append(reminder)
                    new_messages.append(reminder)
                    self._emit_entry(reminder)
            else:
                repeat_key = ""
                repeat_count = 0

            # E4-1：捕获计划（第一轮的 assistant 文本输出）
            if self.config.planning and not plan_captured:
                plan_text = final_msg.text().strip()
                plan_captured = True
                if not tool_calls:
                    # 计划轮无工具调用——跳到下一轮执行
                    continue

            wrap_up_injected = False
            if self.config.max_total_tokens is not None:
                used = estimate_context_tokens(context.messages)
                if used >= self.config.max_total_tokens:
                    if budget_warned:
                        break
                    budget_warned = True
                    wrap_up_injected = True
                    wrap_up = UserMessage(
                        content=(
                            "[system] Token budget exceeded. Wrap up now and give "
                            "the final answer without further tool calls."
                        )
                    )
                    context.messages.append(wrap_up)
                    new_messages.append(wrap_up)
                    self._emit_entry(wrap_up)
                # E1-3: 工具结果占比检查
                elif self.config.tool_result_budget_ratio < 1.0:
                    tool_tokens = estimate_tool_result_tokens(context.messages)
                    tool_budget = int(self.config.max_total_tokens * self.config.tool_result_budget_ratio)
                    if tool_tokens > tool_budget and tool_tokens > 0:
                        wrap_up_injected = True
                        wrap_up = UserMessage(
                            content=(
                                f"[system] Tool result context ({tool_tokens} tokens) exceeds "
                                f"{self.config.tool_result_budget_ratio:.0%} budget ({tool_budget} tokens). "
                                f"Wrap up with current information."
                            )
                        )
                        context.messages.append(wrap_up)
                        new_messages.append(wrap_up)
                        self._emit_entry(wrap_up)

            if results and all(r.terminate for r in results):
                break
            if await _maybe_call(self.config.should_stop_after_turn, final_msg, results):
                break

            # 每轮结束后触发（Capability after_turn 观察点）
            await _maybe_call(self.config.prepare_next_turn, context, final_msg)

            if not tool_calls and not wrap_up_injected:
                follow_up = (await _maybe_call(self.config.get_follow_up_messages)) or []
                if not follow_up:
                    break
                context.messages.extend(follow_up)
                new_messages.extend(follow_up)
                for m in follow_up:
                    self._emit_entry(m)

        yield AgentEnd(new_messages, truncated_history=hit_length)

    # ------------------------------------------------------------------
    # 流式包装：确保异常被编码为 StreamError
    # ------------------------------------------------------------------

    async def _stream_once(
        self, context: Context, llm_messages: List[Message]
    ) -> AsyncIterator[AssistantMessageEvent]:
        model = self.config.model
        try:
            stream_ctx = Context(
                messages=llm_messages,
                system_prompt=context.system_prompt,
                tools=context.tools,
                response_format=context.response_format or self.config.response_format,
            )
            async for ev in self.config.stream(model, stream_ctx, self.config.abort_event):
                yield ev
        except asyncio.CancelledError:
            raise
        except Exception as e:  # StreamFn 契约兜底
            yield StreamError(
                "error",
                AssistantMessage(
                    model=_model_name(model),
                    stop_reason=StopReason.ERROR,
                    error_message=f"{type(e).__name__}: {e}",
                ),
            )

    # ------------------------------------------------------------------
    # 工具调用
    # ------------------------------------------------------------------

    async def _invoke_tool_calls(
        self, context: Context, tool_calls: List[ToolCall], produced: List[ToolResultMessage]
    ) -> AsyncIterator[AgentEvent]:
        tool_map = {t.name: t for t in context.tools}
        results: List[Optional[ToolResultMessage]] = [None] * len(tool_calls)
        pending: List[Any] = []  # (index, tool, params)

        # 阶段 1：校验 + before_tool_call veto（严格保序，veto 顺序语义确定）
        for i, tc in enumerate(tool_calls):
            yield ToolExecutionStart(tc.id, tc.name, dict(tc.arguments))
            tool = tool_map.get(tc.name)
            if tool is None:
                available = ", ".join(sorted(tool_map.keys()))
                results[i] = _error_result(
                    tc, f"Unknown tool: '{tc.name}'. Available tools: {available}"
                )
                continue
            try:
                params = validate_tool_arguments(tool.parameters, tc.arguments)
            except ToolValidationError as e:
                schema_hint = ""
                required = tool.parameters.get("required", [])
                if required:
                    schema_hint = f" Required: {', '.join(required)}."
                results[i] = _error_result(
                    tc, f"Invalid arguments for '{tc.name}': {e}.{schema_hint}"
                )
                continue
            veto = await _maybe_call(self.config.before_tool_call, tc, params)
            if isinstance(veto, dict) and veto.get("block"):
                reason = veto.get("reason") or "blocked by before_tool_call hook"
                blocked = _error_result(tc, f"Tool call blocked: {reason}")
                if veto.get("terminate"):
                    blocked.terminate = True
                results[i] = blocked
                continue
            pending.append((i, tool, params))

        # 阶段 2：执行（可选并行；on_update 事件实时流出，结果消息不落 context）
        # per-tool 并发分类（P1-5）：连续 concurrency_safe 工具成并行段，
        # unsafe 工具（bash/write/edit）单独成 barrier 段串行，段间等待。
        if pending and self.config.parallel_tools and len(pending) > 1:
            for segment in _split_by_concurrency_safety(pending):
                if len(segment) > 1:
                    async for ev in self._run_tools_parallel(tool_calls, segment, results):
                        yield ev
                else:
                    i, tool, params = segment[0]
                    tc = tool_calls[i]
                    holder: List[ToolResultMessage] = []
                    if self.config.tool_executor is not None:
                        result_msg = await self.config.tool_executor(tc, params)
                        holder.append(result_msg)
                    else:
                        async for ev in self._run_one_tool(tool, tc, params, holder):
                            yield ev
                    results[i] = holder[0] if holder else _error_result(
                        tc, "tool produced no result"
                    )
        else:
            for i, tool, params in pending:
                tc = tool_calls[i]
                holder: List[ToolResultMessage] = []
                if self.config.tool_executor is not None:
                    # 代理模式：委托宿主执行
                    result_msg = await self.config.tool_executor(tc, params)
                    holder.append(result_msg)
                else:
                    # 进程内模式：现有逻辑不变
                    async for ev in self._run_one_tool(tool, tc, params, holder):
                        yield ev
                results[i] = holder[0] if holder else _error_result(
                    tc, "tool produced no result"
                )

        # 阶段 3：after_tool_call + 落 context（源顺序，结果消息序确定）
        for i, tc in enumerate(tool_calls):
            result_msg = results[i] or _error_result(tc, "tool produced no result")
            if self.config.after_tool_call is not None:
                patched = await _maybe_call(self.config.after_tool_call, result_msg)
                if patched is not None:
                    result_msg = patched
            context.messages.append(result_msg)
            produced.append(result_msg)
            self._emit_entry(result_msg)
            yield ToolExecutionEnd(tc.id, tc.name, result_msg.is_error, result_msg)

    async def _run_tools_parallel(
        self, tool_calls: List[ToolCall], pending: List[Any],
        results: List[Optional[ToolResultMessage]],
    ) -> AsyncIterator[AgentEvent]:
        queue: "asyncio.Queue[Any]" = asyncio.Queue()
        done_marker = object()
        holders: Dict[int, List[ToolResultMessage]] = {}

        async def _consume(index: int, tool, params: Dict[str, Any]) -> None:
            tc = tool_calls[index]
            holder: List[ToolResultMessage] = []
            holders[index] = holder
            try:
                if self.config.tool_executor is not None:
                    result_msg = await self.config.tool_executor(tc, params)
                    holder.append(result_msg)
                else:
                    async for ev in self._run_one_tool(tool, tc, params, holder):
                        await queue.put(ev)
            except asyncio.CancelledError:
                raise
            except Exception as e:  # 单个执行失败不影响其余
                holder.append(_error_result(tc, f"tool execution crashed: {type(e).__name__}: {e}"))
            finally:
                await queue.put((done_marker, index))

        tasks = [
            asyncio.ensure_future(_consume(i, tool, params))
            for (i, tool, params) in pending
        ]
        try:
            finished = 0
            while finished < len(tasks):
                item = await queue.get()
                if isinstance(item, tuple) and item[0] is done_marker:
                    finished += 1
                    index = item[1]
                    holder = holders.get(index) or []
                    results[index] = holder[0] if holder else _error_result(
                        tool_calls[index], "tool produced no result"
                    )
                else:
                    yield item
        finally:
            for t in tasks:
                if not t.done():
                    t.cancel()

    async def _run_one_tool(
        self, tool, tc: ToolCall, params: Dict[str, Any], holder: List[ToolResultMessage]
    ) -> AsyncIterator[AgentEvent]:
        queue: "asyncio.Queue[Any]" = asyncio.Queue()

        def on_update(partial_result: Any) -> None:
            queue.put_nowait(partial_result)

        async def _safe_run() -> AgentToolResult:
            try:
                return await tool.run(tc.id, params, on_update=on_update)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                args_brief = ", ".join(
                    f"{k}={str(v)[:40]!r}" for k, v in list(tc.arguments.items())[:3]
                )
                return AgentToolResult(
                    content=[TextContent(
                        f"Tool '{tc.name}' failed: {type(e).__name__}: {e}\n"
                        f"Arguments: {args_brief}"
                    )],
                    is_error=True,
                )

        task = asyncio.ensure_future(_safe_run())
        try:
            while not task.done():
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=0.05)
                    yield ToolExecutionUpdate(tc.id, tc.name, item)
                except asyncio.TimeoutError:
                    pass
            while not queue.empty():
                yield ToolExecutionUpdate(tc.id, tc.name, queue.get_nowait())
        finally:
            if not task.done():
                task.cancel()

        result = task.result()
        holder.append(ToolResultMessage(
            tool_call_id=tc.id,
            tool_name=tc.name,
            content=result.content if result.content else [TextContent("")],
            is_error=result.is_error,
            details=result.details,
            usage=result.usage,
            terminate=result.terminate,
        ))


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def _apply_delta(partial: AssistantMessage, ev: AssistantMessageEvent) -> None:
    if isinstance(ev, TextDelta):
        if partial.content and isinstance(partial.content[-1], TextContent):
            partial.content[-1].text += ev.text
        else:
            partial.content.append(TextContent(ev.text))
    elif isinstance(ev, ThinkingDelta):
        if partial.content and isinstance(partial.content[-1], ThinkingContent):
            partial.content[-1].thinking += ev.thinking
        else:
            partial.content.append(ThinkingContent(ev.thinking))


def _replace_tool_call(partial: AssistantMessage, index: int, tool_call: ToolCall) -> None:
    tool_call_positions = [
        i for i, b in enumerate(partial.content) if isinstance(b, ToolCall)
    ]
    if index < len(tool_call_positions):
        partial.content[tool_call_positions[index]] = tool_call


def _error_result(tc: ToolCall, message: str) -> ToolResultMessage:
    return ToolResultMessage(
        tool_call_id=tc.id,
        tool_name=tc.name,
        content=[TextContent(f"Error: {message}")],
        is_error=True,
    )


def _fail_tool_calls_from_truncated(message: AssistantMessage) -> List[ToolResultMessage]:
    return [
        _error_result(
            tc,
            "assistant message was truncated (stop_reason=length); "
            "tool call arguments may be incomplete and were not executed",
        )
        for tc in message.tool_calls()
    ]
