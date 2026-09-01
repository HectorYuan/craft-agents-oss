"""OpenAI-compatible Chat Completions 流式实现（覆盖 deepseek/openai/volc/qwen）。

纯状态机 OpenAIStreamState 负责 SSE 行 -> AssistantMessageEvent 的转换，
可离线单测；网络层只做传输。
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from ..types import (
    AssistantMessage,
    AssistantMessageEvent,
    ContentBlock,
    Context,
    ImageContent,
    Message,
    StopReason,
    StreamDone,
    StreamError,
    StreamStart,
    TextContent,
    TextDelta,
    ThinkingContent,
    ThinkingDelta,
    ToolCall,
    ToolCallDelta,
    ToolCallEnd,
    ToolCallStart,
    ToolResultMessage,
    Usage,
    UserMessage,
    new_id,
)


# ---------------------------------------------------------------------------
# Context -> wire payload 转换（纯函数，可单测）
# ---------------------------------------------------------------------------

def _user_text_and_images(m: UserMessage):
    if isinstance(m.content, str):
        return m.content, []
    text_parts, images = [], []
    for b in m.content:
        if isinstance(b, TextContent):
            text_parts.append(b.text)
        elif isinstance(b, ImageContent):
            images.append({
                "type": "image_url",
                "image_url": {"url": f"data:{b.mime_type};base64,{b.data}"},
            })
    return "".join(text_parts), images


def to_openai_messages(system_prompt: Optional[str], messages: List[Message]) -> List[Dict[str, Any]]:
    wire: List[Dict[str, Any]] = []
    if system_prompt:
        wire.append({"role": "system", "content": system_prompt})
    for m in messages:
        if isinstance(m, UserMessage):
            text, images = _user_text_and_images(m)
            if images:
                parts: List[Dict[str, Any]] = [{"type": "text", "text": text}] if text else []
                parts.extend(images)
                wire.append({"role": "user", "content": parts})
            else:
                wire.append({"role": "user", "content": text})
        elif isinstance(m, AssistantMessage):
            text = m.text()
            tool_calls = m.tool_calls()
            entry: Dict[str, Any] = {"role": "assistant"}
            entry["content"] = text if text else None
            if tool_calls:
                entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments, ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ]
            wire.append(entry)
        elif isinstance(m, ToolResultMessage):
            wire.append({
                "role": "tool",
                "tool_call_id": m.tool_call_id,
                "content": m.text(),
            })
    return wire


def to_openai_tools(context: Context) -> List[Dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters or {"type": "object", "properties": {}},
            },
        }
        for t in context.tools
    ]


# ---------------------------------------------------------------------------
# SSE 状态机（纯逻辑，可离线单测）
# ---------------------------------------------------------------------------

def _map_finish(reason: Optional[str]) -> str:
    if reason == "tool_calls":
        return StopReason.TOOL_USE
    if reason == "length":
        return StopReason.LENGTH
    return StopReason.STOP


class OpenAIStreamState:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.text_parts: List[str] = []
        self.thinking_parts: List[str] = []
        self.tool_calls: Dict[int, Dict[str, Any]] = {}
        self.usage = Usage()
        self.finish_reason: Optional[str] = None

    def feed_line(self, line: str) -> List[AssistantMessageEvent]:
        events: List[AssistantMessageEvent] = []
        stripped = line.strip()
        if not stripped or stripped.startswith(":"):
            return events
        if not stripped.startswith("data:"):
            return events
        payload = stripped[5:].strip()
        if payload == "[DONE]":
            return events
        try:
            chunk = json.loads(payload)
        except ValueError:
            return events
        if not isinstance(chunk, dict):
            return events

        usage = chunk.get("usage")
        if isinstance(usage, dict):
            if usage.get("prompt_tokens") is not None:
                self.usage.input = int(usage["prompt_tokens"])
            if usage.get("completion_tokens") is not None:
                self.usage.output = int(usage["completion_tokens"])
            cached = usage.get("prompt_tokens_details") or {}
            if isinstance(cached, dict) and cached.get("cached_tokens"):
                self.usage.cache_read = int(cached["cached_tokens"])
            details = usage.get("completion_tokens_details") or {}
            if isinstance(details, dict) and details.get("reasoning_tokens"):
                self.usage.reasoning = int(details["reasoning_tokens"])

        choices = chunk.get("choices") or []
        if not choices:
            return events
        choice = choices[0]
        delta = choice.get("delta") or {}

        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning:
            self.thinking_parts.append(reasoning)
            events.append(ThinkingDelta(reasoning))

        content = delta.get("content")
        if content:
            self.text_parts.append(content)
            events.append(TextDelta(content))

        for tc in delta.get("tool_calls") or []:
            idx = int(tc.get("index", 0))
            entry = self.tool_calls.get(idx)
            if entry is None:
                entry = {
                    "id": tc.get("id") or new_id("call_"),
                    "name": (tc.get("function") or {}).get("name") or "",
                    "args": "",
                }
                self.tool_calls[idx] = entry
                events.append(ToolCallStart(idx, ToolCall(id=entry["id"], name=entry["name"])))
            fn_delta = tc.get("function") or {}
            args_fragment = fn_delta.get("arguments")
            if args_fragment:
                entry["args"] += args_fragment
                events.append(ToolCallDelta(idx, args_fragment))
            if tc.get("id"):
                entry["id"] = tc["id"]
            name_fragment = fn_delta.get("name")
            if name_fragment:
                entry["name"] = name_fragment

        finish = choice.get("finish_reason")
        if finish:
            self.finish_reason = finish
        return events

    def partial_message(self) -> AssistantMessage:
        """从已累积的部分状态构建 AssistantMessage（流式中断时用）。

        只保留 text/thinking 前缀，丢弃 tool_calls：中断的 tool_call
        没有配对的 tool result，留在 context 会让下次 LLM 请求 400。
        """
        content: List[ContentBlock] = []
        if self.thinking_parts:
            content.append(ThinkingContent("".join(self.thinking_parts)))
        if self.text_parts:
            content.append(TextContent("".join(self.text_parts)))
        return AssistantMessage(
            content=content,
            model=self.model_id,
            stop_reason=StopReason.ERROR,
            usage=self.usage,
        )

    def finish(self) -> List[AssistantMessageEvent]:
        events: List[AssistantMessageEvent] = []
        content: List[ContentBlock] = []
        if self.thinking_parts:
            content.append(ThinkingContent("".join(self.thinking_parts)))
        if self.text_parts:
            content.append(TextContent("".join(self.text_parts)))
        for idx in sorted(self.tool_calls):
            entry = self.tool_calls[idx]
            try:
                args = json.loads(entry["args"]) if entry["args"] else {}
            except ValueError:
                args = {}
            if not isinstance(args, dict):
                args = {}
            tool_call = ToolCall(id=entry["id"], name=entry["name"], arguments=args)
            content.append(tool_call)
            events.append(ToolCallEnd(idx, tool_call))
        stop_reason = _map_finish(self.finish_reason)
        if not self.finish_reason and self.tool_calls:
            stop_reason = StopReason.TOOL_USE
        message = AssistantMessage(
            content=content,
            model=self.model_id,
            stop_reason=stop_reason,
            usage=self.usage,
        )
        events.append(StreamDone(stop_reason, message))
        return events


# ---------------------------------------------------------------------------
# StreamFn：永不抛异常，失败编码为 StreamError
# ---------------------------------------------------------------------------

async def openai_completions_stream(model, context, abort_event=None):
    import aiohttp

    model_id = model.id
    if not model.api_key:
        yield StreamError(
            "error",
            AssistantMessage(
                model=model_id,
                stop_reason=StopReason.ERROR,
                error_message=f"missing API key: set {model.api_key_env}",
            ),
        )
        return

    wire_messages = to_openai_messages(context.system_prompt, context.messages)
    wire_tools = to_openai_tools(context)
    payload: Dict[str, Any] = {
        "model": model_id,
        "messages": wire_messages,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if getattr(context, "response_format", None) == "json":
        payload["response_format"] = {"type": "json_object"}
    thinking_level = getattr(context, "thinking_level", None)
    if thinking_level and getattr(model, "supports_thinking_control", False):
        # DeepSeek V3.2+ thinking 开关；默认（None）不注入保持模型默认行为
        payload["thinking"] = {"type": "disabled" if thinking_level == "off" else "enabled"}
    if wire_tools:
        payload["tools"] = wire_tools
    headers = {
        "Authorization": f"Bearer {model.api_key}",
        "Content-Type": "application/json",
    }
    url = model.base_url.rstrip("/") + "/chat/completions"

    from .retry import retry_post, should_degrade_tools, strip_tools_from_payload

    state = OpenAIStreamState(model_id)
    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            resp, error = await retry_post(session, url, headers, payload)
            if error and should_degrade_tools(error) and payload.get("tools"):
                # provider 不接受 tools 参数：剥参降级为纯对话重试一轮
                payload = strip_tools_from_payload(payload)
                resp, error = await retry_post(session, url, headers, payload)
            if error:
                yield StreamError(
                    "error",
                    AssistantMessage(
                        model=model_id,
                        stop_reason=StopReason.ERROR,
                        error_message=error,
                    ),
                )
                return
            try:
                yield StreamStart(AssistantMessage(model=model_id))
                async for raw_line in resp.content:
                    if abort_event is not None and abort_event.is_set():
                        yield StreamError(
                            "aborted",
                            AssistantMessage(
                                model=model_id,
                                stop_reason=StopReason.ABORTED,
                                error_message="aborted by user",
                            ),
                        )
                        return
                    line = raw_line.decode("utf-8", errors="replace")
                    for ev in state.feed_line(line):
                        yield ev
                for ev in state.finish():
                    yield ev
            finally:
                resp.close()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        partial = state.partial_message()
        partial.stop_reason = StopReason.ERROR
        partial.error_message = f"stream interrupted: {type(e).__name__}: {e}"
        yield StreamError("error", partial)
