"""Anthropic Messages API 流式实现。

纯状态机 AnthropicStreamState 负责 SSE 事件 -> AssistantMessageEvent 的转换；
消息转换合并连续 user 角色消息（toolResult 也以 user 角色发送）。
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
)


# ---------------------------------------------------------------------------
# Context -> wire payload 转换（纯函数，可单测）
# ---------------------------------------------------------------------------

def _user_blocks(m: UserMessage) -> List[Dict[str, Any]]:
    if isinstance(m.content, str):
        return [{"type": "text", "text": m.content}]
    blocks: List[Dict[str, Any]] = []
    for b in m.content:
        if isinstance(b, TextContent):
            blocks.append({"type": "text", "text": b.text})
        elif isinstance(b, ImageContent):
            blocks.append({
                "type": "image",
                "source": {"type": "base64", "media_type": b.mime_type, "data": b.data},
            })
    return blocks or [{"type": "text", "text": ""}]


def to_anthropic_messages(messages: List[Message]) -> List[Dict[str, Any]]:
    wire: List[Dict[str, Any]] = []
    for m in messages:
        if isinstance(m, UserMessage):
            blocks = _user_blocks(m)
        elif isinstance(m, AssistantMessage):
            blocks = []
            for b in m.content:
                if isinstance(b, TextContent):
                    blocks.append({"type": "text", "text": b.text})
                elif isinstance(b, ToolCall):
                    blocks.append({
                        "type": "tool_use",
                        "id": b.id,
                        "name": b.name,
                        "input": b.arguments or {},
                    })
            if not blocks:
                continue
        elif isinstance(m, ToolResultMessage):
            blocks = [{
                "type": "tool_result",
                "tool_use_id": m.tool_call_id,
                "content": m.text(),
                "is_error": m.is_error,
            }]
        else:
            continue
        current_role = "assistant" if isinstance(m, AssistantMessage) else "user"
        if current_role == "user" and wire and wire[-1]["role"] == "user":
            wire[-1]["content"].extend(blocks)
        else:
            wire.append({"role": current_role, "content": blocks})
    return wire


def to_anthropic_tools(context: Context) -> List[Dict[str, Any]]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.parameters or {"type": "object", "properties": {}},
        }
        for t in context.tools
    ]


# ---------------------------------------------------------------------------
# SSE 状态机（纯逻辑，可离线单测）
# ---------------------------------------------------------------------------

def _map_stop_reason(reason: Optional[str]) -> str:
    if reason == "tool_use":
        return StopReason.TOOL_USE
    if reason == "max_tokens":
        return StopReason.LENGTH
    return StopReason.STOP


class AnthropicStreamState:
    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.blocks: Dict[int, Dict[str, Any]] = {}
        self.usage = Usage()
        self.stop_reason: Optional[str] = None
        self.error_message: Optional[str] = None
        self.message_stopped = False

    def feed_event(self, data: Dict[str, Any]) -> List[AssistantMessageEvent]:
        events: List[AssistantMessageEvent] = []
        etype = data.get("type")

        if etype == "message_start":
            msg = data.get("message") or {}
            usage = msg.get("usage") or {}
            if usage.get("input_tokens") is not None:
                self.usage.input = int(usage["input_tokens"])
            if usage.get("cache_read_input_tokens") is not None:
                self.usage.cache_read = int(usage["cache_read_input_tokens"])
            if usage.get("cache_creation_input_tokens") is not None:
                self.usage.cache_write = int(usage["cache_creation_input_tokens"])

        elif etype == "content_block_start":
            index = int(data.get("index", 0))
            block = data.get("content_block") or {}
            kind = block.get("type", "text")
            if kind == "tool_use":
                entry = {
                    "kind": "tool_use",
                    "id": block.get("id") or "",
                    "name": block.get("name") or "",
                    "args": "",
                }
                self.blocks[index] = entry
                events.append(ToolCallStart(
                    index,
                    ToolCall(id=entry["id"], name=entry["name"]),
                ))
            else:
                self.blocks[index] = {"kind": kind, "parts": []}

        elif etype == "content_block_delta":
            index = int(data.get("index", 0))
            delta = data.get("delta") or {}
            entry = self.blocks.get(index)
            if entry is None:
                return events
            dtype = delta.get("type")
            if dtype == "text_delta":
                entry["parts"].append(delta.get("text", ""))
                events.append(TextDelta(delta.get("text", "")))
            elif dtype == "thinking_delta":
                entry["parts"].append(delta.get("thinking", ""))
                events.append(ThinkingDelta(delta.get("thinking", "")))
            elif dtype == "input_json_delta":
                fragment = delta.get("partial_json", "")
                entry["args"] += fragment
                if fragment:
                    events.append(ToolCallDelta(index, fragment))

        elif etype == "content_block_stop":
            index = int(data.get("index", 0))
            entry = self.blocks.get(index)
            if entry is not None and entry["kind"] == "tool_use":
                try:
                    args = json.loads(entry["args"]) if entry["args"] else {}
                except ValueError:
                    args = {}
                if not isinstance(args, dict):
                    args = {}
                tool_call = ToolCall(id=entry["id"], name=entry["name"], arguments=args)
                entry["parsed"] = tool_call
                events.append(ToolCallEnd(index, tool_call))

        elif etype == "message_delta":
            delta = data.get("delta") or {}
            if delta.get("stop_reason"):
                self.stop_reason = delta["stop_reason"]
            usage = data.get("usage") or {}
            if usage.get("output_tokens") is not None:
                self.usage.output = int(usage["output_tokens"])

        elif etype == "message_stop":
            self.message_stopped = True

        elif etype == "error":
            err = data.get("error") or {}
            self.error_message = str(err.get("message") or data)

        return events

    def finish(self) -> List[AssistantMessageEvent]:
        events: List[AssistantMessageEvent] = []
        content: List[ContentBlock] = []
        for index in sorted(self.blocks):
            entry = self.blocks[index]
            if entry["kind"] == "tool_use":
                content.append(entry.get("parsed") or ToolCall(id=entry["id"], name=entry["name"]))
            elif entry["kind"] == "thinking":
                content.append(ThinkingContent("".join(entry["parts"])))
            else:
                joined = "".join(entry["parts"])
                if joined:
                    content.append(TextContent(joined))
        if self.error_message is not None:
            message = AssistantMessage(
                model=self.model_id,
                stop_reason=StopReason.ERROR,
                error_message=self.error_message,
            )
            events.append(StreamError("error", message))
            return events
        stop_reason = _map_stop_reason(self.stop_reason)
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

async def anthropic_stream(model, context, abort_event=None):
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

    payload: Dict[str, Any] = {
        "model": model_id,
        "max_tokens": model.max_output_tokens,
        "messages": to_anthropic_messages(context.messages),
        "stream": True,
    }
    system_prompt = context.system_prompt
    if getattr(context, "response_format", None) == "json":
        json_hint = (
            "\n\n<output-format>\n"
            "You MUST reply with ONLY a valid JSON object. "
            "No prose, no markdown fences.\n"
            "</output-format>"
        )
        system_prompt = (system_prompt or "") + json_hint
    if system_prompt:
        payload["system"] = system_prompt
    wire_tools = to_anthropic_tools(context)
    if wire_tools:
        payload["tools"] = wire_tools
    headers = {
        "x-api-key": model.api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    url = model.base_url.rstrip("/") + "/v1/messages"

    from .retry import retry_post

    state = AnthropicStreamState(model_id)
    try:
        timeout = aiohttp.ClientTimeout(total=None, connect=30, sock_read=600)
        async with aiohttp.ClientSession(timeout=timeout) as session:
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
                    stripped = line.strip()
                    if not stripped.startswith("data:"):
                        continue
                    try:
                        data = json.loads(stripped[5:].strip())
                    except ValueError:
                        continue
                    for ev in state.feed_event(data):
                        yield ev
                for ev in state.finish():
                    yield ev
            finally:
                resp.close()
    except asyncio.CancelledError:
        raise
    except Exception as e:
        yield StreamError(
            "error",
            AssistantMessage(
                model=model_id,
                stop_reason=StopReason.ERROR,
                error_message=f"{type(e).__name__}: {e}",
            ),
        )
