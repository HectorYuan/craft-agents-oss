"""Faux provider：脚本化确定性 StreamFn，驱动循环单测（不打真实 API）。

scripts 是列表，每个元素为一次 stream 调用的剧本：
- AssistantMessage：按内容块顺序产出 delta 事件后 StreamDone
- BaseException：产出 StreamError("error", ...)
脚本耗尽后产出兜底 StreamDone(stop)。
"""
from __future__ import annotations

import json
from typing import Any, List, Optional, Union

from ..types import (
    AssistantMessage,
    AssistantMessageEvent,
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
    new_id,
)


class FauxStreamFn:
    def __init__(self, scripts: List[Union[AssistantMessage, BaseException]]) -> None:
        self.scripts = list(scripts)
        self.calls = 0
        self.seen_contexts: List[Any] = []

    @property
    def last_context(self) -> Optional[Any]:
        return self.seen_contexts[-1] if self.seen_contexts else None

    async def __call__(self, model, context, abort_event=None):
        model_id = str(getattr(model, "id", model))
        self.seen_contexts.append(context)
        index = self.calls
        self.calls += 1

        if index >= len(self.scripts):
            yield StreamDone(
                StopReason.STOP,
                AssistantMessage(model=model_id, content=[TextContent("[faux] no more scripts")]),
            )
            return

        script = self.scripts[index]
        if isinstance(script, BaseException):
            yield StreamError(
                "error",
                AssistantMessage(
                    model=model_id,
                    stop_reason=StopReason.ERROR,
                    error_message=str(script),
                ),
            )
            return

        if abort_event is not None and abort_event.is_set():
            yield StreamError(
                "aborted",
                AssistantMessage(
                    model=model_id,
                    stop_reason=StopReason.ABORTED,
                    error_message="aborted before stream",
                ),
            )
            return

        yield StreamStart(AssistantMessage(model=model_id))

        tc_index = 0
        for block in script.content:
            if isinstance(block, ThinkingContent):
                half = block.thinking[: len(block.thinking) // 2]
                parts = [half, block.thinking[len(half):]] if half else [block.thinking]
                for part in parts:
                    if part:
                        yield ThinkingDelta(part)
            elif isinstance(block, TextContent):
                words = block.text.split(" ")
                chunks = [" ".join(words[i:i + 3]) for i in range(0, len(words), 3)] or [""]
                for i, chunk in enumerate(chunks):
                    piece = chunk + (" " if i < len(chunks) - 1 and chunk else "")
                    if piece:
                        yield TextDelta(piece)
            elif isinstance(block, ToolCall):
                call_id = block.id or new_id("faux_call_")
                yield ToolCallStart(tc_index, ToolCall(id=call_id, name=block.name))
                args_json = json.dumps(block.arguments or {}, ensure_ascii=False)
                mid = len(args_json) // 2
                for fragment in (args_json[:mid], args_json[mid:]):
                    if fragment:
                        yield ToolCallDelta(tc_index, fragment)
                yield ToolCallEnd(
                    tc_index,
                    ToolCall(id=call_id, name=block.name, arguments=dict(block.arguments or {})),
                )
                tc_index += 1

        yield StreamDone(script.stop_reason, script)
